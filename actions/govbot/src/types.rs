use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// A complete log entry with wrapped content and metadata
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LogEntry {
    /// The log content (either full JSON or vote event result)
    pub log: LogContent,
    /// The relative filename path
    pub filename: String,
}

/// Log content can be either a full JSON value or a vote event result
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum LogContent {
    /// Full JSON content (for non-vote-event files)
    Full(serde_json::Value),
    /// Vote event result (for vote_event files)
    VoteEvent { result: VoteEventResult },
}

/// Vote event result type
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum VoteEventResult {
    Pass,
    Fail,
    Unknown,
}

impl From<&str> for VoteEventResult {
    fn from(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "pass" => VoteEventResult::Pass,
            "fail" => VoteEventResult::Fail,
            _ => VoteEventResult::Unknown,
        }
    }
}

/// Source information
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Source {
    pub url: String,
    pub note: String,
}

/// Complete metadata structure from metadata.json
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Metadata {
    pub title: Option<String>,
    pub description: Option<String>,
    pub sources: Option<Vec<Source>>,
    // Note: sponsors field removed - use the new join system instead
}

/// Internal representation of a file with its timestamp
#[derive(Debug, Clone)]
pub struct FileWithTimestamp {
    pub path: PathBuf,
    pub timestamp: Option<String>,
    pub relative_path: String,
}
