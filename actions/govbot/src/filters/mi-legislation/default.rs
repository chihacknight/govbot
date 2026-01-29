// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// CONTEXT/ENVIRONMENT SETUP: See govbot/README.md
//
// TO UPDATE THIS FILTER FOR mi-legislation (Michigan):
// 1. First, gather real data by running this command:
//    `just govbot logs --repos=mi --limit=100`
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
// 5. Test your changes: `just govbot logs --repos=mi --limit=100 --filter=default`
//
// Current filter removes: routine introductions, referrals, and first readings
// ======================================

// Filter for mi-legislation (Michigan)
// Filters out routine introductions, referrals, and first readings

use crate::filter::FilterResult;
use serde_json::Value;

pub fn should_keep(entry: &Value) -> FilterResult {
    if let Some(log) = entry.get("log") {
        if let Some(action) = log.get("action") {
            // Filter out "introduction" and "referral-committee" classifications
            if let Some(classification) = action.get("classification") {
                if let Some(class_array) = classification.as_array() {
                    for class in class_array {
                        if let Some(class_str) = class.as_str() {
                            if class_str == "introduction" || class_str == "referral-committee" {
                                return FilterResult::FilterOut;
                            }
                        }
                    }
                }
            }

            // Filter out routine descriptions
            if let Some(description) = action.get("description") {
                if let Some(desc_str) = description.as_str() {
                    // Filter out "referred to Committee on" - routine referral
                    if desc_str.starts_with("referred to Committee on") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "REFERRED TO COMMITTEE" - routine referral
                    if desc_str.starts_with("REFERRED TO COMMITTEE") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "read a first time" - routine first reading
                    if desc_str == "read a first time" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "INTRODUCED BY" - routine introduction
                    if desc_str.starts_with("INTRODUCED BY") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "introduced by" - routine introduction
                    if desc_str.starts_with("introduced by") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "bill electronically reproduced" - routine status
                    if desc_str.starts_with("bill electronically reproduced") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "re-referred to Committee on" - routine re-referral
                    if desc_str.starts_with("re-referred to Committee on") {
                        return FilterResult::FilterOut;
                    }
                }
            }
        }
    }

    FilterResult::Keep
}
