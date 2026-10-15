/**
 * Telling people when govbot has an update.
 *
 * Neither piece updates itself: Claude Desktop only auto-updates extensions
 * installed from Anthropic's directory, so a privately distributed `.mcpb` is
 * replaced by hand, and the CLI in ~/.govbot/bin is only replaced by re-running
 * the installer. Without a nudge, people quietly miss fixes.
 *
 * Rules this module keeps:
 * - **Never on the request path.** The check starts in the background at
 *   startup and is never awaited by a tool; tools read whatever is known.
 * - **Offline costs nothing.** A failed or slow fetch (3s cap) means no notice
 *   and no error. Nothing is cached on failure, so the next start tries again.
 * - **At most once a day.** A successful result is cached for 24h in
 *   ~/.govbot/update-check.json.
 * - **Never stdout.** Diagnostics go to stderr; stdout is the MCP transport.
 * - `GOVBOT_NO_UPDATE_CHECK=1` skips it entirely (the snapshot harness sets it).
 */

import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, join } from "node:path";

/** Stable: the release workflow overwrites this asset on the `nightly` tag. */
export const RELEASE_BASE = "https://github.com/chihacknight/govbot/releases/download/nightly";
export const VERSION_URL = `${RELEASE_BASE}/govbot-mcp-version.json`;
export const BUNDLE_URL = `${RELEASE_BASE}/govbot.mcpb`;
export const CLI_INSTALL_COMMAND =
  'sh -c "$(curl -fsSL https://raw.githubusercontent.com/chihacknight/govbot/main/actions/govbot/scripts/install-nightly.sh)"';

export const DEFAULT_CACHE_PATH = join(homedir(), ".govbot", "update-check.json");
export const CACHE_MAX_AGE_MS = 24 * 60 * 60 * 1000;
export const FETCH_TIMEOUT_MS = 3_000;

/** What the release publishes in govbot-mcp-version.json. */
export interface RemoteVersions {
  mcp: string;
  cli_min?: string;
  built?: string;
}

/** What is known right now. Tools read this; they never wait for it. */
export type UpdateState =
  | { status: "disabled" }
  | { status: "pending" }
  | { status: "unavailable" }
  | { status: "checked"; checkedAt: string; remote: RemoteVersions };

interface CacheFile {
  checked_at: string;
  remote: RemoteVersions;
}

// ---------------------------------------------------------------------------
// Pure decisions
// ---------------------------------------------------------------------------

/** A parsed version: `major.minor.patch`, plus any pre-release identifiers. */
export interface Version {
  core: [number, number, number];
  /** `["nightly", "202610151200"]` for `0.1.0-nightly.202610151200`; empty for a release. */
  prerelease: string[];
  /** The matched text without build metadata, e.g. `0.1.0-nightly.202610151200`. */
  text: string;
}

