//! Walking cloned repositories and reading the OCD-files layout into records.
//!
//! The layout, per `actions/format/docs/DATA_STRUCTURES.md`:
//!
//! ```text
//! {locale}-legislation/
//!   country:us/state:{code}/sessions/{session}/bills/{bill_id}/
//!     metadata.json
//!     logs/{ts}.vote_event.{result}.{chamber}.json   # dot form
//!     logs/{ts}_vote_event_{result}.json             # underscore form
//! ```
//!
//! Two things here are deliberately not shared with the rest of the crate.
//!
//! `processor.rs` never opens vote-event files at all — it regexes `pass`/`fail`
//! out of the *filename* — so it cannot see the `votes[]` array this whole command
//! exists to read. And `extract_timestamp_from_path` in `main.rs` requires an
//! underscore, so it silently yields nothing for the dot-form filenames that make
//! up roughly half of all logs. Both conventions are handled here.

use anyhow::Result;
use serde_json::Value;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use super::names::{repair_split_rows, RawVoteRow};
use super::ocd::Jurisdiction;

/// Where a fact came from, precise enough to check by hand.
#[derive(Debug, Clone, serde::Serialize)]
pub struct Citation {
    pub repo: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub commit: Option<String>,
    pub path: String,
}

/// One bill, as read from `metadata.json`.
#[derive(Debug, Clone)]
pub struct BillRecord {
    pub jurisdiction: Jurisdiction,
    pub session_id: String,
    pub bill_id: String,
    pub identifier: String,
    pub metadata: Value,
    pub dir: PathBuf,
    pub citation: Citation,
}

impl BillRecord {
    pub fn title(&self) -> &str {
        self.metadata
            .get("title")
            .and_then(Value::as_str)
            .unwrap_or_default()
    }

    pub fn subjects(&self) -> Vec<String> {
        string_array(self.metadata.get("subject"))
    }

    pub fn classification(&self) -> Vec<String> {
        string_array(self.metadata.get("classification"))
    }

    /// The first abstract, which is the closest thing to a summary most
    /// jurisdictions publish. Many publish none at all.
    pub fn abstract_text(&self) -> Option<String> {
        self.metadata
            .get("abstracts")?
            .as_array()?
            .iter()
            .find_map(|entry| entry.get("abstract").and_then(Value::as_str))
            .map(|s| s.to_string())
    }

    /// Sponsors, with the pseudo-JSON `person_id` dropped — it is derived from the
    /// name and carries no identity the name does not already carry.
    pub fn sponsorships(&self) -> Vec<Sponsorship> {
        self.metadata
            .get("sponsorships")
            .and_then(Value::as_array)
            .map(|entries| {
                entries
                    .iter()
                    .filter_map(|entry| {
                        let name = entry.get("name").and_then(Value::as_str)?;
                        Some(Sponsorship {
                            name: name.to_string(),
                            classification: entry
                                .get("classification")
                                .and_then(Value::as_str)
                                .unwrap_or_default()
                                .to_string(),
                            entity_type: entry
                                .get("entity_type")
                                .and_then(Value::as_str)
                                .unwrap_or("person")
                                .to_string(),
                            primary: entry
                                .get("primary")
                                .and_then(Value::as_bool)
                                .unwrap_or(false),
                        })
                    })
                    .collect()
            })
            .unwrap_or_default()
    }

    /// Bioguide ids for federal bills, from `extras`. Absent for state bills.
    pub fn sponsor_bioguides(&self) -> Vec<String> {
        let extras = self.metadata.get("extras");
        let mut ids = string_array(extras.and_then(|e| e.get("sponsor_bioguides")));
        ids.extend(string_array(
            extras.and_then(|e| e.get("cosponsor_bioguides")),
        ));
        ids
    }

