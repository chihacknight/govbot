/**
 * What check_local_data and the generic error path say when something goes wrong.
 *
 * These drive the built server over stdio with a stub `govbot` (via GOVBOT_BIN)
 * and a throwaway workspace, because the decision being tested — "is this a
 * first run, or a broken tool?" — is made from the CLI's real exit and stderr.
 * Getting it wrong tells Claude nothing is cloned and sends it off to re-clone
 * gigabytes that are already on disk.
 */

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { chmodSync, mkdirSync, mkdtempSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { classifyCoverageFailure, clonedLocales } from "./tools.js";

const here = dirname(fileURLToPath(import.meta.url));
const SERVER = join(here, "index.js");
const TOO_OLD = join(here, "..", "scenarios", "fixtures", "govbot-too-old");

/**
 * A workspace with these locales "cloned". A `.git` folder is enough for
 * clonedLocales() to count it; the stub CLIs never look inside.
 */
function workspaceWith(locales: string[]): string {
  const dir = mkdtempSync(join(tmpdir(), "govbot-mcp-test-"));
  mkdirSync(join(dir, "govbot_data", "repos"), { recursive: true });
  for (const locale of locales) {
    mkdirSync(join(dir, "govbot_data", "repos", `${locale}-legislation`, ".git"), { recursive: true });
  }
  return dir;
}

/** A stub CLI: answers --version, and runs `body` for everything else. */
function stub(body: string): string {
  const path = join(mkdtempSync(join(tmpdir(), "govbot-stub-")), "govbot");
  writeFileSync(
    path,
    `#!/bin/sh\nif [ "$1" = "--version" ]; then echo "govbot 9.9.9"; exit 0; fi\n${body}\n`,
  );
  chmodSync(path, 0o755);
  return path;
}

function call(
  bin: string,
  ws: string,
  name: string,
  args: Record<string, unknown>,
): { text: string; isError: boolean } {
  const requests = [
    {
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "t", version: "1" } },
    },
    { jsonrpc: "2.0", method: "notifications/initialized" },
    { jsonrpc: "2.0", id: 2, method: "tools/call", params: { name, arguments: args } },
  ];
  const result = spawnSync(process.execPath, [SERVER], {
    input: requests.map((r) => JSON.stringify(r)).join("\n") + "\n",
    // GOVBOT_NO_UPDATE_CHECK keeps the server's background update check (#235)
    // from reaching the network during tests.
    env: { ...process.env, GOVBOT_BIN: bin, GOVBOT_WORKSPACE: ws, GOVBOT_NO_UPDATE_CHECK: "1" },
    encoding: "utf8",
  });
  const reply = result.stdout
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line))
    .find((message) => message.id === 2);
  assert.ok(reply?.result, `no reply to tools/call: ${result.stdout}${result.stderr}`);
  return {
    text: reply.result.content.map((c: { text: string }) => c.text).join("\n"),
    isError: reply.result.isError === true,
  };
}

