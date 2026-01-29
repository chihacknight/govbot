// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// CONTEXT/ENVIRONMENT SETUP: See govbot/README.md
//
// TO UPDATE THIS FILTER FOR vi-legislation (U.S. Virgin Islands):
// 1. First, gather real data by running this command:
//    `just govbot logs --repos=vi --limit=100`
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
// 5. Test your changes: `just govbot logs --repos=vi --limit=100 --filter=default`
//
// Current filter removes: routine status updates and transfers
// ======================================

// Filter for vi-legislation (U.S. Virgin Islands)
// Filters out routine status updates and transfers

use crate::filter::FilterResult;
use serde_json::Value;

pub fn should_keep(entry: &Value) -> FilterResult {
    if let Some(log) = entry.get("log") {
        if let Some(action) = log.get("action") {
            // Filter out routine descriptions
            if let Some(description) = action.get("description") {
                if let Some(desc_str) = description.as_str() {
                    // Filter out "received" - routine receipt
                    if desc_str == "received" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Assigned" - routine assignment
                    if desc_str == "Assigned" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "To Senate" - routine transfer
                    if desc_str == "To Senate" {
                        return FilterResult::FilterOut;
                    }
                }
            }
        }
    }

    FilterResult::Keep
}
