//! `govbot query` — bounded, cited answers over cloned legislation.
//!
//! `govbot logs` streams unbounded nested JSON Lines. That is the right shape for a
//! Unix pipe and the wrong shape for anything with a context window: there is no
//! way to cap the output, no way to filter by tag score, and every row carries the
//! full nesting of its source files.
//!
//! `query` answers the same corpus with a capped, flat array. Every row carries a
//! citation — repository, commit, and path — so any claim built on it can be
//! checked by hand. Every response carries a coverage report and, where the data
//! cannot support the question, plainly worded caveats.
//!
//! The vocabulary is Open Civic Data, because the data already speaks it: every
//! `metadata.json` carries `jurisdiction: {id, name, classification, division_id}`.

pub mod names;
pub mod ocd;
pub mod scan;

use anyhow::Result;
use serde::Serialize;
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::path::PathBuf;

pub use names::{Confidence, MatchMethod, NameIndex, NameMatch};
pub use ocd::{District, Jurisdiction};
use scan::{BillRecord, ControlFlow, VoteEventRecord};

/// The four things a caller can ask for.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum QueryKind {
    /// Bills, optionally narrowed by person, tag score, subject, or text.
    Bills,
    /// Roll calls, optionally narrowed to how one person voted.
    Votes,
    /// The distinct people named in the data, with how often each appears.
    People,
    /// What data is present and what it can and cannot answer.
    Coverage,
}

impl QueryKind {
    pub fn parse(input: &str) -> Option<Self> {
        match input.trim().to_lowercase().as_str() {
            "bills" | "bill" => Some(QueryKind::Bills),
            "votes" | "vote" | "vote_events" => Some(QueryKind::Votes),
            "people" | "person" => Some(QueryKind::People),
            "coverage" => Some(QueryKind::Coverage),
            _ => None,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            QueryKind::Bills => "bills",
            QueryKind::Votes => "votes",
            QueryKind::People => "people",
            QueryKind::Coverage => "coverage",
        }
    }
}

/// Everything one `govbot query` invocation needs to know.
#[derive(Debug, Clone)]
pub struct QueryRequest {
    pub kind: QueryKind,
    pub repos_dir: PathBuf,
    /// Where `govbot tag` wrote its output. Tag files live beside `govbot.yml`,
    /// which for a workspace is the workspace root.
    pub tags_dir: PathBuf,
    pub jurisdictions: Vec<Jurisdiction>,
    pub session: Option<String>,
    /// Restrict to one bill, by its identifier or directory name.
    pub identifier: Option<String>,
    /// A legislator name to match against sponsors and voters.
    pub person: Option<String>,
    /// A tag from `govbot.yml`, used to rank and filter by relevance.
    pub tag: Option<String>,
    pub min_score: Option<f64>,
    pub min_confidence: Confidence,
    /// Free-text match against identifier, title, abstract, and subjects.
    pub text: Option<String>,
    pub subject: Option<String>,
    pub limit: usize,
    /// Votes only: a case-insensitive substring of the vote event's motion text.
    /// In Illinois, floor votes read "Third Reading" or "Concurrence" and committee
    /// votes carry the committee's name ("Executive Appointments").
    pub motion: Option<String>,
    /// Votes only: the chamber that voted, `upper` or `lower` (`senate` and
    /// `house` are accepted). See [`normalize_chamber`].
    pub chamber: Option<String>,
}

/// The envelope every query returns.
///
/// `coverage` and `caveats` are present on success as well as on failure — the
/// point is that a caller should never have to infer whether an empty result means
/// "nothing matched" or "this jurisdiction publishes no such data".
#[derive(Debug, Serialize)]
pub struct QueryResponse {
    pub query: Value,
    pub results: Vec<Value>,
    pub truncation: Truncation,
    pub coverage: Vec<Value>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub caveats: Vec<String>,
    /// Votes only: totals over every matching vote, not just the rows returned,
    /// so "how did they vote on the floor" can be answered without paging.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub summary: Option<Value>,
}

#[derive(Debug, Serialize)]
pub struct Truncation {
    pub returned: usize,
    pub total_matching: usize,
    pub limit: usize,
}

/// Run a query.
pub fn run(request: &QueryRequest) -> Result<QueryResponse> {
    let mut caveats = Vec::new();
    let mut coverage = Vec::new();

    // A jurisdiction that was asked for but never cloned is an error condition, not
    // an empty result. An empty result reads as "this person did nothing", which is
    // exactly the fabrication this command exists to prevent.
    let mut missing = Vec::new();
    for jurisdiction in &request.jurisdictions {
        if scan::jurisdiction_root(&request.repos_dir, jurisdiction).is_none() {
            missing.push(jurisdiction.locale.clone());
        }
    }
    if !missing.is_empty() {
        caveats.push(format!(
            "Not cloned yet, so nothing here reflects them: {}. \
             Run `govbot clone {}` first. This is missing data, not an empty record.",
            missing.join(", "),
            missing.join(" ")
        ));
    }

    for jurisdiction in &request.jurisdictions {
        if scan::jurisdiction_root(&request.repos_dir, jurisdiction).is_some() {
            let report = coverage_for(request, jurisdiction)?;
            caveats.extend(report.caveats.clone());
            coverage.push(report.to_json());
        }
    }

    // Motion and chamber describe vote events. Ignoring them elsewhere would echo
    // them back in `query` as if they had narrowed the result.
    if request.kind != QueryKind::Votes {
        for (flag, given) in [("motion", &request.motion), ("chamber", &request.chamber)] {
            if given.is_some() {
                anyhow::bail!(
                    "`{flag}` only applies to votes queries. Drop it, or use `query votes`."
                );
            }
        }
    }

    let mut summary = None;
    let (results, total_matching, extra_caveats) = match request.kind {
        QueryKind::Bills => query_bills(request)?,
        QueryKind::Votes => {
            let (results, total, caveats, votes_summary) = query_votes(request)?;
            summary = Some(votes_summary);
            (results, total, caveats)
        }
        QueryKind::People => query_people(request)?,
        QueryKind::Coverage => (Vec::new(), 0, Vec::new()),
    };
    caveats.extend(extra_caveats);

    Ok(QueryResponse {
        query: describe(request),
        truncation: Truncation {
            returned: results.len(),
            total_matching,
            limit: request.limit,
        },
        results,
        coverage,
        caveats,
        summary,
    })
}