    /// The most recent action, by date.
    pub fn latest_action(&self) -> Option<(String, String)> {
        let actions = self.metadata.get("actions")?.as_array()?;
        actions
            .iter()
            .filter_map(|action| {
                let date = action.get("date").and_then(Value::as_str)?;
                let description = action.get("description").and_then(Value::as_str)?;
                Some((date.to_string(), description.to_string()))
            })
            .max_by(|a, b| a.0.cmp(&b.0))
    }

    pub fn jurisdiction_name(&self) -> Option<String> {
        self.metadata
            .get("jurisdiction")?
            .get("name")?
            .as_str()
            .map(|s| s.to_string())
    }

    /// Every text field worth matching a free-text query against.
    pub fn searchable_text(&self) -> String {
        let mut text = String::new();
        text.push_str(&self.identifier);
        text.push(' ');
        text.push_str(self.title());
        if let Some(abstract_text) = self.abstract_text() {
            text.push(' ');
            text.push_str(&abstract_text);
        }
        for subject in self.subjects() {
            text.push(' ');
            text.push_str(&subject);
        }
        text.to_lowercase()
    }
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct Sponsorship {
    pub name: String,
    pub classification: String,
    pub entity_type: String,
    pub primary: bool,
}

impl Sponsorship {
    pub fn is_person(&self) -> bool {
        self.entity_type == "person"
    }
}

/// One roll call, as read from a `logs/*vote_event*.json` file.
#[derive(Debug, Clone)]
pub struct VoteEventRecord {
    pub bill_identifier: String,
    pub motion_text: String,
    pub start_date: String,
    pub result: String,
    pub chamber: String,
    pub counts: BTreeMap<String, i64>,
    /// Per-member rows, after the Wyoming split-row repair.
    pub votes: Vec<RawVoteRow>,
    /// How many rows the repair rejoined.
    pub repaired_rows: usize,
    pub citation: Citation,
}

impl VoteEventRecord {
    /// Whether this event records how individuals voted, or only a tally.
    ///
    /// Alaska publishes 1,342 vote events with no member rows at all; the
    /// distinction is the difference between "we can tell you how they voted" and
    /// "we cannot".
    pub fn has_member_votes(&self) -> bool {
        !self.votes.is_empty()
    }
}

/// Resolve the commit a repository is currently on, for citations.
pub fn head_commit(repo_path: &Path) -> Option<String> {
    let repo = git2::Repository::open(repo_path).ok()?;
    let head = repo.head().ok()?;
    let commit = head.peel_to_commit().ok()?;
    Some(commit.id().to_string()[..7].to_string())
}

/// Strip the `~` prefix govbot's upstream uses for pseudo-JSON blobs and pull one
/// field out of the object inside.
///
/// `"~{\"classification\": \"lower\"}"` -> `"lower"`.
fn pseudo_json_field(raw: Option<&Value>, field: &str) -> String {
    let Some(text) = raw.and_then(Value::as_str) else {
        return String::new();
    };
    let trimmed = text.trim_start_matches('~');
    serde_json::from_str::<Value>(trimmed)
        .ok()
        .and_then(|value| {
            value
                .get(field)
                .and_then(Value::as_str)
                .map(|s| s.to_string())
        })
        .unwrap_or_default()
}

fn string_array(value: Option<&Value>) -> Vec<String> {
    value
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .map(|s| s.to_string())
                .collect()
        })
        .unwrap_or_default()
}

/// Whether a log filename is a vote event, in either naming convention.
fn is_vote_event_file(file_name: &str) -> bool {
    file_name.contains(".vote_event.") || file_name.contains("_vote_event_")
}

/// The directory holding a jurisdiction's sessions, or `None` if it isn't cloned.
pub fn jurisdiction_root(repos_dir: &Path, jurisdiction: &Jurisdiction) -> Option<PathBuf> {
    let root = repos_dir
        .join(jurisdiction.repo_name())
        .join("country:us")
        .join(format!("state:{}", jurisdiction.path_segment()))
        .join("sessions");
    root.is_dir().then_some(root)
}

