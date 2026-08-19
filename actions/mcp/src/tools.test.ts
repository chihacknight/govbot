/**
 * Tests for the pure helpers in the tool layer.
 *
 * The parts that shell out to `govbot` are covered by the snapshot session in
 * `render-snapshots.sh`; what is worth unit-testing here are the small decisions
 * that would fail silently and wrongly.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import { detectTaggingMode, normalizeLocale } from "./tools.js";

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
