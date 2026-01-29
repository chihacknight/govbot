// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// CONTEXT/ENVIRONMENT SETUP: See govbot/README.md
//
// TO UPDATE THIS FILTER FOR ut-legislation (Utah):
// 1. First, gather real data by running this command:
//    `just govbot logs --repos=ut --limit=100`
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
// 5. Test your changes: `just govbot logs --repos=ut --limit=100 --filter=default`
//
// Current filter removes: routine readings, status updates, and transfers
// ======================================

// Filter for ut-legislation (Utah)
// Filters out routine readings, status updates, and transfers

use crate::filter::FilterResult;
use serde_json::Value;

pub fn should_keep(entry: &Value) -> FilterResult {
    if let Some(log) = entry.get("log") {
        if let Some(action) = log.get("action") {
            // Filter out routine descriptions
            if let Some(description) = action.get("description") {
                if let Some(desc_str) = description.as_str() {
                    // Filter out "House/ 1st reading (Introduced)" - routine first reading
                    if desc_str == "House/ 1st reading (Introduced)" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Senate/ 1st reading (Introduced)" - routine first reading
                    if desc_str == "Senate/ 1st reading (Introduced)" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "House/ 2nd reading" - routine second reading
                    if desc_str == "House/ 2nd reading" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Senate/ 2nd & 3rd readings/ suspension" - routine readings
                    if desc_str.starts_with("Senate/ 2nd & 3rd readings/ suspension") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "House/ passed 2nd & 3rd readings/ suspension" - routine readings
                    if desc_str.starts_with("House/ passed 2nd & 3rd readings/ suspension") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Senate/ to House" - routine transfer
                    if desc_str == "Senate/ to House" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "House/ to Senate" - routine transfer
                    if desc_str == "House/ to Senate" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "House/ received from Senate" - routine receipt
                    if desc_str == "House/ received from Senate" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Senate/ received from House" - routine receipt
                    if desc_str == "Senate/ received from House" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "House/ Rules to 3rd Reading Calendar" - routine calendar
                    if desc_str == "House/ Rules to 3rd Reading Calendar" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "House/ enrolled bill to Printing" - routine status
                    if desc_str == "House/ enrolled bill to Printing" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Senate/ enrolled bill to Printing" - routine status
                    if desc_str == "Senate/ enrolled bill to Printing" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Senate/ received bill from Legislative Printing" - routine receipt
                    if desc_str == "Senate/ received bill from Legislative Printing" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Bill Numbered but not Distributed" - routine status
                    if desc_str == "Bill Numbered but not Distributed" {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Numbered Bill Publicly Distributed" - routine status
                    if desc_str == "Numbered Bill Publicly Distributed" {
                        return FilterResult::FilterOut;
                    }
                }
            }
        }
    }

    FilterResult::Keep
}