/// The repository directory for a jurisdiction, cloned or not.
pub fn repo_dir(repos_dir: &Path, jurisdiction: &Jurisdiction) -> PathBuf {
    repos_dir.join(jurisdiction.repo_name())
}

/// Session ids present on disk for a jurisdiction.
pub fn sessions(repos_dir: &Path, jurisdiction: &Jurisdiction) -> Vec<String> {
    let Some(root) = jurisdiction_root(repos_dir, jurisdiction) else {
        return Vec::new();
    };
    let Ok(entries) = std::fs::read_dir(&root) else {
        return Vec::new();
    };
    let mut ids: Vec<String> = entries
        .filter_map(|entry| entry.ok())
        .filter(|entry| entry.path().is_dir())
        .filter_map(|entry| entry.file_name().into_string().ok())
        .collect();
    ids.sort();
    ids
}

/// Read every bill in a jurisdiction, optionally restricted to one session.
///
/// Bills stream through `visit` rather than accumulating, so a caller that only
/// wants twenty rows out of Illinois' 12,780 bills never holds them all.
pub fn for_each_bill<F>(
    repos_dir: &Path,
    jurisdiction: &Jurisdiction,
    session_filter: Option<&str>,
    mut visit: F,
) -> Result<()>
where
    F: FnMut(BillRecord) -> Result<ControlFlow>,
{
    let Some(root) = jurisdiction_root(repos_dir, jurisdiction) else {
        return Ok(());
    };
    let repo_name = jurisdiction.repo_name();
    let commit = head_commit(&repo_dir(repos_dir, jurisdiction));

    for session_id in sessions(repos_dir, jurisdiction) {
        if let Some(wanted) = session_filter {
            if session_id != wanted {
                continue;
            }
        }
        let bills_dir = root.join(&session_id).join("bills");
        let Ok(entries) = std::fs::read_dir(&bills_dir) else {
            continue;
        };

        let mut bill_dirs: Vec<PathBuf> = entries
            .filter_map(|entry| entry.ok())
            .map(|entry| entry.path())
            .filter(|path| path.is_dir())
            .collect();
        // Deterministic order, so output and snapshots are stable.
        bill_dirs.sort();

        for dir in bill_dirs {
            let metadata_path = dir.join("metadata.json");
            let Ok(raw) = std::fs::read_to_string(&metadata_path) else {
                continue;
            };
            let Ok(metadata) = serde_json::from_str::<Value>(&raw) else {
                continue;
            };

            let bill_id = dir
                .file_name()
                .and_then(|name| name.to_str())
                .unwrap_or_default()
                .to_string();
            let identifier = metadata
                .get("identifier")
                .and_then(Value::as_str)
                .unwrap_or(&bill_id)
                .to_string();

            let record = BillRecord {
                jurisdiction: jurisdiction.clone(),
                session_id: session_id.clone(),
                bill_id,
                identifier,
                metadata,
                dir: dir.clone(),
                citation: Citation {
                    repo: repo_name.clone(),
                    commit: commit.clone(),
                    path: relative_path(&dir.join("metadata.json"), repos_dir, &repo_name),
                },
            };

            if visit(record)? == ControlFlow::Stop {
                return Ok(());
            }
        }
    }
    Ok(())
}

/// Whether a scan should keep going.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ControlFlow {
    Continue,
    Stop,
}

/// Read the roll calls attached to one bill.
pub fn vote_events(bill: &BillRecord, repos_dir: &Path) -> Vec<VoteEventRecord> {
    let logs_dir = bill.dir.join("logs");
    let Ok(entries) = std::fs::read_dir(&logs_dir) else {
        return Vec::new();
    };

    let mut paths: Vec<PathBuf> = entries
        .filter_map(|entry| entry.ok())
        .map(|entry| entry.path())
        .filter(|path| {
            path.file_name()
                .and_then(|name| name.to_str())
                .is_some_and(is_vote_event_file)
        })
        .collect();
    paths.sort();

    paths
        .iter()
        .filter_map(|path| read_vote_event(path, bill, repos_dir))
        .collect()
}

