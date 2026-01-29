// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// CONTEXT/ENVIRONMENT SETUP: See govbot/README.md
//
// TO UPDATE THIS FILTER FOR hi-legislation (Hawaii):
// 1. First, gather real data by running this command:
//    `just govbot logs --repos=hi --limit=100`
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
// 5. Test your changes: `just govbot logs --repos=hi --limit=100 --filter=default`
//
// Current filter removes: routine introductions, first readings, and committee referral patterns
// ======================================

// Filter for hi-legislation (Hawaii)
// Filters out routine introductions, first readings, and committee referral patterns

use crate::filter::FilterResult;
use serde_json::Value;

pub fn should_keep(entry: &Value) -> FilterResult {
    if let Some(log) = entry.get("log") {
        if let Some(action) = log.get("action") {
            // Filter out "introduction" and "reading-1" classifications
            if let Some(classification) = action.get("classification") {
                if let Some(class_array) = classification.as_array() {
                    for class in class_array {
                        if let Some(class_str) = class.as_str() {
                            if class_str == "introduction" || class_str == "reading-1" {
                                return FilterResult::FilterOut;
                            }
                        }
                    }
                }
            }

            // Filter out routine descriptions
            if let Some(description) = action.get("description") {
                if let Some(desc_str) = description.as_str() {
                    // Filter out "Introduced and Pass First Reading" - routine introduction
                    if desc_str == "Introduced and Pass First Reading." {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Introduced and passed First Reading" - routine introduction
                    if desc_str == "Introduced and passed First Reading." {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Report filed." - routine status update
                    if desc_str == "Report filed." {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Referred to..." - routine committee referral
                    if desc_str.starts_with("Referred to") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "The committee(s) on...has scheduled a public hearing" - routine scheduling
                    if desc_str.contains("has scheduled a public hearing") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Notice of hearing" - routine scheduling
                    if desc_str.contains("Notice of") && desc_str.contains("hearing") {
                        return FilterResult::FilterOut;
                    }
                }
            }
        }
    }

    FilterResult::Keep
}
