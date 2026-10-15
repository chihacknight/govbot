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
import { chmodSync, mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { classifyCoverageFailure } from "./tools.js";

const here = dirname(fileURLToPath(import.meta.url));
const SERVER = join(here, "index.js");
const TOO_OLD = join(here, "..", "scenarios", "fixtures", "govbot-too-old");

/** A workspace with IL and USA "cloned" (empty repo folders are enough here). */
function workspaceWith(locales: string[]): string {
  const dir = mkdtempSync(join(tmpdir(), "govbot-mcp-test-"));
  for (const locale of locales) {
    mkdirSync(join(dir, "govbot_data", "repos", `${locale}-legislation`), { recursive: true });
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
    env: { ...process.env, GOVBOT_BIN: bin, GOVBOT_WORKSPACE: ws },
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
  assert.equal(classifyCoverageFailure("error: unrecognized subcommand 'query'"), "tool-problem");
  assert.equal(classifyCoverageFailure("`govbot query` did not return readable JSON."), "tool-problem");
});