fn describe(request: &QueryRequest) -> Value {
    let mut described = serde_json::Map::new();
    described.insert("type".into(), json!(request.kind.as_str()));
    described.insert(
        "jurisdictions".into(),
        json!(request
            .jurisdictions
            .iter()
            .map(|j| j.ocd_jurisdiction_id())
            .collect::<Vec<_>>()),
    );
    for (key, value) in [
        ("session", request.session.clone()),
        ("identifier", request.identifier.clone()),
        ("person", request.person.clone()),
        ("tag", request.tag.clone()),
        ("text", request.text.clone()),
        ("subject", request.subject.clone()),
        ("motion", request.motion.clone()),
        ("chamber", request.chamber.clone()),
    ] {
        if let Some(value) = value {
            described.insert(key.into(), json!(value));
        }
    }
    if let Some(min_score) = request.min_score {
        described.insert("min_score".into(), json!(min_score));
    }
    described.insert("min_confidence".into(), json!(request.min_confidence));
    Value::Object(described)
}

// ---------------------------------------------------------------------------
// Tag scores
// ---------------------------------------------------------------------------

/// Scores written by `govbot tag`, loaded per session.
///
/// Tag files are keyed by the bill id that `govbot logs` emitted, which is the
/// bill's `identifier` — `"HR 1"`, with a space, where the directory is `HR1`.
/// Both are tried.
struct TagScores {
    threshold: f64,
    by_bill: BTreeMap<String, Value>,
}

impl TagScores {
    fn load(request: &QueryRequest, jurisdiction: &Jurisdiction, session_id: &str) -> Option<Self> {
        let tag = request.tag.as_ref()?;
        let path = request
            .tags_dir
            .join("country:us")
            .join(format!("state:{}", jurisdiction.path_segment()))
            .join("sessions")
            .join(session_id)
            .join("tags")
            .join(format!("{tag}.tag.json"));

        let raw = std::fs::read_to_string(&path).ok()?;
        let value: Value = serde_json::from_str(&raw).ok()?;

        let threshold = value
            .get("tag_config")
            .and_then(|config| config.get("threshold"))
            .and_then(Value::as_f64)
            .unwrap_or(0.5);

        let by_bill = value
            .get("bills")
            .and_then(Value::as_object)
            .map(|bills| {
                bills
                    .iter()
                    .filter_map(|(bill_id, entry)| {
                        entry.get("score").map(|s| (bill_id.clone(), s.clone()))
                    })
                    .collect()
            })
            .unwrap_or_default();

        Some(Self { threshold, by_bill })
    }

    fn score_for(&self, bill: &BillRecord) -> Option<&Value> {
        self.by_bill
            .get(&bill.identifier)
            .or_else(|| self.by_bill.get(&bill.bill_id))
    }
}

// ---------------------------------------------------------------------------
// Bills
// ---------------------------------------------------------------------------

fn query_bills(request: &QueryRequest) -> Result<(Vec<Value>, usize, Vec<String>)> {
    let mut caveats = Vec::new();

    // Matching a person needs to know every name in scope before it can tell a
    // unique surname from an ambiguous one, so that costs a first pass.
    let person_match = match request.person.as_deref() {
        Some(person) => {
            let index = build_sponsor_index(request)?;
            let resolved = index.resolve(person);
            caveats.extend(describe_match(person, &resolved, request.min_confidence));
            Some(resolved)
        }
        None => None,
    };

    if let Some(resolved) = &person_match {
        if !resolved.is_attributable(request.min_confidence) {
            return Ok((Vec::new(), 0, caveats));
        }
    }

    let mut rows: Vec<(f64, Value)> = Vec::new();
    let mut total = 0usize;

    for jurisdiction in &request.jurisdictions {
        for session_id in sessions_in_scope(request, jurisdiction) {
            let scores = TagScores::load(request, jurisdiction, &session_id);
            if request.tag.is_some() && scores.is_none() {
                caveats.push(format!(
                    "No tag file for '{}' in {} session {}. Run `govbot tag` before \
                     filtering by tag, or results will be missing rather than empty.",
                    request.tag.clone().unwrap_or_default(),
                    jurisdiction.locale,
                    session_id
                ));
            }

            scan::for_each_bill(
                &request.repos_dir,
                jurisdiction,
                Some(&session_id),
                |bill| {
                    if !bill_matches(request, &bill) {
                        return Ok(ControlFlow::Continue);
                    }

                    let sponsorship = match person_match.as_ref() {
                        Some(resolved) => {
                            let Some(found) = matching_sponsorship(&bill, resolved) else {
                                return Ok(ControlFlow::Continue);
                            };
                            Some(found)
                        }
                        None => None,
                    };

                    let score = match scores.as_ref() {
                        Some(scores) => {
                            let Some(score) = scores.score_for(&bill) else {
                                return Ok(ControlFlow::Continue);
                            };
                            let final_score =
                                score.get("final_score").and_then(Value::as_f64).unwrap_or(0.0);
                            let floor = request.min_score.unwrap_or(scores.threshold);
                            if final_score < floor {
                                return Ok(ControlFlow::Continue);
                            }
                            Some((final_score, score.clone()))
                        }
                        None => None,
                    };

                    total += 1;
                    let rank = score.as_ref().map(|(value, _)| *value).unwrap_or(0.0);
                    rows.push((
                        rank,
                        bill_row(&bill, sponsorship, score, person_match.as_ref()),
                    ));
                    Ok(ControlFlow::Continue)
                },
            )?;
        }
    }

    // Rank by tag score when there is one; otherwise keep the deterministic
    // filesystem order the scan produced.
    if request.tag.is_some() {
        rows.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal));
    }
    let results = rows
        .into_iter()
        .take(request.limit)
        .map(|(_, row)| row)
        .collect();

    Ok((results, total, caveats))
}

