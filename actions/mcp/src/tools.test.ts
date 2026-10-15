/**
 * Tests for the pure helpers in the tool layer.
 *
 * The parts that shell out to `govbot` are covered by the snapshot session in
 * `render-snapshots.sh`; what is worth unit-testing here are the small decisions
 * that would fail silently and wrongly.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import {
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

// ---------------------------------------------------------------------------
// summarize: shaping query results for the model
// ---------------------------------------------------------------------------

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
