/**
 * Running the `govbot` CLI as a child process.
 *
 * This server owns no data model of its own. Everything it reports comes from
 * `govbot`, so that terminal users and Claude Desktop users see the same
 * answers from the same code.
 *
 * One hard rule runs through this file: **nothing here may write to stdout.**
 * Stdout is the MCP transport, and a single stray byte on it corrupts the
 * JSON-RPC stream and disconnects the client with no visible error. All
 * diagnostics go to stderr.
 */

import { spawn } from "node:child_process";
import { accessSync, constants } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

/** How a `govbot` invocation ended. */
export interface CommandResult {
  stdout: string;
  stderr: string;
  code: number;
}

/** Raised when the CLI is missing, failed, or produced something unreadable. */
export class GovbotError extends Error {
  constructor(
    message: string,
    readonly detail?: string,
  ) {
    super(message);
    this.name = "GovbotError";
  }
}

/**
 * Locate the `govbot` binary.
 *
 * Checked in order: an explicit override, the default install location used by
 * `install-nightly.sh`, a local release build, then whatever is on `PATH`.
 */
export function resolveBinary(): string {
  const override = process.env.GOVBOT_BIN;
  if (override) return override;

  const candidates = [
    join(homedir(), ".govbot", "bin", "govbot"),
    join(homedir(), ".cargo", "bin", "govbot"),
  ];
  for (const candidate of candidates) {
    try {
      accessSync(candidate, constants.X_OK);
      return candidate;
    } catch {
      // Try the next one; falling through to PATH is fine.
    }
  }
  return "govbot";
}

/** Long enough for a clone of a large jurisdiction, which can take minutes. */
const DEFAULT_TIMEOUT_MS = 15 * 60 * 1000;

export interface RunOptions {
  cwd?: string;
  timeoutMs?: number;
  /** Fed to the process on stdin, for `govbot tag`. */
  stdin?: string;
  /** Called with each chunk of stderr, for progress reporting. */
  onProgress?: (chunk: string) => void;
}

/**
 * Run `govbot` and collect its output.
 *
 * Resolves even when the command fails, so callers can decide what a non-zero
 * exit means; only a missing binary or a timeout rejects.
 */
export function run(args: string[], options: RunOptions = {}): Promise<CommandResult> {
  const binary = resolveBinary();
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;

  return new Promise((resolve, reject) => {
    const child = spawn(binary, args, {
      cwd: options.cwd,
      // Inherit the environment so GOVBOT_DIR and friends keep working, but
      // never a TTY — govbot's wizard is interactive when stdin is a terminal.
      env: { ...process.env },
      stdio: ["pipe", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";
    let settled = false;

    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      child.kill("SIGKILL");
      reject(
        new GovbotError(
          `\`govbot ${args[0] ?? ""}\` did not finish within ${Math.round(timeoutMs / 1000)}s.`,
          stderr.slice(-2000),
        ),
      );
    }, timeoutMs);

    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk: Buffer) => {
      const text = chunk.toString();
      stderr += text;
      options.onProgress?.(text);
    });

    child.on("error", (error: NodeJS.ErrnoException) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (error.code === "ENOENT") {
        reject(
          new GovbotError(
            `The govbot command-line tool was not found (looked for "${binary}").`,
            "Install it with:\n" +
              '  sh -c "$(curl -fsSL https://raw.githubusercontent.com/chihacknight/govbot/main/actions/govbot/scripts/install-nightly.sh)"\n' +
              "Or set GOVBOT_BIN to its full path.",
          ),
        );
        return;
      }
      reject(new GovbotError(`Could not run govbot: ${error.message}`));
    });

    child.on("close", (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({ stdout, stderr, code: code ?? -1 });
    });

    // The child may exit before consuming all of stdin — `govbot tag` bails out
    // early on a bad config, for instance. Without this handler the resulting
    // EPIPE is an unhandled 'error' event, which takes down the whole server and
    // disconnects Claude Desktop with no explanation.
    child.stdin.on("error", (error: NodeJS.ErrnoException) => {
      if (error.code !== "EPIPE") {
        options.onProgress?.(`stdin error: ${error.message}`);
      }
    });

    if (options.stdin !== undefined) {
      child.stdin.end(options.stdin);
    } else {
      child.stdin.end();
    }
  });
}

/**
 * Run a `govbot` subcommand that prints JSON, and parse it.
 *
 * A non-zero exit is surfaced with the CLI's own stderr attached, because that
 * message is usually the actionable one ("run `govbot clone` first").
 */
export async function runJson<T = unknown>(
  args: string[],
  options: RunOptions = {},
): Promise<T> {
  const result = await run(args, options);

  if (result.code !== 0) {
    throw new GovbotError(
      `\`govbot ${args.join(" ")}\` failed.`,
      result.stderr.trim() || result.stdout.trim() || `Exit code ${result.code}.`,
    );
  }

  try {
    return JSON.parse(result.stdout) as T;
  } catch {
    throw new GovbotError(
      `\`govbot ${args[0] ?? ""}\` did not return readable JSON.`,
      result.stdout.slice(0, 500),
    );
  }
}

/** The installed CLI version, or `null` if it could not be run at all. */
export async function version(): Promise<string | null> {
  try {
    const result = await run(["--version"], { timeoutMs: 10_000 });
    return result.code === 0 ? result.stdout.trim() : null;
  } catch {
    return null;
  }
}
