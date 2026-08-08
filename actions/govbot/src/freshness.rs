//! Per-jurisdiction freshness reporting for a cloned corpus.
//!
//! Answers a recurring question from corpus consumers: "which jurisdictions are
//! behind, and is the lag on govbot's ingestion side or upstream (an out-of-session
//! legislature / a stuck scraper)?"
//!
//! Everything here is computed from the data already on disk, so it runs offline
//! and is deterministic (lags are measured against a corpus-derived frontier, not
//! the wall clock). Two independent signals are surfaced per jurisdiction:
//!
//! * **newest action** — the most recent `actions[].date` across the jurisdiction's
//!   bills. This is the *legislative* frontier: how current the real-world activity is.
//! * **last ingest** — the most recent govbot-written timestamp (`_processing`
//!   fields). This is the *pipeline* frontier: when govbot last recorded anything.
//!
//! Reading the two together is what separates the failure modes:
//!
//! * old action **and** old ingest → govbot has not written new data for this
//!   jurisdiction in a while (candidate ingestion/scraper stall — a govbot-side issue).
//! * old action **but** recent ingest → govbot is still writing data; the upstream
//!   source simply has no newer legislative activity (out of session / upstream quiet —
//!   not a govbot bug).

use std::path::Path;

use chrono::{DateTime, NaiveDate, Utc};
use jwalk::WalkDir;

/// Freshness statistics for a single jurisdiction (one cloned repo).
#[derive(Debug, Clone)]
pub struct JurisdictionFreshness {
    /// Jurisdiction code derived from the data path (e.g. `wy`, `gu`, `us`).
    pub code: String,
    /// Repository directory name the data was read from.
    pub repo: String,
    /// Number of bills (metadata.json files) seen.
    pub bills: usize,
    /// Number of actions seen across all bills.
    pub actions: usize,
    /// Most recent `actions[].date` in the jurisdiction (legislative frontier).
    pub newest_action: Option<DateTime<Utc>>,
    /// Most recent govbot-written ingestion timestamp (pipeline frontier).
    pub last_ingest: Option<DateTime<Utc>>,
}

/// Corpus-wide freshness: per-jurisdiction rows plus the frontiers lag is measured against.
#[derive(Debug, Clone)]
pub struct CorpusFreshness {
    pub jurisdictions: Vec<JurisdictionFreshness>,
    /// Newest legislative action anywhere in the corpus.
    pub action_frontier: Option<DateTime<Utc>>,
    /// Newest ingestion timestamp anywhere in the corpus.
    pub ingest_frontier: Option<DateTime<Utc>>,
}

impl JurisdictionFreshness {
    /// Days this jurisdiction's newest action trails the corpus action frontier.
    pub fn action_lag_days(&self, frontier: Option<DateTime<Utc>>) -> Option<i64> {
        lag_days(self.newest_action, frontier)
    }

    /// Days this jurisdiction's last ingest trails the corpus ingest frontier.
    pub fn ingest_lag_days(&self, frontier: Option<DateTime<Utc>>) -> Option<i64> {
        lag_days(self.last_ingest, frontier)
    }
}

/// Whole-day lag between a value and a frontier (0 when the value is the frontier).
fn lag_days(value: Option<DateTime<Utc>>, frontier: Option<DateTime<Utc>>) -> Option<i64> {
    match (value, frontier) {
        (Some(v), Some(f)) => Some((f.date_naive() - v.date_naive()).num_days()),
        _ => None,
    }
}

/// Parse a timestamp from the data. Handles RFC3339 (`...Z` or `...+00:00`) and,
/// as a fallback, a bare `YYYY-MM-DD` date (treated as midnight UTC).
pub fn parse_ts(raw: &str) -> Option<DateTime<Utc>> {
    let raw = raw.trim();
    if raw.is_empty() {
        return None;
    }
    if let Ok(dt) = DateTime::parse_from_rfc3339(raw) {
        return Some(dt.with_timezone(&Utc));
    }
    if let Ok(date) = NaiveDate::parse_from_str(raw, "%Y-%m-%d") {
        return date.and_hms_opt(0, 0, 0).map(|dt| dt.and_utc());
    }
    None
}

