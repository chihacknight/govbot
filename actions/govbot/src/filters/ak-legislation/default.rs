// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// CONTEXT/ENVIRONMENT SETUP: See govbot/README.md
//
// TO UPDATE THIS FILTER FOR ak-legislation (Alaska):
// 1. First, gather real data by running this command:
//    `just govbot logs --repos=ak --limit=100`
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
// 5. Test your changes: `just govbot logs --repos=ak --limit=100 --filter=default`
//
// Current filter removes: routine committee abbreviations, minutes, hearings, referrals, and filing actions
// ======================================

// Filter for ak-legislation (Alaska)
// Filters out routine committee abbreviations, minutes, hearings, referrals, and filing actions

use crate::filter::FilterResult;
use serde_json::Value;

pub fn should_keep(entry: &Value) -> FilterResult {
    if let Some(log) = entry.get("log") {
        if let Some(action) = log.get("action") {
            // Filter out "filing" classification - routine
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

            if let Some(description) = action.get("description") {
                if let Some(desc_str) = description.as_str() {
                    // Filter out routine committee abbreviations like "(H) EDC, FIN", "(S) HSS, L&C"
                    if desc_str.starts_with("(H) ") && desc_str.len() < 20 && desc_str.contains(",")
                    {
                        return FilterResult::FilterOut;
                    }
                    if desc_str.starts_with("(S) ") && desc_str.len() < 20 && desc_str.contains(",")
                    {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Minutes" - routine
                    if desc_str.contains("Minutes") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Heard & Held" - routine
                    if desc_str.contains("Heard & Held") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "READ THE FIRST TIME - REFERRALS" - routine
                    if desc_str == "READ THE FIRST TIME - REFERRALS" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out fiscal notes - routine
                    if desc_str.starts_with("FN") && desc_str.contains(": ZERO") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "NR:" (no recommendation) - routine
                    if desc_str.starts_with("NR:") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out prefiling
                    if desc_str.contains("Prefile released") {
                        return FilterResult::FilterOut;
                    }
                }
            }
        }
    }

    FilterResult::Keep
}
