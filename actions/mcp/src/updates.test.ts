/**
 * Tests for the update check.
 *
 * The things that matter: version comparison never produces a false notice,
 * the cache is honoured for a day, and being offline costs neither an error
 * nor a delay.
 */

import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, existsSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import {
  BUNDLE_URL,
  CLI_INSTALL_COMMAND,
  checkForUpdates,
  describeState,
  fetchRemote,
  isDisabled,
  isOlder,
  parseRemote,
  parseVersion,
  startUpdateCheck,
  updateNotices,
  type UpdateState,
} from "./updates.js";

const tempCache = () => join(mkdtempSync(join(tmpdir(), "govbot-updates-")), "update-check.json");
const checked = (mcp: string, cli_min?: string): UpdateState => ({
  status: "checked",
  checkedAt: "2026-10-14T00:00:00.000Z",
  remote: { mcp, ...(cli_min ? { cli_min } : {}) },
});
const jsonResponse = (body: unknown) =>
  (async () => new Response(JSON.stringify(body), { status: 200 })) as typeof fetch;

// ---------------------------------------------------------------------------
// Version comparison
// ---------------------------------------------------------------------------

test("versions parse from `govbot --version` output and bare strings", () => {
  assert.deepEqual(parseVersion("govbot 0.1.0"), [0, 1, 0]);
  assert.deepEqual(parseVersion("0.12.3\n"), [0, 12, 3]);
  assert.deepEqual(parseVersion("1.2.3-nightly.4"), [1, 2, 3]);
  assert.equal(parseVersion("unknown"), null);
  assert.equal(parseVersion(null), null);
});

test("comparison is numeric, strict, and false whenever either side is unparseable", () => {
  assert.equal(isOlder("0.1.0", "0.2.0"), true);
  assert.equal(isOlder("0.9.0", "0.10.0"), true, "numeric, not lexical");
  assert.equal(isOlder("0.2.0", "0.2.0"), false);
  assert.equal(isOlder("1.0.0", "0.9.9"), false);
  // A version we cannot read must never make someone think an update exists.
  assert.equal(isOlder("unknown", "9.9.9"), false);
  assert.equal(isOlder("0.1.0", "garbage"), false);
});

test("malformed version files are treated as no data", () => {
  assert.equal(parseRemote(null), null);
  assert.equal(parseRemote({}), null);
  assert.equal(parseRemote({ mcp: "latest" }), null);
  assert.deepEqual(parseRemote({ mcp: "0.2.0", cli_min: "0.1.0", built: "x", extra: 1 }), {
    mcp: "0.2.0",
    cli_min: "0.1.0",
    built: "x",
  });
});

// ---------------------------------------------------------------------------
// Notices
// ---------------------------------------------------------------------------

test("no notice when everything is current", () => {
  assert.deepEqual(
    updateNotices({ bundle: "0.1.0", cli: "govbot 0.1.0", cliMin: "0.1.0", state: checked("0.1.0", "0.1.0") }),
    [],
  );
});

test("a newer bundle gives the stable download URL and the drag-in step", () => {
  const [notice, ...rest] = updateNotices({
    bundle: "0.1.0",
    cli: "govbot 0.1.0",
    cliMin: "0.1.0",
    state: checked("0.2.0"),
  });
  assert.equal(rest.length, 0);
  assert.match(notice!, /0\.2\.0/);
  assert.ok(notice!.includes(BUNDLE_URL));
  assert.match(notice!, /Settings → Extensions/);
});

test("a CLI below the published minimum points at the one-line installer", () => {
  const notices = updateNotices({
    bundle: "0.2.0",
    cli: "govbot 0.1.0",
    cliMin: "0.1.0",
    state: checked("0.2.0", "0.2.0"),
  });
  assert.equal(notices.length, 1);
  assert.ok(notices[0]!.includes(CLI_INSTALL_COMMAND));
  assert.match(notices[0]!, /0\.1\.0.*0\.2\.0 or newer/);
});

test("the server's own CLI minimum applies offline, without any fetched data", () => {
  for (const status of ["unavailable", "disabled", "pending"] as const) {
    const notices = updateNotices({ bundle: "0.2.0", cli: "govbot 0.1.0", cliMin: "0.2.0", state: { status } });
    assert.equal(notices.length, 1, status);
    assert.ok(notices[0]!.includes(CLI_INSTALL_COMMAND));
  }
});

test("the higher of the two CLI minimums wins", () => {
  const notices = updateNotices({
    bundle: "0.1.0",
    cli: "govbot 0.2.0",
    cliMin: "0.3.0",
    state: checked("0.1.0", "0.1.0"),
  });
  assert.match(notices[0]!, /0\.3\.0 or newer/);
});

test("offline with nothing cached means no notice", () => {
  assert.deepEqual(
    updateNotices({ bundle: "0.1.0", cli: "govbot 0.1.0", cliMin: "0.1.0", state: { status: "unavailable" } }),
    [],
  );
});

test("a missing CLI is left to the existing not-installed message", () => {
  assert.deepEqual(
    updateNotices({ bundle: "0.1.0", cli: null, cliMin: "0.5.0", state: checked("0.1.0", "0.5.0") }),
    [],
  );
});

test("the status line never claims up to date without a check", () => {
  assert.match(describeState(checked("0.1.0")), /none found \(last checked 2026-10-14\)/);
  assert.match(describeState({ status: "unavailable" }), /could not check/);
  assert.match(describeState({ status: "disabled" }), /not checked/);
  assert.match(describeState({ status: "pending" }), /still checking/);
});

// ---------------------------------------------------------------------------
// Caching
// ---------------------------------------------------------------------------

