use anyhow::{Context, Result};
use serde_json::Value;
use std::collections::HashSet;
use std::fs;
use std::path::Path;

/// Load and parse govbot.yml configuration
pub fn load_config(config_path: &Path) -> Result<Value> {
    let contents = fs::read_to_string(config_path)
        .with_context(|| format!("Failed to read config file: {}", config_path.display()))?;
    serde_yaml::from_str(&contents)
        .with_context(|| format!("Failed to parse YAML: {}", config_path.display()))
}

/// Get repos list from config, handling 'all' special case
pub fn get_repos_from_config(config: &Value) -> Vec<String> {
    if let Some(repos) = config.get("repos") {
        if let Some(arr) = repos.as_array() {
            return arr
                .iter()
                .filter_map(|v| v.as_str().map(|s| s.to_string()))
                .collect();
        } else if let Some(s) = repos.as_str() {
            return vec![s.to_string()];
        }
    }
    vec!["all".to_string()]
}

/// Filter entries by tags
/// Only includes entries that have tags (excludes untagged entries)
/// If tag_names is empty, includes any entry that has tags
/// If tag_names are specified, only includes entries that have at least one matching tag
pub fn filter_by_tags(entry: &Value, tag_names: &[String]) -> bool {
    // Get tags from entry - if no tags field exists, exclude it
    let tags = match entry.get("tags").and_then(|t| t.as_object()) {
        Some(tags) => tags,
        None => {
            // Entry has no tags field - exclude it (only include tagged entries)
            return false;
        }
    };

    // If tags object is empty, exclude it (only include entries with actual tags)
    if tags.is_empty() {
        return false;
    }

    // If no specific tags requested, include any entry that has tags
    if tag_names.is_empty() {
        return true;
    }

    // Check if any specified tag matches
    for tag_name in tag_names {
        if tags.contains_key(tag_name) {
            return true;
        }
    }

    // Entry has tags but none match the specified tags - exclude it
    false
}

/// Extract a stable GUID for a log entry.
/// Pure data-shaping helper (no RSS dependency): prefers the source log path,
/// falling back to `timestamp + bill_id`. Lives here so entry identity stays
/// available to all consumers even when the `rss` feature is disabled.
pub fn extract_guid(entry: &Value) -> String {
    // Use source log path as GUID if available
    if let Some(sources) = entry.get("sources").and_then(|s| s.as_object()) {
        if let Some(log_source) = sources.get("log").and_then(|s| s.as_str()) {
            return log_source.to_string();
        }
    }

    // Fall back to timestamp + bill_id
    let timestamp = entry
        .get("timestamp")
        .and_then(|t| t.as_str())
        .unwrap_or("");
    let bill_id = entry
        .get("id")
        .or_else(|| entry.get("log").and_then(|l| l.get("bill_id")))
        .and_then(|id| id.as_str())
        .unwrap_or("");

    format!("{}_{}", timestamp, bill_id)
}

/// Deduplicate entries by GUID
pub fn deduplicate_entries(entries: Vec<Value>) -> Vec<Value> {
    let mut seen = HashSet::new();
    let mut result = Vec::new();

    for entry in entries {
        let guid = extract_guid(&entry);
        if !seen.contains(&guid) {
            seen.insert(guid);
            result.push(entry);
        }
    }

    result
}

/// Sort entries by timestamp (newest first)
pub fn sort_by_timestamp(mut entries: Vec<Value>) -> Vec<Value> {
    entries.sort_by(|a, b| {
        let ts_a = a.get("timestamp").and_then(|t| t.as_str()).unwrap_or("");
        let ts_b = b.get("timestamp").and_then(|t| t.as_str()).unwrap_or("");
        ts_b.cmp(ts_a) // Reverse order (newest first)
    });
    entries
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    // These data-shaping helpers must work with AND without the `rss` feature
    // (issue #26: entry identity/filtering/sorting belong to core, feed
    // rendering belongs to the gated `govbot::rss` module).

    #[test]
    fn extract_guid_prefers_source_log_path() {
        let entry = json!({
            "sources": {"log": "wy-legislation/country:us/state:wy/logs/x.json"},
            "timestamp": "20250101T000000Z",
            "id": "SF0001"
        });
        assert_eq!(
            extract_guid(&entry),
            "wy-legislation/country:us/state:wy/logs/x.json"
        );
    }

    #[test]
    fn extract_guid_falls_back_to_timestamp_and_bill_id() {
        let entry = json!({"timestamp": "20250101T000000Z", "id": "SF0001"});
        assert_eq!(extract_guid(&entry), "20250101T000000Z_SF0001");

        let nested = json!({
            "timestamp": "20250101T000000Z",
            "log": {"bill_id": "HB0002"}
        });
        assert_eq!(extract_guid(&nested), "20250101T000000Z_HB0002");

        let empty = json!({});
        assert_eq!(extract_guid(&empty), "_");
    }

    #[test]
    fn deduplicate_entries_keeps_first_occurrence() {
        let a = json!({"timestamp": "20250102T000000Z", "id": "SF0001"});
        let dup = json!({"timestamp": "20250102T000000Z", "id": "SF0001"});
        let b = json!({"timestamp": "20250101T000000Z", "id": "SF0002"});
        let out = deduplicate_entries(vec![a.clone(), dup, b.clone()]);
        assert_eq!(out, vec![a, b]);
    }

    #[test]
    fn sort_by_timestamp_orders_newest_first() {
        let old = json!({"timestamp": "20250101T000000Z"});
        let new = json!({"timestamp": "20250102T000000Z"});
        let out = sort_by_timestamp(vec![old.clone(), new.clone()]);
        assert_eq!(out, vec![new, old]);
    }

    #[test]
    fn filter_by_tags_keeps_only_matching_tagged_entries() {
        let matching = json!({"tags": {"budget": {}}});
        let other_tag = json!({"tags": {"lgbtq": {}}});
        let untagged = json!({"id": "SF0001"});
        assert!(filter_by_tags(&matching, &["budget".to_string()]));
        assert!(!filter_by_tags(&other_tag, &["budget".to_string()]));
        assert!(!filter_by_tags(&untagged, &["budget".to_string()]));
        // Empty tag filter includes any tagged entry, still excludes untagged.
        assert!(filter_by_tags(&matching, &[]));
        assert!(!filter_by_tags(&untagged, &[]));
    }
}
