// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// CONTEXT/ENVIRONMENT SETUP: See govbot/README.md
//
// TO UPDATE THIS FILTER FOR ne-legislation (Nebraska):
// 1. First, gather real data by running this command:
//    `just govbot logs --repos=ne --limit=100`
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
// 5. Test your changes: `just govbot logs --repos=ne --limit=100 --filter=default`
//
// Current filter removes: routine referrals, hearing notifications, and filing actions
// ======================================

// Filter for ne-legislation (Nebraska)
// Filters out routine referrals, hearing notifications, and filing actions

use crate::filter::FilterResult;
use serde_json::Value;

pub fn should_keep(entry: &Value) -> FilterResult {
    if let Some(log) = entry.get("log") {
        if let Some(action) = log.get("action") {
            // Filter out "filing" and "referral-committee" classifications
            if let Some(classification) = action.get("classification") {
                if let Some(class_array) = classification.as_array() {
                    for class in class_array {
                        if let Some(class_str) = class.as_str() {
                            if class_str == "filing" || class_str == "referral-committee" {
                                return FilterResult::FilterOut;
                            }
                        }
                    }
                }
            }

            // Filter out routine descriptions
            if let Some(description) = action.get("description") {
                if let Some(desc_str) = description.as_str() {
                    // Filter out "Referred to" - routine referral
                    if desc_str.starts_with("Referred to") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Notice of hearing for" - routine hearing scheduling
                    if desc_str.starts_with("Notice of hearing for") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Placed on Select File" - routine filing
                    if desc_str == "Placed on Select File" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Motion to suspend rules to indefinitely postpone filed" - routine filing
                    if desc_str == "Motion to suspend rules to indefinitely postpone filed" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Date of introduction" - routine introduction
                    if desc_str == "Date of introduction" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Advanced to Enrollment and Review" - routine status
                    if desc_str.starts_with("Advanced to Enrollment and Review") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Placed on General File with" - routine filing
                    if desc_str.starts_with("Placed on General File with") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out amendment pending notifications
                    if desc_str.contains("pending") && desc_str.contains("FA") {
                        return FilterResult::FilterOut;
                    }
                }
            }
        }
    }

    FilterResult::Keep
}
