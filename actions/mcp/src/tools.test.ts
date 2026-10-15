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
  describeVoteSummary,
  detectTaggingMode,
  normalizeLocale,
  summarize,
  type QueryResponse,
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

test("vote totals are stated up front, with the person's votes per motion", () => {
  const lines = describeVoteSummary(
    {
      by_motion: [
        { motion_text: "Third Reading", votes: 3, person_votes: { yes: 2, no: 1 } },
        { motion_text: "", votes: 1 },
      ],
      motions_not_listed: 4,
      person_votes: { no: 1, yes: 2 },
      dates: { earliest: "2025-01-15", latest: "2026-05-31" },
    },
    4,
  );
  assert.equal(
    lines[0],
    "Totals across all 4 matching votes, 2025-01-15 to 2026-05-31 (rows below are newest first):",
  );
  assert.equal(lines[1], "  This person voted: yes 2, no 1.");
  assert.equal(lines[3], "    Third Reading: 3 (yes 2, no 1)");
  assert.equal(lines[4], "    (no motion text): 1");
  assert.match(lines[5] ?? "", /4 more motions/);

  // With a tag, rows are ranked by topic score first, so "newest first" would mislead.
  assert.match(
    describeVoteSummary({ by_motion: [] }, 1, true)[0] ?? "",
    /\(rows below are most on-topic first, then newest\):$/,
  );
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

const IL = {
  jurisdiction: { id: "ocd-jurisdiction/country:us/state:il/government", name: "Illinois", locale: "il" },
  bills: 12780,
  vote_events: 9300,
  member_vote_rows: 1000,
  roll_call_data: "available" as const,
  sessions: ["104th"],
};

const COSPONSOR_NAMES = Array.from({ length: 25 }, (_, i) => `Cosponsor ${i + 1}`);

/** A bill shaped like the CLI's output, with one primary sponsor and 25 cosponsors. */
function bigBill(): Record<string, unknown> {
  return {
    citation: {
      commit: "a09a582",
      path: "country:us/state:il/sessions/104th/bills/HB3526/metadata.json",
      repo: "il-legislation",
    },
    classification: ["bill"],
    identifier: "HB3526",
    jurisdiction: { id: IL.jurisdiction.id, name: "Illinois" },
    latest_action: { date: "2025-04-11", description: "Re-referred to Rules Committee" },
    legislative_session: "104th",
    sponsorships: [
      // Cosponsors listed before the primary, as Congress data does.
      ...COSPONSOR_NAMES.slice(0, 3).map((name) => cosponsor(name)),
      { classification: "primary", entity_type: "person", name: "Lead Sponsor", primary: true },
      ...COSPONSOR_NAMES.slice(3).map((name) => cosponsor(name)),
    ],
    tag: { final_score: 0.81, score: { final_score: 0.81, keyword_match: ["rent"] } },
    title: "LANDLORD-TENANT-RENT",
  };
}

function cosponsor(name: string) {
  return { classification: "cosponsor", entity_type: "person", name, primary: false };
}

function billsResponse(query: Record<string, unknown>, results: Record<string, unknown>[]): QueryResponse {
  return {
    query: { type: "bills", ...query },
    results,
    truncation: { returned: results.length, total_matching: 61, limit: 20 },
    coverage: [IL],
  };
}

/** The JSON rows after the prose header: one object per line. */
function rowsOf(text: string): Record<string, unknown>[] {
  return text
    .split("\n")
    .filter((line) => line.startsWith("{"))
    .map((line) => JSON.parse(line) as Record<string, unknown>);
}

test("a broad bill search keeps the primary sponsor whole and trims cosponsors to names", () => {
  const text = summarize(billsResponse({ text: "rent" }, [bigBill()]));
  const [row] = rowsOf(text);
  assert.ok(row);

  assert.deepEqual(row.sponsorships, [
    { classification: "primary", entity_type: "person", name: "Lead Sponsor", primary: true },
  ]);
  assert.deepEqual(row.cosponsors, COSPONSOR_NAMES.slice(0, 5));
  assert.equal(row.cosponsors_total, 25);

  // Nothing Claude needs to cite or rank is lost.
  const original = bigBill();
  for (const key of ["citation", "identifier", "title", "legislative_session", "latest_action", "tag", "jurisdiction"]) {
    assert.deepEqual(row[key], original[key], key);
  }
  // A trimmed list must not be read as "did not cosponsor".
  assert.match(text, /Cosponsor lists are trimmed to 5 names/);
});

test("rows are one compact JSON object per line", () => {
  const text = summarize(billsResponse({ text: "rent" }, [bigBill(), bigBill()]));
  assert.equal(rowsOf(text).length, 2);
  assert.doesNotMatch(text, /^\s+"/m, "no pretty-printed JSON");
  assert.ok(text.startsWith("Showing 2 of 61 matches (limit 20)."));
});

test("with identifier or person set, every cosponsor is kept", () => {
  for (const query of [{ identifier: "HB3526" }, { person: "Cosponsor 25" }]) {
    const text = summarize(billsResponse(query, [bigBill()]));
    const [row] = rowsOf(text);
    assert.deepEqual(row, bigBill(), JSON.stringify(query));
    assert.doesNotMatch(text, /trimmed/);
  }
});

test("a short cosponsor list is not flagged as trimmed", () => {
  const bill = bigBill();
  bill.sponsorships = (bill.sponsorships as unknown[]).slice(0, 4); // 3 cosponsors + primary
  const text = summarize(billsResponse({}, [bill]));
  const [row] = rowsOf(text);
  assert.deepEqual(row?.cosponsors, COSPONSOR_NAMES.slice(0, 3));
  assert.equal(row?.cosponsors_total, 3);
  assert.doesNotMatch(text, /trimmed/);
});

test("a bill with no sponsor flagged primary keeps its list as-is", () => {
  // Relabelling a bill's authors as cosponsors would misattribute who led it.
  const bill = bigBill();
  bill.sponsorships = COSPONSOR_NAMES.map((name) => ({ ...cosponsor(name), classification: "author" }));
  const [row] = rowsOf(summarize(billsResponse({}, [bill])));
  assert.deepEqual(row, bill);
});

test("non-bill rows pass through unchanged", () => {
  const vote = {
    bill_identifier: "HB1056",
    citation: { commit: "a09a582", path: "x.vote_event.json", repo: "il-legislation" },
    match: { candidates: ["Smith"], confidence: "high", method: "exact_name" },
    person_vote: { option: "yes", voter_name: "Smith" },
  };
  const text = summarize({
    query: { type: "votes", person: "Smith" },
    results: [vote],
    truncation: { returned: 1, total_matching: 1, limit: 20 },
    coverage: [IL],
  });
  assert.deepEqual(rowsOf(text), [vote]);
});

test("coverage reports what is cloned instead of 'No matching records.'", () => {
  const text = summarize({
    query: { type: "coverage" },
    results: [],
    truncation: { returned: 0, total_matching: 0, limit: 20 },
    coverage: [IL],
  });
  assert.doesNotMatch(text, /No matching records/);
  assert.doesNotMatch(text, /\[\]/);
  assert.match(text, /Illinois \(il\): 12780 bills, 9300 recorded votes, sessions 104th\./);
});

test("an empty bill search says so without an empty JSON array", () => {
  const text = summarize({
    query: { type: "bills", text: "nothing" },
    results: [],
    truncation: { returned: 0, total_matching: 0, limit: 20 },
    coverage: [],
    caveats: ["Not cloned yet, so nothing here reflects them: ma."],
  });
  assert.equal(
    text,
    "No matching records.\n\nRead these before answering:\n  - Not cloned yet, so nothing here reflects them: ma.",
  );
});

test("rows say once where citation paths live, and that source_url is the official page", () => {
  // A relative git path is useless to someone who doesn't know where the clone
  // is; stating the folder once is cheaper than an absolute path on every row.
  const text = summarize(billsResponse({ text: "rent" }, [bigBill(), bigBill()]), "/home/x/govbot_data/repos");
  const notes = text.split("\n").filter((line) => line.includes("citation.path"));
  assert.equal(notes.length, 1);
  assert.match(notes[0] ?? "", /\/home\/x\/govbot_data\/repos\/<citation\.repo>/);
  assert.match(notes[0] ?? "", /source_url/);
  assert.equal(rowsOf(text).length, 2, "the note is not mistaken for a row");
});

test("no citation note when no row carries a citation", () => {
  for (const [type, results] of [
    ["bills", []],
    ["people", [{ name: "Smith", sponsored: 3 }]],
  ] as const) {
    const text = summarize(
      { query: { type }, results: [...results], truncation: { returned: results.length, total_matching: results.length, limit: 20 }, coverage: [IL] },
      "/home/x/govbot_data/repos",
    );
    assert.doesNotMatch(text, /citation\.path/, type);
  }
});

test("coverage for an uncloned jurisdiction doesn't claim nothing is cloned", () => {
  // Reported on #236: with IL and USA cloned, asking about ca said
  // "No government data has been cloned to this computer yet."
  const caveat =
    "Not cloned yet, so nothing here reflects them: ca. Run `govbot clone ca` first. This is missing data, not an empty record.";
  const response: QueryResponse = {
    query: { type: "coverage", jurisdictions: ["ocd-jurisdiction/country:us/state:ca/government"] },
    results: [],
    truncation: { returned: 0, total_matching: 0, limit: 20 },
    coverage: [],
    caveats: [caveat],
  };
  const text = summarize(response, undefined, [IL]);
  assert.doesNotMatch(text, /No government data has been cloned/);
  assert.match(text, /^The requested jurisdictions are not cloned to this computer\./);
  assert.match(text, /Cloned to this computer:\n  Illinois \(il\): 12780 bills/);
  assert.match(text, /nothing here reflects them: ca/);

  // Nothing cloned at all, but a jurisdiction was named: still about that request.
  assert.match(summarize(response, undefined, []), /not cloned to this computer\.\nNothing else is cloned either\./);

  // No jurisdictions requested and nothing cloned: the first-run message.
  assert.match(
    summarize({ ...response, query: { type: "coverage", jurisdictions: [] }, caveats: [] }),
    /^No government data has been cloned to this computer yet\./,
  );
});
