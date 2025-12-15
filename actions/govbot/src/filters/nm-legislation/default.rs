// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// CONTEXT/ENVIRONMENT SETUP: See govbot/README.md
//
// TO UPDATE THIS FILTER FOR nm-legislation (New Mexico):
// 1. First, gather real data by running this command:
//    `just govbot logs --repos=nm --limit=100`
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
// 5. Test your changes: `just govbot logs --repos=nm --limit=100 --filter=default`
//
// Current filter removes: routine committee referrals and routine committee actions
// ======================================

// Filter for nm-legislation (New Mexico)
// Filters out routine committee referrals and routine committee actions

use serde_json::Value;
use crate::filter::FilterResult;

pub fn should_keep(entry: &Value) -> FilterResult {
    if let Some(log) = entry.get("log") {
        if let Some(action) = log.get("action") {
            // Filter out routine committee referrals
            if let Some(classification) = action.get("classification") {
                if let Some(class_array) = classification.as_array() {
                    for class in class_array {
                        if let Some(class_str) = class.as_str() {
                            // Filter out "referral-committee" - very routine, happens to almost every bill
                            if class_str == "referral-committee" {
                                return FilterResult::FilterOut;
                            }
                        }
                    }
                }
            }

            // Filter out routine committee actions
            if let Some(description) = action.get("description") {
                if let Some(desc_str) = description.as_str() {
                    // "DO PASS, as amended, committee report adopted" is very routine
                    if desc_str.contains("DO PASS") && desc_str.contains("committee report adopted") {
                        return FilterResult::FilterOut;
                    }
                    // "Sent to [Committee]" is routine referral language
                    if desc_str.starts_with("Sent to ") && desc_str.contains("Committee") {
                        return FilterResult::FilterOut;
                    }
                }
            }
        }
    }

    FilterResult::Keep
}
