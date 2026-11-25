//! Reading a bill's activity logs, in either layout.
//!
//! Current layout (written by `actions/format/utils/log_jsonl.py`):
//!
//! ```text
//! sessions/{session}/bills/{bill_id}/action_logs.jsonl      # one action per line, append-only; a
//!                                                           #   rewording repeats the action's id
//! sessions/{session}/bills/{bill_id}/vote_event_logs.jsonl  # one roll call per line; a correction
//!                                                           #   repeats the vote's id later on
//! ```
//!
//! Readers show the last line per id (the current wording or version); earlier lines
//! are the history. An action keeps its first line's `first_seen`, a vote takes the
//! correction's.
//!
//! ```text
//! ```
//!
//! Each line is `{"id", "first_seen", "chamber", "action" | "vote_event", "bill_id"}`.
//!
//! Old layout, still in repos not yet converted: one file per entry in
//! `bills/{bill_id}/logs/`, named `{YYYYMMDDTHHMMSSZ}_{slug}.json`,
//! `{ts}.classification.{c}.{chamber}.json`, `{ts}.vote_event.pass.{chamber}.json` or
//! `{ts}_vote_event_{result}.json`, plus symlinks to them under `sessions/{session}/logs/`.
//!
//! Every reader gets the same [`LogRecord`] whichever layout a bill is in, carrying the
//! entry in the shape the old files held (`{"action": …, "bill_id": …}` for an action,
//! the bare vote event for a vote), so what `govbot logs` prints doesn't depend on the
//! layout.

use serde_json::Value;
use std::path::{Path, PathBuf};

pub const ACTION_LOG_FILE: &str = "action_logs.jsonl";
pub const VOTE_EVENT_LOG_FILE: &str = "vote_event_logs.jsonl";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LogKind {
    Action,
    VoteEvent,
}

#[derive(Debug, Clone)]
pub struct LogRecord {
    pub kind: LogKind,
    /// The entry as the old per-entry files held it.
    pub value: Value,
    /// The file the entry was read from.
    pub file: PathBuf,
    /// The bill folder (`…/bills/{bill_id}`), where `metadata.json` lives.
    pub bill_dir: PathBuf,
    /// For a `.jsonl` line, the line's `id`; appended to the file path as `#{id}` it
    /// names this entry stably (an RSS guid, a reference someone can grep for).
    pub anchor: Option<String>,
    /// 1-based line number in the `.jsonl` file (citations use `#L{n}`).
    pub line: Option<usize>,
    /// The government's date for the entry as `YYYYMMDDTHHMMSSZ`, in the source's own
    /// clock time like the old filenames.
    pub timestamp: Option<String>,
    /// When Govbot first recorded it (only in the current layout).
    pub first_seen: Option<String>,
}

/// `2025-01-29T02:27:03+00:00` or `2025-03-27` -> `20250129T022703Z` / `20250327T000000Z`.
///
/// Mirrors `format_timestamp` in actions/format: the wall-clock time as written, no
/// conversion to UTC, so both layouts produce the same value for the same entry.
pub fn timestamp_of(date: &str) -> Option<String> {
    use chrono::{DateTime, NaiveDate, NaiveDateTime};
    let naive = DateTime::parse_from_rfc3339(date)
        .map(|dt| dt.naive_local())
        .or_else(|_| NaiveDateTime::parse_from_str(date, "%Y-%m-%dT%H:%M:%S"))
        .or_else(|_| NaiveDate::parse_from_str(date, "%Y-%m-%d").map(|d| d.and_hms_opt(0, 0, 0).unwrap()))
        .ok()?;
    Some(naive.format("%Y%m%dT%H%M%SZ").to_string())
}

/// The `YYYYMMDDTHHMMSSZ` prefix of an old log filename, in either naming form.
fn timestamp_prefix(file_name: &str) -> Option<String> {
    let prefix = file_name.get(..16)?;
    let bytes = prefix.as_bytes();
    let ok = bytes[..8].iter().all(u8::is_ascii_digit)
        && bytes[8] == b'T'
        && bytes[9..15].iter().all(u8::is_ascii_digit)
        && bytes[15] == b'Z';
    ok.then(|| prefix.to_string())
}

fn is_named(path: &Path, name: &str) -> bool {
    path.file_name().and_then(|n| n.to_str()) == Some(name)
}

