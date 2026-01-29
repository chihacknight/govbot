// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// CONTEXT/ENVIRONMENT SETUP: See govbot/README.md
//
// TO UPDATE THIS FILTER FOR ok-legislation (Oklahoma):
// 1. First, gather real data by running this command:
//    `just govbot logs --repos=ok --limit=100`
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
// 5. Test your changes: `just govbot logs --repos=ok --limit=100 --filter=default`
//
// Current filter removes: routine introductions, readings, referrals, and status updates
// ======================================

// Filter for ok-legislation (Oklahoma)
// Filters out routine introductions, readings, referrals, and status updates

use crate::filter::FilterResult;
use serde_json::Value;

pub fn should_keep(entry: &Value) -> FilterResult {
    if let Some(log) = entry.get("log") {
        if let Some(action) = log.get("action") {
            // Filter out "introduction", "reading-1", "reading-2", and "referral-committee" classifications
            if let Some(classification) = action.get("classification") {
                if let Some(class_array) = classification.as_array() {
                    for class in class_array {
                        if let Some(class_str) = class.as_str() {
                            if class_str == "introduction" || class_str == "reading-1" || class_str == "reading-2" || class_str == "referral-committee" {
                                return FilterResult::FilterOut;
                            }
                        }
                    }
                }
            }

            // Filter out routine descriptions
            if let Some(description) = action.get("description") {
                if let Some(desc_str) = description.as_str() {
                    // Filter out "First Reading" - routine first reading
                    if desc_str == "First Reading" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Second Reading referred to" - routine reading + referral
                    if desc_str.starts_with("Second Reading referred to") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Referred to" - routine referral
                    if desc_str.starts_with("Referred to") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Authored by" - routine authorship
                    if desc_str.starts_with("Authored by") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Coauthored by" - routine coauthorship
                    if desc_str.starts_with("Coauthored by") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Referred for enrollment" - routine status
                    if desc_str == "Referred for enrollment" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Referred for engrossment" - routine status
                    if desc_str == "Referred for engrossment" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Withdrawn from Rules Committee" - routine withdrawal
                    if desc_str == "Withdrawn from Rules Committee" {
                        return FilterResult::FilterOut;
                    }
                }
            }
        }
    }

    FilterResult::Keep
}
