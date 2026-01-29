// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// CONTEXT/ENVIRONMENT SETUP: See govbot/README.md
//
// TO UPDATE THIS FILTER FOR id-legislation (Idaho):
// 1. First, gather real data by running this command:
//    `just govbot logs --repos=id --limit=100`
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
// 5. Test your changes: `just govbot logs --repos=id --limit=100 --filter=default`
//
// Current filter removes: routine introductions, readings, and status updates
// ======================================

// Filter for id-legislation (Idaho)
// Filters out routine introductions, readings, and status updates

use crate::filter::FilterResult;
use serde_json::Value;

pub fn should_keep(entry: &Value) -> FilterResult {
    if let Some(log) = entry.get("log") {
        if let Some(action) = log.get("action") {
            // Filter out "introduction" classification
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

            // Filter out routine descriptions
            if let Some(description) = action.get("description") {
                if let Some(desc_str) = description.as_str() {
                    // Filter out "Introduced, read first time" - routine introduction
                    if desc_str.starts_with("Introduced, read first time") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Read second time; Filed for Third Reading" - routine reading
                    if desc_str == "Read second time; Filed for Third Reading" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "U.C. to hold place on third reading calendar" - routine scheduling
                    if desc_str.contains("U.C. to hold place on third reading calendar") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Reported Printed; referred to" - routine referral
                    if desc_str.starts_with("Reported Printed; referred to") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Reported out as amended; filed for first reading" - routine status
                    if desc_str == "Reported out as amended; filed for first reading" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Amendments reported printed" - routine status
                    if desc_str == "Amendments reported printed" {
                        return FilterResult::FilterOut;
                    }
                }
            }
        }
    }

    FilterResult::Keep
}
