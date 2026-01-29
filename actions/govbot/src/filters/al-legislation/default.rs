// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// This file contains a filter for al-legislation (Alabama) that removes "noisy" routine log entries
// to make the output more focused on important legislative actions.
//
// TO UPDATE THIS FILTER:
// 1. Run: `just govbot logs --repos=al --limit=100` to see recent log entries
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
// 5. Test your changes: `just govbot logs --repos=al --limit=100 --filter=default`
//
// Current filter removes: routine filing, first reading/referral, and pending committee status updates
// ======================================

// Filter for al-legislation (Alabama)
// Filters out routine filing, first reading/referral, and pending committee status updates

use crate::filter::FilterResult;
use serde_json::Value;

pub fn should_keep(entry: &Value) -> FilterResult {
    if let Some(log) = entry.get("log") {
        if let Some(action) = log.get("action") {
            // Filter out "filing" classification - very routine, every bill gets filed
            if let Some(classification) = action.get("classification") {
                if let Some(class_array) = classification.as_array() {
                    for class in class_array {
                        if let Some(class_str) = class.as_str() {
                            if class_str == "filing" {
                                return FilterResult::FilterOut;
                            }
                        }
                    }
                }
            }

            // Filter out routine first reading + committee referral
            // "Read for the first time and referred to..." happens to almost every bill
            if let Some(description) = action.get("description") {
                if let Some(desc_str) = description.as_str() {
                    if desc_str.starts_with("Read for the first time and referred to") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Pending Committee Action" - routine status updates
                    if desc_str.starts_with("Pending Committee Action in House of Origin") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out simple "Filed" descriptions
                    if desc_str == "Filed" {
                        return FilterResult::FilterOut;
                    }
                }
            }
        }
    }

    FilterResult::Keep
}
