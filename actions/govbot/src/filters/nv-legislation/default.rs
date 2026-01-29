// LLM PROMPT FOR UPDATING THIS FILTER:
// ======================================
// CONTEXT/ENVIRONMENT SETUP: See govbot/README.md
//
// TO UPDATE THIS FILTER FOR nv-legislation (Nevada):
// 1. First, gather real data by running this command:
//    `just govbot logs --repos=nv --limit=100`
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
// 5. Test your changes: `just govbot logs --repos=nv --limit=100 --filter=default`
//
// Current filter removes: routine prefiling, referrals, and status updates
// ======================================

// Filter for nv-legislation (Nevada)
// Filters out routine prefiling, referrals, and status updates

use crate::filter::FilterResult;
use serde_json::Value;

pub fn should_keep(entry: &Value) -> FilterResult {
    if let Some(log) = entry.get("log") {
        if let Some(action) = log.get("action") {
            // Filter out routine descriptions
            if let Some(description) = action.get("description") {
                if let Some(desc_str) = description.as_str() {
                    // Filter out "Prefiled.\rReferred to Committee" - routine prefiling + referral
                    if desc_str.starts_with("Prefiled.")
                        && desc_str.contains("Referred to Committee")
                    {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Taken from General File. Placed on General File" - routine scheduling
                    if desc_str.contains("Taken from General File")
                        && desc_str.contains("Placed on General File")
                    {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "From committee: Do pass" - routine committee report
                    if desc_str.starts_with("From committee: Do pass") {
                        return FilterResult::FilterOut;
                    }
                    // Filter out "Placed on Second Reading File" - routine reading
                    if desc_str.contains("Placed on Second Reading File") {
                        return FilterResult::FilterOut;
                    }
                }
            }
        }
    }

    FilterResult::Keep
}