fn bill_matches(request: &QueryRequest, bill: &BillRecord) -> bool {
    if let Some(identifier) = &request.identifier {
        let wanted = identifier.trim().to_lowercase().replace(' ', "");
        let actual = bill.identifier.to_lowercase().replace(' ', "");
        if actual != wanted && bill.bill_id.to_lowercase() != wanted {
            return false;
        }
    }
    if let Some(subject) = &request.subject {
        let wanted = subject.to_lowercase();
        if !bill
            .subjects()
            .iter()
            .any(|s| s.to_lowercase().contains(&wanted))
        {
            return false;
        }
    }
    if let Some(text) = &request.text {
        let haystack = bill.searchable_text();
        // Every term must appear as a whole word. Plain substring matching is far
        // too loose here: searching for "rent" would match "Trenton", which is the
        // kind of quiet nonsense that makes a values answer untrustworthy.
        if !text
            .to_lowercase()
            .split_whitespace()
            .all(|term| contains_word(&haystack, term))
        {
            return false;
        }
    }
    true
}

/// Whether `haystack` contains `needle` as a whole word.
///
/// Word boundaries are any non-alphanumeric character, which suits legislative
/// text where terms are separated by spaces, hyphens, and punctuation.
fn contains_word(haystack: &str, needle: &str) -> bool {
    if needle.is_empty() {
        return true;
    }
    let bytes = haystack.as_bytes();
    let mut from = 0usize;
    while let Some(offset) = haystack[from..].find(needle) {
        let start = from + offset;
        let end = start + needle.len();
        let before_ok = start == 0 || !is_word_byte(bytes[start - 1]);
        let after_ok = end == bytes.len() || !is_word_byte(bytes[end]);
        if before_ok && after_ok {
            return true;
        }
        // Advance by one byte boundary so overlapping matches are still found.
        from = match haystack[start..].char_indices().nth(1) {
            Some((next, _)) => start + next,
            None => return false,
        };
    }
    false
}

fn is_word_byte(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || byte >= 0x80
}

fn matching_sponsorship(bill: &BillRecord, resolved: &NameMatch) -> Option<scan::Sponsorship> {
    bill.sponsorships().into_iter().find(|sponsorship| {
        sponsorship.is_person() && resolved.candidates.contains(&sponsorship.name)
    })
}

fn bill_row(
    bill: &BillRecord,
    sponsorship: Option<scan::Sponsorship>,
    score: Option<(f64, Value)>,
    person_match: Option<&NameMatch>,
) -> Value {
    let mut row = serde_json::Map::new();
    row.insert("identifier".into(), json!(bill.identifier));
    row.insert("title".into(), json!(bill.title()));
    row.insert("legislative_session".into(), json!(bill.session_id));
    row.insert(
        "jurisdiction".into(),
        json!({
            "id": bill.jurisdiction.ocd_jurisdiction_id(),
            "name": bill.jurisdiction_name(),
        }),
    );

    let classification = bill.classification();
    if !classification.is_empty() {
        row.insert("classification".into(), json!(classification));
    }
    let subjects = bill.subjects();
    if !subjects.is_empty() {
        row.insert("subject".into(), json!(subjects));
    }
    if let Some(abstract_text) = bill.abstract_text() {
        row.insert("abstract".into(), json!(truncate(&abstract_text, 400)));
    }
    if let Some((date, description)) = bill.latest_action() {
        row.insert(
            "latest_action".into(),
            json!({ "date": date, "description": truncate(&description, 200) }),
        );
    }

    if let Some(sponsorship) = sponsorship {
        row.insert(
            "sponsorship".into(),
            json!({
                "name": sponsorship.name,
                "classification": sponsorship.classification,
                "primary": sponsorship.primary,
            }),
        );
    } else {
        let sponsorships = bill.sponsorships();
        if !sponsorships.is_empty() {
            row.insert("sponsorships".into(), json!(sponsorships));
        }
    }

    if let Some((final_score, breakdown)) = score {
        row.insert(
            "tag".into(),
            json!({ "final_score": final_score, "score": breakdown }),
        );
    }
    if let Some(resolved) = person_match {
        row.insert("match".into(), json!(resolved));
    }

    row.insert("citation".into(), json!(bill.citation));
    Value::Object(row)
}

// ---------------------------------------------------------------------------
// Votes
// ---------------------------------------------------------------------------

fn query_votes(request: &QueryRequest) -> Result<(Vec<Value>, usize, Vec<String>, Value)> {
    let mut caveats = Vec::new();
    let mut summary = VoteSummary::default();

    let person_match = match request.person.as_deref() {
        Some(person) => {
            let index = build_voter_index(request)?;
            let resolved = index.resolve(person);
            caveats.extend(describe_match(person, &resolved, request.min_confidence));
            Some(resolved)
        }
        None => None,
    };

    if let Some(resolved) = &person_match {
        if !resolved.is_attributable(request.min_confidence) {
            return Ok((Vec::new(), 0, caveats, summary.to_json()));
        }
    }

    // (start date, row). Pruned to the newest as it grows; see `keep_newest`.
    let mut results: Vec<(String, Value)> = Vec::new();
    let mut total = 0usize;
    let mut excluded_by_event_filter = 0usize;

    for jurisdiction in &request.jurisdictions {
        for session_id in sessions_in_scope(request, jurisdiction) {
            scan::for_each_bill(
                &request.repos_dir,
                jurisdiction,
                Some(&session_id),
                |bill| {
                    if !bill_matches(request, &bill) {
                        return Ok(ControlFlow::Continue);
                    }
                    for event in scan::vote_events(&bill, &request.repos_dir) {
                        let person_vote = match person_match.as_ref() {
                            Some(resolved) => {
                                let Some(found) = matching_vote(&event, resolved) else {
                                    continue;
                                };
                                Some(found)
                            }
                            None => None,
                        };
                        // After the person match, so an empty result can say how
                        // many of their votes the motion or chamber filter removed.
                        if !event_matches(request, &event) {
                            excluded_by_event_filter += 1;
                            continue;
                        }
                        total += 1;
                        summary.record(&event, person_vote.as_ref());
                        let row = vote_row(&bill, &event, person_vote, person_match.as_ref());
                        results.push((event.start_date.clone(), row));
                        keep_newest(&mut results, request.limit);
                    }
                    Ok(ControlFlow::Continue)
                },
            )?;
        }
    }

    if total == 0 && excluded_by_event_filter > 0 {
        caveats.push(event_filter_caveat(request, excluded_by_event_filter));
    }

    sort_newest_first(&mut results);
    results.truncate(request.limit);
    let results = results.into_iter().map(|(_, row)| row).collect();
    Ok((results, total, caveats, summary.to_json()))
}

