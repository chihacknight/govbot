// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// CONTEXT/ENVIRONMENT SETUP: See govbot/README.md
//
// TO UPDATE THIS FILTER FOR ca-legislation (California):
// 1. First, gather real data by running this command:
//    `just govbot logs --repos=ca --limit=100`
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
// 5. Test your changes: `just govbot logs --repos=ca --limit=100 --filter=default`
//
// Current filter removes: routine committee referrals, introductions, and routine reading actions
// ======================================

// Filter for ca-legislation (California)
// Filters out routine committee referrals, introductions, and routine reading actions

use crate::filter::FilterResult;
use serde_json::Value;

pub fn should_keep(entry: &Value) -> FilterResult {
    if let Some(log) = entry.get("log") {
        if let Some(action) = log.get("action") {
            // Filter out "referral-committee" classification - very routine
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

            if let Some(description) = action.get("description") {
                if let Some(desc_str) = description.as_str() {
                    // Filter out "Referred to Com. on..." - very routine
                    if desc_str.starts_with("Referred to Com. on") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out simple "Introduced." - routine
                    if desc_str == "Introduced." {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Read second time. Ordered to third reading." - routine
                    if desc_str == "Read second time. Ordered to third reading." {
                        return FilterResult::FilterOut;
                    }
                    // Filter out routine scheduling like "Set for hearing..."
                    if desc_str.starts_with("Set for hearing")
                        || desc_str.starts_with("June ")
                            && desc_str.contains("set for first hearing")
                    {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "From printer. May be heard in committee..." - routine
                    if desc_str.starts_with("From printer. May be heard in committee") {
                        return FilterResult::FilterOut;
                    }
                }
            }
        }
    }

    FilterResult::Keep
}
