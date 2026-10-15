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
use std::collections::{BTreeMap, HashSet};
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
}

#[derive(Debug, Serialize)]
pub struct Truncation {
    pub returned: usize,
    pub total_matching: usize,
    pub limit: usize,
}

/// Run a query.
pub fn run(request: &QueryRequest) -> Result<QueryResponse> {
    // People and coverage have no topic filter. Running anyway would echo the
    // `tag` back in `query` while ignoring it, which reads as "filtered by topic".
    if matches!(request.kind, QueryKind::People | QueryKind::Coverage) {
        for (flag, given) in [("tag", request.tag.is_some()), ("min_score", request.min_score.is_some())] {
            if given {
                anyhow::bail!(
                    "`{flag}` is not supported for {} queries. Use `query bills` or `query \
                     votes` with `tag` for topic results, or drop `{flag}`.",
                    request.kind.as_str()
                );
            }
        }
    }

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

    let (results, total_matching, extra_caveats) = match request.kind {
        QueryKind::Bills => query_bills(request)?,
        QueryKind::Votes => query_votes(request)?,
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
    /// Bills scored for this topic, matched or not. `None` for tag files written
    /// before `govbot tag` recorded `scored_bills`: coverage unknown.
    scored: Option<HashSet<String>>,
}

impl TagScores {
    /// `Ok(None)` when there is no tag file: the session has not been scored for
    /// this topic. A file that exists but cannot be read or parsed is an error
    /// naming it. Treating it as unscored would hide the damage and advise a re-run
    /// that, for a hand-edited or truncated file, may not be what the person wants.
    fn load(
        request: &QueryRequest,
        jurisdiction: &Jurisdiction,
        session_id: &str,
    ) -> Result<Option<Self>> {
        let Some(tag) = request.tag.as_ref() else {
            return Ok(None);
        };
        let path = request
            .tags_dir
            .join("country:us")
            .join(format!("state:{}", jurisdiction.path_segment()))
            .join("sessions")
            .join(session_id)
            .join("tags")
            .join(format!("{tag}.tag.json"));

        let raw = match std::fs::read_to_string(&path) {
            Ok(raw) => raw,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(error) => anyhow::bail!("Could not read tag file {}: {error}", path.display()),
        };
        let value: Value = serde_json::from_str(&raw).map_err(|error| {
            anyhow::anyhow!(
                "Tag file {} is not valid JSON: {error}. Fix or delete it, then run \
                 `govbot tag` again.",
                path.display()
            )
        })?;

        let threshold = value
            .get("tag_config")
            .and_then(|config| config.get("threshold"))
            .and_then(Value::as_f64)
            .unwrap_or(0.5);

        let by_bill: BTreeMap<String, Value> = value
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

        // A bill with a score was scored even if `scored_bills` omits it (a run
        // interrupted between writing a match and recording what it scored).
        let scored = value
            .get("scored_bills")
            .and_then(Value::as_array)
            .map(|ids| {
                ids.iter()
                    .filter_map(Value::as_str)
                    .map(str::to_string)
                    .chain(by_bill.keys().cloned())
                    .collect()
            });

        Ok(Some(Self {
            threshold,
            by_bill,
            scored,
        }))
    }

    /// `None` when the file predates `scored_bills`.
    fn was_scored(&self, bill: &BillRecord) -> Option<bool> {
        let scored = self.scored.as_ref()?;
        Some(scored.contains(&bill.identifier) || scored.contains(&bill.bill_id))
    }

    fn score_for(&self, bill: &BillRecord) -> Option<&Value> {
        self.by_bill
            .get(&bill.identifier)
            .or_else(|| self.by_bill.get(&bill.bill_id))
    }
}

/// The topic names `govbot.yml` defines, if there is a `govbot.yml` beside the tag
/// files.
///
/// `None` means there is no config to check against — `--tags-dir` can point at
/// bare `govbot tag` output — in which case an unknown topic simply finds no tag
/// files and every scope reports itself unscored.
fn defined_topics(tags_dir: &std::path::Path) -> Result<Option<Vec<String>>> {
    let path = tags_dir.join("govbot.yml");
    let raw = match std::fs::read_to_string(&path) {
        Ok(raw) => raw,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => anyhow::bail!("Could not read {}: {error}", path.display()),
    };
    // `query bills --tag` reads this file only to learn which topics exist, but a
    // broken one stops every topic query, so the error says which file and what
    // to fix rather than just "parse error".
    let config: serde_yaml::Value = serde_yaml::from_str(&raw).map_err(|error| {
        anyhow::anyhow!(
            "{} is not valid YAML, so the topics it defines cannot be checked: {error}. \
             Fix the YAML in that file; until then no topic query can run.",
            path.display()
        )
    })?;
    let mut topics: Vec<String> = match config.get("tags") {
        // No `tags:` at all: a workspace with no topics yet.
        None | Some(serde_yaml::Value::Null) => Vec::new(),
        Some(serde_yaml::Value::Mapping(tags)) => tags
            .keys()
            .filter_map(|key| key.as_str().map(str::to_string))
            .collect(),
        Some(_) => anyhow::bail!(
            "In {}, `tags:` must map each topic name to its definition, but it is not a \
             mapping. Fix that file; until then no topic query can run.",
            path.display()
        ),
    };
    topics.sort();
    Ok(Some(topics))
}

// ---------------------------------------------------------------------------
// Bills
// ---------------------------------------------------------------------------

/// A misspelled or invented topic ("renters" for "renter protections") finds no
/// tag files anywhere, so every scope would report itself "not scored yet" and
/// hide the real mistake. Failing with the defined names lets the caller retry
/// with the right one.
fn ensure_topic_defined(request: &QueryRequest) -> Result<()> {
    if let Some(tag) = request.tag.as_deref() {
        if let Some(topics) = defined_topics(&request.tags_dir)? {
            if !topics.iter().any(|topic| topic == tag) {
                let defined = if topics.is_empty() {
                    format!("none ({} has no `tags:` entries)", request.tags_dir.join("govbot.yml").display())
                } else {
                    topics.join(", ")
                };
                anyhow::bail!("No topic named '{tag}'. Defined topics: {defined}");
            }
        }
    }
    Ok(())
}

/// No tag file means nobody has scored this session for this topic. (`govbot
/// tag` writes one for every session it scores, matches or not.) The scope then
/// contributes nothing: returning its bills or votes unfiltered would present
/// every one of them as on topic.
fn unscored_caveat(
    request: &QueryRequest,
    jurisdiction: &Jurisdiction,
    session_id: &str,
    tag: &str,
) -> Result<String> {
    Ok(format!(
        "{} ({}) has not been scored for '{}' yet, so it contributes no \
         results. This is missing data, not an empty record. Run `govbot \
         tag` (tag_with_local_ai in Claude Desktop) for {}.",
        jurisdiction_display_name(request, jurisdiction, session_id)?,
        session_id,
        tag,
        jurisdiction.locale
    ))
}

/// The bill's topic score if it clears `--min-score` (default: the topic's own
/// threshold); `None` if it has no score or falls below.
fn topic_score(request: &QueryRequest, scores: &TagScores, bill: &BillRecord) -> Option<(f64, Value)> {
    let score = scores.score_for(bill)?;
    let final_score = score.get("final_score").and_then(Value::as_f64).unwrap_or(0.0);
    let floor = request.min_score.unwrap_or(scores.threshold);
    (final_score >= floor).then(|| (final_score, score.clone()))
}

fn query_bills(request: &QueryRequest) -> Result<(Vec<Value>, usize, Vec<String>)> {
    let mut caveats = Vec::new();

    ensure_topic_defined(request)?;

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
            let scores = TagScores::load(request, jurisdiction, &session_id)?;
            if let (Some(tag), None) = (request.tag.as_deref(), scores.as_ref()) {
                caveats.push(unscored_caveat(request, jurisdiction, &session_id, tag)?);
                continue;
            }

            // Of the bills the tag filter is applied to (those passing every other
            // filter), how many were scored. Only meaningful with a tag file that
            // records `scored_bills`.
            let mut candidates = 0usize;
            let mut scored_candidates = 0usize;

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
                            let Some(found) =
                                matching_sponsorship(&bill, resolved, request.person.as_deref())
                            else {
                                return Ok(ControlFlow::Continue);
                            };
                            Some(found)
                        }
                        None => None,
                    };

                    let score = match scores.as_ref() {
                        Some(scores) => {
                            candidates += 1;
                            if scores.was_scored(&bill) == Some(true) {
                                scored_candidates += 1;
                            }
                            let Some(score) = topic_score(request, scores, &bill) else {
                                return Ok(ControlFlow::Continue);
                            };
                            Some(score)
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

            if let (Some(tag), Some(scores)) = (request.tag.as_deref(), scores.as_ref()) {
                if let Some(caveat) = coverage_caveat(
                    request,
                    jurisdiction,
                    &session_id,
                    tag,
                    "bills",
                    scores.scored.is_some(),
                    scored_candidates,
                    candidates,
                )? {
                    caveats.push(caveat);
                }
            }
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

/// The caveat for a scored session whose coverage is partial or unknown; `None`
/// when every bill in scope was scored.
///
/// Partial is the normal case: tag_with_local_ai reads a few hundred log entries
/// per jurisdiction, and a large session has thousands of bills. Without this, "3
/// matches" from a session where 3 of 18,380 bills were scored reads as complete.
/// The wording follows tag_with_local_ai's own coverage report.
fn coverage_caveat(
    request: &QueryRequest,
    jurisdiction: &Jurisdiction,
    session_id: &str,
    tag: &str,
    // What was counted: "bills", or for votes "bills with recorded votes".
    noun: &str,
    tracked: bool,
    scored: usize,
    total: usize,
) -> Result<Option<String>> {
    // `total == 0`: nothing in scope (an empty session, or other filters excluded
    // everything), so there is nothing that could be missing.
    if total == 0 || (tracked && scored >= total) {
        return Ok(None);
    }
    let name = jurisdiction_display_name(request, jurisdiction, session_id)?;
    // Other filters (text, subject, identifier, person) shrink the set the topic is
    // checked against; say so, so the count is not read as the session's size.
    let narrowed = request.identifier.is_some()
        || request.subject.is_some()
        || request.text.is_some()
        || request.person.is_some();
    let in_scope = if narrowed { " matching the other filters" } else { "" };
    if !tracked {
        return Ok(Some(format!(
            "{name} ({session_id}) was tagged for '{tag}' before govbot recorded which \
             bills it scored, so coverage is unknown: some of its {} {noun}{in_scope} may \
             never have been checked, and are missing from these results rather than \
             non-matching. Run `govbot tag` (tag_with_local_ai in Claude Desktop) for {} \
             again to record coverage, or use `query` with `text` to search every bill.",
            thousands(total),
            jurisdiction.locale
        )));
    }
    Ok(Some(format!(
        "{} of {} {noun}{in_scope} in {name} ({session_id}) have been scored for '{tag}'. \
         The other {} were not checked, so they are missing from these results, not \
         non-matching. Use `query` with `text` to search every bill, or run `govbot tag` \
         (tag_with_local_ai in Claude Desktop) for {} with a higher limit.",
        thousands(scored),
        thousands(total),
        thousands(total - scored),
        jurisdiction.locale
    )))
}

/// 12780 -> "12,780", matching how tag_with_local_ai prints counts.
fn thousands(n: usize) -> String {
    let digits = n.to_string();
    let mut out = String::new();
    for (i, c) in digits.chars().enumerate() {
        if i > 0 && (digits.len() - i) % 3 == 0 {
            out.push(',');
        }
        out.push(c);
    }
    out
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

fn matching_sponsorship(
    bill: &BillRecord,
    resolved: &NameMatch,
    person: Option<&str>,
) -> Option<scan::Sponsorship> {
    // Asked by member id: the id itself must be on the bill. Matching the name it
    // resolved to instead would pick up a namesake's bills (another jurisdiction,
    // say) and miss the member's bills under a second spelling (`Bernie Sanders` /
    // `Bernard Sanders` are both S000033).
    if resolved.method == MatchMethod::Bioguide {
        let id = person.unwrap_or_default().trim().to_uppercase();
        return bill
            .sponsorships_by_id()
            .into_iter()
            .find(|(bioguide, _)| *bioguide == id)
            .map(|(_, sponsorship)| sponsorship);
    }
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

fn query_votes(request: &QueryRequest) -> Result<(Vec<Value>, usize, Vec<String>)> {
    let mut caveats = Vec::new();

    ensure_topic_defined(request)?;

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
            return Ok((Vec::new(), 0, caveats));
        }
    }

    // (topic score, start date, row). Without a tag, rows stay in scan order and
    // stop accumulating at the limit. With one, every on-topic row is kept so the
    // most on-topic votes can be ranked first; that set is small.
    let mut results: Vec<(f64, String, Value)> = Vec::new();
    let mut total = 0usize;
    // Bills on the topic (passing every other filter too), for saying so when none
    // of them had a recorded vote.
    let mut tagged_bills = 0usize;

    for jurisdiction in &request.jurisdictions {
        for session_id in sessions_in_scope(request, jurisdiction) {
            // The tag step mirrors `query_bills`: an unscored session contributes no
            // rows, and a partly scored one says how much was checked.
            let scores = TagScores::load(request, jurisdiction, &session_id)?;
            if let (Some(tag), None) = (request.tag.as_deref(), scores.as_ref()) {
                caveats.push(unscored_caveat(request, jurisdiction, &session_id, tag)?);
                continue;
            }
            // Coverage is counted over bills with at least one vote in scope (one
            // cast by `person`, if given): a bill with no roll call could not have
            // added a row whether it was scored or not.
            let mut candidates = 0usize;
            let mut scored_candidates = 0usize;

            scan::for_each_bill(
                &request.repos_dir,
                jurisdiction,
                Some(&session_id),
                |bill| {
                    if !bill_matches(request, &bill) {
                        return Ok(ControlFlow::Continue);
                    }
                    // `None`: no tag. `Some(None)`: tagged, but this bill is not on
                    // the topic, so its votes only count toward coverage.
                    let topic = scores.as_ref().map(|scores| topic_score(request, scores, &bill));
                    if let Some(Some(_)) = topic {
                        tagged_bills += 1;
                    }
                    let mut events_in_scope = 0usize;
                    for event in scan::vote_events(&bill, &request.repos_dir) {
                        let person_vote = match person_match.as_ref() {
                            Some(resolved) => {
                                let scope = vote_scope(jurisdiction, &event.chamber, &session_id);
                                let Some(found) = matching_vote(
                                    &event,
                                    resolved,
                                    request.min_confidence,
                                    scope.as_deref(),
                                ) else {
                                    continue;
                                };
                                Some(found)
                            }
                            None => None,
                        };
                        events_in_scope += 1;
                        if let Some(None) = topic {
                            continue;
                        }
                        total += 1;
                        if topic.is_some() || results.len() < request.limit {
                            let mut row = vote_row(
                                &bill,
                                &event,
                                person_vote,
                                person_match.as_ref(),
                            );
                            let rank = match &topic {
                                Some(Some((final_score, _))) => {
                                    row["topic_score"] = json!(final_score);
                                    *final_score
                                }
                                _ => 0.0,
                            };
                            results.push((rank, event.start_date.clone(), row));
                        }
                    }
                    if let (Some(scores), true) = (scores.as_ref(), events_in_scope > 0) {
                        candidates += 1;
                        if scores.was_scored(&bill) == Some(true) {
                            scored_candidates += 1;
                        }
                    }
                    Ok(ControlFlow::Continue)
                },
            )?;

            if let (Some(tag), Some(scores)) = (request.tag.as_deref(), scores.as_ref()) {
                if let Some(caveat) = coverage_caveat(
                    request,
                    jurisdiction,
                    &session_id,
                    tag,
                    "bills with recorded votes",
                    scores.scored.is_some(),
                    scored_candidates,
                    candidates,
                )? {
                    caveats.push(caveat);
                }
            }
        }
    }

    if let Some(tag) = request.tag.as_deref() {
        // Most bills never reach a roll call. Without this, an empty result reads
        // as the legislator having avoided the topic.
        if tagged_bills > 0 && total == 0 {
            let by = match request.person.as_deref() {
                Some(person) => format!(" that includes {person}"),
                None => String::new(),
            };
            caveats.push(format!(
                "{} {} tagged for '{tag}' in scope, but none has a recorded vote{by}. \
                 Most bills never reach a roll call, so this says nothing about how \
                 anyone stands on the topic.",
                thousands(tagged_bills),
                if tagged_bills == 1 { "bill is" } else { "bills are" },
            ));
        }
        // Most on-topic first; among equal scores (votes on one bill), the latest
        // vote first, since that is usually the decisive one (final passage).
        results.sort_by(|a, b| {
            b.0.partial_cmp(&a.0)
                .unwrap_or(std::cmp::Ordering::Equal)
                .then_with(|| b.1.cmp(&a.1))
        });
    }
    let results = results
        .into_iter()
        .take(request.limit)
        .map(|(_, _, row)| row)
        .collect();

    Ok((results, total, caveats))
}

/// The row in `event` cast by the resolved person, if any. A surname-only
/// spelling counts only when it was linked in this event's `scope` (see
/// [`vote_scope`]) and its medium confidence meets the caller's minimum. A row
/// carrying a member id counts only when the id is the person's.
fn matching_vote(
    event: &VoteEventRecord,
    resolved: &NameMatch,
    minimum: Confidence,
    scope: Option<&str>,
) -> Option<names::RawVoteRow> {
    event
        .votes
        .iter()
        .find(|row| {
            resolved
                .confidence_for_row(row, scope)
                .is_some_and(|c| c >= minimum && c > Confidence::None)
        })
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

    // A row reached through a surname-only spelling reports its own, lower
    // confidence rather than the full-name match's.
    let row_match = match (person_match, &person_vote) {
        (Some(resolved), Some(vote)) => Some(resolved.for_spelling(&vote.voter_name)),
        (resolved, _) => resolved.cloned(),
    };
    if let Some(vote) = person_vote {
        let mut entry = serde_json::Map::new();
        entry.insert("voter_name".into(), json!(vote.voter_name));
        entry.insert("option".into(), json!(vote.option));
        if !vote.note.is_empty() {
            entry.insert("note".into(), json!(vote.note));
        }
        row.insert("person_vote".into(), Value::Object(entry));
    }
    if let Some(resolved) = row_match {
        row.insert("match".into(), json!(resolved));
    }
    if event.repaired_rows > 0 {
        row.insert("split_rows_repaired".into(), json!(event.repaired_rows));
    }

    row.insert("citation".into(), json!(event.citation));
    Value::Object(row)
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
    /// `votes`, split by [`vote_scope`], so a bare surname's votes can be folded
    /// into a full name one scope at a time. Votes with no scope are not here.
    votes_by_scope: BTreeMap<String, usize>,
    /// Bare-surname spellings folded in by `NameIndex::surname_links`.
    surname_only_spellings: Vec<String>,
    /// The member id this person's vote rows carry (Congress only).
    member_id: Option<String>,
}

impl PersonTally {
    fn record_spelling(&mut self, raw: &str) {
        if !self.spellings.iter().any(|seen| seen == raw) {
            self.spellings.push(raw.to_string());
        }
    }
}

fn query_people(request: &QueryRequest) -> Result<(Vec<Value>, usize, Vec<String>)> {
    let mut caveats = vec![
        "These names are derived from sponsorship and vote records, not from a \
         legislator roster. They carry no party, district, or term information, and \
         a name appearing here is not proof that person currently holds office."
            .to_string(),
    ];

    // Keyed by `names::identity_key`, so `Smith, S` and `SMITH, S` are one
    // person, and `Kelly (IL)` and `Kelly (PA)` are two.
    let mut tallies: BTreeMap<String, PersonTally> = BTreeMap::new();
    let wanted = request.person.as_ref().map(|p| names::normalize(p));
    // Built alongside the tallies so bare surnames can be linked afterwards, with
    // the same rule `query votes` uses.
    let mut index = NameIndex::new();

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
                            .entry(names::identity_key(&sponsorship.name, None))
                            .or_default();
                        entry.record_spelling(&sponsorship.name);
                        index.insert(&sponsorship.name);
                        if sponsorship.primary {
                            entry.sponsored += 1;
                        } else {
                            entry.cosponsored += 1;
                        }
                    }
                    for event in scan::vote_events(&bill, &request.repos_dir) {
                        let scope = vote_scope(jurisdiction, &event.chamber, &session_id);
                        for vote in &event.votes {
                            if names::is_suspect_fragment(&vote.voter_name) {
                                continue;
                            }
                            index.insert_vote(&vote.voter_name, scope.as_deref(), &vote.note);
                            let id = names::member_id(&vote.note);
                            let entry = tallies
                                .entry(names::identity_key(&vote.voter_name, id.as_deref()))
                                .or_default();
                            entry.record_spelling(&vote.voter_name);
                            entry.member_id = id;
                            entry.votes += 1;
                            if let Some(scope) = &scope {
                                *entry.votes_by_scope.entry(scope.clone()).or_default() += 1;
                            }
                        }
                    }
                    Ok(ControlFlow::Continue)
                },
            )?;
        }
    }

    // Fold each linkable bare surname (`Cunningham`) into the one full-named
    // person it belongs to (`Cunningham, Bill`), so one legislator is one row.
    // Only the bare spelling's votes in scopes where the link holds move; the
    // same `Peters` in Congress stays its own row. Sponsorships carry no scope,
    // so they never move. The link is medium confidence, so a higher minimum
    // leaves every row as the data spells it, matching `query votes`.
    let fold = request.min_confidence <= Confidence::Medium;
    let mut withheld = false;
    let bare_keys: Vec<String> = tallies
        .keys()
        .filter(|key| !key.contains(' '))
        .cloned()
        .collect();
    for bare_key in bare_keys {
        let mut bare = tallies.remove(&bare_key).expect("key came from the map");
        for link in index.surname_links(&bare_key) {
            let Some(person) = tallies.get_mut(&link.person_key) else {
                continue;
            };
            let Some(&moved) = bare.votes_by_scope.get(&link.scope) else {
                continue;
            };
            if !fold {
                withheld = true;
                continue;
            }
            bare.votes_by_scope.remove(&link.scope);
            bare.votes -= moved;
            person.votes += moved;
            for spelling in &link.bare_spellings {
                person.record_spelling(spelling);
                if !person.surname_only_spellings.contains(spelling) {
                    person.surname_only_spellings.push(spelling.clone());
                }
            }
        }
        if bare.votes + bare.sponsored + bare.cosponsored > 0 {
            tallies.insert(bare_key, bare);
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
            if !tally.surname_only_spellings.is_empty() {
                row.insert(
                    "surname_only_spellings".into(),
                    json!(tally.surname_only_spellings),
                );
            }
            if let Some(id) = &tally.member_id {
                row.insert("member_id".into(), json!(id));
            }
            row.insert("sponsored".into(), json!(tally.sponsored));
            row.insert("cosponsored".into(), json!(tally.cosponsored));
            row.insert("votes".into(), json!(tally.votes));
            (activity, Value::Object(row))
        })
        .collect();

    rows.sort_by(|a, b| b.0.cmp(&a.0));
    let total = rows.len();
    let results: Vec<Value> = rows
        .into_iter()
        .take(request.limit)
        .map(|(_, row)| row)
        .collect();

    if results.iter().any(|row| row.get("surname_only_spellings").is_some()) {
        caveats.push(
            "Rows with `surname_only_spellings` combine a full name with records that \
             print only the surname (e.g. Illinois floor votes say \"Cunningham\" where \
             committee votes say \"Cunningham, Bill\"). They were combined because only \
             one legislator with that surname appears with a full name in the same \
             chamber and session; that link is by surname only (medium confidence)."
                .to_string(),
        );
    }
    if withheld {
        caveats.push(format!(
            "Some names appear twice: once in full (\"Cunningham, Bill\") and once \
             as a bare surname (\"Cunningham\", as Illinois floor votes print it). \
             They were not combined, because that link is by surname only (medium \
             confidence), below the requested minimum of {:?}.",
            request.min_confidence
        ));
    }

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
                            voters.insert_vote(&vote.voter_name, None, &vote.note);
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