// Build metadata (`+...`) is matched so it is not mistaken for anything else,
// but semver says it never affects ordering, so it is dropped.
const VERSION_PATTERN = /(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?/;

/**
 * The first semver version in a string, so `govbot 0.1.0` and `0.1.0` both
 * parse. Returns null for anything unparseable, which always means "no notice".
 */
export function parseVersion(input: string | null | undefined): Version | null {
  const match = input?.match(VERSION_PATTERN);
  if (!match) return null;
  const core: [number, number, number] = [Number(match[1]), Number(match[2]), Number(match[3])];
  const prerelease = match[4] ? match[4].split(".") : [];
  return { core, prerelease, text: core.join(".") + (match[4] ? `-${match[4]}` : "") };
}

/**
 * Semver pre-release precedence for two identifiers: numeric ones compare as
 * numbers (by length first, so 12-digit nightly stamps never lose precision),
 * numeric sorts before alphanumeric, and the rest compare as ASCII.
 */
function compareIdentifier(a: string, b: string): number {
  const aNumeric = /^\d+$/.test(a);
  const bNumeric = /^\d+$/.test(b);
  if (aNumeric && bNumeric) {
    const x = a.replace(/^0+(?=\d)/, "");
    const y = b.replace(/^0+(?=\d)/, "");
    if (x.length !== y.length) return x.length - y.length;
    return x < y ? -1 : x > y ? 1 : 0;
  }
  if (aNumeric !== bNumeric) return aNumeric ? -1 : 1;
  return a < b ? -1 : a > b ? 1 : 0;
}

/**
 * Semver precedence: `0.2.0-rc.1 < 0.2.0`, `0.1.0 < 0.2.0-rc.1`, and nightly
 * builds (`0.1.0-nightly.<UTC YYYYMMDDHHMM>`, stamped by the release workflow)
 * order by build time. One consequence, intended: a local build reports plain
 * `0.1.0`, which ranks above every `0.1.0-nightly.*`, so a developer's own build
 * is never told to "update" to a nightly of the same version.
 */
export function compareVersions(left: Version, right: Version): number {
  for (let i = 0; i < 3; i++) {
    if (left.core[i]! !== right.core[i]!) return left.core[i]! - right.core[i]!;
  }
  // A release outranks any pre-release of the same core version.
  if (!left.prerelease.length || !right.prerelease.length) {
    return right.prerelease.length - left.prerelease.length;
  }
  const shared = Math.min(left.prerelease.length, right.prerelease.length);
  for (let i = 0; i < shared; i++) {
    const order = compareIdentifier(left.prerelease[i]!, right.prerelease[i]!);
    if (order !== 0) return order;
  }
  return left.prerelease.length - right.prerelease.length;
}

/** True only when both parse and `a` is strictly older than `b`. */
export function isOlder(a: string | null | undefined, b: string | null | undefined): boolean {
  const left = parseVersion(a);
  const right = parseVersion(b);
  if (!left || !right) return false;
  return compareVersions(left, right) < 0;
}

/** Whichever minimum is higher; either may be missing. */
function higherMinimum(a: string | null | undefined, b: string | null | undefined): string | null {
  if (!parseVersion(a)) return parseVersion(b) ? b! : null;
  if (!parseVersion(b)) return a!;
  return isOlder(a, b) ? b! : a!;
}

/** Validate the fetched JSON; anything malformed is treated as no data. */
export function parseRemote(value: unknown): RemoteVersions | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  if (typeof record.mcp !== "string" || !parseVersion(record.mcp)) return null;
  return {
    mcp: record.mcp,
    ...(typeof record.cli_min === "string" ? { cli_min: record.cli_min } : {}),
    ...(typeof record.built === "string" ? { built: record.built } : {}),
  };
}

export interface NoticeInput {
  /** This server's version. */
  bundle: string;
  /** Output of `govbot --version`, or null if the CLI is not installed. */
  cli: string | null;
  /** The oldest CLI this server needs, from package.json. Known offline. */
  cliMin: string | null;
  state: UpdateState;
}

/**
 * The plain-language notices to show, if any.
 *
 * The CLI check uses the higher of this server's own minimum (known offline)
 * and the published one. A missing CLI produces no notice here: the tools
 * already say "not installed" with the same installer command.
 */
export function updateNotices(input: NoticeInput): string[] {
  const notices: string[] = [];
  const remote = input.state.status === "checked" ? input.state.remote : null;

  if (remote && isOlder(input.bundle, remote.mcp)) {
    notices.push(
      `Update available: govbot for Claude Desktop ${remote.mcp} is out (this is ${input.bundle}). ` +
        `To update, download ${BUNDLE_URL}, then drag it into Claude Desktop → Settings → Extensions.`,
    );
  }

  const needed = higherMinimum(input.cliMin, remote?.cli_min);
  if (input.cli && needed && isOlder(input.cli, needed)) {
    const current = parseVersion(input.cli)!.text;
    notices.push(
      `Update needed: the govbot command-line tool on this computer is ${current}, but ` +
        `${needed} or newer is needed. Some answers may fail until it is updated. ` +
        `To update, run this in Terminal:\n  ${CLI_INSTALL_COMMAND}`,
    );
  }

  return notices;
}

/** One line for "is govbot up to date?", when there is nothing to update. */
export function describeState(state: UpdateState): string {
  switch (state.status) {
    case "checked":
      return `Updates: none found (last checked ${state.checkedAt.slice(0, 10)}).`;
    case "disabled":
      return "Updates: not checked (GOVBOT_NO_UPDATE_CHECK is set).";
    case "pending":
      return "Updates: still checking — ask again in a moment.";
    case "unavailable":
      return "Updates: could not check (this computer may be offline). That is fine; nothing else depends on it.";
  }
}

/**
 * The version block every status tool ends with, so "is govbot up to date?"
 * gets the same answer whichever tool Claude happened to call: the installed
 * versions on one line, then either the update notices or the check's status.
 *
 * Edge case: when the check hasn't succeeded (pending, offline, disabled), the
 * status line is shown even alongside a notice, because a notice from the
 * offline CLI minimum says nothing about whether a newer bundle exists. After a
 * successful check the notices are the whole story, and "none found" would
 * contradict them.
 */
