// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// CONTEXT/ENVIRONMENT SETUP: See govbot/README.md
//
// TO UPDATE THIS FILTER FOR ia-legislation (Iowa):
// 1. First, gather real data by running this command:
//    `just govbot logs --repos=ia --limit=100`
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
// 5. Test your changes: `just govbot logs --repos=ia --limit=100 --filter=default`
//
// Current filter removes: routine introductions, referrals, and subcommittee notifications
// ======================================

// Filter for ia-legislation (Iowa)
// Filters out routine introductions, referrals, and subcommittee notifications

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
                    // Filter out "Introduced, referred to" - routine referral
                    if desc_str.starts_with("Introduced, referred to") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Introduced, placed on calendar" - routine introduction
                    if desc_str == "Introduced, placed on calendar." {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Subcommittee:" - routine subcommittee assignment
                    if desc_str.starts_with("Subcommittee:") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Subcommittee Meeting:" - routine scheduling
                    if desc_str.starts_with("Subcommittee Meeting:") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Read first time, passed on file" - routine reading
                    if desc_str == "Read first time, passed on file." {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Subcommittee recommends passage" - routine subcommittee action
                    if desc_str == "Subcommittee recommends passage." {
                        return FilterResult::FilterOut;
                    }
                }
            }
        }
    }

    FilterResult::Keep
}