/// Whether `path` sits directly in a bill folder (`…/bills/{bill_id}/{file}`).
fn in_bill_folder(path: &Path) -> bool {
    path.parent()
        .and_then(Path::parent)
        .is_some_and(|bills| is_named(bills, "bills"))
}

/// Whether an old-layout filename is a vote event, in either naming form.
pub fn is_legacy_vote_file(file_name: &str) -> bool {
    file_name.contains(".vote_event.") || file_name.contains("_vote_event_")
}

/// Every log entry in the file at `path`, or `None` if `path` isn't a bill log file.
///
/// Only real files directly under a bill count: the old `sessions/{s}/logs/` folder
/// only held symlinks to them, and reading it too doubled every entry. Callers should
/// skip symlinks (`std::fs::symlink_metadata`, or jwalk's `file_type()`, which does not
/// follow them); this function refuses the session-level folder by its position.
pub fn read_log_records(path: &Path) -> Option<Vec<LogRecord>> {
    if is_named(path, ACTION_LOG_FILE) && in_bill_folder(path) {
        return Some(read_jsonl(path, LogKind::Action));
    }
    if is_named(path, VOTE_EVENT_LOG_FILE) && in_bill_folder(path) {
        return Some(read_jsonl(path, LogKind::VoteEvent));
    }
    // Old layout: …/bills/{bill_id}/logs/{file}.json
    let logs_dir = path.parent()?;
    let is_legacy = path.extension().and_then(|e| e.to_str()) == Some("json")
        && is_named(logs_dir, "logs")
        && in_bill_folder(logs_dir);
    if !is_legacy {
        return None;
    }
    Some(read_legacy(path).into_iter().collect())
}

fn read_legacy(path: &Path) -> Option<LogRecord> {
    let file_name = path.file_name()?.to_str()?;
    let contents = match std::fs::read_to_string(path) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("Error reading {}: {}", path.display(), e);
            return None;
        }
    };
    let value: Value = match serde_json::from_str(&contents) {
        Ok(v) => v,
        Err(e) => {
            eprintln!("Error parsing JSON from {}: {}", path.display(), e);
            return None;
        }
    };
    let kind = if value.get("action").is_some() || !is_legacy_vote_file(file_name) {
        LogKind::Action
    } else {
        LogKind::VoteEvent
    };
    Some(LogRecord {
        kind,
        value,
        file: path.to_path_buf(),
        bill_dir: path.parent()?.parent()?.to_path_buf(),
        anchor: None,
        line: None,
        timestamp: timestamp_prefix(file_name),
        first_seen: None,
    })
}

fn read_jsonl(path: &Path, kind: LogKind) -> Vec<LogRecord> {
    let contents = match std::fs::read_to_string(path) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("Error reading {}: {}", path.display(), e);
            return Vec::new();
        }
    };
    let Some(bill_dir) = path.parent().map(Path::to_path_buf) else {
        return Vec::new();
    };

    let mut records: Vec<LogRecord> = Vec::new();
    let mut index_of: std::collections::HashMap<String, usize> = std::collections::HashMap::new();
    for (index, raw) in contents.lines().enumerate() {
        if raw.trim().is_empty() {
            continue;
        }
        let line: Value = match serde_json::from_str(raw) {
            Ok(v) => v,
            Err(e) => {
                eprintln!("Error parsing JSON from {} line {}: {}", path.display(), index + 1, e);
                continue;
            }
        };
        let id = line.get("id").and_then(Value::as_str).map(str::to_string);
        let first_seen = line.get("first_seen").and_then(Value::as_str).map(str::to_string);
        let (value, date) = match kind {
            LogKind::Action => {
                let action = line.get("action").cloned().unwrap_or(Value::Null);
                let date = action.get("occurred_at").and_then(Value::as_str).map(str::to_string);
                let mut legacy = serde_json::Map::new();
                legacy.insert("action".into(), action);
                legacy.insert("bill_id".into(), line.get("bill_id").cloned().unwrap_or(Value::Null));
                (Value::Object(legacy), date)
            }
            LogKind::VoteEvent => {
                let vote = line.get("vote_event").cloned().unwrap_or(Value::Null);
                let date = vote.get("start_date").and_then(Value::as_str).map(str::to_string);
                (vote, date)
            }
        };
        let record = LogRecord {
            kind,
            value,
            file: path.to_path_buf(),
            bill_dir: bill_dir.clone(),
            anchor: id.clone(),
            line: Some(index + 1),
            timestamp: date.as_deref().and_then(timestamp_of),
            first_seen,
        };
        // A correction repeats the id of the entry it corrects: keep only the newest
        // version of each entry, in the position the entry first appeared.
        // - A vote correction (result, counts, member votes) is news, so it carries
        //   its own first_seen.
        // - An action correction is the scraper rewording an action it already
        //   published (MT "(H) First Reading" -> "(H) 1st Reading"); that isn't news,
        //   so it keeps the first line's first_seen.
        if let Some(&at) = id.as_ref().and_then(|id| index_of.get(id)) {
            let first_seen = records[at].first_seen.clone();
            records[at] = record;
            if kind == LogKind::Action {
                records[at].first_seen = first_seen;
            }
            continue;
        }
        if let Some(id) = id {
            index_of.insert(id, records.len());
        }
        records.push(record);
    }
    records
}

