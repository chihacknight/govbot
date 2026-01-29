// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// CONTEXT/ENVIRONMENT SETUP: See govbot/README.md
//
// TO UPDATE THIS FILTER FOR wa-legislation (Washington):
// 1. First, gather real data by running this command:
//    `just govbot logs --repos=wa --limit=100`
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
// 5. Test your changes: `just govbot logs --repos=wa --limit=100 --filter=default`
//
// Current filter removes: routine readings, referrals, and scheduling
// ======================================

// Filter for wa-legislation (Washington)
// Filters out routine readings, referrals, and scheduling

use crate::filter::FilterResult;
use serde_json::Value;

pub fn should_keep(entry: &Value) -> FilterResult {
    if let Some(log) = entry.get("log") {
        if let Some(action) = log.get("action") {
            // Filter out "reading-1", "reading-2", and "referral-committee" classifications
            if let Some(classification) = action.get("classification") {
                if let Some(class_array) = classification.as_array() {
                    for class in class_array {
                        if let Some(class_str) = class.as_str() {
                            if class_str == "reading-1" || class_str == "reading-2" || class_str == "referral-committee" {
                                return FilterResult::FilterOut;
                            }
                        }
                    }
                }
            }

            // Filter out routine descriptions
            if let Some(description) = action.get("description") {
                if let Some(desc_str) = description.as_str() {
                    // Filter out "First reading, referred to" - routine reading + referral
                    if desc_str.starts_with("First reading, referred to") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Referred to" - routine referral
                    if desc_str.starts_with("Referred to") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Rules Committee relieved of further consideration.  Placed on second reading" - routine status
                    if desc_str.starts_with("Rules Committee relieved of further consideration.  Placed on second reading") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Passed to Rules Committee for second reading" - routine status
                    if desc_str == "Passed to Rules Committee for second reading" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Public hearing in the" - routine hearing scheduling
                    if desc_str.starts_with("Public hearing in the") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Executive session scheduled, but no action was taken" - routine status
                    if desc_str.starts_with("Executive session scheduled, but no action was taken") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Rules suspended.  Placed on Third Reading" - routine status
                    if desc_str.starts_with("Rules suspended.  Placed on Third Reading") {
                        return FilterResult::FilterOut;
                    }
                }
            }
        }
    }

    FilterResult::Keep
}
