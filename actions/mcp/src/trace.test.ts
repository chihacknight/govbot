/**
 * Tests for the optional tool-call trace.
 *
 * The trace exists for the improvement loop; what matters is that it never
 * touches stdout (the MCP transport) and that it is silent when not asked for.
 */

import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { withTrace } from "./trace.js";

const answer = async (args: { text: string }) => ({
  content: [{ type: "text", text: `found ${args.text}` }],
});

/** Run `fn` while counting writes to stdout. */
async function countStdoutWrites(fn: () => Promise<void>): Promise<number> {
  const original = process.stdout.write.bind(process.stdout);
  let writes = 0;
  process.stdout.write = ((...args: Parameters<typeof original>) => {
    writes += 1;
    return original(...args);
  }) as typeof process.stdout.write;
  try {
    await fn();
  } finally {
    process.stdout.write = original;
  }
  return writes;
}

test("one JSON line per call, and nothing on stdout", async () => {
  const file = join(mkdtempSync(join(tmpdir(), "govbot-trace-")), "trace.jsonl");
  process.env.GOVBOT_MCP_TRACE = file;
  try {
    const traced = withTrace("query", answer);
    const writes = await countStdoutWrites(async () => {
      const result = await traced({ text: "rent" });
      assert.equal(result.content[0]?.text, "found rent");
      await traced({ text: "transit" });
    });
    assert.equal(writes, 0);

    const lines = readFileSync(file, "utf8").trim().split("\n");
    assert.equal(lines.length, 2);
    const first = JSON.parse(lines[0]!);
    assert.equal(first.tool, "query");
    assert.deepEqual(first.args, { text: "rent" });
    assert.equal(first.isError, false);
    assert.equal(first.preview, "found rent");
  } finally {
    delete process.env.GOVBOT_MCP_TRACE;
  }
});

test("no trace file is written unless GOVBOT_MCP_TRACE is set", async () => {
  const file = join(mkdtempSync(join(tmpdir(), "govbot-trace-")), "trace.jsonl");
  delete process.env.GOVBOT_MCP_TRACE;
  await withTrace("query", answer)({ text: "rent" });
  assert.equal(existsSync(file), false);
});
