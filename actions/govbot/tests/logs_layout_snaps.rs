//! `govbot logs` over both log layouts.
//!
//! The mocks are in the current layout: each bill has `action_logs.jsonl` (and,
//! where there are roll calls, `vote_event_logs.jsonl`). Repos not yet converted
//! still have one file per entry under `bills/{id}/logs/` plus symlinks to them
//! under `sessions/{s}/logs/`. Both must print the same entries, each once.

use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use std::process::Command;

fn manifest_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

fn govbot_logs(govbot_dir: &Path) -> Vec<Value> {
    let output = Command::new(env!("CARGO_BIN_EXE_govbot"))
        .args(["logs", "--repos", "wy", "--join", "bill", "--filter", "none", "--limit", "none"])
        .arg("--govbot-dir")
        .arg(govbot_dir)
        .output()
        .expect("failed to run govbot logs");
    assert!(output.status.success(), "stderr: {}", String::from_utf8_lossy(&output.stderr));
    String::from_utf8(output.stdout)
        .unwrap()
        .lines()
        .map(|l| serde_json::from_str(l).unwrap())
        .collect()
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

fn mocks_copy() -> (tempfile::TempDir, PathBuf) {
    let dir = tempfile::tempdir().unwrap();
    let repo = dir.path().join("repos").join("wy-legislation");
    copy_dir(&manifest_dir().join("mocks/govbot_data/repos/wy-legislation"), &repo);
    (dir, repo)
}

fn bill_dirs(repo: &Path) -> Vec<PathBuf> {
    let mut out = Vec::new();
    for session in std::fs::read_dir(repo.join("country:us/state:wy/sessions")).unwrap() {
        let bills = session.unwrap().path().join("bills");
        for bill in std::fs::read_dir(bills).unwrap() {
            out.push(bill.unwrap().path());
        }
    }
    out.sort();
    out
}

fn sorted(mut entries: Vec<Value>) -> Vec<Value> {
    entries.sort_by_key(|e| e.to_string());
    entries
}

#[test]
fn every_mock_action_prints_once_with_its_line_and_date() {
    let entries = govbot_logs(&manifest_dir().join("mocks/govbot_data"));
    assert!(!entries.is_empty());
    for e in &entries {
        let log_source = e["sources"]["log"].as_str().unwrap();
        assert!(log_source.contains("/action_logs.jsonl#"), "{log_source}");
        assert!(e["timestamp"].is_string(), "every entry has its date: {e}");
    }
    let mut sources: Vec<&str> = entries.iter().map(|e| e["sources"]["log"].as_str().unwrap()).collect();
    let n = sources.len();
    sources.sort();
    sources.dedup();
    assert_eq!(sources.len(), n, "no entry printed twice");
    insta::assert_json_snapshot!("logs_wy_mocks", sorted(entries));
}

/// Turn the mocks back into the old layout: one file per action, named by the
/// line's id, and a symlink to each under sessions/{s}/logs/.
fn to_old_layout(repo: &Path) {
    for bill in bill_dirs(repo) {
        let jsonl = bill.join("action_logs.jsonl");
        let Ok(contents) = std::fs::read_to_string(&jsonl) else { continue };
        let logs = bill.join("logs");
        std::fs::create_dir_all(&logs).unwrap();
        let session_logs = bill.parent().unwrap().parent().unwrap().join("logs");
        std::fs::create_dir_all(&session_logs).unwrap();
        for raw in contents.lines() {
            let line: Value = serde_json::from_str(raw).unwrap();
            let name = format!("{}.json", line["id"].as_str().unwrap());
            let old = json!({ "action": line["action"], "bill_id": line["bill_id"] });
            std::fs::write(logs.join(&name), serde_json::to_string_pretty(&old).unwrap()).unwrap();
            let bill_name = bill.file_name().unwrap().to_str().unwrap();
            std::os::unix::fs::symlink(
                format!("../bills/{bill_name}/logs/{name}"),
                session_logs.join(format!("{bill_name}-{name}")),
            )
            .unwrap();
        }
        std::fs::remove_file(jsonl).unwrap();
    }
}

#[test]
fn the_old_layout_prints_the_same_entries_once_despite_the_symlinks() {
    let (dir, repo) = mocks_copy();
    to_old_layout(&repo);
    let old = govbot_logs(dir.path());
    let current = govbot_logs(&manifest_dir().join("mocks/govbot_data"));
    assert_eq!(old.len(), current.len(), "the session symlinks must not double the output");

    // Same entries; only sources.log names the file instead of the line.
    let normalized: Vec<Value> = old
        .into_iter()
        .map(|mut e| {
            let log_source = e["sources"]["log"].as_str().unwrap().to_string();
            let renamed = log_source.replace("/logs/", "/action_logs.jsonl#");
            e["sources"]["log"] = Value::String(renamed.trim_end_matches(".json").to_string());
            e
        })
        .collect();
    assert_eq!(sorted(normalized), sorted(current));
}

#[test]
fn a_corrected_vote_prints_once_in_its_newest_version() {
    let (dir, repo) = mocks_copy();
    let bill = bill_dirs(&repo).into_iter().next().unwrap();
    let vote = |result: &str| {
        json!({"start_date": "2025-02-05T17:30:55+00:00", "motion_text": "Third reading", "result": result,
               "organization": "~{\"classification\": \"lower\"}", "bill_identifier": "HB0001",
               "votes": [], "counts": [{"option": "yes", "value": 1}]})
    };
    let lines = [
        json!({"id": "v1", "first_seen": null, "chamber": "lower", "vote_event": vote("fail"), "bill_id": "HB0001"}),
        json!({"id": "v2", "first_seen": null, "chamber": "lower", "vote_event": vote("pass"), "bill_id": "HB0001"}),
        json!({"id": "v1", "first_seen": "2026-09-29T10:33:32+00:00", "chamber": "lower", "vote_event": vote("pass"), "bill_id": "HB0001"}),
    ];
    let text: String = lines.iter().map(|l| format!("{l}\n")).collect();
    std::fs::write(bill.join("vote_event_logs.jsonl"), text).unwrap();

    let votes: Vec<Value> = govbot_logs(dir.path())
        .into_iter()
        .filter(|e| e["sources"]["log"].as_str().unwrap().contains("/vote_event_logs.jsonl#"))
        .collect();
    let ids: Vec<&str> = votes
        .iter()
        .map(|e| e["sources"]["log"].as_str().unwrap().rsplit('#').next().unwrap())
        .collect();
    assert_eq!(ids, ["v1", "v2"]);
    assert_eq!(votes[0]["timestamp"], "20250205T173055Z");
}