test("an old CLI is reported as a tool problem, not as nothing cloned", () => {
  const out = call(TOO_OLD, workspaceWith(["il", "usa"]), "check_local_data", {});
  assert.equal(out.isError, true);
  assert.doesNotMatch(out.text, /No government data has been cloned/);
  assert.match(out.text, /unrecognized subcommand 'query'/);
  assert.match(out.text, /Don't re-clone/);
  assert.match(out.text, /Cloned here: il, usa\./);
  assert.match(out.text, /install-nightly\.sh/);
});

test("an unreadable jurisdiction name lists what is cloned instead", () => {
  const bin = stub(
    `echo 'Error: Could not read "Illinois" as a jurisdiction. Use a locale code such as \`il\`.' >&2; exit 1`,
  );
  const out = call(bin, workspaceWith(["il", "usa"]), "check_local_data", {
    jurisdictions: ["Illinois"],
  });
  assert.equal(out.isError, true);
  assert.doesNotMatch(out.text, /No government data has been cloned/);
  assert.match(out.text, /Could not read "Illinois"/);
  assert.match(out.text, /Cloned here: il, usa\./);
});

test("a state that is not cloned is named, alongside the ones that are", () => {
  const bin = stub(
    `echo '{"query":{},"results":[],"truncation":{"returned":0,"total_matching":0,"limit":20},"coverage":[]}'`,
  );
  const out = call(bin, workspaceWith(["il", "usa"]), "check_local_data", {
    jurisdictions: ["ca"],
  });
  assert.equal(out.isError, false);
  assert.doesNotMatch(out.text, /No government data cloned yet/);
  assert.match(out.text, /ca is not cloned yet\. Cloned here: il, usa\./);
});

test("a genuinely empty workspace is still a normal first run", () => {
  const bin = stub(`echo "Error: No cloned data at $4/repos. Run \\\`govbot clone <jurisdiction>\\\` first." >&2; exit 1`);
  const out = call(bin, workspaceWith([]), "check_local_data", {});
  assert.equal(out.isError, false);
  assert.match(out.text, /No government data has been cloned to this computer yet/);
});

test("a missing CLI on clone comes with the install step", () => {
  const out = call("/nonexistent/govbot", workspaceWith([]), "clone_government_data", {
    jurisdictions: ["wy"],
  });
  assert.equal(out.isError, true);
  assert.match(out.text, /was not found/);
  assert.match(out.text, /install-nightly\.sh/);
});

test("only the CLI's own nothing-cloned messages count as a first run", () => {
  assert.equal(classifyCoverageFailure("Error: No cloned data at /x/repos. Run …"), "first-run");
  assert.equal(classifyCoverageFailure("Error: Nothing cloned at /x/repos yet."), "first-run");
  assert.equal(
    classifyCoverageFailure('Error: Could not read "Illinois" as a jurisdiction.'),
    "bad-jurisdiction",
  );
  assert.equal(classifyCoverageFailure("error: unrecognized subcommand 'query'"), "outdated");
  assert.equal(classifyCoverageFailure("error: unexpected argument '--limit' found"), "outdated");
  assert.equal(classifyCoverageFailure("`govbot query` did not finish within 900s."), "timeout");
  assert.equal(classifyCoverageFailure("`govbot query` did not return readable JSON."), "tool-problem");
});

test("a crash is not blamed on an old tool", () => {
  const bin = stub(`echo "thread 'main' panicked at src/query.rs:1" >&2; exit 101`);
  const out = call(bin, workspaceWith(["il"]), "check_local_data", {});
  assert.equal(out.isError, true);
  assert.doesNotMatch(out.text, /older than this connector/);
  assert.match(out.text, /panicked/);
  assert.match(out.text, /still there/);
});

test("an old CLI on query gets the install step and the data-is-still-there line", () => {
  const out = call(TOO_OLD, workspaceWith(["il", "usa"]), "query", { type: "bills" });
  assert.equal(out.isError, true);
  assert.match(out.text, /unrecognized subcommand 'query'/);
  assert.match(out.text, /still there/);
  assert.match(out.text, /Cloned here: il, usa\./);
  assert.match(out.text, /install-nightly\.sh/);
});

test("an interrupted clone (a folder that is not a git repo) does not count as cloned", () => {
  const ws = workspaceWith(["usa"]);
  mkdirSync(join(ws, "govbot_data", "repos", "il-legislation"));
  const bin = stub(
    `echo '{"query":{},"results":[],"truncation":{"returned":0,"total_matching":0,"limit":20},"coverage":[]}'`,
  );
  const out = call(bin, ws, "check_local_data", { jurisdictions: ["il"] });
  assert.match(out.text, /il is not cloned yet\. Cloned here: usa\./);
});

test("clonedLocales follows the CLI's rule: git repos, symlinks, legacy suffix", () => {
  const repos = join(workspaceWith(["il"]), "govbot_data", "repos");
  // Symlinked repo folder (e.g. data kept on another disk).
  const elsewhere = mkdtempSync(join(tmpdir(), "govbot-elsewhere-"));
  mkdirSync(join(elsewhere, "wy-legislation", ".git"), { recursive: true });
  symlinkSync(join(elsewhere, "wy-legislation"), join(repos, "wy-legislation"));
  // Legacy name from older clones.
  mkdirSync(join(repos, "gu-data-pipeline", ".git"), { recursive: true });
  // Worktree-style `.git` file.
  mkdirSync(join(repos, "ak-legislation"));
  writeFileSync(join(repos, "ak-legislation", ".git"), "gitdir: /elsewhere\n");
  // Not repos: interrupted clone, dangling symlink, stray file, wrong suffix.
  mkdirSync(join(repos, "ca-legislation"));
  symlinkSync(join(elsewhere, "gone"), join(repos, "tx-legislation"));
  writeFileSync(join(repos, "notes-legislation"), "");
  mkdirSync(join(repos, "scratch", ".git"), { recursive: true });

  assert.deepEqual(clonedLocales(repos), ["ak", "gu", "il", "wy"]);
  assert.deepEqual(clonedLocales(join(repos, "missing")), []);
});
