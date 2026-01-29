// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// This file contains a filter for ar-legislation (Arkansas) that removes "noisy" routine log entries
// to make the output more focused on important legislative actions.
//
// TO UPDATE THIS FILTER:
// 1. Run: `just govbot logs --repos=ar --limit=100` to see recent log entries
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
// 5. Test your changes: `just govbot logs --repos=ar --limit=100 --filter=default`
//
// Current filter removes: routine filing, first reading/referrals, and routine procedural actions
// ======================================

// Filter for ar-legislation (Arkansas)
// Filters out routine filing, first reading/referrals, and routine procedural actions

use crate::filter::FilterResult;
use serde_json::Value;

pub fn should_keep(entry: &Value) -> FilterResult {
    if let Some(log) = entry.get("log") {
        if let Some(action) = log.get("action") {
            // Filter out "introduction" classification - very routine
            if let Some(classification) = action.get("classification") {
                if let Some(class_array) = classification.as_array() {
                    for class in class_array {
                        if let Some(class_str) = class.as_str() {
                            if class_str == "introduction" {
                                return FilterResult::FilterOut;
                            }
                        }
                    }
                }
            }

            if let Some(description) = action.get("description") {
                if let Some(desc_str) = description.as_str() {
                    // Filter out simple "Filed" - very routine
                    if desc_str == "Filed" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out routine first reading + referral patterns
                    if desc_str.contains("Read first time")
                        && desc_str.contains("rules suspended")
                        && desc_str.contains("referred to")
                    {
                        return FilterResult::FilterOut;
                    }
                    // Filter out routine first + second reading
                    if desc_str.contains("Read the first time")
                        && desc_str.contains("rules suspended")
                        && desc_str.contains("read the second time")
                    {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Placed on second reading for the purpose of amendment" - routine
                    if desc_str == "Placed on second reading for the purpose of amendment." {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Rules suspended" - routine procedural
                    if desc_str == "Rules suspended." {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "REPORTED CORRECTLY ENGROSSED" - routine
                    if desc_str == "REPORTED CORRECTLY ENGROSSED" {
                        return FilterResult::FilterOut;
                    }
                }
            }
        }
    }

    FilterResult::Keep
}