fn matching_vote(event: &VoteEventRecord, resolved: &NameMatch) -> Option<names::RawVoteRow> {
    event
        .votes
        .iter()
        .find(|row| resolved.candidates.contains(&row.voter_name))
        .cloned()
}

fn vote_row(
    bill: &BillRecord,
    event: &VoteEventRecord,
    person_vote: Option<names::RawVoteRow>,
    person_match: Option<&NameMatch>,
) -> Value {
    let mut row = serde_json::Map::new();
    row.insert("bill_identifier".into(), json!(event.bill_identifier));
    row.insert("bill_title".into(), json!(bill.title()));
    row.insert("legislative_session".into(), json!(bill.session_id));
    row.insert(
        "jurisdiction".into(),
        json!({ "id": bill.jurisdiction.ocd_jurisdiction_id() }),
    );
    row.insert("motion_text".into(), json!(event.motion_text));
    row.insert("start_date".into(), json!(event.start_date));
    row.insert("result".into(), json!(event.result));
    if !event.chamber.is_empty() {
        row.insert("organization".into(), json!(event.chamber));
    }
    row.insert("counts".into(), json!(event.counts));
    row.insert("has_member_votes".into(), json!(event.has_member_votes()));

    if let Some(vote) = person_vote {
        let mut entry = serde_json::Map::new();
        entry.insert("voter_name".into(), json!(vote.voter_name));
        entry.insert("option".into(), json!(vote.option));
        if !vote.note.is_empty() {
            entry.insert("note".into(), json!(vote.note));
        }
        row.insert("person_vote".into(), Value::Object(entry));
    }
    if let Some(resolved) = person_match {
        row.insert("match".into(), json!(resolved));
    }
    if event.repaired_rows > 0 {
        row.insert("split_rows_repaired".into(), json!(event.repaired_rows));
    }

    row.insert("citation".into(), json!(event.citation));
    Value::Object(row)
}

/// Without this, "0 third-reading votes" reads as "never voted on the floor".
/// Often the votes are there under a motion worded differently, or the person's
/// floor votes are recorded under another spelling of their name.
fn event_filter_caveat(request: &QueryRequest, excluded: usize) -> String {
    let filters: Vec<String> = [("motion", &request.motion), ("chamber", &request.chamber)]
        .iter()
        .filter_map(|(name, value)| value.as_ref().map(|v| format!("{name} \"{v}\"")))
        .collect();
    let whose = match &request.person {
        Some(person) => format!(" matched to \"{person}\""),
        None => String::new(),
    };
    format!(
        "No votes matched {}, but {excluded} other vote(s){whose} are in scope. This \
         is not evidence that they did not vote: drop the filter and read \
         `summary.by_motion` for how motions are worded here, and check `query people` \
         for other spellings of the name (some states print only the surname on \
         floor votes).",
        filters.join(" and ")
    )
}

/// The vote-event filters: `motion` and `chamber`.
fn event_matches(request: &QueryRequest, event: &VoteEventRecord) -> bool {
    if let Some(motion) = &request.motion {
        // A substring, not whole words, so "third reading" also finds
        // "Third Reading, Amendment 1" and "concur" finds "Concurrence".
        if !event
            .motion_text
            .to_lowercase()
            .contains(motion.trim().to_lowercase().as_str())
        {
            return false;
        }
    }
    if let Some(chamber) = &request.chamber {
        if normalize_chamber(&event.chamber) != normalize_chamber(chamber) {
            return false;
        }
    }
    true
}

/// Open Civic Data names chambers `upper` and `lower`; people say Senate and
/// House (or Assembly, in some states). Nebraska's single chamber is
/// `legislature`. Anything else is compared as given, lowercased.
fn normalize_chamber(chamber: &str) -> String {
    let chamber = chamber.trim().to_lowercase();
    match chamber.as_str() {
        "senate" => "upper".to_string(),
        "house" | "assembly" | "house of representatives" => "lower".to_string(),
        _ => chamber,
    }
}

/// Drop everything past the newest `limit` rows once the buffer holds twice
/// that many. Sorting the whole match set at the end would hold every row in
/// memory (tens of thousands for a state with no `person`) when only `limit`
/// are returned.
fn keep_newest(rows: &mut Vec<(String, Value)>, limit: usize) {
    if rows.len() >= limit.saturating_mul(2).max(1) {
        sort_newest_first(rows);
        rows.truncate(limit);
    }
}

/// The sort is stable, so equal dates keep scan order and repeated runs agree.
/// Dates are compared as strings: ISO dates order correctly that way, and a
/// date-only value ("2026-02-17") sorts just before timestamps on the same day.
/// Timestamps with different UTC offsets can be misordered by hours, never by
/// days. An event with no date sorts last.
fn sort_newest_first(rows: &mut [(String, Value)]) {
    rows.sort_by(|a, b| b.0.cmp(&a.0));
}