test("a successful check is cached, and a fresh cache skips the network", async () => {
  const cachePath = tempCache();
  const now = new Date("2026-10-14T12:00:00Z");

  const first = await checkForUpdates({ cachePath, now, fetchImpl: jsonResponse({ mcp: "0.2.0", cli_min: "0.1.0" }) });
  assert.equal(first.status, "checked");
  const written = JSON.parse(readFileSync(cachePath, "utf8"));
  assert.equal(written.checked_at, now.toISOString());
  assert.equal(written.remote.mcp, "0.2.0");

  let fetched = false;
  const second = await checkForUpdates({
    cachePath,
    now: new Date("2026-10-15T11:59:00Z"), // 23h59m later
    fetchImpl: (async () => {
      fetched = true;
      throw new Error("should not be called");
    }) as typeof fetch,
  });
  assert.equal(fetched, false);
  assert.deepEqual(second, { status: "checked", checkedAt: now.toISOString(), remote: { mcp: "0.2.0", cli_min: "0.1.0" } });
});

test("a cache older than a day is refreshed", async () => {
  const cachePath = tempCache();
  writeFileSync(cachePath, JSON.stringify({ checked_at: "2026-10-13T00:00:00.000Z", remote: { mcp: "0.1.0" } }));
  const now = new Date("2026-10-14T12:00:00Z");
  const state = await checkForUpdates({ cachePath, now, fetchImpl: jsonResponse({ mcp: "0.3.0" }) });
  assert.equal(state.status === "checked" && state.remote.mcp, "0.3.0");
  assert.equal(JSON.parse(readFileSync(cachePath, "utf8")).checked_at, now.toISOString());
});

test("a cache dated in the future (clock change) is not trusted forever", async () => {
  const cachePath = tempCache();
  writeFileSync(cachePath, JSON.stringify({ checked_at: "2030-01-01T00:00:00.000Z", remote: { mcp: "0.1.0" } }));
  const state = await checkForUpdates({
    cachePath,
    now: new Date("2026-10-14T12:00:00Z"),
    fetchImpl: jsonResponse({ mcp: "0.4.0" }),
  });
  assert.equal(state.status === "checked" && state.remote.mcp, "0.4.0");
});

test("when the refresh fails, a stale cache is still used and kept", async () => {
  const cachePath = tempCache();
  const stale = { checked_at: "2026-10-01T00:00:00.000Z", remote: { mcp: "0.2.0" } };
  writeFileSync(cachePath, JSON.stringify(stale));
  const state = await checkForUpdates({
    cachePath,
    now: new Date("2026-10-14T12:00:00Z"),
    fetchImpl: (async () => {
      throw new TypeError("fetch failed");
    }) as typeof fetch,
  });
  assert.deepEqual(state, { status: "checked", checkedAt: stale.checked_at, remote: stale.remote });
  assert.deepEqual(JSON.parse(readFileSync(cachePath, "utf8")), stale);
});

test("a corrupt cache file is ignored, not fatal", async () => {
  const cachePath = tempCache();
  writeFileSync(cachePath, "{not json");
  const state = await checkForUpdates({ cachePath, fetchImpl: jsonResponse({ mcp: "0.2.0" }) });
  assert.equal(state.status, "checked");
});

test("a 404 or malformed body is no data, and nothing is cached", async () => {
  const cachePath = tempCache();
  const notFound = (async () => new Response("Not Found", { status: 404 })) as typeof fetch;
  assert.deepEqual(await checkForUpdates({ cachePath, fetchImpl: notFound }), { status: "unavailable" });
  assert.deepEqual(await checkForUpdates({ cachePath, fetchImpl: jsonResponse({ nope: true }) }), {
    status: "unavailable",
  });
  assert.equal(existsSync(cachePath), false);
});

// ---------------------------------------------------------------------------
// Offline: no failure, no delay
// ---------------------------------------------------------------------------

test("offline (connection refused, real fetch): no error, no cache, no notice", async () => {
  const cachePath = tempCache();
  // Port 9 on localhost has nothing listening; this exercises Node's real fetch.
  const started = Date.now();
  const state = await checkForUpdates({ cachePath, url: "http://127.0.0.1:9/govbot-mcp-version.json" });
  assert.deepEqual(state, { status: "unavailable" });
  assert.ok(Date.now() - started < 3_000);
  assert.equal(existsSync(cachePath), false);
});

test("a network that hangs is abandoned at the timeout", async () => {
  // A server that accepts the connection and never answers — the worst case
  // for a captive portal or a dead Wi-Fi.
  const server = createServer(() => {});
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as AddressInfo;
  try {
    const started = Date.now();
    const remote = await fetchRemote(`http://127.0.0.1:${port}/v.json`, 200);
    const elapsed = Date.now() - started;
    assert.equal(remote, null);
    assert.ok(elapsed < 1_500, `took ${elapsed}ms`);
  } finally {
    server.closeAllConnections();
    server.close();
  }
});

test("even a fetch that ignores its abort signal cannot hold things up", async () => {
  const never = (() => new Promise(() => {})) as typeof fetch;
  const started = Date.now();
  assert.equal(await fetchRemote("http://example.invalid/", 100, never), null);
  assert.ok(Date.now() - started < 1_000);
});

test("starting the check returns immediately and never throws", () => {
  const started = Date.now();
  startUpdateCheck({
    cachePath: tempCache(),
    fetchImpl: (() => new Promise(() => {})) as typeof fetch,
    timeoutMs: 50,
  });
  assert.ok(Date.now() - started < 50);
});

test("GOVBOT_NO_UPDATE_CHECK switches it off", () => {
  assert.equal(isDisabled({ GOVBOT_NO_UPDATE_CHECK: "1" }), true);
  assert.equal(isDisabled({ GOVBOT_NO_UPDATE_CHECK: "0" }), false);
  assert.equal(isDisabled({}), false);
});
