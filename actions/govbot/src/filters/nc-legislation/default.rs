// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// CONTEXT/ENVIRONMENT SETUP: See govbot/README.md
//
// TO UPDATE THIS FILTER FOR nc-legislation (North Carolina):
// 1. First, gather real data by running this command:
//    `just govbot logs --repos=nc --limit=100`
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
// 5. Test your changes: `just govbot logs --repos=nc --limit=100 --filter=default`
//
// Current filter removes: routine referrals, readings, and status updates
// ======================================

// Filter for nc-legislation (North Carolina)
// Filters out routine referrals, readings, and status updates

use crate::filter::FilterResult;
use serde_json::Value;

pub fn should_keep(entry: &Value) -> FilterResult {
    if let Some(log) = entry.get("log") {
        if let Some(action) = log.get("action") {
            // Filter out "referral-committee" and "reading-1" classifications
            if let Some(classification) = action.get("classification") {
                if let Some(class_array) = classification.as_array() {
                    for class in class_array {
                        if let Some(class_str) = class.as_str() {
                            if class_str == "referral-committee" || class_str == "reading-1" {
                                return FilterResult::FilterOut;
                            }
                        }
                    }
                }
            }

            // Filter out routine descriptions
            if let Some(description) = action.get("description") {
                if let Some(desc_str) = description.as_str() {
                    // Filter out "Ref to the Com on" - routine referral
                    if desc_str.starts_with("Ref to the Com on") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Re-ref to" - routine re-referral
                    if desc_str.starts_with("Re-ref to") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Re-ref Com On" - routine re-referral
                    if desc_str.starts_with("Re-ref Com On") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Ref To Com On" - routine referral
                    if desc_str.starts_with("Ref To Com On") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Passed 1st Reading" - routine first reading
                    if desc_str == "Passed 1st Reading" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Passed 2nd Reading" - routine second reading
                    if desc_str == "Passed 2nd Reading" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Filed" - routine filing
                    if desc_str == "Filed" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Withdrawn From Com" - routine withdrawal
                    if desc_str == "Withdrawn From Com" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Ordered Enrolled" - routine status
                    if desc_str == "Ordered Enrolled" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Reptd Fav" - routine committee report
                    if desc_str == "Reptd Fav" {
                        return FilterResult::FilterOut;
                    }
                }
            }
        }
    }

    FilterResult::Keep
}
