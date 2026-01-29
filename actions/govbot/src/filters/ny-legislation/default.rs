// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// CONTEXT/ENVIRONMENT SETUP: See govbot/README.md
//
// TO UPDATE THIS FILTER FOR ny-legislation (New York):
// 1. First, gather real data by running this command:
//    `just govbot logs --repos=ny --limit=100`
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
// 5. Test your changes: `just govbot logs --repos=ny --limit=100 --filter=default`
//
// Current filter removes: routine referrals, introductions, and status updates
// ======================================

// Filter for ny-legislation (New York)
// Filters out routine referrals, introductions, and status updates

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
                    // Filter out "REFERRED TO" - routine referral
                    if desc_str.starts_with("REFERRED TO") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "REPORTED REFERRED TO RULES" - routine referral
                    if desc_str == "REPORTED REFERRED TO RULES" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "INTRODUCED" - routine introduction
                    if desc_str == "INTRODUCED" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "DELIVERED TO ASSEMBLY" - routine status
                    if desc_str == "DELIVERED TO ASSEMBLY" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "AMEND AND RECOMMIT TO" - routine amendment + recommit
                    if desc_str.starts_with("AMEND AND RECOMMIT TO") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "1ST REPORT CAL" - routine calendar status
                    if desc_str.starts_with("1ST REPORT CAL") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "REPORTED TO CALENDAR FOR CONSIDERATION" - routine status
                    if desc_str == "REPORTED TO CALENDAR FOR CONSIDERATION" {
                        return FilterResult::FilterOut;
                    }
                }
            }
        }
    }

    FilterResult::Keep
}