/// Every log entry for one bill folder, in either layout: the `.jsonl` files if
/// present, else the old `logs/` files (real files only, sorted by name).
pub fn bill_log_records(bill_dir: &Path) -> Vec<LogRecord> {
    let mut out = Vec::new();
    let mut found_jsonl = false;
    for name in [ACTION_LOG_FILE, VOTE_EVENT_LOG_FILE] {
        let path = bill_dir.join(name);
        if path.is_file() {
            found_jsonl = true;
            out.extend(read_log_records(&path).unwrap_or_default());
        }
    }
    if found_jsonl {
        return out;
    }
    let Ok(entries) = std::fs::read_dir(bill_dir.join("logs")) else {
        return out;
    };
    let mut paths: Vec<PathBuf> = entries
        .filter_map(|e| e.ok())
        .filter(|e| e.file_type().is_ok_and(|t| t.is_file()))
        .map(|e| e.path())
        .collect();
    paths.sort();
    for path in paths {
        out.extend(read_log_records(&path).unwrap_or_default());
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn timestamps_match_the_old_filenames() {
        assert_eq!(timestamp_of("2025-01-29T02:27:03+00:00").as_deref(), Some("20250129T022703Z"));
        // Not converted to UTC: the old filenames kept the source's clock time.
        assert_eq!(timestamp_of("2026-03-18T04:00:00-05:00").as_deref(), Some("20260318T040000Z"));
        assert_eq!(timestamp_of("2025-03-27").as_deref(), Some("20250327T000000Z"));
        assert_eq!(timestamp_of("no_date"), None);
        assert_eq!(timestamp_prefix("20250131T030931Z.classification.introduction.lower.json").as_deref(), Some("20250131T030931Z"));
        assert_eq!(timestamp_prefix("20250129T022703Z_bill_number_assigned.json").as_deref(), Some("20250129T022703Z"));
        assert_eq!(timestamp_prefix("None_bill.json"), None);
    }

    fn bill(dir: &Path) -> PathBuf {
        let bill = dir.join("country:us/state:wy/sessions/2025/bills/SF0001");
        std::fs::create_dir_all(&bill).unwrap();
        bill
    }

    #[test]
    fn reads_jsonl_lines_and_keeps_the_newest_vote_version() {
        let tmp = tempfile::tempdir().unwrap();
        let bill = bill(tmp.path());
        std::fs::write(
            bill.join(ACTION_LOG_FILE),
            r#"{"id": "a1", "first_seen": "2026-09-29T10:33:32+00:00", "chamber": "upper", "action": {"description": "Introduced", "occurred_at": "2025-01-14T21:05:15+00:00"}, "bill_id": "SF0001"}
"#,
        )
        .unwrap();
        std::fs::write(
            bill.join(VOTE_EVENT_LOG_FILE),
            concat!(
                r#"{"id": "v1", "first_seen": null, "chamber": "upper", "vote_event": {"start_date": "2025-02-05T17:30:55+00:00", "result": "fail", "bill_identifier": "SF0001"}, "bill_id": "SF0001"}"#, "\n",
                r#"{"id": "v2", "first_seen": null, "chamber": "upper", "vote_event": {"start_date": "2025-02-06T10:00:00+00:00", "result": "pass", "bill_identifier": "SF0001"}, "bill_id": "SF0001"}"#, "\n",
                r#"{"id": "v1", "first_seen": "2026-09-29T10:33:32+00:00", "chamber": "upper", "vote_event": {"start_date": "2025-02-05T17:30:55+00:00", "result": "pass", "bill_identifier": "SF0001"}, "bill_id": "SF0001"}"#, "\n",
            ),
        )
        .unwrap();

        let records = bill_log_records(&bill);
        assert_eq!(records.len(), 3);
        let action = &records[0];
        assert_eq!(action.kind, LogKind::Action);
        assert_eq!(action.value["action"]["description"], "Introduced");
        assert_eq!(action.value["bill_id"], "SF0001");
        assert_eq!(action.timestamp.as_deref(), Some("20250114T210515Z"));
        assert_eq!(action.first_seen.as_deref(), Some("2026-09-29T10:33:32+00:00"));

        let votes: Vec<_> = records.iter().filter(|r| r.kind == LogKind::VoteEvent).collect();
        assert_eq!(votes.len(), 2);
        assert_eq!(votes[0].anchor.as_deref(), Some("v1"));
        assert_eq!(votes[0].value["result"], "pass", "the correction replaces the first version");
        assert_eq!(votes[0].line, Some(3));
        assert_eq!(votes[0].first_seen.as_deref(), Some("2026-09-29T10:33:32+00:00"), "a vote correction is news");
    }

    #[test]
    fn a_reworded_action_shows_once_in_its_new_wording_and_keeps_its_first_seen() {
        // MT 2026-08-10: "(H) First Reading" -> "(H) 1st Reading" on every past bill.
        let tmp = tempfile::tempdir().unwrap();
        let bill = bill(tmp.path());
        std::fs::write(
            bill.join(ACTION_LOG_FILE),
            concat!(
                r#"{"id": "a1", "first_seen": "2025-11-27T09:41:00+00:00", "chamber": "lower", "action": {"description": "(H) First Reading", "occurred_at": "2025-02-26T15:00:00+00:00"}, "bill_id": "HB794"}"#, "\n",
                r#"{"id": "a2", "first_seen": "2025-11-27T09:41:00+00:00", "chamber": "lower", "action": {"description": "(H) Referred to Committee", "occurred_at": "2025-02-27T15:00:00+00:00"}, "bill_id": "HB794"}"#, "\n",
                r#"{"id": "a1", "first_seen": "2026-08-10T07:00:00+00:00", "chamber": "lower", "action": {"description": "(H) 1st Reading", "occurred_at": "2025-02-26T15:00:00+00:00"}, "bill_id": "HB794"}"#, "\n",
            ),
        )
        .unwrap();
        let records = bill_log_records(&bill);
        assert_eq!(records.len(), 2);
        assert_eq!(records[0].value["action"]["description"], "(H) 1st Reading");
        assert_eq!(records[0].first_seen.as_deref(), Some("2025-11-27T09:41:00+00:00"), "a rewording isn't news");
        assert_eq!(records[0].line, Some(3));
        assert_eq!(records[1].anchor.as_deref(), Some("a2"));
    }

    #[test]
    fn reads_the_old_layout_and_ignores_the_session_folder() {
        let tmp = tempfile::tempdir().unwrap();
        let bill = bill(tmp.path());
        std::fs::create_dir_all(bill.join("logs")).unwrap();
        let action = bill.join("logs/20250131T030931Z.classification.introduction.lower.json");
        std::fs::write(&action, r#"{"action": {"description": "Introduced"}, "bill_id": "SF0001"}"#).unwrap();
        std::fs::write(bill.join("logs/20250205T173055Z_vote_event_fail.json"), r#"{"result": "fail", "motion_text": "x"}"#).unwrap();
        let session_logs = tmp.path().join("country:us/state:wy/sessions/2025/logs");
        std::fs::create_dir_all(&session_logs).unwrap();
        let copy = session_logs.join("20250131T030931Z.classification.introduction.lower.json");
        std::fs::copy(&action, &copy).unwrap();

        let records = bill_log_records(&bill);
        assert_eq!(records.len(), 2);
        assert_eq!(records[0].timestamp.as_deref(), Some("20250131T030931Z"), "dotted names get a timestamp too");
        assert_eq!(records[1].kind, LogKind::VoteEvent);
        assert!(read_log_records(&copy).is_none(), "the session-level folder is not a bill log");
    }
}
