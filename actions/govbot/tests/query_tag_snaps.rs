//! `govbot query bills --tag` against the wy/gu mocks.
//!
//! The guarded failure: a topic that was never scored for a jurisdiction, or a
//! topic name that does not exist, used to drop the tag filter and return every bill
//! in scope as a "match". These tests pin that an unscored scope contributes no rows
//! and that an undefined topic is an error naming the topics that do exist.
//!
//! It also pins how much of a session a tag file says was scored: `govbot tag`
//! records every bill it scored in `scored_bills`, so a session scored with no
//! matches is not "unscored", a partly scored one says so, and a tag file from
//! before `scored_bills` existed says its coverage is unknown.
//!
//! The mocks ship no tag files, so each test writes a small workspace — a
//! `govbot.yml` and, where needed, one tag file — into a temp dir and points
//! `--tags-dir` at it. The `govbot_tag_*` tests produce the tag files by running
//! `govbot logs | govbot tag` on the mocks instead.

use std::path::{Path, PathBuf};
use std::process::Command;

use serde_json::{json, Value};

const TOPIC: &str = "public budgets";

fn manifest_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

/// Jurisdictions are always passed explicitly: the mocks are not git checkouts, so
/// "everything cloned" resolves to nothing for them.
///
/// `CARGO_BIN_EXE_govbot` is built by cargo for integration tests, so no manual
/// `cargo build` is needed here.
fn govbot(tags_dir: &Path, args: &[&str]) -> (String, String, i32) {
    let output = Command::new(env!("CARGO_BIN_EXE_govbot"))
        .args(args)
        .arg("--govbot-dir")
        .arg(manifest_dir().join("mocks").join("govbot_data"))
        .arg("--tags-dir")
        .arg(tags_dir)
        .output()
        .expect("failed to run govbot");
    (
        String::from_utf8_lossy(&output.stdout).to_string(),
        String::from_utf8_lossy(&output.stderr).to_string(),
        output.status.code().unwrap_or(-1),
    )
}

const GOVBOT_YML: &str = "tags:\n  public budgets:\n    description: Appropriations and budgets\n    \
     include_keywords: [appropriations]\n  renter protections:\n    description: Tenants\n    \
     include_keywords: [tenant]\n";

/// A workspace that defines two topics and has scored only wy 2025 for one of
/// them: HB0001-HB0003 of its five bills.
fn workspace() -> tempfile::TempDir {
    workspace_with_tag_file(json!({
        "tag_config": { "threshold": 0.5 },
        // HB0001 clears the threshold, HB0002 does not.
        "bills": {
            "HB0001": { "score": { "final_score": 0.9 } },
            "HB0002": { "score": { "final_score": 0.2 } },
        },
        // HB0003 was scored and did not match; HB0004 and HB0005 were never scored.
        "scored_bills": ["HB0001", "HB0002", "HB0003"],
    }))
}

/// `govbot.yml` plus `tag_file` as wy 2025's 'public budgets' tag file.
fn workspace_with_tag_file(tag_file: Value) -> tempfile::TempDir {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("govbot.yml"), GOVBOT_YML).unwrap();
    write_tag_file(
        dir.path(),
        &serde_json::to_string_pretty(&tag_file).unwrap(),
    );
    dir
}

fn tag_file_path(workspace: &Path) -> PathBuf {
    workspace
        .join("country:us/state:wy/sessions/2025/tags")
        .join(format!("{TOPIC}.tag.json"))
}

fn write_tag_file(workspace: &Path, contents: &str) {
    let path = tag_file_path(workspace);
    std::fs::create_dir_all(path.parent().unwrap()).unwrap();
    std::fs::write(path, contents).unwrap();
}

/// Error text with the temp workspace path replaced, so snapshots are stable.
fn redact(text: &str, workspace: &Path) -> String {
    text.trim()
        .replace(&workspace.display().to_string(), "[WORKSPACE]")
}