/// Totals over every vote a query matched, including the ones past `limit`.
#[derive(Default)]
struct VoteSummary {
    /// Motion text → (events, the person's options → count).
    by_motion: BTreeMap<String, (usize, BTreeMap<String, usize>)>,
    /// The person's options across every matched event.
    person_votes: BTreeMap<String, usize>,
    earliest: Option<String>,
    latest: Option<String>,
}

/// How many motions `summary.by_motion` lists. Without a `motion` filter a
/// state has hundreds (every committee, and in Congress every resolution), and
/// the point of the summary is to be read in one go.
const SUMMARY_MOTIONS: usize = 25;

impl VoteSummary {
    fn record(&mut self, event: &VoteEventRecord, person_vote: Option<&names::RawVoteRow>) {
        let entry = self.by_motion.entry(event.motion_text.clone()).or_default();
        entry.0 += 1;
        if let Some(vote) = person_vote {
            *entry.1.entry(vote.option.clone()).or_default() += 1;
            *self.person_votes.entry(vote.option.clone()).or_default() += 1;
        }
        if !event.start_date.is_empty() {
            if self
                .earliest
                .as_ref()
                .map_or(true, |d| event.start_date < *d)
            {
                self.earliest = Some(event.start_date.clone());
            }
            if self.latest.as_ref().map_or(true, |d| event.start_date > *d) {
                self.latest = Some(event.start_date.clone());
            }
        }
    }

    fn to_json(&self) -> Value {
        // Most frequent first; ties by name, so the order is stable.
        let mut motions: Vec<_> = self.by_motion.iter().collect();
        motions.sort_by(|a, b| b.1 .0.cmp(&a.1 .0).then_with(|| a.0.cmp(b.0)));
        let listed: Vec<Value> = motions
            .iter()
            .take(SUMMARY_MOTIONS)
            .map(|(motion, (events, options))| {
                let mut row = serde_json::Map::new();
                row.insert("motion_text".into(), json!(motion));
                row.insert("votes".into(), json!(events));
                if !options.is_empty() {
                    row.insert("person_votes".into(), json!(options));
                }
                Value::Object(row)
            })
            .collect();

        let mut summary = serde_json::Map::new();
        summary.insert("by_motion".into(), json!(listed));
        if motions.len() > SUMMARY_MOTIONS {
            summary.insert(
                "motions_not_listed".into(),
                json!(motions.len() - SUMMARY_MOTIONS),
            );
        }
        if !self.person_votes.is_empty() {
            summary.insert("person_votes".into(), json!(self.person_votes));
        }
        if let (Some(earliest), Some(latest)) = (&self.earliest, &self.latest) {
            summary.insert(
                "dates".into(),
                json!({ "earliest": earliest, "latest": latest }),
            );
        }
        Value::Object(summary)
    }
}

#[cfg(test)]
mod vote_filter_tests {
    use super::*;

    fn event(motion: &str, chamber: &str, date: &str) -> VoteEventRecord {
        VoteEventRecord {
            bill_identifier: "SB1".into(),
            motion_text: motion.into(),
            start_date: date.into(),
            result: "pass".into(),
            chamber: chamber.into(),
            counts: BTreeMap::new(),
            votes: Vec::new(),
            repaired_rows: 0,
            citation: scan::Citation {
                repo: "il-legislation".into(),
                commit: None,
                path: "x.json".into(),
            },
        }
    }

    fn request(motion: Option<&str>, chamber: Option<&str>) -> QueryRequest {
        QueryRequest {
            kind: QueryKind::Votes,
            repos_dir: PathBuf::new(),
            tags_dir: PathBuf::new(),
            jurisdictions: Vec::new(),
            session: None,
            identifier: None,
            person: None,
            tag: None,
            min_score: None,
            min_confidence: Confidence::Medium,
            text: None,
            subject: None,
            limit: 20,
            motion: motion.map(str::to_string),
            chamber: chamber.map(str::to_string),
        }
    }

    #[test]
    fn motion_is_a_case_insensitive_substring() {
        let third = request(Some("third reading"), None);
        assert!(event_matches(&third, &event("Third Reading", "upper", "")));
        assert!(event_matches(
            &third,
            &event("Third Reading, Amendment 1", "upper", "")
        ));
        assert!(!event_matches(
            &third,
            &event("Executive Appointments", "upper", "")
        ));
    }

    #[test]
    fn chamber_accepts_senate_and_house() {
        let floor = event("Third Reading", "upper", "");
        assert!(event_matches(&request(None, Some("senate")), &floor));
        assert!(event_matches(&request(None, Some("Upper")), &floor));
        assert!(!event_matches(&request(None, Some("house")), &floor));
        assert!(event_matches(
            &request(None, Some("House")),
            &event("Motion", "lower", "")
        ));
        // An event that names no chamber never matches a chamber filter.
        assert!(!event_matches(
            &request(None, Some("upper")),
            &event("Motion", "", "")
        ));
    }

    #[test]
    fn votes_come_back_newest_first_with_undated_last() {
        let mut rows: Vec<(String, Value)> =
            ["2025-03-01", "", "2026-02-17T10:00:00+00:00", "2026-02-17"]
                .iter()
                .enumerate()
                .map(|(i, d)| (d.to_string(), json!(i)))
                .collect();
        sort_newest_first(&mut rows);
        let order: Vec<Value> = rows.into_iter().map(|(_, row)| row).collect();
        assert_eq!(order, vec![json!(2), json!(3), json!(0), json!(1)]);
    }

    #[test]
    fn pruning_keeps_the_same_rows_as_sorting_everything() {
        let dates: Vec<String> = (0..57)
            .map(|i| format!("2026-01-{:02}", (i * 7) % 28 + 1))
            .collect();
        let mut pruned = Vec::new();
        for (i, d) in dates.iter().enumerate() {
            pruned.push((d.clone(), json!(i)));
            keep_newest(&mut pruned, 5);
        }
        sort_newest_first(&mut pruned);
        pruned.truncate(5);

        let mut all: Vec<(String, Value)> = dates
            .iter()
            .enumerate()
            .map(|(i, d)| (d.clone(), json!(i)))
            .collect();
        sort_newest_first(&mut all);
        all.truncate(5);
        assert_eq!(pruned, all);
    }

