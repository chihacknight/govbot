// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// CONTEXT/ENVIRONMENT SETUP: See govbot/README.md
//
// TO UPDATE THIS FILTER FOR wi-legislation (Wisconsin):
// 1. First, gather real data by running this command:
//    `just govbot logs --repos=wi --limit=100`
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
// 5. Test your changes: `just govbot logs --repos=wi --limit=100 --filter=default`
//
// Current filter removes: routine introductions, referrals, and status updates
// ======================================

// Filter for wi-legislation (Wisconsin)
// Filters out routine introductions, referrals, and status updates

use crate::filter::FilterResult;
use serde_json::Value;

pub fn should_keep(entry: &Value) -> FilterResult {
    if let Some(log) = entry.get("log") {
        if let Some(action) = log.get("action") {
            // Filter out "introduction", "reading-1", and "referral-committee" classifications
            if let Some(classification) = action.get("classification") {
                if let Some(class_array) = classification.as_array() {
                    for class in class_array {
                        if let Some(class_str) = class.as_str() {
                            if class_str == "introduction" || class_str == "reading-1" || class_str == "referral-committee" {
                                return FilterResult::FilterOut;
                            }
                        }
                    }
                }
            }

            // Filter out routine descriptions
            if let Some(description) = action.get("description") {
                if let Some(desc_str) = description.as_str() {
                    // Filter out "Read first time and referred to" - routine introduction + referral
                    if desc_str.starts_with("Read first time and referred to") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Representative...added as a coauthor" - routine authorship
                    if desc_str.contains("added as a coauthor") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Representative...added as a cosponsor" - routine sponsorship
                    if desc_str.contains("added as a cosponsor") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Assembly Amendment...offered by" - routine amendment
                    if desc_str.starts_with("Assembly Amendment") && desc_str.contains("offered by") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Senate Amendment...offered by" - routine amendment
                    if desc_str.starts_with("Senate Amendment") && desc_str.contains("offered by") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Received from Assembly" - routine receipt
                    if desc_str == "Received from Assembly" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Received from Senate" - routine receipt
                    if desc_str == "Received from Senate" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Public hearing held" - routine status
                    if desc_str == "Public hearing held" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Executive action taken" - routine status
                    if desc_str == "Executive action taken" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Fiscal estimate received" - routine status
                    if desc_str == "Fiscal estimate received" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Placed on calendar" - routine calendar scheduling
                    if desc_str.starts_with("Placed on calendar") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Withdrawn from committee on Rules and referred to calendar" - routine withdrawal
                    if desc_str.starts_with("Withdrawn from committee on Rules and referred to calendar") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Ordered immediately messaged" - routine status
                    if desc_str == "Ordered immediately messaged" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Rules suspended" - routine status
                    if desc_str == "Rules suspended" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Read a second time" - routine reading
                    if desc_str == "Read a second time" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Ordered to a third reading" - routine reading
                    if desc_str == "Ordered to a third reading" {
                        return FilterResult::FilterOut;
                    }
                }
            }
        }
    }

    FilterResult::Keep
}
