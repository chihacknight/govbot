use std::fs;
use std::process::Command;

/// `govbot logs --limit N` must pick the same files on every machine. The walk used to
/// follow filesystem order (differs between macOS and Linux), so a limited tagging run
/// scored different bills per machine. Files are created in reverse order here so a
/// creation-order walk would fail.
#[test]
fn limited_logs_are_in_sorted_order() {
    let dir = tempfile::tempdir().unwrap();
    let repo = dir.path().join("repos").join("xx-legislation");
    for session in ["2026", "2025"] {
        for bill in ["HB0003", "HB0002", "HB0001"] {
            let logs = repo
                .join("country:us/state:xx/sessions")
                .join(session)
                .join("bills")
                .join(bill)
                .join("logs");
            fs::create_dir_all(&logs).unwrap();
            fs::write(
                logs.join("20250101T000000Z_action.json"),
                format!(r#"{{"bill_id":"{bill}","session":"{session}"}}"#),
            )
            .unwrap();
        }
    }

    let out = Command::new(env!("CARGO_BIN_EXE_govbot"))
        .args(["logs", "--repos", "xx", "--limit", "3", "--govbot-dir"])
        .arg(dir.path())
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&out.stdout);
    let got: Vec<(String, String)> = stdout
        .lines()
        .filter_map(|l| serde_json::from_str::<serde_json::Value>(l).ok())
        .map(|v| {
            let src = v["sources"]["log"].as_str().unwrap();
            let session = src.split("/sessions/").nth(1).unwrap().split('/').next().unwrap();
            (session.to_string(), v["log"]["bill_id"].as_str().unwrap().to_string())
        })
        .collect();
    let want: Vec<(String, String)> = ["HB0001", "HB0002", "HB0003"]
        .iter()
        .map(|b| ("2025".to_string(), b.to_string()))
        .collect();
    assert_eq!(got, want, "stderr: {}", String::from_utf8_lossy(&out.stderr));
}