    #[test]
    fn summary_counts_every_match_and_the_persons_options() {
        let mut summary = VoteSummary::default();
        let yes = names::RawVoteRow {
            voter_name: "Cunningham".into(),
            option: "yes".into(),
            note: String::new(),
        };
        let no = names::RawVoteRow {
            option: "no".into(),
            ..yes.clone()
        };
        summary.record(&event("Third Reading", "upper", "2026-03-01"), Some(&yes));
        summary.record(&event("Third Reading", "upper", "2025-05-01"), Some(&no));
        summary.record(&event("Executive", "upper", "2025-04-01"), Some(&yes));
        let json = summary.to_json();
        assert_eq!(json["by_motion"][0]["motion_text"], "Third Reading");
        assert_eq!(json["by_motion"][0]["votes"], 2);
        assert_eq!(
            json["by_motion"][0]["person_votes"],
            json!({"no": 1, "yes": 1})
        );
        assert_eq!(json["person_votes"], json!({"no": 1, "yes": 2}));
        assert_eq!(
            json["dates"],
            json!({"earliest": "2025-04-01", "latest": "2026-03-01"})
        );
        assert!(json.get("motions_not_listed").is_none());
    }

    #[test]
    fn summary_lists_the_commonest_motions_and_counts_the_rest() {
        let mut summary = VoteSummary::default();
        for i in 0..(SUMMARY_MOTIONS + 3) {
            summary.record(&event(&format!("Committee {i:02}"), "upper", ""), None);
        }
        let json = summary.to_json();
        assert_eq!(json["by_motion"].as_array().unwrap().len(), SUMMARY_MOTIONS);
        assert_eq!(json["motions_not_listed"], 3);
        assert!(json.get("person_votes").is_none());
    }

    #[test]
    fn an_empty_filtered_result_is_not_reported_as_inaction() {
        let mut floor = request(Some("third reading"), Some("senate"));
        floor.person = Some("Cunningham, Bill".into());
        let caveat = event_filter_caveat(&floor, 1761);
        assert!(caveat.contains("motion \"third reading\" and chamber \"senate\""));
        assert!(caveat.contains("1761 other vote(s) matched to \"Cunningham, Bill\""));
        assert!(caveat.contains("not evidence that they did not vote"));
    }

    #[test]
    fn motion_and_chamber_are_refused_outside_votes() {
        let mut bills = request(Some("third reading"), None);
        bills.kind = QueryKind::Bills;
        let error = run(&bills).unwrap_err().to_string();
        assert!(error.contains("`motion` only applies to votes"), "{error}");
    }
}

// ---------------------------------------------------------------------------
// People
// ---------------------------------------------------------------------------

/// Tallies for one distinct name found in the data.
#[derive(Default)]
struct PersonTally {
    /// Every way this person's name is spelled in the data, in first-seen order.
    spellings: Vec<String>,
    sponsored: usize,
    cosponsored: usize,
    votes: usize,
}

impl PersonTally {
    fn record_spelling(&mut self, raw: &str) {
        if !self.spellings.iter().any(|seen| seen == raw) {
            self.spellings.push(raw.to_string());
        }
    }
}

fn query_people(request: &QueryRequest) -> Result<(Vec<Value>, usize, Vec<String>)> {
    let caveats = vec![
        "These names are derived from sponsorship and vote records, not from a \
         legislator roster. They carry no party, district, or term information, and \
         a name appearing here is not proof that person currently holds office."
            .to_string(),
    ];

    // Keyed by normalized name, so `Smith, S` and `SMITH, S` are one person.
    let mut tallies: BTreeMap<String, PersonTally> = BTreeMap::new();
    let wanted = request.person.as_ref().map(|p| names::normalize(p));

    for jurisdiction in &request.jurisdictions {
        for session_id in sessions_in_scope(request, jurisdiction) {
            scan::for_each_bill(
                &request.repos_dir,
                jurisdiction,
                Some(&session_id),
                |bill| {
                    for sponsorship in bill.sponsorships() {
                        if !sponsorship.is_person() {
                            continue;
                        }
                        let entry = tallies
                            .entry(names::normalize(&sponsorship.name).key())
                            .or_default();
                        entry.record_spelling(&sponsorship.name);
                        if sponsorship.primary {
                            entry.sponsored += 1;
                        } else {
                            entry.cosponsored += 1;
                        }
                    }
                    for event in scan::vote_events(&bill, &request.repos_dir) {
                        for vote in &event.votes {
                            if names::is_suspect_fragment(&vote.voter_name) {
                                continue;
                            }
                            let entry = tallies
                                .entry(names::normalize(&vote.voter_name).key())
                                .or_default();
                            entry.record_spelling(&vote.voter_name);
                            entry.votes += 1;
                        }
                    }
                    Ok(ControlFlow::Continue)
                },
            )?;
        }
    }

    let mut rows: Vec<(usize, Value)> = tallies
        .into_iter()
        .filter(|(key, _)| match &wanted {
            // A name filter here is a substring search, because the caller is
            // browsing the roster rather than attributing anything to a person.
            Some(wanted) => wanted.surname().is_some_and(|s| key.contains(s)),
            None => true,
        })
        .map(|(_, tally)| {
            let activity = tally.sponsored + tally.cosponsored + tally.votes;
            let mut row = serde_json::Map::new();
            row.insert("name".into(), json!(tally.spellings.first()));
            if tally.spellings.len() > 1 {
                row.insert(
                    "also_spelled".into(),
                    json!(&tally.spellings[1..]),
                );
            }
            row.insert("sponsored".into(), json!(tally.sponsored));
            row.insert("cosponsored".into(), json!(tally.cosponsored));
            row.insert("votes".into(), json!(tally.votes));
            (activity, Value::Object(row))
        })
        .collect();

    rows.sort_by(|a, b| b.0.cmp(&a.0));
    let total = rows.len();
    let results = rows
        .into_iter()
        .take(request.limit)
        .map(|(_, row)| row)
        .collect();

    Ok((results, total, caveats))
}

