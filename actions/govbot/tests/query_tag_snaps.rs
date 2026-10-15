//! `govbot query bills --tag` against the wy/gu mocks.
//!
//! The guarded failure: a topic that was never scored for a jurisdiction, or a
//! topic name that does not exist, used to drop the tag filter and return every bill
//! in scope as a "match". These tests pin that an unscored scope contributes no rows
//! and that an undefined topic is an error naming the topics that do exist.
//!
//! The mocks ship no tag files, so each test writes a small workspace — a
//! `govbot.yml` and, where needed, one tag file — into a temp dir and points
//! `--tags-dir` at it.

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

/// A workspace that defines two topics and has scored only wy 2025 for one of them.
fn workspace() -> tempfile::TempDir {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(
        dir.path().join("govbot.yml"),
        format!(
            "tags:\n  {TOPIC}:\n    description: Appropriations and budgets\n  \
             renter protections:\n    description: Tenants\n"
        ),
    )
    .unwrap();

    let tags = dir.path().join("country:us/state:wy/sessions/2025/tags");
    std::fs::create_dir_all(&tags).unwrap();
    // HB0001 clears the threshold, HB0002 does not; the other three wy 2025 bills
    // are absent, which is how `govbot tag` records a bill it did not match.
    let tag_file = json!({
        "tag_config": { "threshold": 0.5 },
        "bills": {
            "HB0001": { "score": { "final_score": 0.9 } },
            "HB0002": { "score": { "final_score": 0.2 } },
        }
    });
    std::fs::write(
        tags.join(format!("{TOPIC}.tag.json")),
        serde_json::to_string_pretty(&tag_file).unwrap(),
    )
    .unwrap();
    dir
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
