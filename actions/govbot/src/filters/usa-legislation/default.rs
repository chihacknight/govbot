// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// CONTEXT/ENVIRONMENT SETUP: See govbot/README.md
//
// TO UPDATE THIS FILTER FOR usa-legislation (United States):
// 1. First, gather real data by running this command:
//    `just govbot logs --repos=usa --limit=100`
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
// 5. Test your changes: `just govbot logs --repos=usa --limit=100 --filter=default`
//
// Current filter: TODO - Analyze output to identify noisy patterns
// ======================================

// Filter for usa-legislation (United States)
// TODO: Analyze output from `just govbot logs --limit=10` to identify noisy patterns
// and add specific filters for this locale

use crate::filter::FilterResult;
use serde_json::Value;

pub fn should_keep(entry: &Value) -> FilterResult {
    if let Some(log) = entry.get("log") {
        if let Some(_action) = log.get("action") {
            // Add locale-specific filters here based on observed patterns
            // Common patterns to consider filtering:
            // - "referral-committee" classification
            // - "filing" or "introduction" classifications  
            // - Routine reading actions
            // - Prefiling actions
            // - Routine committee actions
        }
    }

    FilterResult::Keep
}
