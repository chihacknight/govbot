// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// CONTEXT/ENVIRONMENT SETUP: See govbot/README.md
//
// TO UPDATE THIS FILTER FOR mp-legislation (Northern Mariana Islands):
// 1. First, gather real data by running this command:
//    `just govbot logs --repos=mp --limit=100`
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
// 5. Test your changes: `just govbot logs --repos=mp --limit=100 --filter=default`
//
// Current filter removes: routine introduction and reading actions
// ======================================

// Filter for mp-legislation (Northern Mariana Islands)
// Filters out routine introduction and reading actions

use serde_json::Value;
use crate::filter::FilterResult;

pub fn should_keep(entry: &Value) -> FilterResult {
    if let Some(log) = entry.get("log") {
        if let Some(action) = log.get("action") {
            // Filter out routine introduction actions
            if let Some(description) = action.get("description") {
                if let Some(desc_str) = description.as_str() {
                    // "Date Introduced" is very routine - every bill gets this
                    if desc_str == "Date Introduced" {
                        return FilterResult::FilterOut;
                    }
                    // Routine reading actions
                    if desc_str == "House First Reading" 
                        || desc_str == "House Final Reading"
                        || desc_str == "Senate First Reading"
                        || desc_str == "Senate Final Reading" {
                        return FilterResult::FilterOut;
                    }
                }
            }

            // Filter out "introduction" classification - very routine
            if let Some(classification) = action.get("classification") {
                if let Some(class_array) = classification.as_array() {
                    for class in class_array {
                        if let Some(class_str) = class.as_str() {
                            if class_str == "introduction" {
                                return FilterResult::FilterOut;
                            }
                            // Reading classifications are routine
                            if class_str == "reading-1" || class_str == "reading-2" {
                                return FilterResult::FilterOut;
                            }
                        }
                    }
                }
            }
        }
    }

    FilterResult::Keep
}
