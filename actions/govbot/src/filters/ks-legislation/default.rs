// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// CONTEXT/ENVIRONMENT SETUP: See govbot/README.md
//
// TO UPDATE THIS FILTER FOR ks-legislation (Kansas):
// 1. First, gather real data by running this command:
//    `just govbot logs --repos=ks --limit=100`
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
// 5. Test your changes: `just govbot logs --repos=ks --limit=100 --filter=default`
//
// Current filter removes: routine introductions, referrals, and hearing notifications
// ======================================

// Filter for ks-legislation (Kansas)
// Filters out routine introductions, referrals, and hearing notifications

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
                    // Filter out "Introduced" - routine introduction
                    if desc_str == "Introduced" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Received and Introduced" - routine introduction
                    if desc_str == "Received and Introduced" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Referred to Committee on" - routine referral
                    if desc_str.starts_with("Referred to Committee on") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Hearing:" - routine hearing scheduling
                    if desc_str.starts_with("Hearing:") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Committee of the Whole - Now working on" - routine status
                    if desc_str == "Committee of the Whole - Now working on" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Referred to Committee of the Whole" - routine referral
                    if desc_str == "Referred to Committee of the Whole" {
                        return FilterResult::FilterOut;
                    }
                }
            }
        }
    }

    FilterResult::Keep
}