/// Keep `slot` holding the later of itself and `candidate`.
fn keep_latest(slot: &mut Option<DateTime<Utc>>, candidate: Option<DateTime<Utc>>) {
    if let Some(c) = candidate {
        let is_later = match *slot {
            Some(cur) => c > cur,
            None => true,
        };
        if is_later {
            *slot = Some(c);
        }
    }
}

/// Extract the jurisdiction code from a bill path, preferring the `state:` segment
/// (e.g. `.../country:us/state:wy/...` → `wy`) and falling back to `country:`
/// (e.g. federal data at `country:us/...` → `us`).
fn code_from_path(path: &Path) -> Option<String> {
    let mut country: Option<String> = None;
    for comp in path.components() {
        let seg = comp.as_os_str().to_string_lossy();
        if let Some(rest) = seg.strip_prefix("state:") {
            if !rest.is_empty() {
                return Some(rest.to_string());
            }
        } else if let Some(rest) = seg.strip_prefix("country:") {
            if country.is_none() && !rest.is_empty() {
                country = Some(rest.to_string());
            }
        }
    }
    country
}

/// Strip a known repo-name suffix to recover a jurisdiction code from the directory
/// name, used only when the data path carries no `state:`/`country:` segment.
fn code_from_repo_name(repo: &str) -> String {
    for suffix in ["-legislation", "-data-pipeline"] {
        if let Some(stripped) = repo.strip_suffix(suffix) {
            return stripped.to_string();
        }
    }
    repo.to_string()
}

/// Read one bill's metadata.json and fold its action dates and ingestion timestamps
/// into the running per-repo aggregates.
fn fold_bill(
    contents: &str,
    newest_action: &mut Option<DateTime<Utc>>,
    last_ingest: &mut Option<DateTime<Utc>>,
    action_count: &mut usize,
) {
    let Ok(value) = serde_json::from_str::<serde_json::Value>(contents) else {
        return;
    };

    if let Some(actions) = value.get("actions").and_then(|a| a.as_array()) {
        for action in actions {
            *action_count += 1;
            if let Some(date) = action.get("date").and_then(|d| d.as_str()) {
                keep_latest(newest_action, parse_ts(date));
            }
            if let Some(created) = action
                .get("_processing")
                .and_then(|p| p.get("log_file_created"))
                .and_then(|d| d.as_str())
            {
                keep_latest(last_ingest, parse_ts(created));
            }
        }
    }

    if let Some(updated) = value
        .get("_processing")
        .and_then(|p| p.get("logs_latest_update"))
        .and_then(|d| d.as_str())
    {
        keep_latest(last_ingest, parse_ts(updated));
    }
}

/// Scan a single repo directory, aggregating freshness across its bills.
/// Returns `None` if the directory holds no bill metadata.
pub fn scan_repo(repo_dir: &Path) -> Option<JurisdictionFreshness> {
    let repo_name = repo_dir
        .file_name()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or_default();

    let mut bills = 0usize;
    let mut actions = 0usize;
    let mut newest_action = None;
    let mut last_ingest = None;
    let mut code: Option<String> = None;

    for entry in WalkDir::new(repo_dir).into_iter().flatten() {
        let path = entry.path();
        if path.file_name().and_then(|n| n.to_str()) != Some("metadata.json") {
            continue;
        }
        // Only count bill metadata (.../bills/{id}/metadata.json), not dataset-level files.
        let is_bill = path
            .parent()
            .and_then(|p| p.parent())
            .and_then(|p| p.file_name())
            .and_then(|n| n.to_str())
            == Some("bills");
        if !is_bill {
            continue;
        }

        if code.is_none() {
            code = code_from_path(&path);
        }

        let Ok(contents) = std::fs::read_to_string(&path) else {
            continue;
        };
        bills += 1;
        fold_bill(&contents, &mut newest_action, &mut last_ingest, &mut actions);
    }

    if bills == 0 {
        return None;
    }

    Some(JurisdictionFreshness {
        code: code.unwrap_or_else(|| code_from_repo_name(&repo_name)),
        repo: repo_name,
        bills,
        actions,
        newest_action,
        last_ingest,
    })
}

