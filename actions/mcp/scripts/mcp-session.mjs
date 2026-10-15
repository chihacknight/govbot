#!/usr/bin/env node
/**
 * Drive the MCP server over stdio with a scripted sequence of JSON-RPC requests
 * and print the responses.
 *
 * Used by render-snapshots.sh, and by hand when you want to see what a tool
 * actually returns. Also the one place that checks the rule the whole transport
 * depends on: stdout must carry JSON-RPC frames and nothing else.
 *
 * `--timings` also writes, to stderr, when each frame arrived (ms since start) and
 * its method or id — to check that progress notifications really arrive every
 * few seconds. Stdout, and so every snapshot, is the same with or without it.
 */

import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";

const args = process.argv.slice(2);
const timings = args.includes("--timings");
const [requestsFile] = args.filter((arg) => arg !== "--timings");
if (!requestsFile) {
  process.stderr.write("usage: mcp-session.mjs [--timings] <requests.jsonl>\n");
  process.exit(2);
}

const requests = readFileSync(requestsFile, "utf8").trimEnd();
const child = spawn(process.execPath, ["dist/index.js"], {
  stdio: ["pipe", "pipe", "pipe"],
});

let stdout = "";
const started = Date.now();
let partial = "";
child.stdout.on("data", (chunk) => {
  stdout += chunk;
  if (!timings) return;
  partial += chunk;
  const lines = partial.split("\n");
  partial = lines.pop();
  for (const line of lines) {
    let label = "(not JSON)";
    try {
      const frame = JSON.parse(line);
      label = frame.method ?? `result id=${frame.id}`;
      if (frame.method === "notifications/progress") {
        label += ` progress=${frame.params.progress} total=${frame.params.total ?? "-"} ${frame.params.message ?? ""}`;
      }
    } catch {
      // Reported as impure below; only the label is affected here.
    }
    process.stderr.write(`[${String(Date.now() - started).padStart(6)} ms] ${label}\n`);
  }
});
child.stderr.on("data", () => {
  // Diagnostics belong on stderr and are deliberately not part of the snapshot.
});

child.stdin.end(requests + "\n");

child.on("close", () => {
  const lines = stdout.split("\n").filter((line) => line.trim());
  const impure = [];
  const messages = [];

  for (const line of lines) {
    try {
      messages.push(JSON.parse(line));
    } catch {
      impure.push(line);
    }
  }

  if (impure.length) {
    process.stderr.write(
      `stdout carried ${impure.length} line(s) that are not JSON-RPC:\n` +
        impure.map((l) => `  ${l.slice(0, 200)}`).join("\n") +
        "\nThis corrupts the MCP transport and disconnects the client.\n",
    );
    process.exit(1);
  }

  process.stdout.write(JSON.stringify(messages, null, 2) + "\n");
});
