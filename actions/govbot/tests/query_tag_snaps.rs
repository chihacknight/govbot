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
/// download, deterministic scores.
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
    // A run cut short the way `govbot logs --limit` cuts one: only the first log
    // entries, which here cover some of wy 2025's bills and none of 2026's.
    let logs: String = wy_logs().lines().take(5).map(|line| format!("{line}\n")).collect();
    govbot_tag(ws.path(), &logs);

    let (stdout, stderr, code) = govbot(
        ws.path(),
        &["query", "bills", "--jurisdiction", "wy", "--tag", TOPIC],
    );
    assert_eq!(code, 0, "stderr: {stderr}");
    insta::assert_json_snapshot!(summarize(&stdout));
}