/// Scan every repo directory under `repos_dir`, optionally filtering to a set of
/// jurisdiction codes. Rows are sorted most-stale-first: jurisdictions with a known
/// action lag ordered by descending lag, then those with no recorded actions, each
/// group broken by code.
pub fn scan_corpus(repos_dir: &Path, only: Option<&[String]>) -> std::io::Result<CorpusFreshness> {
    let filter: Option<Vec<String>> =
        only.map(|codes| codes.iter().map(|c| c.trim().to_lowercase()).collect());

    let mut jurisdictions = Vec::new();

    if repos_dir.exists() {
        let mut repo_dirs: Vec<_> = std::fs::read_dir(repos_dir)?
            .flatten()
            .map(|e| e.path())
            .filter(|p| p.is_dir())
            .collect();
        repo_dirs.sort();

        for repo_dir in repo_dirs {
            if let Some(mut row) = scan_repo(&repo_dir) {
                row.code = row.code.to_lowercase();
                if let Some(ref codes) = filter {
                    if !codes.contains(&row.code) {
                        continue;
                    }
                }
                jurisdictions.push(row);
            }
        }
    }

    let action_frontier = jurisdictions
        .iter()
        .filter_map(|j| j.newest_action)
        .max();
    let ingest_frontier = jurisdictions.iter().filter_map(|j| j.last_ingest).max();

    jurisdictions.sort_by(|a, b| {
        let la = a.action_lag_days(action_frontier);
        let lb = b.action_lag_days(action_frontier);
        match (la, lb) {
            // Larger lag first (most stale at the top).
            (Some(x), Some(y)) => y.cmp(&x).then_with(|| a.code.cmp(&b.code)),
            // Rows with no recorded actions sort after rows that have a lag.
            (Some(_), None) => std::cmp::Ordering::Less,
            (None, Some(_)) => std::cmp::Ordering::Greater,
            (None, None) => a.code.cmp(&b.code),
        }
    });

    Ok(CorpusFreshness {
        jurisdictions,
        action_frontier,
        ingest_frontier,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_rfc3339_and_bare_dates() {
        assert!(parse_ts("2026-03-11T10:00:00Z").is_some());
        assert!(parse_ts("2026-03-11T10:00:00+00:00").is_some());
        assert!(parse_ts("2026-03-11").is_some());
        assert!(parse_ts("").is_none());
        assert!(parse_ts("not-a-date").is_none());
    }

    #[test]
    fn lag_is_whole_days_against_frontier() {
        let frontier = parse_ts("2026-08-06T00:00:00Z");
        let value = parse_ts("2026-03-11T23:59:00Z");
        assert_eq!(lag_days(value, frontier), Some(148));
        assert_eq!(lag_days(frontier, frontier), Some(0));
        assert_eq!(lag_days(None, frontier), None);
    }

    #[test]
    fn code_prefers_state_over_country() {
        let path = Path::new("wy-legislation/country:us/state:wy/sessions/2026/bills/HB1/metadata.json");
        assert_eq!(code_from_path(path).as_deref(), Some("wy"));

        let federal = Path::new("usa-legislation/country:us/legislature/bills/HR1/metadata.json");
        assert_eq!(code_from_path(federal).as_deref(), Some("us"));
    }

    #[test]
    fn repo_name_suffix_stripped_as_fallback() {
        assert_eq!(code_from_repo_name("wy-legislation"), "wy");
        assert_eq!(code_from_repo_name("wy-data-pipeline"), "wy");
        assert_eq!(code_from_repo_name("wy"), "wy");
    }
}
