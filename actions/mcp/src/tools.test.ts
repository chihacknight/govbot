/**
 * Tests for the pure helpers in the tool layer.
 *
 * The parts that shell out to `govbot` are covered by the snapshot session in
 * `render-snapshots.sh`; what is worth unit-testing here are the small decisions
 * that would fail silently and wrongly.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import { describeVoteSummary, detectTaggingMode, normalizeLocale } from "./tools.js";

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
});
