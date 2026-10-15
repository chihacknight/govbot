/**
 * Tests for the pure helpers in the tool layer.
 *
 * The parts that shell out to `govbot` are covered by the snapshot session in
 * `render-snapshots.sh`; what is worth unit-testing here are the small decisions
 * that would fail silently and wrongly.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import { readFileSync } from "node:fs";

import {
  countScoredBills,
  describeTagCoverage,
  detectTaggingMode,
  normalizeLocale,
} from "./tools.js";

test("keyword fallback is detected rather than passed off as AI tagging", () => {
  // govbot falls back to keyword matching when the model cannot be loaded, and
  // says so only on stderr. Reporting those results as AI-tagged would be an
  // accuracy regression the person cannot see.
  assert.equal(
    detectTaggingMode("Embedding files not available; using keyword-based matching."),
    "keyword",
  );
  assert.equal(
    detectTaggingMode(
      "Warning: Failed to initialize embedding matcher: no such file\nFalling back to keyword-based matching.",
    ),
    "keyword",
  );
  assert.equal(
    detectTaggingMode("Using embedding mode:\n  Model: /tmp/model.onnx"),
    "embedding",
  );
});

test("Open Civic Data ids are accepted wherever a locale code is expected", () => {
  // The model is told to speak OCD, but `govbot clone` only understands locales.
  assert.equal(normalizeLocale("il"), "il");
  assert.equal(normalizeLocale("IL"), "il");
  assert.equal(
    normalizeLocale("ocd-jurisdiction/country:us/state:il/government"),
    "il",
  );
  assert.equal(normalizeLocale("ocd-division/country:us/state:wy/sldl:23"), "wy");
});

test("federal maps to the locale it lives under on disk", () => {
  // Congress is `state:usa` in the path layout but has no `state:` segment in OCD.
  assert.equal(normalizeLocale("ocd-jurisdiction/country:us/government"), "usa");
  assert.equal(normalizeLocale("ocd-division/country:us"), "usa");
  assert.equal(normalizeLocale("usa"), "usa");
});

// `govbot logs --join bill --filter none --limit 400 --repos wy,gu` against the
// wy/gu mocks in actions/govbot/mocks: 20 log entries for 10 Wyoming bills across
// two sessions. Guam's mock bills have no log entries, so none appear.
const WY_LOGS = readFileSync(new URL("../src/fixtures/wy-logs.jsonl", import.meta.url), "utf8");

function coverageEntry(locale: string, name: string, bills: number) {
  return {
    jurisdiction: { id: `ocd-jurisdiction/country:us/state:${locale}/government`, name, locale },
    bills,
    vote_events: 0,
    member_vote_rows: 0,
    roll_call_data: "none" as const,
    sessions: [],
  };
}

test("scored bills are counted per bill and session, not per log entry", () => {
  // --limit caps log entries, and a bill has several. HB0002 exists in both 2025
  // and 2026, and they are different bills.
  assert.deepEqual(countScoredBills(WY_LOGS), new Map([["wy", 10]]));
  // Blank and unparseable lines, and entries with no jurisdiction path, are not bills.
  assert.deepEqual(
    countScoredBills('\nnot json\n{"id":"HB1","sources":{"log":"elsewhere"}}\n'),
    new Map(),
  );
});

test("a partial run says what was not checked instead of letting zero read as none", () => {
  const result = describeTagCoverage(
    new Map([["il", 384]]),
    [coverageEntry("il", "Illinois", 12780)],
  );
  assert.equal(result.partial, true);
  assert.deepEqual(result.jurisdictions, [
    { jurisdiction: "il", name: "Illinois", scored: 384, total: 12780 },
  ]);
  assert.match(result.lines[0]!, /^Illinois: scored 384 of 12,780 bills \(3%\)\. The other 12,396 were not checked/);
  const text = result.lines.join("\n");
  assert.match(text, /not evidence that no such bills exist/);
  assert.match(text, /`query` with `text`/);
  // 12,396 bills at 25 a second is 8.3 minutes.
  assert.match(text, /at least 9 minutes/);
});

test("a jurisdiction with no log entries is reported as unscored, not omitted", () => {
  // Guam's mock bills have no log entries, so a tag run cannot reach any of them.
  const result = describeTagCoverage(countScoredBills(WY_LOGS), [
    coverageEntry("wy", "Wyoming", 10),
    coverageEntry("gu", "Guam", 5),
  ]);
  assert.equal(result.lines[0], "Wyoming: scored all 10 bills.");
  assert.match(result.lines[1]!, /^Guam: scored 0 of 5 bills \(0%\)/);
  assert.match(result.lines[1]!, /a higher limit will not reach them/);
  assert.equal(result.partial, true);
  // Raising the limit cannot help, so it is not suggested.
  assert.doesNotMatch(result.lines.join("\n"), /rerun with a higher limit/);
});

test("a complete run carries no partial-run warning", () => {
  const result = describeTagCoverage(countScoredBills(WY_LOGS), [
    coverageEntry("wy", "Wyoming", 10),
  ]);
  assert.equal(result.partial, false);
  assert.deepEqual(result.lines, ["Wyoming: scored all 10 bills."]);
});

test("percentages never round a partial run up to 100% or a nonzero one down to 0%", () => {
  const nearlyAll = describeTagCoverage(new Map([["il", 12779]]), [coverageEntry("il", "Illinois", 12780)]);
  assert.match(nearlyAll.lines[0]!, /\(99%\)/);
  const barely = describeTagCoverage(new Map([["il", 1]]), [coverageEntry("il", "Illinois", 12780)]);
  assert.match(barely.lines[0]!, /\(under 1%\)/);
});

test("unknown totals are reported as partial rather than guessed", () => {
  const result = describeTagCoverage(new Map([["il", 384]]), null);
  assert.equal(result.partial, true);
  assert.deepEqual(result.jurisdictions, [
    { jurisdiction: "il", name: "IL", scored: 384, total: null },
  ]);
  assert.match(result.lines[0]!, /unknown total/);
});