export function versionStatus(input: NoticeInput): string {
  const cli = input.cli ? (parseVersion(input.cli)?.text ?? input.cli) : "not installed";
  const installed = `Installed: govbot for Claude Desktop ${input.bundle}, govbot command-line tool ${cli}.`;
  const notices = updateNotices(input);
  const head = [installed];
  if (!notices.length || input.state.status !== "checked") head.push(describeState(input.state));
  return [head.join("\n"), ...notices].join("\n\n");
}

// ---------------------------------------------------------------------------
// Cache and fetch
// ---------------------------------------------------------------------------

/** The cached result regardless of age, or null if missing or unreadable. */
export async function readCache(path: string): Promise<CacheFile | null> {
  try {
    const parsed = JSON.parse(await readFile(path, "utf8"));
    const remote = parseRemote(parsed?.remote);
    const checkedAt = parsed?.checked_at;
    if (!remote || typeof checkedAt !== "string" || Number.isNaN(Date.parse(checkedAt))) {
      return null;
    }
    return { checked_at: checkedAt, remote };
  } catch {
    return null;
  }
}

/** Fresh means younger than maxAge, and not from the future (a clock change). */
export function isFresh(cache: CacheFile, now: Date, maxAgeMs = CACHE_MAX_AGE_MS): boolean {
  const age = now.getTime() - Date.parse(cache.checked_at);
  return age >= 0 && age < maxAgeMs;
}

async function writeCache(path: string, cache: CacheFile): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  // Write-then-rename, so two servers starting at once never leave a torn file.
  const temp = `${path}.${process.pid}.tmp`;
  await writeFile(temp, JSON.stringify(cache, null, 2) + "\n");
  await rename(temp, path);
}

/** Fetch the published versions. Resolves null on any failure; never throws. */
export async function fetchRemote(
  url = VERSION_URL,
  timeoutMs = FETCH_TIMEOUT_MS,
  fetchImpl: typeof fetch = fetch,
): Promise<RemoteVersions | null> {
  try {
    // The race guards against a fetch implementation that ignores the signal.
    const response = await Promise.race([
      fetchImpl(url, { signal: AbortSignal.timeout(timeoutMs), redirect: "follow" }),
      new Promise<never>((_, reject) => {
        const timer = setTimeout(() => reject(new Error("timeout")), timeoutMs);
        timer.unref();
      }),
    ]);
    if (!response.ok) return null;
    return parseRemote(await response.json());
  } catch {
    return null;
  }
}

export interface CheckOptions {
  cachePath?: string;
  url?: string;
  timeoutMs?: number;
  now?: Date;
  fetchImpl?: typeof fetch;
}

/**
 * Work out what is known: a fresh cache is used as-is; otherwise fetch, and
 * cache on success. If the fetch fails, a stale cache is still used — a
 * version that was newer yesterday is still newer today.
 */
export async function checkForUpdates(options: CheckOptions = {}): Promise<UpdateState> {
  const cachePath = options.cachePath ?? DEFAULT_CACHE_PATH;
  const now = options.now ?? new Date();

  const cached = await readCache(cachePath);
  if (cached && isFresh(cached, now)) {
    return { status: "checked", checkedAt: cached.checked_at, remote: cached.remote };
  }

  const remote = await fetchRemote(options.url, options.timeoutMs, options.fetchImpl);
  if (!remote) {
    return cached
      ? { status: "checked", checkedAt: cached.checked_at, remote: cached.remote }
      : { status: "unavailable" };
  }

  const fresh: CacheFile = { checked_at: now.toISOString(), remote };
  await writeCache(cachePath, fresh).catch((error) => {
    process.stderr.write(`[govbot-mcp] could not cache update check: ${String(error)}\n`);
  });
  return { status: "checked", checkedAt: fresh.checked_at, remote };
}

// ---------------------------------------------------------------------------
// The process-wide state the tools read
// ---------------------------------------------------------------------------

export function isDisabled(env: NodeJS.ProcessEnv = process.env): boolean {
  const value = env.GOVBOT_NO_UPDATE_CHECK;
  return Boolean(value) && value !== "0";
}

let state: UpdateState = isDisabled() ? { status: "disabled" } : { status: "pending" };

/** Start the check in the background. Returns immediately; never throws. */
export function startUpdateCheck(options: CheckOptions = {}): void {
  if (isDisabled()) {
    state = { status: "disabled" };
    return;
  }
  checkForUpdates(options)
    .then((result) => {
      state = result;
    })
    .catch((error) => {
      state = { status: "unavailable" };
      process.stderr.write(`[govbot-mcp] update check failed: ${String(error)}\n`);
    });
}

/** Whatever is known right now. */
export function currentUpdateState(): UpdateState {
  return state;
}
