// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// CONTEXT/ENVIRONMENT SETUP: See govbot/README.md
//
// TO UPDATE THIS FILTER FOR ms-legislation (Mississippi):
// 1. First, gather real data by running this command:
//    `just govbot logs --repos=ms --limit=100`
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
// 5. Test your changes: `just govbot logs --repos=ms --limit=100 --filter=default`
//
// Current filter removes: routine referrals and status updates
// ======================================

// Filter for ms-legislation (Mississippi)
// Filters out routine referrals and status updates

use crate::filter::FilterResult;
use serde_json::Value;

pub fn should_keep(entry: &Value) -> FilterResult {
    if let Some(log) = entry.get("log") {
        if let Some(action) = log.get("action") {
            // Filter out "referral-committee" classification
            if let Some(classification) = action.get("classification") {
                if let Some(class_array) = classification.as_array() {
                    for class in class_array {
                        if let Some(class_str) = class.as_str() {
                            if class_str == "referral-committee" {
                                return FilterResult::FilterOut;
                            }
                        }
                    }
                }
            }

            // Filter out routine descriptions
            if let Some(description) = action.get("description") {
                if let Some(desc_str) = description.as_str() {
                    // Filter out "Referred To" - routine referral
                    if desc_str.starts_with("Referred To") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Enrolled Bill Signed" - routine status
                    if desc_str == "Enrolled Bill Signed" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Immediate Release" - routine status
                    if desc_str == "Immediate Release" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Motion to Reconsider Tabled" - routine status
                    if desc_str == "Motion to Reconsider Tabled" {
                        return FilterResult::FilterOut;
                    }
                }
            }
        }
    }

    FilterResult::Keep
}