fn read_vote_event(path: &Path, bill: &BillRecord, repos_dir: &Path) -> Option<VoteEventRecord> {
    let raw = std::fs::read_to_string(path).ok()?;
    let value: Value = serde_json::from_str(&raw).ok()?;

    // The body is authoritative for `result`, not the filename.
    let result = value
        .get("result")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string();

    let rows: Vec<RawVoteRow> = value
        .get("votes")
        .and_then(Value::as_array)
        .map(|entries| {
            entries
                .iter()
                .filter_map(|entry| {
                    let voter_name = entry.get("voter_name").and_then(Value::as_str)?;
                    Some(RawVoteRow {
                        voter_name: voter_name.to_string(),
                        option: entry
                            .get("option")
                            .and_then(Value::as_str)
                            .unwrap_or_default()
                            .to_string(),
                        note: entry
                            .get("note")
                            .and_then(Value::as_str)
                            .unwrap_or_default()
                            .to_string(),
                    })
                })
                .collect()
        })
        .unwrap_or_default();

    let (votes, repaired_rows) = repair_split_rows(rows);

    let mut counts = BTreeMap::new();
    if let Some(entries) = value.get("counts").and_then(Value::as_array) {
        for entry in entries {
            let (Some(option), Some(count)) = (
                entry.get("option").and_then(Value::as_str),
                entry.get("value").and_then(Value::as_i64),
            ) else {
                continue;
            };
            counts.insert(option.to_string(), count);
        }
    }

    Some(VoteEventRecord {
        bill_identifier: value
            .get("bill_identifier")
            .and_then(Value::as_str)
            .unwrap_or(&bill.identifier)
            .to_string(),
        motion_text: value
            .get("motion_text")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string(),
        start_date: value
            .get("start_date")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string(),
        result,
        chamber: pseudo_json_field(value.get("organization"), "classification"),
        counts,
        votes,
        repaired_rows,
        citation: Citation {
            repo: bill.citation.repo.clone(),
            commit: bill.citation.commit.clone(),
            path: relative_path(path, repos_dir, &bill.citation.repo),
        },
    })
}

/// A path relative to the repository root, which is what a citation should show.
fn relative_path(path: &Path, repos_dir: &Path, repo_name: &str) -> String {
    let repo_root = repos_dir.join(repo_name);
    path.strip_prefix(&repo_root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn recognises_both_vote_event_filename_conventions() {
        assert!(is_vote_event_file("20250522T105400Z.vote_event.pass.lower.json"));
        assert!(is_vote_event_file("20250522T104600Z_vote_event_fail.json"));
        assert!(!is_vote_event_file(
            "20250129T022703Z_bill_number_assigned.json"
        ));
        assert!(!is_vote_event_file(
            "20250131T030931Z.classification.introduction.lower.json"
        ));
    }

    #[test]
    fn unwraps_pseudo_json_organization_blobs() {
        let value = serde_json::json!("~{\"classification\": \"lower\"}");
        assert_eq!(pseudo_json_field(Some(&value), "classification"), "lower");

        let value = serde_json::json!("~{\"name\": \"Appropriations\"}");
        assert_eq!(pseudo_json_field(Some(&value), "name"), "Appropriations");

        // Garbage in, empty string out — never a panic.
        let value = serde_json::json!("not json at all");
        assert_eq!(pseudo_json_field(Some(&value), "classification"), "");
        assert_eq!(pseudo_json_field(None, "classification"), "");
    }

    #[test]
    fn reads_string_arrays_defensively() {
        let value = serde_json::json!(["Transportation", "Consumer Protection"]);
        assert_eq!(string_array(Some(&value)).len(), 2);
        assert!(string_array(None).is_empty());
        assert!(string_array(Some(&serde_json::json!("not an array"))).is_empty());
    }
}
