//! A locale's data repos come from pipeline-manager's jurisdictions.yml (repo reorg,
//! 2026-11): the old one-repo-per-state repo, cloned into `<locale>-legislation`, then
//! each session pair, cloned into its own name. Offline: nothing is cloned here.

use govbot::git;
use govbot::query::scan::{self, ControlFlow};
use govbot::query::Jurisdiction;
use std::fs;
use std::path::Path;
use std::sync::Mutex;

// repo_targets reads GOVBOT_REPO_URL_TEMPLATE; one test sets it, so they take turns.
static ENV: Mutex<()> = Mutex::new(());

fn bill(repos: &Path, folder: &str, session: &str, id: &str) {
    bill_in(repos, folder, "tx", session, id)
}

fn bill_in(repos: &Path, folder: &str, state: &str, session: &str, id: &str) {
    let dir = repos
        .join(folder)
        .join(format!("country:us/state:{}/sessions", state))
        .join(session)
        .join("bills")
        .join(id);
    fs::create_dir_all(&dir).unwrap();
    fs::write(dir.join("metadata.json"), format!(r#"{{"identifier": "{}"}}"#, id)).unwrap();
    git2::Repository::init(repos.join(folder)).unwrap();
}

#[test]
fn texas_has_its_history_repo_and_the_90r_pair() {
    let _env = ENV.lock().unwrap_or_else(|e| e.into_inner());
    std::env::remove_var("GOVBOT_REPO_URL_TEMPLATE");
    let targets = git::repo_targets("tx");
    let got: Vec<(&str, &str, bool)> = targets
        .iter()
        .map(|t| (t.url.as_str(), t.folder.as_str(), t.optional))
        .collect();
    assert_eq!(
        got,
        vec![
            ("https://github.com/govbot-history/tx-legislation-data.git", "tx-legislation", false),
            ("https://github.com/govbot-data/tx-90r.git", "tx-90r", true),
        ]
    );
    // A running (manual) state keeps its current repo and folder.
    let oh: Vec<String> = git::repo_targets("oh").into_iter().map(|t| t.url).collect();
    assert_eq!(oh, vec!["https://github.com/govbot-data/oh-legislation.git".to_string()]);
}

#[test]
fn a_session_folder_belongs_to_its_state() {
    let _env = ENV.lock().unwrap_or_else(|e| e.into_inner());
    assert_eq!(govbot::locale::locale_for_folder("tx-90r"), Some("tx"));
    assert_eq!(govbot::locale::locale_for_folder("tx-legislation"), Some("tx"));
    assert_eq!(govbot::locale::locale_for_folder("nope"), None);

    let tmp = tempfile::tempdir().unwrap();
    bill(tmp.path(), "tx-legislation", "89R", "HB1");
    bill(tmp.path(), "tx-90r", "90R", "HB2");
    assert_eq!(git::get_available_locales(tmp.path()).unwrap(), vec!["tx".to_string()]);
}

#[test]
fn bills_are_read_from_every_folder_and_cite_their_own_repo() {
    let _env = ENV.lock().unwrap_or_else(|e| e.into_inner());
    let tmp = tempfile::tempdir().unwrap();
    bill(tmp.path(), "tx-legislation", "89R", "HB1");
    bill(tmp.path(), "tx-90r", "90R", "HB2");
    let tx = Jurisdiction::new("tx");

    assert_eq!(scan::sessions(tmp.path(), &tx), vec!["89R".to_string(), "90R".to_string()]);

    let mut seen = Vec::new();
    scan::for_each_bill(tmp.path(), &tx, None, |b| {
        seen.push((b.session_id.clone(), b.identifier.clone(), b.citation.repo.clone()));
        Ok(ControlFlow::Continue)
    })
    .unwrap();
    assert_eq!(
        seen,
        vec![
            ("89R".to_string(), "HB1".to_string(), "tx-legislation".to_string()),
            ("90R".to_string(), "HB2".to_string(), "tx-90r".to_string()),
        ]
    );

    // A session filter reaches into the session pair's folder.
    let mut only = Vec::new();
    scan::for_each_bill(tmp.path(), &tx, Some("90R"), |b| {
        only.push(b.identifier.clone());
        Ok(ControlFlow::Continue)
    })
    .unwrap();
    assert_eq!(only, vec!["HB2".to_string()]);
}

#[test]
fn a_custom_url_template_keeps_one_repo_per_locale() {
    let _env = ENV.lock().unwrap_or_else(|e| e.into_inner());
    std::env::set_var("GOVBOT_REPO_URL_TEMPLATE", "https://example.org/acme/{locale}-data.git");
    let targets = git::repo_targets("tx");
    std::env::remove_var("GOVBOT_REPO_URL_TEMPLATE");
    assert_eq!(targets.len(), 1);
    assert_eq!(targets[0].url, "https://example.org/acme/tx-data.git");
    assert_eq!(targets[0].folder, "tx-data");
}

#[test]
fn a_seeded_session_is_read_from_its_pair_only() {
    let _env = ENV.lock().unwrap_or_else(|e| e.into_inner());
    let tmp = tempfile::tempdir().unwrap();
    // The history repo holds 103rd and 104th; the il-104th pair was seeded with 104th.
    bill_in(tmp.path(), "il-legislation", "il", "103rd", "HB1");
    bill_in(tmp.path(), "il-legislation", "il", "104th", "HB2");
    bill_in(tmp.path(), "il-104th", "il", "104th", "HB2");
    let il = Jurisdiction::new("il");

    assert_eq!(scan::sessions(tmp.path(), &il), vec!["103rd".to_string(), "104th".to_string()]);
    let mut seen = Vec::new();
    scan::for_each_bill(tmp.path(), &il, None, |b| {
        seen.push((b.session_id.clone(), b.identifier.clone(), b.citation.repo.clone()));
        Ok(ControlFlow::Continue)
    })
    .unwrap();
    assert_eq!(
        seen,
        vec![
            ("103rd".to_string(), "HB1".to_string(), "il-legislation".to_string()),
            ("104th".to_string(), "HB2".to_string(), "il-104th".to_string()),
        ]
    );
    let shadowed = git::shadowed_session_dirs(tmp.path());
    assert!(git::is_shadowed(
        &tmp.path().join("il-legislation/country:us/state:il/sessions/104th/bills/HB2/metadata.json"),
        &shadowed
    ));
    assert!(!git::is_shadowed(&tmp.path().join("il-104th/country:us/state:il/sessions/104th"), &shadowed));
}
