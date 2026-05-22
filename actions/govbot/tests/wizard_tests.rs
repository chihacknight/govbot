use govbot::config::Manifest;
use govbot::wizard::{generate_govbot_yml, WizardChoices, WizardSession};

// ============================================================
// Full wizard session snapshots — shows the entire user experience
// for each combination of choices (display + generated files)
// ============================================================

#[test]
fn wizard_session_all_datasets() {
    let session = WizardSession::from_choices(&WizardChoices {
        datasets: vec!["all".to_string()],
        base_url: "https://myuser.github.io/my-govbot".to_string(),
    });
    let mut settings = insta::Settings::clone_current();
    settings.set_snapshot_path("snapshots");
    settings.bind(|| {
        insta::assert_snapshot!("wizard_session_all", &session.to_snapshot());
    });
}

#[test]
fn wizard_session_specific_datasets() {
    let session = WizardSession::from_choices(&WizardChoices {
        datasets: vec!["il".to_string(), "ca".to_string(), "ny".to_string()],
        base_url: "https://activist.github.io/legislation".to_string(),
    });
    let mut settings = insta::Settings::clone_current();
    settings.set_snapshot_path("snapshots");
    settings.bind(|| {
        insta::assert_snapshot!("wizard_session_specific", &session.to_snapshot());
    });
}

#[test]
fn wizard_session_single_state() {
    let session = WizardSession::from_choices(&WizardChoices {
        datasets: vec!["wy".to_string()],
        base_url: "https://sartaj.me/govbot".to_string(),
    });
    let mut settings = insta::Settings::clone_current();
    settings.set_snapshot_path("snapshots");
    settings.bind(|| {
        insta::assert_snapshot!("wizard_session_single_state", &session.to_snapshot());
    });
}

// ============================================================
// govbot.yml generation — focused tests on just the YAML output
// ============================================================

#[test]
fn test_generate_govbot_yml_all_datasets() {
    let yml = generate_govbot_yml(&["all".to_string()], "https://myuser.github.io/my-govbot");
    let mut settings = insta::Settings::clone_current();
    settings.set_snapshot_path("snapshots");
    settings.bind(|| {
        insta::assert_snapshot!("wizard_all", &yml);
    });
}

#[test]
fn test_generate_govbot_yml_specific_datasets() {
    let yml = generate_govbot_yml(
        &["il".to_string(), "ca".to_string(), "ny".to_string()],
        "https://example.com",
    );
    let mut settings = insta::Settings::clone_current();
    settings.set_snapshot_path("snapshots");
    settings.bind(|| {
        insta::assert_snapshot!("wizard_specific", &yml);
    });
}

#[test]
fn test_generate_govbot_yml_single_dataset() {
    let yml = generate_govbot_yml(&["wy".to_string()], "https://sartaj.me/govbot");
    let mut settings = insta::Settings::clone_current();
    settings.set_snapshot_path("snapshots");
    settings.bind(|| {
        insta::assert_snapshot!("wizard_single", &yml);
    });
}

// ============================================================
// Round-trip tests — generate YAML, write to disk, parse back
// as a typed Manifest, and verify the parsed manifest structure
// ============================================================

#[test]
fn test_generated_yml_is_valid_manifest() {
    let yml = generate_govbot_yml(&["all".to_string()], "https://myuser.github.io/my-govbot");
    let dir = tempfile::tempdir().unwrap();
    let config_path = dir.path().join("govbot.yml");
    std::fs::write(&config_path, &yml).unwrap();

    let manifest = Manifest::load(&config_path).expect("generated govbot.yml should parse");

    // datasets
    assert_eq!(manifest.datasets, vec!["all"]);

    // transforms — the classify transform shells out to fastclass.
    let classify = manifest
        .transforms
        .get("classify")
        .expect("should have a classify transform");
    assert_eq!(classify.reads, "docs");
    assert_eq!(classify.writes, "classification");
    assert!(
        classify.classifier.is_some(),
        "classify should reference a bundle"
    );

    // publish — the RSS feed publisher.
    let feed = manifest
        .publish
        .get("feed")
        .expect("should have a feed publisher");
    assert_eq!(
        feed.base_url.as_deref(),
        Some("https://myuser.github.io/my-govbot")
    );

    // pipelines
    assert!(manifest.pipelines.contains_key("default"));
}

#[test]
fn test_generated_yml_specific_datasets_round_trip() {
    let yml = generate_govbot_yml(&["il".to_string(), "ca".to_string()], "https://example.com");
    let dir = tempfile::tempdir().unwrap();
    let config_path = dir.path().join("govbot.yml");
    std::fs::write(&config_path, &yml).unwrap();

    let manifest = Manifest::load(&config_path).expect("generated govbot.yml should parse");
    assert_eq!(manifest.datasets, vec!["il", "ca"]);
}

/// A manifest carrying the retired `tags:` block must fail to parse.
#[test]
fn test_manifest_with_tags_block_fails() {
    let yml = "datasets:\n  - all\ntags:\n  education:\n    description: x\n";
    let dir = tempfile::tempdir().unwrap();
    let config_path = dir.path().join("govbot.yml");
    std::fs::write(&config_path, yml).unwrap();

    let result = Manifest::load(&config_path);
    assert!(
        result.is_err(),
        "a govbot.yml containing `tags:` must fail to parse"
    );
}

#[test]
fn test_write_files_creates_govbot_yml() {
    let choices = WizardChoices {
        datasets: vec!["wy".to_string()],
        base_url: "https://sartaj.me/govbot".to_string(),
    };
    let session = WizardSession::from_choices(&choices);
    let dir = tempfile::tempdir().unwrap();

    session
        .write_files(dir.path())
        .expect("write_files should succeed");

    // Verify govbot.yml was created and parses as a Manifest.
    let config_path = dir.path().join("govbot.yml");
    assert!(config_path.exists(), "govbot.yml should exist");
    let manifest = Manifest::load(&config_path).expect("written govbot.yml should parse");
    assert_eq!(manifest.datasets, vec!["wy"]);

    // Verify .gitignore was created.
    let gitignore_path = dir.path().join(".gitignore");
    assert!(gitignore_path.exists(), ".gitignore should exist");
    let gitignore = std::fs::read_to_string(&gitignore_path).unwrap();
    assert!(
        gitignore.contains(".govbot"),
        ".gitignore should contain .govbot"
    );

    // Verify workflow was created.
    let workflow_path = dir.path().join(".github/workflows/build.yml");
    assert!(workflow_path.exists(), "build.yml workflow should exist");
}