// ---------------------------------------------------------------------------
// Coverage
// ---------------------------------------------------------------------------

/// What one jurisdiction's data can and cannot answer.
struct CoverageReport {
    jurisdiction: Jurisdiction,
    jurisdiction_name: Option<String>,
    sessions: Vec<String>,
    bills: usize,
    vote_events: usize,
    vote_events_with_member_votes: usize,
    member_vote_rows: usize,
    distinct_voter_names: usize,
    /// Raw spellings before normalization; higher than the headcount where a
    /// jurisdiction spells the same legislator more than one way.
    distinct_voter_spellings: usize,
    suspect_name_fragments: usize,
    split_rows_repaired: usize,
    caveats: Vec<String>,
}

impl CoverageReport {
    /// A one-word summary of whether individual votes can be attributed here.
    fn roll_call_data(&self) -> &'static str {
        if self.vote_events == 0 {
            "none"
        } else if self.vote_events_with_member_votes == 0 {
            "counts_only"
        } else {
            "available"
        }
    }

    fn to_json(&self) -> Value {
        json!({
            "jurisdiction": {
                "id": self.jurisdiction.ocd_jurisdiction_id(),
                "division_id": self.jurisdiction.ocd_division_id(),
                "name": self.jurisdiction_name,
                "locale": self.jurisdiction.locale,
            },
            "sessions": self.sessions,
            "bills": self.bills,
            "vote_events": self.vote_events,
            "vote_events_with_member_votes": self.vote_events_with_member_votes,
            "member_vote_rows": self.member_vote_rows,
            "distinct_voter_names": self.distinct_voter_names,
            "distinct_voter_spellings": self.distinct_voter_spellings,
            "suspect_name_fragments": self.suspect_name_fragments,
            "split_rows_repaired": self.split_rows_repaired,
            "roll_call_data": self.roll_call_data(),
        })
    }
}

fn coverage_for(request: &QueryRequest, jurisdiction: &Jurisdiction) -> Result<CoverageReport> {
    let mut report = CoverageReport {
        jurisdiction: jurisdiction.clone(),
        jurisdiction_name: None,
        sessions: sessions_in_scope(request, jurisdiction),
        bills: 0,
        vote_events: 0,
        vote_events_with_member_votes: 0,
        member_vote_rows: 0,
        distinct_voter_names: 0,
        distinct_voter_spellings: 0,
        suspect_name_fragments: 0,
        split_rows_repaired: 0,
        caveats: Vec::new(),
    };

    let mut voters = NameIndex::new();
    for session_id in report.sessions.clone() {
        scan::for_each_bill(
            &request.repos_dir,
            jurisdiction,
            Some(&session_id),
            |bill| {
                report.bills += 1;
                if report.jurisdiction_name.is_none() {
                    report.jurisdiction_name = bill.jurisdiction_name();
                }
                for event in scan::vote_events(&bill, &request.repos_dir) {
                    report.vote_events += 1;
                    report.split_rows_repaired += event.repaired_rows;
                    if event.has_member_votes() {
                        report.vote_events_with_member_votes += 1;
                        report.member_vote_rows += event.votes.len();
                        for vote in &event.votes {
                            voters.insert(&vote.voter_name);
                        }
                    }
                }
                Ok(ControlFlow::Continue)
            },
        )?;
    }
    report.distinct_voter_names = voters.distinct_people();
    report.distinct_voter_spellings = voters.distinct_raw_spellings();
    report.suspect_name_fragments = voters.suspect_fragment_count();

    let name = report
        .jurisdiction_name
        .clone()
        .unwrap_or_else(|| jurisdiction.locale.to_uppercase());

    match report.roll_call_data() {
        "none" => report.caveats.push(format!(
            "{name} publishes no roll-call votes in this dataset ({} bills, 0 vote \
             events). Sponsorship is the only available evidence. Do not describe \
             this as a legislator not having voted on something.",
            report.bills
        )),
        "counts_only" => report.caveats.push(format!(
            "{name} publishes vote totals but not how individuals voted ({} vote \
             events, 0 member rows). Report the tallies; do not attribute a vote to \
             any person.",
            report.vote_events
        )),
        _ => {}
    }

    if report.suspect_name_fragments > 0 {
        report.caveats.push(format!(
            "{name} has {} voter names that look like upstream parsing debris — \
             one- or two-letter fragments left when a name such as \"Brown, L.\" was \
             split on its comma. {} rows were rejoined; anything still fragmentary is \
             excluded from attribution and from counts.",
            report.suspect_name_fragments, report.split_rows_repaired
        ));
    }

    Ok(report)
}

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

fn sessions_in_scope(request: &QueryRequest, jurisdiction: &Jurisdiction) -> Vec<String> {
    let available = scan::sessions(&request.repos_dir, jurisdiction);
    match &request.session {
        Some(wanted) => available.into_iter().filter(|s| s == wanted).collect(),
        None => available,
    }
}

/// A first pass over sponsorship names, so a surname can be told unique from
/// ambiguous before anything is attributed.
fn build_sponsor_index(request: &QueryRequest) -> Result<NameIndex> {
    let mut index = NameIndex::new();
    for jurisdiction in &request.jurisdictions {
        for session_id in sessions_in_scope(request, jurisdiction) {
            scan::for_each_bill(
                &request.repos_dir,
                jurisdiction,
                Some(&session_id),
                |bill| {
                    for sponsorship in bill.sponsorships() {
                        if sponsorship.is_person() {
                            index.insert(&sponsorship.name);
                        }
                    }
                    for bioguide in bill.sponsor_bioguides() {
                        if let Some(primary) =
                            bill.sponsorships().iter().find(|s| s.is_person())
                        {
                            index.insert_identifier(&bioguide, &primary.name);
                        }
                    }
                    Ok(ControlFlow::Continue)
                },
            )?;
        }
    }
    Ok(index)
}