/// The parts of a response these tests are about. Rows are reduced to their
/// identifiers so the snapshot does not carry commit hashes or absolute paths.
fn summarize(stdout: &str) -> Value {
    let response: Value = serde_json::from_str(stdout).expect("stdout is JSON");
    let rows: Vec<Value> = response["results"]
        .as_array()
        .unwrap()
        .iter()
        .map(|row| {
            json!({
                "identifier": row["identifier"],
                "session": row["legislative_session"],
                "final_score": row["tag"]["final_score"],
            })
        })
        .collect();
    json!({
        "truncation": response["truncation"],
        "results": rows,
        "caveats": response["caveats"],
    })
}

#[test]
fn undefined_topic_is_an_error_listing_defined_topics() {
    let ws = workspace();
    let (stdout, stderr, code) = govbot(
        ws.path(),
        &["query", "bills", "--jurisdiction", "wy", "--tag", "renters"],
    );
    assert_ne!(code, 0, "an undefined topic must fail; stdout was {stdout}");
    assert!(stdout.trim().is_empty());
    insta::assert_snapshot!(stderr.trim());
}

#[test]
fn unscored_jurisdiction_contributes_no_rows() {
    let ws = workspace();
    let (stdout, stderr, code) = govbot(
        ws.path(),
        &["query", "bills", "--jurisdiction", "gu", "--tag", TOPIC],
    );
    assert_eq!(code, 0, "stderr: {stderr}");
    let summary = summarize(&stdout);
    assert_eq!(summary["truncation"]["total_matching"], 0);
    insta::assert_json_snapshot!(summary);
}

#[test]
fn mixed_scope_counts_only_scored_rows() {
    let ws = workspace();
    // wy 2025 is scored; wy 2026 and gu 38th are not. 15 bills are in scope, and
    // exactly one clears the threshold.
    let (stdout, stderr, code) = govbot(
        ws.path(),
        &[
            "query",
            "bills",
            "--jurisdiction",
            "wy",
            "--jurisdiction",
            "gu",
            "--tag",
            TOPIC,
        ],
    );
    assert_eq!(code, 0, "stderr: {stderr}");
    let summary = summarize(&stdout);
    assert_eq!(summary["truncation"]["total_matching"], 1);
    insta::assert_json_snapshot!(summary);
}

#[test]
fn defined_topic_with_no_tag_files_anywhere_returns_nothing() {
    let ws = workspace();
    let (stdout, stderr, code) = govbot(
        ws.path(),
        &[
            "query",
            "bills",
            "--jurisdiction",
            "wy",
            "--jurisdiction",
            "gu",
            "--tag",
            "renter protections",
        ],
    );
    assert_eq!(code, 0, "stderr: {stderr}");
    let summary = summarize(&stdout);
    assert_eq!(summary["truncation"]["total_matching"], 0);
    assert_eq!(summary["results"], json!([]));
}

#[test]
fn partly_scored_session_says_how_much_was_scored() {
    let ws = workspace();
    let (stdout, stderr, code) = govbot(
        ws.path(),
        &["query", "bills", "--jurisdiction", "wy", "--session", "2025", "--tag", TOPIC],
    );
    assert_eq!(code, 0, "stderr: {stderr}");
    let summary = summarize(&stdout);
    assert_eq!(summary["truncation"]["total_matching"], 1);
    insta::assert_json_snapshot!(summary["caveats"]);
}

#[test]
fn fully_scored_session_has_no_coverage_caveat() {
    let ws = workspace_with_tag_file(json!({
        "tag_config": { "threshold": 0.5 },
        "bills": { "HB0001": { "score": { "final_score": 0.9 } } },
        // HB0001 is scored by being in `bills`, even though this list omits it.
        "scored_bills": ["HB0002", "HB0003", "HB0004", "HB0005"],
    }));
    let (stdout, stderr, code) = govbot(
        ws.path(),
        &["query", "bills", "--jurisdiction", "wy", "--session", "2025", "--tag", TOPIC],
    );
    assert_eq!(code, 0, "stderr: {stderr}");
    let caveats = summarize(&stdout)["caveats"].to_string();
    assert!(!caveats.contains("scored"), "unexpected coverage caveat: {caveats}");
}

