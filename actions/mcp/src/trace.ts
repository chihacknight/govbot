/**
 * Optional tool-call trace.
 *
 * When GOVBOT_MCP_TRACE names a file, every tool call appends one JSON line to it:
 * which tool ran, with what arguments, how long it took, and the start of what it
 * returned. The improvement loop (`scripts/desktop-capture.sh`) reads this to see
 * exactly what Claude asked the server for during a scenario, without having to
 * read it back off a screenshot.
 *
 * Unset (the default for anyone installing govbot), this does nothing. It only
 * ever writes to the named file — stdout belongs to the MCP transport.
 */

import { appendFileSync } from "node:fs";

/** The fields of a tool result the trace looks at. */
interface TraceableResult {
  content: { type: string; text: string }[];
  isError?: boolean;
}

/** How much of each result to keep; enough to judge it, small enough to diff. */
const PREVIEW_CHARS = 500;

export interface TraceRecord {
  at: string;
  tool: string;
  args: unknown;
  ms: number;
  isError: boolean;
  chars: number;
  preview: string;
}

export function traceRecord(
  tool: string,
  args: unknown,
  ms: number,
  result: TraceableResult,
): TraceRecord {
  const text = result.content.map((part) => part.text).join("\n");
  return {
    at: new Date().toISOString(),
    tool,
    args: args ?? {},
    ms: Math.round(ms),
    isError: result.isError === true,
    chars: text.length,
    preview: text.slice(0, PREVIEW_CHARS),
  };
}

/** Wrap a tool handler so each call is traced when GOVBOT_MCP_TRACE is set. */
export function withTrace<A extends unknown[], R extends TraceableResult>(
  tool: string,
  handler: (...args: A) => Promise<R>,
): (...args: A) => Promise<R> {
  return async (...args: A) => {
    const file = process.env.GOVBOT_MCP_TRACE;
    if (!file) return handler(...args);

    const started = performance.now();
    const result = await handler(...args);
    try {
      const record = traceRecord(tool, args[0], performance.now() - started, result);
      appendFileSync(file, `${JSON.stringify(record)}\n`);
    } catch (error) {
      // A trace that cannot be written must never break the answer itself.
      const message = error instanceof Error ? error.message : String(error);
      process.stderr.write(`[govbot-mcp] trace not written: ${message}\n`);
    }
    return result;
  };
}
