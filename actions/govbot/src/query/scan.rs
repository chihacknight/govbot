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
    /// The official web page for the record — the legislature's bill page, or the
    /// roll-call page for a vote — taken from the record's own `sources`. It
    /// is what a person without git can click to check a claim.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub source_url: Option<String>,
}

/// Pick the one source URL worth showing a person, from `sources: [{url, note}]`.
///
/// Only http(s) URLs are ever returned: a relative path, `ftp:` or `javascript:`
/// value in a scraped `sources` list is not something to present as the official
/// page, so a record with nothing else gets no `source_url` at all.
///
/// Congress lists the govinfo bulk-data XML first and the congress.gov page
/// second; a person wants the page, so the first URL that is not `.xml` wins.
/// US House and Senate roll calls list only their XML; those are rewritten to
/// the human-readable page for the same vote (see `roll_call_page`), and any
/// other XML is returned as-is, since it is still better than nothing.
pub fn official_source_url(record: &Value) -> Option<String> {
    let urls: Vec<&str> = record
        .get("sources")?
        .as_array()?
        .iter()
        .filter_map(|source| source.get("url").and_then(Value::as_str))
        .map(str::trim)
        .filter(|url| {
            let lower = url.to_ascii_lowercase();
            lower.starts_with("https://") || lower.starts_with("http://")
        })
        .collect();
    let is_xml = |url: &str| {
        let lower = url.to_ascii_lowercase();
        let path = lower.split(['?', '#']).next().unwrap_or_default();
        path.ends_with(".xml")
    };
    if let Some(page) = urls.iter().find(|url| !is_xml(url)) {
        return Some(page.to_string());
    }
    let first = urls.first()?;
    Some(roll_call_page(first).unwrap_or_else(|| first.to_string()))
}