#[test]
fn tag_file_without_scored_bills_reports_unknown_coverage() {
    // The format `govbot tag` wrote before `scored_bills`: matches only.
    let ws = workspace_with_tag_file(json!({
        "tag_config": { "threshold": 0.5 },
        "bills": { "HB0001": { "score": { "final_score": 0.9 } } },
    }));
    let (stdout, stderr, code) = govbot(
        ws.path(),
        &["query", "bills", "--jurisdiction", "wy", "--session", "2025", "--tag", TOPIC],
    );
    assert_eq!(code, 0, "stderr: {stderr}");
    let summary = summarize(&stdout);
    // Still a scored session: its match is returned, and it is not called unscored.
    assert_eq!(summary["truncation"]["total_matching"], 1);
    insta::assert_json_snapshot!(summary["caveats"]);
}

#[test]
fn unreadable_tag_file_is_an_error_naming_it() {
    let ws = workspace();
    write_tag_file(ws.path(), "{ \"bills\": { truncated");
    let (stdout, stderr, code) = govbot(
        ws.path(),
        &["query", "bills", "--jurisdiction", "wy", "--tag", TOPIC],
    );
    assert_ne!(code, 0, "a broken tag file must fail; stdout was {stdout}");
    insta::assert_snapshot!(redact(&stderr, ws.path()));
}

#[test]
fn malformed_govbot_yml_is_an_error_naming_it() {
    let ws = workspace();
    std::fs::write(ws.path().join("govbot.yml"), "tags:\n  public budgets: [\n").unwrap();
    let (stdout, stderr, code) = govbot(
        ws.path(),
        &["query", "bills", "--jurisdiction", "wy", "--tag", TOPIC],
    );
    assert_ne!(code, 0, "stdout was {stdout}");
    insta::assert_snapshot!(redact(&stderr, ws.path()));
}

#[test]
fn govbot_yml_tags_that_are_not_a_mapping_is_an_error_naming_it() {
    let ws = workspace();
    std::fs::write(ws.path().join("govbot.yml"), "tags:\n  - public budgets\n").unwrap();
    let (stdout, stderr, code) = govbot(
        ws.path(),
        &["query", "bills", "--jurisdiction", "wy", "--tag", TOPIC],
    );
    assert_ne!(code, 0, "stdout was {stdout}");
    insta::assert_snapshot!(redact(&stderr, ws.path()));
}

// ---------------------------------------------------------------------------
// `govbot logs | govbot tag` on the mocks, then query
// ---------------------------------------------------------------------------

/// The wy mock log entries, as tag_with_local_ai feeds them to `govbot tag`.
fn wy_logs() -> String {
    let output = Command::new(env!("CARGO_BIN_EXE_govbot"))
        .args(["logs", "--repos", "wy", "--join", "bill", "--filter", "none", "--limit", "none"])
        .arg("--govbot-dir")
        .arg(manifest_dir().join("mocks").join("govbot_data"))
        .output()
        .expect("failed to run govbot logs");
    assert!(output.status.success());
    String::from_utf8(output.stdout).unwrap()
}

