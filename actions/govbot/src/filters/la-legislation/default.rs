// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// CONTEXT/ENVIRONMENT SETUP: See govbot/README.md
//
// TO UPDATE THIS FILTER FOR la-legislation (Louisiana):
// 1. First, gather real data by running this command:
//    `just govbot logs --repos=la --limit=100`
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
// 5. Test your changes: `just govbot logs --repos=la --limit=100 --filter=default`
//
// Current filter removes: routine prefiling, referrals, and reading actions
// ======================================

// Filter for la-legislation (Louisiana)
// Filters out routine prefiling, referrals, and reading actions

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
                    // Filter out "Prefiled and under the rules provisionally referred to" - routine prefiling
                    if desc_str
                        .starts_with("Prefiled and under the rules provisionally referred to")
                    {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Read by title, rules suspended, referred to" - routine referral
                    if desc_str.starts_with("Read by title, rules suspended, referred to") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Read by title, ordered engrossed, passed to 3rd reading" - routine reading
                    if desc_str == "Read by title, ordered engrossed, passed to 3rd reading." {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Read by title, rules suspended, passed to 3rd reading" - routine reading
                    if desc_str == "Read by title, rules suspended, passed to 3rd reading." {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Read by title, passed to 3rd reading" - routine reading
                    if desc_str == "Read by title, passed to 3rd reading." {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Scheduled for floor debate on" - routine scheduling
                    if desc_str.starts_with("Scheduled for floor debate on") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Reported without Legislative Bureau amendments" - routine status
                    if desc_str == "Reported without Legislative Bureau amendments." {
                        return FilterResult::FilterOut;
                    }
                }
            }
        }
    }

    FilterResult::Keep
}
