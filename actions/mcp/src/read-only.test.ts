/**
 * check_local_data and query are annotated `readOnlyHint: true`, so they must
 * never create, initialise or rewrite the workspace.
 *
 * A fake `govbot` stands in for the CLI so this runs offline and without a real
 * install. It answers like a fresh install with nothing cloned, and logs each
 * call to a file *outside* the workspace, which proves it actually ran (spawning
 * in a missing working directory fails before the binary starts).
 */

import assert from "node:assert/strict";
import { chmodSync, existsSync, mkdtempSync, readdirSync, readFileSync, statSync, writeFileSync, appendFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { checkLocalData, query } from "./tools.js";
import * as workspace from "./workspace.js";

const scratch = mkdtempSync(join(tmpdir(), "govbot-mcp-readonly-"));
const callLog = join(scratch, "calls.log");
const fakeBin = join(scratch, "govbot");
writeFileSync(
  fakeBin,
  `#!/bin/sh
echo "$*" >> "${callLog}"
if [ "$1" = "--version" ]; then echo "govbot 0.0.0-test"; exit 0; fi
echo "No repositories found. Run govbot clone first." >&2
exit 1
`,
);
chmodSync(fakeBin, 0o755);
process.env.GOVBOT_BIN = fakeBin;

/** Every path under `dir` with its mtime, so any write shows up as a difference. */
function snapshot(dir: string): Map<string, number> {
  const out = new Map<string, number>();
  for (const name of readdirSync(dir, { recursive: true }) as string[]) {
    out.set(name, statSync(join(dir, name)).mtimeMs);
  }
  return out;
}

async function readEverything(): Promise<void> {
  await checkLocalData({}); // also what the govbot://workspace/coverage resource runs
  await checkLocalData({ jurisdictions: ["il"] });
  await query({ type: "coverage" });
  await query({ type: "bills", text: "transit", jurisdictions: ["il"] });
}

test("reading with no workspace leaves no workspace behind", async () => {
  const ws = join(scratch, "never-created");
  process.env.GOVBOT_WORKSPACE = ws;
  writeFileSync(callLog, "");

  await readEverything();

  assert.equal(existsSync(ws), false, "a read created the workspace");
  // The CLI still ran (from the home directory), so the person gets its answer
  // rather than a confusing spawn error.
  assert.match(readFileSync(callLog, "utf8"), /^query bills /m);
});

test("reading an existing workspace changes no file, and a later setup keeps edits", async () => {
  const ws = join(scratch, "existing");
  process.env.GOVBOT_WORKSPACE = ws;
  await workspace.ensure();
  appendFileSync(join(ws, "README.md"), "\nTracking IL housing bills for our tenants union.\n");
  appendFileSync(join(ws, ".gitignore"), "\nmy-notes/\n");
  const before = snapshot(ws);

  await readEverything();

  assert.deepEqual(snapshot(ws), before, "a read wrote to the workspace");

  // setup_workspace, clone, save and tag all call ensure(); none may undo an edit.
  await workspace.ensure();
  assert.match(readFileSync(join(ws, "README.md"), "utf8"), /tenants union/);
  assert.match(readFileSync(join(ws, ".gitignore"), "utf8"), /my-notes\//);
});