/// The human-readable page for a US House or Senate roll-call XML URL, if the
/// URL has one of the two shapes usa-legislation uses (checked against every
/// vote source in that repo, October 2026):
///
/// - House: `https://clerk.house.gov/evs/2025/roll003.xml` is shown at
///   `https://clerk.house.gov/Votes/20253` — the year followed by the roll
///   number without leading zeros.
/// - Senate: `.../roll_call_votes/vote1191/vote_119_1_00001.xml` is shown at the
///   same path ending in `.htm`.
///
/// Anything else returns `None` and the caller keeps the original URL.
fn roll_call_page(url: &str) -> Option<String> {
    const HOUSE: &str = "https://clerk.house.gov/evs/";
    const SENATE: &str = "https://www.senate.gov/legislative/LIS/roll_call_votes/";

    if let Some(rest) = url.strip_prefix(HOUSE) {
        let (year, file) = rest.split_once('/')?;
        let roll = file.strip_prefix("roll")?.strip_suffix(".xml")?;
        let all_digits = |s: &str| !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit());
        if year.len() != 4 || !all_digits(year) || !all_digits(roll) {
            return None;
        }
        let roll: u32 = roll.parse().ok()?;
        return Some(format!("https://clerk.house.gov/Votes/{year}{roll}"));
    }
    if let Some(rest) = url.strip_prefix(SENATE) {
        let (dir, file) = rest.split_once('/')?;
        let stem = file.strip_suffix(".xml")?;
        if !dir.starts_with("vote") || !stem.starts_with("vote_") || file.contains('/') {
            return None;
        }
        return Some(format!("{SENATE}{dir}/{stem}.htm"));
    }
    None
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

    /// Each person sponsorship that carries a bioguide id, paired with that id.
    /// Federal bills only; state bills have no ids and return nothing.
    ///
    /// `extras.sponsor_bioguides` and `extras.cosponsor_bioguides` are parallel to
    /// the primary and the non-primary person sponsorships, in the order they
    /// appear in `sponsorships`. That order is the only link between an id and a
    /// name, so a group whose length disagrees with its id list is skipped rather
    /// than guessed at. (In the 119th Congress every bill's lengths agree, and each
    /// id pairs with one person.) Pairing every id with the bill's first sponsor
    /// instead is what once sent `K000376` (Mike Kelly) to John Moolenaar's bills.
    pub fn sponsorships_by_id(&self) -> Vec<(String, Sponsorship)> {
        let extras = self.metadata.get("extras");
        let primary_ids = string_array(extras.and_then(|e| e.get("sponsor_bioguides")));
        let cosponsor_ids = string_array(extras.and_then(|e| e.get("cosponsor_bioguides")));
        if primary_ids.is_empty() && cosponsor_ids.is_empty() {
            return Vec::new();
        }

        let (primaries, cosponsors): (Vec<Sponsorship>, Vec<Sponsorship>) = self
            .sponsorships()
            .into_iter()
            .filter(Sponsorship::is_person)
            .partition(|s| s.primary);

        let mut paired = Vec::new();
        for (ids, people) in [(primary_ids, primaries), (cosponsor_ids, cosponsors)] {
            if ids.len() != people.len() {
                continue;
            }
            for (id, person) in ids.into_iter().zip(people) {
                let id = id.trim().to_uppercase();
                if !id.is_empty() {
                    paired.push((id, person));
                }
            }
        }
        paired
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
///
/// Tries libgit2 first, then falls back to reading git's own files. The fallback
/// is not redundant: libgit2 refuses to open a repository declaring an extension
/// it does not recognise, and `--filter=blob:none` partial clones declare
/// `extensions.partialClone`. Those clones are exactly what someone fetching a
/// large jurisdiction ends up with, and a citation without a commit is a citation
/// nobody can check.
pub fn head_commit(repo_path: &Path) -> Option<String> {
    if let Some(sha) = head_commit_via_libgit2(repo_path) {
        return Some(sha);
    }
    head_commit_from_files(repo_path)
}

fn head_commit_via_libgit2(repo_path: &Path) -> Option<String> {
    let repo = git2::Repository::open(repo_path).ok()?;
    let head = repo.head().ok()?;
    let commit = head.peel_to_commit().ok()?;
    Some(short_sha(&commit.id().to_string()))
}

/// Read `HEAD` and resolve it through loose refs and then `packed-refs`.
fn head_commit_from_files(repo_path: &Path) -> Option<String> {
    let git_dir = repo_path.join(".git");
    let head = std::fs::read_to_string(git_dir.join("HEAD")).ok()?;
    let head = head.trim();

    // A detached HEAD holds the object id directly.
    let Some(reference) = head.strip_prefix("ref: ") else {
        return is_object_id(head).then(|| short_sha(head));
    };

    if let Ok(contents) = std::fs::read_to_string(git_dir.join(reference)) {
        let sha = contents.trim();
        if is_object_id(sha) {
            return Some(short_sha(sha));
        }
    }

    // Shallow and freshly cloned repositories usually keep refs packed.
    let packed = std::fs::read_to_string(git_dir.join("packed-refs")).ok()?;
    for line in packed.lines() {
        if line.starts_with('#') || line.starts_with('^') {
            continue;
        }
        let Some((sha, name)) = line.split_once(' ') else {
            continue;
        };
        if name.trim() == reference && is_object_id(sha) {
            return Some(short_sha(sha));
        }
    }
    None
}

fn is_object_id(value: &str) -> bool {
    value.len() >= 7 && value.chars().all(|c| c.is_ascii_hexdigit())
}

fn short_sha(sha: &str) -> String {
    sha.chars().take(7).collect()
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

            let source_url = official_source_url(&metadata);
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
                    source_url,
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
            // The vote event's own source (the roll-call document), not the bill's.
            source_url: official_source_url(&value),
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
    fn prefers_the_official_page_over_bulk_xml() {
        // usa-legislation bills: govinfo bulk XML first, congress.gov second.
        let bill = serde_json::json!({"sources": [
            {"url": "https://www.govinfo.gov/bulkdata/BILLSTATUS/119/s/BILLSTATUS-119s4369.xml", "note": ""},
            {"url": "https://congress.gov/bill/119th-congress/senate-bill/4369", "note": ""}
        ]});
        assert_eq!(
            official_source_url(&bill).as_deref(),
            Some("https://congress.gov/bill/119th-congress/senate-bill/4369")
        );

        // il-legislation: a query string is not mistaken for a file extension.
        let bill = serde_json::json!({"sources": [
            {"url": "https://ilga.gov/Legislation/BillStatus?DocNum=3526&GAID=18&DocTypeID=HB"}
        ]});
        assert_eq!(
            official_source_url(&bill).as_deref(),
            Some("https://ilga.gov/Legislation/BillStatus?DocNum=3526&GAID=18&DocTypeID=HB")
        );

        // US Senate and House roll calls list only XML: the readable page for
        // the same vote is given instead.
        let vote = serde_json::json!({"sources": [
            {"url": "https://www.senate.gov/legislative/LIS/roll_call_votes/vote1191/vote_119_1_00278.xml"}
        ]});
        assert_eq!(
            official_source_url(&vote).as_deref(),
            Some("https://www.senate.gov/legislative/LIS/roll_call_votes/vote1191/vote_119_1_00278.htm")
        );
        let vote = serde_json::json!({"sources": [
            {"url": "https://clerk.house.gov/evs/2025/roll003.xml"}
        ]});
        assert_eq!(
            official_source_url(&vote).as_deref(),
            Some("https://clerk.house.gov/Votes/20253")
        );
        let vote = serde_json::json!({"sources": [
            {"url": "https://clerk.house.gov/evs/2026/roll150.xml"}
        ]});
        assert_eq!(
            official_source_url(&vote).as_deref(),
            Some("https://clerk.house.gov/Votes/2026150")
        );

        // Other XML, or a roll-call URL of an unfamiliar shape, is kept as-is.
        for url in [
            "https://example.gov/votes/123.xml",
            "https://clerk.house.gov/evs/2025/rollcall003.xml",
            "https://clerk.house.gov/evs/25/roll003.xml",
        ] {
            let vote = serde_json::json!({"sources": [{"url": url}]});
            assert_eq!(official_source_url(&vote).as_deref(), Some(url));
        }

        // No sources, empty sources, or blank URLs: no field rather than "".
        assert_eq!(official_source_url(&serde_json::json!({})), None);
        assert_eq!(
            official_source_url(&serde_json::json!({"sources": []})),
            None
        );
        assert_eq!(
            official_source_url(&serde_json::json!({"sources": [{"url": " "}]})),
            None
        );
    }

    #[test]
    fn never_offers_a_non_web_link_as_the_official_page() {
        for url in [
            "/legislation/bills/HB1.htm",
            "bills/HB1.xml",
            "ftp://ftp.legislature.example/HB1.pdf",
            "javascript:void(0)",
            "mailto:clerk@example.gov",
        ] {
            let record = serde_json::json!({"sources": [{"url": url}]});
            assert_eq!(official_source_url(&record), None, "{url}");
        }

        // A web URL later in the list still wins over a non-web one first.
        let record = serde_json::json!({"sources": [
            {"url": "javascript:void(0)"},
            {"url": "HTTPS://legislature.example/HB1"}
        ]});
        assert_eq!(
            official_source_url(&record).as_deref(),
            Some("HTTPS://legislature.example/HB1")
        );
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
    fn recognises_object_ids() {
        assert!(is_object_id("9be2e4f61f0000000000000000000000000000aa"));
        assert!(is_object_id("598ea01"));
        assert!(!is_object_id("ref: refs/heads/main"));
        assert!(!is_object_id("abc"));
        assert_eq!(short_sha("9be2e4f61f00000"), "9be2e4f");
    }

    /// The fallback exists because libgit2 will not open a partial clone, which is
    /// what `--filter=blob:none` produces.
    #[test]
    fn reads_head_from_git_files_including_packed_refs() {
        let dir = tempfile::tempdir().expect("tempdir");
        let git = dir.path().join(".git");
        std::fs::create_dir_all(git.join("refs/heads")).expect("mkdir");

        std::fs::write(git.join("HEAD"), "ref: refs/heads/main\n").expect("write");
        std::fs::write(
            git.join("packed-refs"),
            "# pack-refs with: peeled fully-peeled sorted\n\
             9be2e4f61f0000000000000000000000000000aa refs/heads/main\n",
        )
        .expect("write");
        assert_eq!(head_commit_from_files(dir.path()).as_deref(), Some("9be2e4f"));

        // A loose ref wins over packed-refs.
        std::fs::write(
            git.join("refs/heads/main"),
            "1111111000000000000000000000000000000000\n",
        )
        .expect("write");
        assert_eq!(head_commit_from_files(dir.path()).as_deref(), Some("1111111"));

        // Detached HEAD.
        std::fs::write(git.join("HEAD"), "2222222000000000000000000000000000000000\n")
            .expect("write");
        assert_eq!(head_commit_from_files(dir.path()).as_deref(), Some("2222222"));
    }

    fn federal_bill(metadata: Value) -> BillRecord {
        BillRecord {
            jurisdiction: Jurisdiction::new("usa"),
            session_id: "119".into(),
            bill_id: "HR1".into(),
            identifier: "HR 1".into(),
            metadata,
            dir: PathBuf::new(),
            citation: Citation {
                repo: "usa-legislation".into(),
                commit: None,
                path: String::new(),
            },
        }
    }

    fn sponsor(name: &str, primary: bool) -> Value {
        serde_json::json!({
            "name": name,
            "classification": if primary { "primary" } else { "cosponsor" },
            "entity_type": "person",
            "primary": primary,
        })
    }

    /// The shape of a real federal bill: cosponsors listed before the primary
    /// sponsor, with ids in two lists parallel to them.
    #[test]
    fn pairs_each_sponsor_id_with_its_own_name() {
        let bill = federal_bill(serde_json::json!({
            "sponsorships": [
                sponsor("Kathy Castor", false),
                sponsor("Erin Houchin", false),
                { "name": "Some Committee", "entity_type": "organization", "primary": false },
                sponsor("Steve Womack", true),
                sponsor("Mike Kelly", false),
            ],
            "extras": {
                "sponsor_bioguides": ["W000809"],
                "cosponsor_bioguides": ["C001066", "H001093", "k000376"],
            },
        }));
        let paired: Vec<(String, String, bool)> = bill
            .sponsorships_by_id()
            .into_iter()
            .map(|(id, s)| (id, s.name, s.primary))
            .collect();
        assert_eq!(
            paired,
            vec![
                ("W000809".into(), "Steve Womack".into(), true),
                ("C001066".into(), "Kathy Castor".into(), false),
                ("H001093".into(), "Erin Houchin".into(), false),
                ("K000376".into(), "Mike Kelly".into(), false),
            ]
        );
    }

    #[test]
    fn a_misaligned_id_list_is_skipped_not_guessed() {
        let bill = federal_bill(serde_json::json!({
            "sponsorships": [
                sponsor("Steve Womack", true),
                sponsor("Kathy Castor", false),
                sponsor("Mike Kelly", false),
            ],
            "extras": {
                "sponsor_bioguides": ["W000809"],
                // One cosponsor id missing: no way to tell whose.
                "cosponsor_bioguides": ["K000376"],
            },
        }));
        let ids: Vec<String> = bill
            .sponsorships_by_id()
            .into_iter()
            .map(|(id, _)| id)
            .collect();
        assert_eq!(ids, vec!["W000809".to_string()]);

        // A state bill has no ids at all.
        let state =
            federal_bill(serde_json::json!({ "sponsorships": [sponsor("Bill Cunningham", true)] }));
        assert!(state.sponsorships_by_id().is_empty());
    }

    #[test]
    fn reads_string_arrays_defensively() {
        let value = serde_json::json!(["Transportation", "Consumer Protection"]);
        assert_eq!(string_array(Some(&value)).len(), 2);
        assert!(string_array(None).is_empty());
        assert!(string_array(Some(&serde_json::json!("not an array"))).is_empty());
    }
}
