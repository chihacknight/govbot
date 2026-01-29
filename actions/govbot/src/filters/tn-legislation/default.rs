// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// CONTEXT/ENVIRONMENT SETUP: See govbot/README.md
//
// TO UPDATE THIS FILTER FOR tn-legislation (Tennessee):
// 1. First, gather real data by running this command:
//    `just govbot logs --repos=tn --limit=100`
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
// 5. Test your changes: `just govbot logs --repos=tn --limit=100 --filter=default`
//
// Current filter removes: routine filings, introductions, referrals, and calendar scheduling
// ======================================

// Filter for tn-legislation (Tennessee)
// Filters out routine filings, introductions, referrals, and calendar scheduling

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
                    // Filter out "Introduced, Passed on First Consideration" - routine introduction
                    if desc_str == "Introduced, Passed on First Consideration" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Placed on Senate Regular Calendar" - routine calendar scheduling
                    if desc_str.starts_with("Placed on Senate Regular Calendar") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Placed on Senate Judiciary Committee calendar" - routine calendar scheduling
                    if desc_str.starts_with("Placed on Senate Judiciary Committee calendar") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Placed on cal. Calendar & Rules Committee" - routine calendar scheduling
                    if desc_str.starts_with("Placed on cal. Calendar & Rules Committee") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Rec. for pass" - routine committee recommendation
                    if desc_str.starts_with("Rec. for pass") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Recommended for passage" - routine committee recommendation
                    if desc_str.starts_with("Recommended for passage") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Sponsor(s) Added" - routine sponsorship
                    if desc_str == "Sponsor(s) Added." {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Engrossed; ready for transmission" - routine status
                    if desc_str.starts_with("Engrossed; ready for transmission") {
                        return FilterResult::FilterOut;
                    }
                }
            }
        }
    }

    FilterResult::Keep
}
