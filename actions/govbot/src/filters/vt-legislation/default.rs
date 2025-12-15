// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// CONTEXT/ENVIRONMENT SETUP: See govbot/README.md
//
// TO UPDATE THIS FILTER FOR vt-legislation (Vermont):
// 1. First, gather real data by running this command:
//    `just govbot logs --repos=vt --limit=100`
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
// 5. Test your changes: `just govbot logs --repos=vt --limit=100 --filter=default`
//
// Current filter removes: routine introductions, referrals, and calendar scheduling
// ======================================

// Filter for vt-legislation (Vermont)
// Filters out routine introductions, referrals, and calendar scheduling

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
                    // Filter out "Read 1st time & referred to" - routine introduction + referral
                    if desc_str.starts_with("Read 1st time & referred to") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Read first time and referred to" - routine introduction + referral
                    if desc_str.starts_with("Read first time and referred to") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Referred to Committee on" - routine referral
                    if desc_str.starts_with("Referred to Committee on") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Referred to Committee on Appropriations per Senate Rule" - routine referral
                    if desc_str.starts_with("Referred to Committee on Appropriations per Senate Rule") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Referred to Committee on Rules per" - routine referral
                    if desc_str.starts_with("Referred to Committee on Rules per") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Entered on Notice Calendar" - routine calendar
                    if desc_str == "Entered on Notice Calendar" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "On Consent Calendar" - routine calendar
                    if desc_str == "On Consent Calendar" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Adopted pursuant to Joint Rule 16b" - routine adoption
                    if desc_str == "Adopted pursuant to Joint Rule 16b" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Adopted in concurrence per Joint Rule 16b" - routine adoption
                    if desc_str == "Adopted in concurrence per Joint Rule 16b" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Committee Bill for Second Reading" - routine status
                    if desc_str == "Committee Bill for Second Reading" {
                        return FilterResult::FilterOut;
                    }
                }
            }
        }
    }

    FilterResult::Keep
}
