// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// CONTEXT/ENVIRONMENT SETUP: See govbot/README.md
//
// TO UPDATE THIS FILTER FOR wv-legislation (West Virginia):
// 1. First, gather real data by running this command:
//    `just govbot logs --repos=wv --limit=100`
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
// 5. Test your changes: `just govbot logs --repos=wv --limit=100 --filter=default`
//
// Current filter removes: routine filings, introductions, referrals, and readings
// ======================================

// Filter for wv-legislation (West Virginia)
// Filters out routine filings, introductions, referrals, and readings

use crate::filter::FilterResult;
use serde_json::Value;

pub fn should_keep(entry: &Value) -> FilterResult {
    if let Some(log) = entry.get("log") {
        if let Some(action) = log.get("action") {
            // Filter out "filing" and "introduction" classifications
            if let Some(classification) = action.get("classification") {
                if let Some(class_array) = classification.as_array() {
                    for class in class_array {
                        if let Some(class_str) = class.as_str() {
                            if class_str == "filing" || class_str == "introduction" {
                                return FilterResult::FilterOut;
                            }
                        }
                    }
                }
            }

            // Filter out routine descriptions
            if let Some(description) = action.get("description") {
                if let Some(desc_str) = description.as_str() {
                    // Filter out "Filed for introduction" - routine filing
                    if desc_str == "Filed for introduction" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Introduced in House" - routine introduction
                    if desc_str == "Introduced in House" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Introduced in Senate" - routine introduction
                    if desc_str == "Introduced in Senate" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "To" - routine referral (e.g., "To House Judiciary")
                    if desc_str.starts_with("To ")
                        && (desc_str.contains("House")
                            || desc_str.contains("Senate")
                            || desc_str.contains("Finance")
                            || desc_str.contains("Judiciary"))
                    {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Read 1st time" - routine reading
                    if desc_str == "Read 1st time" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Read 2nd time" - routine reading
                    if desc_str == "Read 2nd time" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Read 3rd time" - routine reading
                    if desc_str == "Read 3rd time" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "On 2nd reading" - routine reading
                    if desc_str == "On 2nd reading" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Communicated to Senate" - routine status
                    if desc_str == "Communicated to Senate" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Reported do pass" - routine committee report
                    if desc_str == "Reported do pass" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Floor amendment adopted (Voice vote)" - routine amendment
                    if desc_str == "Floor amendment adopted (Voice vote)" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Amendment withdrawn (Voice vote)" - routine amendment
                    if desc_str == "Amendment withdrawn (Voice vote)" {
                        return FilterResult::FilterOut;
                    }
                }
            }
        }
    }

    FilterResult::Keep
}
