// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// CONTEXT/ENVIRONMENT SETUP: See govbot/README.md
//
// TO UPDATE THIS FILTER FOR ma-legislation (Massachusetts):
// 1. First, gather real data by running this command:
//    `just govbot logs --repos=ma --limit=100`
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
// 5. Test your changes: `just govbot logs --repos=ma --limit=100 --filter=default`
//
// Current filter removes: routine hearing scheduling, concurrences, and referrals
// ======================================

// Filter for ma-legislation (Massachusetts)
// Filters out routine hearing scheduling, concurrences, and referrals

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
                    // Filter out "Hearing scheduled for" - routine hearing scheduling
                    if desc_str.starts_with("Hearing scheduled for") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Hearing rescheduled to" - routine hearing rescheduling
                    if desc_str.starts_with("Hearing rescheduled to") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Senate concurred" - routine concurrence
                    if desc_str == "Senate concurred" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "House concurred" - routine concurrence
                    if desc_str == "House concurred" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Referred to the committee on" - routine referral
                    if desc_str.starts_with("Referred to the committee on") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Reporting date extended to" - routine scheduling
                    if desc_str.starts_with("Reporting date extended to") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Accompanied a" - routine status update
                    if desc_str.starts_with("Accompanied a") {
                        return FilterResult::FilterOut;
                    }
                }
            }
        }
    }

    FilterResult::Keep
}