/// Runs `govbot tag` in `workspace` on `logs`. Placeholder model files make the
/// embedding model fail to load, so tagging falls back to keyword matching: no
/// download, deterministic scores. `govbot tag` has no flag to force keyword mode;
/// the model path is passed explicitly with `--govbot-dir`, so no other model is used.
fn govbot_tag(workspace: &Path, logs: &str) {
    use std::io::Write;
    let model_dir = workspace.join("model");
    std::fs::create_dir_all(&model_dir).unwrap();
    std::fs::write(model_dir.join("model.onnx"), "placeholder").unwrap();
    std::fs::write(model_dir.join("tokenizer.json"), "placeholder").unwrap();

    let mut child = Command::new(env!("CARGO_BIN_EXE_govbot"))
        .arg("tag")
        .arg("--govbot-dir")
        .arg(&model_dir)
        .current_dir(workspace)
        // Nothing outside the workspace may influence the run: no inherited
        // GOVBOT_DIR, and HOME pointed at the temp dir so no cache under the
        // developer's home directory can be picked up.
        .env_remove("GOVBOT_DIR")
        .env("HOME", workspace)
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .expect("failed to run govbot tag");
    child.stdin.take().unwrap().write_all(logs.as_bytes()).unwrap();
    let output = child.wait_with_output().unwrap();
    assert!(
        output.status.success(),
        "govbot tag failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
}

/// Each tag file `govbot tag` wrote: its matched bills and its scored bills.
fn tag_files_written(workspace: &Path) -> Value {
    let mut files = serde_json::Map::new();
    for session in ["2025", "2026"] {
        for topic in [TOPIC, "renter protections"] {
            let path = workspace
                .join(format!("country:us/state:wy/sessions/{session}/tags"))
                .join(format!("{topic}.tag.json"));
            let Ok(raw) = std::fs::read_to_string(&path) else {
                continue;
            };
            let file: Value = serde_json::from_str(&raw).unwrap();
            let mut matched: Vec<&String> = file["bills"].as_object().unwrap().keys().collect();
            matched.sort();
            files.insert(
                format!("{session}/{topic}"),
                json!({ "bills": matched, "scored_bills": file["scored_bills"] }),
            );
        }
    }
    Value::Object(files)
}

#[test]
fn govbot_tag_writes_a_tag_file_for_every_session_it_scores() {
    let ws = tempfile::tempdir().unwrap();
    std::fs::write(ws.path().join("govbot.yml"), GOVBOT_YML).unwrap();
    let logs = wy_logs();
    govbot_tag(ws.path(), &logs);
    let written = tag_files_written(ws.path());
    insta::assert_json_snapshot!(written);

    // Re-running over the same logs records the same coverage.
    govbot_tag(ws.path(), &logs);
    assert_eq!(tag_files_written(ws.path()), written);

    // No Wyoming bill mentions tenants. The topic was scored and nothing matched,
    // which is an empty result with no "not scored" or coverage caveat.
    let (stdout, stderr, code) = govbot(
        ws.path(),
        &["query", "bills", "--jurisdiction", "wy", "--tag", "renter protections"],
    );
    assert_eq!(code, 0, "stderr: {stderr}");
    let summary = summarize(&stdout);
    assert_eq!(summary["truncation"]["total_matching"], 0);
    let caveats = summary["caveats"].to_string();
    assert!(!caveats.contains("scored"), "unexpected caveat: {caveats}");
}

#[test]
fn govbot_tag_on_part_of_a_session_reports_partial_coverage() {
    let ws = tempfile::tempdir().unwrap();
    std::fs::write(ws.path().join("govbot.yml"), GOVBOT_YML).unwrap();
    // A run cut short the way `govbot logs --limit` cuts one: some of wy 2025's
    // bills (HB0001, HB0002) and none of 2026's. The entries are picked by bill,
    // not by position: `govbot logs` yields files in directory-iteration order
    // (jwalk, unsorted), which is name order on APFS but hash order on ext4, so
    // "the first five lines" were 2025's bills on macOS and 2026's on Linux CI.
    let logs: String = wy_logs()
        .lines()
        .filter(|line| {
            let entry: Value = serde_json::from_str(line).unwrap();
            entry["bill"]["legislative_session"] == "2025"
                && ["HB0001", "HB0002"].contains(&entry["bill"]["identifier"].as_str().unwrap())
        })
        .map(|line| format!("{line}\n"))
        .collect();
    govbot_tag(ws.path(), &logs);

    let (stdout, stderr, code) = govbot(
        ws.path(),
        &["query", "bills", "--jurisdiction", "wy", "--tag", TOPIC],
    );
    assert_eq!(code, 0, "stderr: {stderr}");
    insta::assert_json_snapshot!(summarize(&stdout));
}

// ---------------------------------------------------------------------------
// `query votes --tag`
// ---------------------------------------------------------------------------
//
// The guarded failure: `query votes --tag` used to ignore the tag, returning every
// vote in scope (all of a legislator's votes) while echoing the tag back as if it
// had been applied. The mocks carry no roll calls, so these tests copy wy into a
// temp data dir and add vote events to some of its bills.

/// Like [`govbot`], against a data dir other than the shipped mocks.
fn govbot_with_data(data_dir: &Path, tags_dir: &Path, args: &[&str]) -> (String, String, i32) {
    let output = Command::new(env!("CARGO_BIN_EXE_govbot"))
        .args(args)
        .arg("--govbot-dir")
        .arg(data_dir)
        .arg("--tags-dir")
        .arg(tags_dir)
        .output()
        .expect("failed to run govbot");
    (
        String::from_utf8_lossy(&output.stdout).to_string(),
        String::from_utf8_lossy(&output.stderr).to_string(),
        output.status.code().unwrap_or(-1),
    )
}

fn copy_dir(from: &Path, to: &Path) {
    std::fs::create_dir_all(to).unwrap();
    for entry in std::fs::read_dir(from).unwrap() {
        let entry = entry.unwrap();
        let target = to.join(entry.file_name());
        if entry.file_type().unwrap().is_dir() {
            copy_dir(&entry.path(), &target);
        } else {
            std::fs::copy(entry.path(), target).unwrap();
        }
    }
}

/// The wy mocks with roll calls on 2025's HB0001 (on topic in [`workspace`]),
/// HB0002 (scored below threshold) and HB0004 (never scored), and on 2026's
/// HB0002 (a session with no tag file). HB0001 has two, so ranking within a bill
/// is visible. Smith votes in all of them; Jones only on HB0002.
fn wy_with_votes() -> tempfile::TempDir {
    let dir = tempfile::tempdir().unwrap();
    let repo = dir.path().join("repos").join("wy-legislation");
    copy_dir(
        &manifest_dir().join("mocks/govbot_data/repos/wy-legislation"),
        &repo,
    );
    let sessions = repo.join("country:us/state:wy/sessions");
    for (session, bill, stamp, voters) in [
        ("2025", "HB0001", "20250210T120000Z", vec!["Smith"]),
        ("2025", "HB0001", "20250301T120000Z", vec!["Smith"]),
        ("2025", "HB0002", "20250215T120000Z", vec!["Smith", "Jones"]),
        ("2025", "HB0004", "20250220T120000Z", vec!["Smith"]),
        ("2026", "HB0002", "20260215T120000Z", vec!["Smith"]),
    ] {
        let votes: Vec<Value> = voters
            .iter()
            .map(|name| json!({ "voter_name": name, "option": "yes", "note": "" }))
            .collect();
        let event = json!({
            "motion_text": format!("Third reading {bill}"),
            "start_date": format!("{}-{}-{}", &stamp[0..4], &stamp[4..6], &stamp[6..8]),
            "result": "pass",
            "organization": "~{\"classification\": \"lower\"}",
            "votes": votes,
            "counts": [{ "option": "yes", "value": voters.len() }],
        });
        std::fs::write(
            sessions
                .join(session)
                .join("bills")
                .join(bill)
                .join("logs")
                .join(format!("{stamp}.vote_event.pass.lower.json")),
            serde_json::to_string_pretty(&event).unwrap(),
        )
        .unwrap();
    }
    dir
}

/// Vote rows reduced to what these tests are about.
fn summarize_votes(stdout: &str) -> Value {
    let response: Value = serde_json::from_str(stdout).expect("stdout is JSON");
    let rows: Vec<Value> = response["results"]
        .as_array()
        .unwrap()
        .iter()
        .map(|row| {
            json!({
                "bill": row["bill_identifier"],
                "session": row["legislative_session"],
                "start_date": row["start_date"],
                "topic_score": row["topic_score"],
            })
        })
        .collect();
    json!({
        "truncation": response["truncation"],
        "results": rows,
        "caveats": response["caveats"],
    })
}

#[test]
fn votes_with_tag_return_only_votes_on_bills_on_the_topic() {
    let ws = workspace();
    let data = wy_with_votes();
    let (stdout, stderr, code) = govbot_with_data(
        data.path(),
        ws.path(),
        &["query", "votes", "--jurisdiction", "wy", "--person", "Smith", "--tag", TOPIC],
    );
    assert_eq!(code, 0, "stderr: {stderr}");
    let summary = summarize_votes(&stdout);
    // HB0001's two votes, latest first. Not HB0002 (below threshold), HB0004
    // (unscored, counted in the coverage caveat), or 2026 (no tag file).
    assert_eq!(summary["truncation"]["total_matching"], 2);
    insta::assert_json_snapshot!(summary);
}

#[test]
fn votes_with_tag_honour_min_score() {
    let ws = workspace();
    let data = wy_with_votes();
    let (stdout, stderr, code) = govbot_with_data(
        data.path(),
        ws.path(),
        &[
            "query", "votes", "--jurisdiction", "wy", "--session", "2025", "--tag", TOPIC,
            "--min-score", "0.1",
        ],
    );
    assert_eq!(code, 0, "stderr: {stderr}");
    let summary = summarize_votes(&stdout);
    let bills: Vec<&str> = summary["results"]
        .as_array()
        .unwrap()
        .iter()
        .map(|row| row["bill"].as_str().unwrap())
        .collect();
    // HB0002 (0.2) now clears the floor, and ranks after HB0001 (0.9).
    assert_eq!(bills, ["HB0001", "HB0001", "HB0002"]);
}

#[test]
fn votes_with_tag_in_an_unscored_session_return_no_rows() {
    let ws = workspace();
    let data = wy_with_votes();
    let (stdout, stderr, code) = govbot_with_data(
        data.path(),
        ws.path(),
        &["query", "votes", "--jurisdiction", "wy", "--session", "2026", "--tag", TOPIC],
    );
    assert_eq!(code, 0, "stderr: {stderr}");
    let summary = summarize_votes(&stdout);
    assert_eq!(summary["truncation"]["total_matching"], 0);
    insta::assert_json_snapshot!(summary["caveats"]);
}

#[test]
fn votes_with_tag_say_when_no_tagged_bill_had_a_vote() {
    let ws = workspace();
    // The shipped mocks: HB0001 is on topic, but wy has no roll calls at all.
    let (stdout, stderr, code) = govbot(
        ws.path(),
        &["query", "votes", "--jurisdiction", "wy", "--session", "2025", "--tag", TOPIC],
    );
    assert_eq!(code, 0, "stderr: {stderr}");
    let no_roll_calls = summarize_votes(&stdout)["caveats"].clone();

    // Jones voted only on HB0002, which is below the threshold: HB0001 had roll
    // calls, just none Jones was in.
    let data = wy_with_votes();
    let (stdout, stderr, code) = govbot_with_data(
        data.path(),
        ws.path(),
        &[
            "query", "votes", "--jurisdiction", "wy", "--session", "2025", "--person", "Jones",
            "--tag", TOPIC,
        ],
    );
    assert_eq!(code, 0, "stderr: {stderr}");
    let not_in_them = summarize_votes(&stdout)["caveats"].clone();

    insta::assert_json_snapshot!(json!({
        "no_roll_calls": no_roll_calls,
        "person_not_in_them": not_in_them,
    }));
}

#[test]
fn votes_with_undefined_topic_is_an_error() {
    let ws = workspace();
    let (stdout, stderr, code) = govbot(
        ws.path(),
        &["query", "votes", "--jurisdiction", "wy", "--tag", "renters"],
    );
    assert_ne!(code, 0, "an undefined topic must fail; stdout was {stdout}");
    assert!(stderr.contains("No topic named 'renters'"), "stderr: {stderr}");
}

#[test]
fn votes_without_tag_are_unchanged() {
    let ws = workspace();
    let data = wy_with_votes();
    let (stdout, stderr, code) = govbot_with_data(
        data.path(),
        ws.path(),
        &["query", "votes", "--jurisdiction", "wy", "--limit", "3"],
    );
    assert_eq!(code, 0, "stderr: {stderr}");
    let summary = summarize_votes(&stdout);
    // All five roll calls match; the first three in scan order, no topic scores.
    assert_eq!(summary["truncation"]["total_matching"], 5);
    insta::assert_json_snapshot!(summary);
}

#[test]
fn people_and_coverage_refuse_a_topic_filter() {
    let ws = workspace();
    for (kind, flag, value) in [
        ("people", "--tag", TOPIC),
        ("people", "--min-score", "0.5"),
        ("coverage", "--tag", TOPIC),
    ] {
        let (stdout, stderr, code) = govbot(
            ws.path(),
            &["query", kind, "--jurisdiction", "wy", flag, value],
        );
        assert_ne!(code, 0, "{kind} {flag} must fail; stdout was {stdout}");
        assert!(stdout.trim().is_empty());
        assert!(
            stderr.contains("is not supported for") && stderr.contains(kind),
            "stderr: {stderr}"
        );
    }
}
