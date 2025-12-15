// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// CONTEXT/ENVIRONMENT SETUP: See govbot/README.md
//
// TO UPDATE THIS FILTER FOR il-legislation (Illinois):
// 1. First, gather real data by running this command:
//    `just govbot logs --repos=il --limit=100`
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
// 5. Test your changes: `just govbot logs --repos=il --limit=100 --filter=default`
//
// Current filter removes: routine co-sponsor additions, Rules Committee referrals, and filings
// ======================================

// Filter for il-legislation (Illinois)
// Filters out routine co-sponsor additions, Rules Committee referrals, and filings

use crate::filter::FilterResult;
use serde_json::Value;

pub fn should_keep(entry: &Value) -> FilterResult {
    if let Some(log) = entry.get("log") {
        if let Some(action) = log.get("action") {
            // Filter out "filing" classification
            if let Some(classification) = action.get("classification") {
                if let Some(class_array) = classification.as_array() {
                    for class in class_array {
                        if let Some(class_str) = class.as_str() {
                            if class_str == "filing" {
                                return FilterResult::FilterOut;
                            }
                        }
                    }
                }
            }

            // Filter out routine descriptions
            if let Some(description) = action.get("description") {
                if let Some(desc_str) = description.as_str() {
                    // Filter out "Added Co-Sponsor" - routine co-sponsor additions
                    if desc_str.starts_with("Added Co-Sponsor") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Added Alternate Co-Sponsor" - routine co-sponsor additions
                    if desc_str.starts_with("Added Alternate Co-Sponsor") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Referred to Rules Committee" - routine referral
                    if desc_str == "Referred to Rules Committee" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Filed with Secretary by" - routine filing
                    if desc_str.starts_with("Filed with Secretary by") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Filed with the Clerk by" - routine filing
                    if desc_str.starts_with("Filed with the Clerk by") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Referred to Assignments" - routine referral
                    if desc_str == "Referred to Assignments" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Rule 2-10 Committee Deadline Established" - routine scheduling
                    if desc_str.starts_with("Rule 2-10") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Sponsor Removed" - routine status update
                    if desc_str.starts_with("Sponsor Removed") {
                        return FilterResult::FilterOut;
                    }
                }
            }
        }
    }

    FilterResult::Keep
}
