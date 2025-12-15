// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// This file contains a filter for az-legislation (Arizona) that removes "noisy" routine log entries
// to make the output more focused on important legislative actions.
//
// TO UPDATE THIS FILTER:
// 1. Run: `just govbot logs --repos=az --limit=100` to see recent log entries
// 2. Analyze the output to identify patterns that are routine/noteworthy but not important:
//    - Routine actions: committee referrals, first readings, filings, prefiling, status updates
//    - Important actions: passage votes, executive signatures, amendments, failures, committee reports with substance
// 3. Look for patterns in:
//    - `classification` array: common values like "referral-committee", "filing", "introduction", "reading-1"
//    - `description` field: text patterns that appear frequently but aren't substantive
// 4. Add new filter conditions following the existing pattern:
//    - Check `classification` array for routine classifications
//    - Check `description` string for routine text patterns (use `starts_with()`, `contains()`, or exact match)
//    - Return `FilterResult::FilterOut` for routine entries, `FilterResult::Keep` for important ones
// 5. Test your changes: `just govbot logs --repos=az --limit=100 --filter=default`
//
// Current filter: No test data available - placeholder filter
// ======================================

// Filter for az-legislation (Arizona)
// Note: Repository not found in test data - keeping default filter for now
// TODO: Analyze output from `just govbot logs --repos=az --limit=100` when data is available

use crate::filter::FilterResult;
use serde_json::Value;

pub fn should_keep(_entry: &Value) -> FilterResult {
    // No data available yet - keep all entries
    FilterResult::Keep
}
