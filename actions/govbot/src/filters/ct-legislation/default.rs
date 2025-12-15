// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// CONTEXT/ENVIRONMENT SETUP: See govbot/README.md
//
// TO UPDATE THIS FILTER FOR ct-legislation (Connecticut):
// 1. First, gather real data by running this command:
//    `just govbot logs --repos=ct --limit=100`
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
// 5. Test your changes: `just govbot logs --repos=ct --limit=100 --filter=default`
//
// Current filter: No test data available - placeholder filter
// ======================================

// Filter for ct-legislation (Connecticut)
// No test data available - placeholder filter

use crate::filter::FilterResult;
use serde_json::Value;

pub fn should_keep(_entry: &Value) -> FilterResult {
    // No test data available for analysis
    FilterResult::Keep
}