/// The same first pass, over voter names.
fn build_voter_index(request: &QueryRequest) -> Result<NameIndex> {
    let mut index = NameIndex::new();
    for jurisdiction in &request.jurisdictions {
        for session_id in sessions_in_scope(request, jurisdiction) {
            scan::for_each_bill(
                &request.repos_dir,
                jurisdiction,
                Some(&session_id),
                |bill| {
                    for event in scan::vote_events(&bill, &request.repos_dir) {
                        for vote in &event.votes {
                            index.insert(&vote.voter_name);
                            // Federal rows carry the bioguide id in `note`, which
                            // is the one exact join this data offers.
                            if !vote.note.is_empty() {
                                index.insert_identifier(&vote.note, &vote.voter_name);
                            }
                        }
                    }
                    Ok(ControlFlow::Continue)
                },
            )?;
        }
    }
    Ok(index)
}

/// Turn a name match into something a caller can act on honestly.
fn describe_match(query: &str, resolved: &NameMatch, minimum: Confidence) -> Vec<String> {
    match resolved.method {
        MatchMethod::Ambiguous => vec![format!(
            "\"{query}\" matches {} people in this data: {}. Nothing has been \
             attributed. Ask which one is meant, then query that exact name.",
            resolved.candidates.len(),
            resolved.candidates.join(", ")
        )],
        MatchMethod::Unmatched => vec![format!(
            "\"{query}\" does not appear in the sponsorship or vote records for the \
             jurisdictions searched. This means the name was not found, not that the \
             person took no action. Check the spelling, or use `govbot query people` \
             to see the names that are present."
        )],
        _ if !resolved.is_attributable(minimum) => vec![format!(
            "\"{query}\" matched with {:?} confidence, below the requested minimum of \
             {:?}, so nothing has been attributed.",
            resolved.confidence, minimum
        )],
        MatchMethod::UniqueSurname | MatchMethod::SurnameInitial => vec![format!(
            "\"{query}\" was matched to \"{}\" by name alone — govbot has no \
             legislator roster, so this is a name match rather than a verified \
             identity. Say so when reporting it.",
            resolved.candidates.join(", ")
        )],
        _ => Vec::new(),
    }
}

fn truncate(text: &str, max_chars: usize) -> String {
    if text.chars().count() <= max_chars {
        return text.to_string();
    }
    let mut truncated: String = text.chars().take(max_chars).collect();
    truncated.push('…');
    truncated
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn text_search_matches_whole_words_only() {
        let haystack = "appoint-trenton taber rent-control and tenant rights".to_lowercase();
        // The bug this guards: "rent" must not match "Trenton".
        assert!(!contains_word(&haystack, "trent"));
        assert!(contains_word(&haystack, "rent"));
        assert!(contains_word(&haystack, "trenton"));
        assert!(contains_word(&haystack, "tenant"));
        assert!(!contains_word(&haystack, "tenants"));
        // Hyphens are boundaries, so a hyphenated compound is searchable by part.
        assert!(contains_word(&haystack, "control"));
        assert!(contains_word(&haystack, "appoint"));
    }

    #[test]
    fn text_search_handles_multibyte_without_panicking() {
        let haystack = "protección de inquilinos ñ".to_lowercase();
        assert!(contains_word(&haystack, "inquilinos"));
        assert!(!contains_word(&haystack, "quilin"));
    }

    #[test]
    fn parses_query_kinds() {
        assert_eq!(QueryKind::parse("bills"), Some(QueryKind::Bills));
        assert_eq!(QueryKind::parse("VOTES"), Some(QueryKind::Votes));
        assert_eq!(QueryKind::parse("people"), Some(QueryKind::People));
        assert_eq!(QueryKind::parse("coverage"), Some(QueryKind::Coverage));
        assert_eq!(QueryKind::parse("nonsense"), None);
    }

    #[test]
    fn truncates_on_character_boundaries() {
        assert_eq!(truncate("short", 10), "short");
        assert_eq!(truncate("abcdefghij", 5), "abcde…");
        // Multi-byte input must not panic or split a character.
        assert_eq!(truncate("ñññññ", 2), "ññ…");
    }

    #[test]
    fn ambiguity_produces_an_actionable_caveat() {
        let resolved = NameMatch {
            method: MatchMethod::Ambiguous,
            confidence: Confidence::None,
            candidates: vec!["Brown, G".into(), "Brown, L".into()],
        };
        let caveats = describe_match("Brown", &resolved, Confidence::Medium);
        assert_eq!(caveats.len(), 1);
        assert!(caveats[0].contains("Nothing has been attributed"));
        assert!(caveats[0].contains("Brown, G"));
    }

    /// The distinction the whole command exists to preserve.
    #[test]
    fn an_unmatched_name_is_not_reported_as_inaction() {
        let resolved = NameMatch {
            method: MatchMethod::Unmatched,
            confidence: Confidence::None,
            candidates: Vec::new(),
        };
        let caveats = describe_match("Nobody", &resolved, Confidence::Medium);
        assert!(caveats[0].contains("not that the person took no action"));
    }

    #[test]
    fn a_name_only_match_says_so() {
        let resolved = NameMatch {
            method: MatchMethod::UniqueSurname,
            confidence: Confidence::Medium,
            candidates: vec!["Filer".into()],
        };
        let caveats = describe_match("Filer", &resolved, Confidence::Medium);
        assert!(caveats[0].contains("no legislator roster"));
    }

    #[test]
    fn a_high_confidence_match_needs_no_caveat() {
        let resolved = NameMatch {
            method: MatchMethod::ExactName,
            confidence: Confidence::High,
            candidates: vec!["Cunningham, Bill".into()],
        };
        assert!(describe_match("Bill Cunningham", &resolved, Confidence::Medium).is_empty());
    }
}
