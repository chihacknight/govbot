// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// CONTEXT/ENVIRONMENT SETUP: See govbot/README.md
//
// TO UPDATE THIS FILTER FOR ga-legislation (Georgia):
// 1. First, gather real data by running this command:
//    `just govbot logs --repos=ga --limit=100`
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
// 5. Test your changes: `just govbot logs --repos=ga --limit=100 --filter=default`
//
// Current filter removes: routine hopper entries, first readers, and routine referrals
// ======================================

// Filter for ga-legislation (Georgia)
// Filters out routine hopper entries, first readers, and routine referrals

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
                    // Filter out "Senate Hopper" and "House Hopper" - routine filing
                    if desc_str == "Senate Hopper" || desc_str == "House Hopper" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "House First Readers" - routine first reading
                    if desc_str == "House First Readers" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Senate Read and Referred" - routine referral
                    if desc_str == "Senate Read and Referred" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "House Second Readers" - routine second reading
                    if desc_str == "House Second Readers" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Senate Read Second Time" - routine second reading
                    if desc_str == "Senate Read Second Time" {
                        return FilterResult::FilterOut;
                    }
                }
            }
        }
    }

    FilterResult::Keep
}