/// The scope a bare surname is linked to a full name within (see
/// `NameIndex::surname_links`): one jurisdiction's chamber in one session.
///
/// `None` when the vote event names no chamber. Without it a House `Johnson`
/// and a Senate `Johnson` would share one scope, so such rows are never linked.
fn vote_scope(jurisdiction: &Jurisdiction, chamber: &str, session_id: &str) -> Option<String> {
    let chamber = chamber.trim();
    if chamber.is_empty() {
        return None;
    }
    Some(format!("{jurisdiction}|{chamber}|{session_id}"))
}

/// A jurisdiction's name as its data spells it ("Illinois"), read from the first
/// bill in the session; the upper-cased locale when the session has no bills.
fn jurisdiction_display_name(
    request: &QueryRequest,
    jurisdiction: &Jurisdiction,
    session_id: &str,
) -> Result<String> {
    let mut name = None;
    scan::for_each_bill(&request.repos_dir, jurisdiction, Some(session_id), |bill| {
        name = bill.jurisdiction_name();
        Ok(ControlFlow::Stop)
    })?;
    Ok(name.unwrap_or_else(|| jurisdiction.locale.to_uppercase()))
}

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
                    for (bioguide, sponsorship) in bill.sponsorships_by_id() {
                        index.insert_identifier(&bioguide, &sponsorship.name);
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
                        // Scope for `NameIndex::surname_links`: a bare surname is
                        // only linked to a full name seen in the same jurisdiction,
                        // chamber and session.
                        let scope = vote_scope(jurisdiction, &event.chamber, &session_id);
                        // Federal rows carry the member id in `note`, which is
                        // the one exact join this data offers; it decides who
                        // is who (see `names::identity_key`).
                        for vote in &event.votes {
                            index.insert_vote(&vote.voter_name, scope.as_deref(), &vote.note);
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
        MatchMethod::Ambiguous => {
            let mut caveat = format!(
                "\"{query}\" matches {} people in this data: {}. Nothing has been \
                 attributed. Ask which one is meant, then query that exact name.",
                resolved.candidates.len(),
                resolved.candidates.join(", ")
            );
            // Congress's roll calls carry no given names, so "Mike Kelly" can only
            // be told apart by the state in the record's own spelling.
            if resolved.candidates.iter().any(|c| c.contains('(')) {
                caveat.push_str(
                    " In Congress's records the parentheses hold the member's state \
                     (House, e.g. \"Kelly (PA)\") or party and state (Senate, e.g. \
                     \"Kelly (D-AZ)\"); use the state the person gave you, or ask for it.",
                );
            }
            if resolved.candidates.iter().any(|c| c.contains('[')) {
                caveat.push_str(
                    " A bracketed code is a member id, shown where the name alone can't \
                     pick out that member (two members recorded under one name, such as \
                     a member and their successor); query the label as listed.",
                );
            }
            vec![caveat]
        }
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
    .into_iter()
    .chain(describe_surname_link(resolved, minimum))
    .chain(describe_unlinked(resolved, minimum))
    .collect()
}

/// Say so when bare-surname rows sit beside this person but couldn't be linked
/// to them, since those rows may well be theirs.
fn describe_unlinked(resolved: &NameMatch, minimum: Confidence) -> Option<String> {
    if resolved.unlinked_surname_only_spellings.is_empty() || !resolved.is_attributable(minimum)
    {
        return None;
    }
    Some(format!(
        "Some records in the same chamber and session as \"{}\" print only the \
         surname (\"{}\") and were left out: more than one legislator with that \
         surname appears there, or the source marked the name in a way govbot can't \
         check, so they can't be attributed by name. This may leave out floor votes.",
        resolved.candidates.join("\", \""),
        resolved.unlinked_surname_only_spellings.join("\", \"")
    ))
}

/// Say so when rows were (or, below the minimum, were not) included through a
/// surname-only spelling, since that is a weaker link than the match itself.
fn describe_surname_link(resolved: &NameMatch, minimum: Confidence) -> Option<String> {
    if resolved.surname_only_spellings.is_empty() || !resolved.is_attributable(minimum) {
        return None;
    }
    let linked = resolved.surname_only_spellings.join("\", \"");
    let matched = resolved.candidates.join("\", \"");
    if MatchMethod::SurnameOnlySpelling.confidence() >= minimum {
        Some(format!(
            "\"{matched}\" and \"{linked}\" were treated as the same legislator and \
             both were included. One of them is a surname-only spelling (Illinois floor \
             votes, for example, print only the surname), and only one legislator with \
             that surname appears with a full name in the same chamber and session. \
             Rows for \"{linked}\" are a surname match, so they have medium \
             confidence. Say so when reporting them."
        ))
    } else {
        Some(format!(
            "Records spelled \"{linked}\" are probably the same legislator as \
             \"{matched}\", but were left out because that link is by surname only \
             (medium confidence), below the requested minimum of {minimum:?}. This may \
             leave out floor votes."
        ))
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
    use std::collections::BTreeSet;

    fn usa_bill(
        bill_id: &str,
        sponsorships: Value,
        primary_ids: &[&str],
        cosponsor_ids: &[&str],
    ) -> BillRecord {
        BillRecord {
            jurisdiction: ocd::Jurisdiction::new("usa"),
            session_id: "119".into(),
            bill_id: bill_id.into(),
            identifier: bill_id.into(),
            metadata: json!({
                "sponsorships": sponsorships,
                "extras": { "sponsor_bioguides": primary_ids, "cosponsor_bioguides": cosponsor_ids },
            }),
            dir: PathBuf::new(),
            citation: scan::Citation {
                repo: "usa-legislation".into(),
                commit: None,
                path: String::new(),
                source_url: None,
            },
        }
    }

    fn person(name: &str, primary: bool) -> Value {
        json!({
            "name": name,
            "classification": if primary { "primary" } else { "cosponsor" },
            "entity_type": "person",
            "primary": primary,
        })
    }

    /// #254: every id on a bill used to resolve to the bill's first sponsor, so
    /// asking for K000376 (Mike Kelly) returned John Moolenaar's bills.
    #[test]
    fn a_sponsor_id_finds_only_that_members_bills_with_their_role() {
        let moolenaar_bill = usa_bill(
            "HR1",
            json!([
                person("John R. Moolenaar", true),
                person("Mike Kelly", false),
                person("Kathy Castor", false)
            ]),
            &["M001136"],
            &["K000376", "C001066"],
        );
        let kelly_bill = usa_bill(
            "HR2",
            json!([person("Kathy Castor", false), person("Mike Kelly", true)]),
            &["K000376"],
            &["C001066"],
        );
        let moolenaar_only = usa_bill(
            "HR3",
            json!([person("John R. Moolenaar", true)]),
            &["M001136"],
            &[],
        );
        let bills = [moolenaar_bill, kelly_bill, moolenaar_only];

        let mut index = NameIndex::new();
        for bill in &bills {
            for (id, sponsorship) in bill.sponsorships_by_id() {
                index.insert(&sponsorship.name);
                index.insert_identifier(&id, &sponsorship.name);
            }
        }

        let roles = |id: &str| -> Vec<(String, String, bool)> {
            let resolved = index.resolve(id);
            assert_eq!(resolved.method, MatchMethod::Bioguide);
            bills
                .iter()
                .filter_map(|bill| {
                    matching_sponsorship(bill, &resolved, Some(id))
                        .map(|s| (bill.bill_id.clone(), s.name, s.primary))
                })
                .collect()
        };
        assert_eq!(
            roles("K000376"),
            vec![
                ("HR1".into(), "Mike Kelly".into(), false),
                ("HR2".into(), "Mike Kelly".into(), true)
            ]
        );
        assert_eq!(
            roles("c001066"),
            vec![
                ("HR1".into(), "Kathy Castor".into(), false),
                ("HR2".into(), "Kathy Castor".into(), false)
            ]
        );
        assert_eq!(
            roles("M001136"),
            vec![
                ("HR1".into(), "John R. Moolenaar".into(), true),
                ("HR3".into(), "John R. Moolenaar".into(), true)
            ]
        );
    }

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
            surname_only_spellings: Vec::new(),
            surname_only_scopes: BTreeMap::new(),
            unlinked_surname_only_spellings: Vec::new(),
            member_ids: Vec::new(),
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
            surname_only_spellings: Vec::new(),
            surname_only_scopes: BTreeMap::new(),
            unlinked_surname_only_spellings: Vec::new(),
            member_ids: Vec::new(),
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
            surname_only_spellings: Vec::new(),
            surname_only_scopes: BTreeMap::new(),
            unlinked_surname_only_spellings: Vec::new(),
            member_ids: Vec::new(),
        };
        let caveats = describe_match("Filer", &resolved, Confidence::Medium);
        assert!(caveats[0].contains("no legislator roster"));
    }

    #[test]
    fn defined_topics_reads_govbot_yml_and_tolerates_its_absence() {
        let dir = tempfile::tempdir().unwrap();
        // No govbot.yml: nothing to validate against, so no error either.
        assert_eq!(defined_topics(dir.path()).unwrap(), None);

        std::fs::write(dir.path().join("govbot.yml"), "repos: [il]\n").unwrap();
        assert_eq!(defined_topics(dir.path()).unwrap(), Some(Vec::new()));

        std::fs::write(
            dir.path().join("govbot.yml"),
            "tags:\n  transit:\n    description: x\n  affordable housing:\n    description: y\n",
        )
        .unwrap();
        assert_eq!(
            defined_topics(dir.path()).unwrap(),
            Some(vec!["affordable housing".to_string(), "transit".to_string()])
        );
    }

    #[test]
    fn defined_topics_rejects_tags_that_are_not_a_mapping() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("govbot.yml"), "tags: [transit]\n").unwrap();
        let error = defined_topics(dir.path()).unwrap_err().to_string();
        assert!(error.contains("govbot.yml"), "{error}");
        assert!(error.contains("not a mapping"), "{error}");
    }

    #[test]
    fn thousands_groups_digits() {
        assert_eq!(thousands(0), "0");
        assert_eq!(thousands(999), "999");
        assert_eq!(thousands(1000), "1,000");
        assert_eq!(thousands(18380), "18,380");
        assert_eq!(thousands(1234567), "1,234,567");
    }

    #[test]
    fn a_high_confidence_match_needs_no_caveat() {
        let resolved = NameMatch {
            method: MatchMethod::ExactName,
            confidence: Confidence::High,
            candidates: vec!["Cunningham, Bill".into()],
            surname_only_spellings: Vec::new(),
            surname_only_scopes: BTreeMap::new(),
            unlinked_surname_only_spellings: Vec::new(),
            member_ids: Vec::new(),
        };
        assert!(describe_match("Bill Cunningham", &resolved, Confidence::Medium).is_empty());
    }

    #[test]
    fn a_surname_only_link_is_named_in_a_caveat() {
        let resolved = NameMatch {
            method: MatchMethod::ExactName,
            confidence: Confidence::High,
            candidates: vec!["Cunningham, Bill".into()],
            surname_only_spellings: vec!["Cunningham".into()],
            surname_only_scopes: BTreeMap::from([(
                "Cunningham".into(),
                BTreeSet::from(["il|upper|104th".to_string()]),
            )]),
            unlinked_surname_only_spellings: Vec::new(),
            member_ids: Vec::new(),
        };
        let caveats = describe_match("Bill Cunningham", &resolved, Confidence::Medium);
        assert_eq!(caveats.len(), 1);
        assert!(caveats[0].contains("Rows for \"Cunningham\""));
        assert!(caveats[0].contains("medium confidence"));

        // Above medium, the floor rows are dropped, and that is said too.
        let caveats = describe_match("Bill Cunningham", &resolved, Confidence::High);
        assert_eq!(caveats.len(), 1);
        assert!(caveats[0].contains("left out"));
    }

    #[test]
    fn a_vote_row_matches_a_surname_only_spelling_at_medium_only() {
        let resolved = NameMatch {
            method: MatchMethod::ExactName,
            confidence: Confidence::High,
            candidates: vec!["Cunningham, Bill".into()],
            surname_only_spellings: vec!["Cunningham".into()],
            surname_only_scopes: BTreeMap::from([(
                "Cunningham".into(),
                BTreeSet::from(["il|upper|104th".to_string()]),
            )]),
            unlinked_surname_only_spellings: Vec::new(),
            member_ids: Vec::new(),
        };
        let event = VoteEventRecord {
            votes: vec![names::RawVoteRow {
                voter_name: "Cunningham".into(),
                option: "yes".into(),
                note: String::new(),
            }],
            bill_identifier: "SB 1".into(),
            motion_text: "Third Reading".into(),
            start_date: String::new(),
            result: "pass".into(),
            chamber: "upper".into(),
            counts: BTreeMap::new(),
            repaired_rows: 0,
            citation: scan::Citation {
                repo: "il-legislation".into(),
                commit: None,
                path: String::new(),
                source_url: None,
            },
        };
        let senate = Some("il|upper|104th");
        assert!(matching_vote(&event, &resolved, Confidence::Medium, senate).is_some());
        assert!(matching_vote(&event, &resolved, Confidence::High, senate).is_none());
        // Linked in the Senate only: a House row, or one whose chamber is
        // unknown, is not this senator's.
        assert!(matching_vote(&event, &resolved, Confidence::Medium, Some("il|lower|104th")).is_none());
        assert!(matching_vote(&event, &resolved, Confidence::Medium, None).is_none());
    }

    #[test]
    fn a_congress_row_is_matched_by_member_id_not_by_name() {
        // `Kelly (PA)` is Mike Kelly. A roll call also holds `Kelly (IL)`, and
        // no row but his own may be returned for him.
        let index = {
            let mut index = NameIndex::new();
            index.insert_vote("Kelly (IL)", Some("usa|lower|119"), "K000385");
            index.insert_vote("Kelly (PA)", Some("usa|lower|119"), "K000376");
            index
        };
        let resolved = index.resolve("Kelly (PA)");
        let row = |name: &str, note: &str| names::RawVoteRow {
            voter_name: name.into(),
            option: "yes".into(),
            note: note.into(),
        };
        let mut event = VoteEventRecord {
            votes: vec![row("Kelly (IL)", "K000385"), row("Kelly (PA)", "K000376")],
            bill_identifier: "HR 1".into(),
            motion_text: "On Passage".into(),
            start_date: String::new(),
            result: "pass".into(),
            chamber: "lower".into(),
            counts: BTreeMap::new(),
            repaired_rows: 0,
            citation: scan::Citation {
                repo: "usa-legislation".into(),
                commit: None,
                path: String::new(),
                source_url: None,
            },
        };
        let house = Some("usa|lower|119");
        let found = matching_vote(&event, &resolved, Confidence::Medium, house).expect("his row");
        assert_eq!(found.note, "K000376");

        // He didn't vote: nothing, rather than the Illinois Kelly's row.
        event.votes.pop();
        assert!(matching_vote(&event, &resolved, Confidence::Medium, house).is_none());
    }

    #[test]
    fn a_congress_ambiguity_says_how_to_pick_by_state() {
        let index = {
            let mut index = NameIndex::new();
            index.insert_vote("Kelly (PA)", Some("usa|lower|119"), "K000376");
            index.insert_vote("Kelly (D-AZ)", Some("usa|upper|119"), "S406");
            index.insert_vote("Grijalva", Some("usa|lower|119"), "G000551");
            index.insert_vote("Grijalva", Some("usa|lower|119"), "G000606");
            index
        };
        let caveats = describe_match("Mike Kelly", &index.resolve("Mike Kelly"), Confidence::Medium);
        assert_eq!(caveats.len(), 1);
        assert!(caveats[0].contains("Kelly (D-AZ), Kelly (PA)"));
        assert!(caveats[0].contains("member's state"));
        assert!(!caveats[0].contains("member id"));

        let caveats = describe_match("Grijalva", &index.resolve("Grijalva"), Confidence::Medium);
        assert!(caveats[0].contains("Grijalva [G000551], Grijalva [G000606]"));
        assert!(caveats[0].contains("member id"));

        // Outside Congress the caveat is as it was.
        let wy = {
            let mut index = NameIndex::new();
            index.insert("Brown, G");
            index.insert("Brown, L");
            index
        };
        let caveats = describe_match("Brown", &wy.resolve("Brown"), Confidence::Medium);
        assert!(!caveats[0].contains("Congress"));
    }

    #[test]
    fn a_vote_with_no_chamber_has_no_scope() {
        let il = ocd::parse_jurisdiction("il").expect("il parses");
        assert_eq!(
            vote_scope(&il, "upper", "104th").as_deref(),
            Some(format!("{il}|upper|104th").as_str())
        );
        assert_eq!(vote_scope(&il, "", "104th"), None);
        assert_eq!(vote_scope(&il, "  ", "104th"), None);
    }

    #[test]
    fn unlinked_bare_rows_are_named_in_a_caveat() {
        let resolved = NameMatch {
            method: MatchMethod::ExactName,
            confidence: Confidence::High,
            candidates: vec!["Brown, L".into()],
            surname_only_spellings: Vec::new(),
            surname_only_scopes: BTreeMap::new(),
            unlinked_surname_only_spellings: vec!["Brown".into()],
            member_ids: Vec::new(),
        };
        let caveats = describe_match("Brown, L", &resolved, Confidence::Medium);
        assert_eq!(caveats.len(), 1);
        assert!(caveats[0].contains("(\"Brown\") and were left out"));
    }
}
