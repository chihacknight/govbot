use govbot::wizard::{generate_govbot_yml, WizardChoices, WizardSession};
use govbot::publish::{load_config, get_repos_from_config};

// ============================================================
// Full wizard session snapshots — shows the entire user experience
// for each combination of choices (display + generated files)
// ============================================================

#[test]
fn wizard_session_all_repos_with_example_tag() {
    let session = WizardSession::from_choices(&WizardChoices {
        repos: vec!["all".to_string()],
        include_example_tag: true,
        base_url: "https://myuser.github.io/my-govbot".to_string(),
    });
    let mut settings = insta::Settings::clone_current();
    settings.set_snapshot_path("snapshots");
    settings.bind(|| {
        insta::assert_snapshot!("wizard_session_all_with_tag", &session.to_snapshot());
    });
}

#[test]
fn wizard_session_all_repos_own_tags() {
    let session = WizardSession::from_choices(&WizardChoices {
        repos: vec!["all".to_string()],
        include_example_tag: false,
        base_url: "https://example.com".to_string(),
    });
    let mut settings = insta::Settings::clone_current();
    settings.set_snapshot_path("snapshots");
    settings.bind(|| {
        insta::assert_snapshot!("wizard_session_all_own_tags", &session.to_snapshot());
    });
}

#[test]
fn wizard_session_specific_repos_with_example_tag() {
    let session = WizardSession::from_choices(&WizardChoices {
        repos: vec!["il".to_string(), "ca".to_string(), "ny".to_string()],
        include_example_tag: true,
        base_url: "https://activist.github.io/legislation".to_string(),
    });
    let mut settings = insta::Settings::clone_current();
    settings.set_snapshot_path("snapshots");
    settings.bind(|| {
        insta::assert_snapshot!("wizard_session_specific_with_tag", &session.to_snapshot());
    });
}

#[test]
fn wizard_session_specific_repos_own_tags() {
    let session = WizardSession::from_choices(&WizardChoices {
        repos: vec!["il".to_string(), "ca".to_string(), "ny".to_string()],
        include_example_tag: false,
        base_url: "https://example.com".to_string(),
    });
    let mut settings = insta::Settings::clone_current();
    settings.set_snapshot_path("snapshots");
    settings.bind(|| {
        insta::assert_snapshot!("wizard_session_specific_own_tags", &session.to_snapshot());
    });
}

#[test]
fn wizard_session_single_state() {
    let session = WizardSession::from_choices(&WizardChoices {
        repos: vec!["wy".to_string()],
        include_example_tag: true,
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
fn test_generate_govbot_yml_all_repos_with_example_tag() {
    let yml = generate_govbot_yml(&["all".to_string()], true, "https://myuser.github.io/my-govbot");
    let mut settings = insta::Settings::clone_current();
    settings.set_snapshot_path("snapshots");
    settings.bind(|| {
        insta::assert_snapshot!("wizard_all_with_tag", &yml);
    });
}

#[test]
fn test_generate_govbot_yml_specific_repos_no_tag() {
    let yml = generate_govbot_yml(
        &["il".to_string(), "ca".to_string(), "ny".to_string()],
        false,
        "https://example.com",
    );
    let mut settings = insta::Settings::clone_current();
    settings.set_snapshot_path("snapshots");
    settings.bind(|| {
        insta::assert_snapshot!("wizard_specific_no_tag", &yml);
    });
}

#[test]
fn test_generate_govbot_yml_all_repos_no_tag() {
    let yml = generate_govbot_yml(&["all".to_string()], false, "https://example.com");
    let mut settings = insta::Settings::clone_current();
    settings.set_snapshot_path("snapshots");
    settings.bind(|| {
        insta::assert_snapshot!("wizard_all_no_tag", &yml);
    });
}

#[test]
fn test_generate_govbot_yml_single_repo_with_tag() {
    let yml = generate_govbot_yml(&["wy".to_string()], true, "https://sartaj.me/govbot");
    let mut settings = insta::Settings::clone_current();
    settings.set_snapshot_path("snapshots");
    settings.bind(|| {
        insta::assert_snapshot!("wizard_single_with_tag", &yml);
    });
}

// ============================================================
// Round-trip tests — generate YAML, write to disk, parse back,
// and verify the parsed config has the expected structure
// ============================================================

#[test]
fn test_generated_yml_is_valid_yaml_with_tag() {
    let yml = generate_govbot_yml(&["all".to_string()], true, "https://myuser.github.io/my-govbot");
    let dir = tempfile::tempdir().unwrap();
    let config_path = dir.path().join("govbot.yml");
    std::fs::write(&config_path, &yml).unwrap();

    let config = load_config(&config_path).expect("generated govbot.yml should be valid YAML");

    // Verify repos
    let repos = get_repos_from_config(&config);
    assert_eq!(repos, vec!["all"]);

    // Verify tags exist and have expected structure
    let tags = config.get("tags").expect("should have tags key");
    let tags_obj = tags.as_object().expect("tags should be an object");
    assert!(tags_obj.contains_key("education"), "should contain education tag");
    let education = tags_obj.get("education").unwrap().as_object().unwrap();
    assert!(education.contains_key("description"), "education tag should have description");
    assert!(education.contains_key("examples"), "education tag should have examples");

    // Verify build config
    let build = config.get("build").expect("should have build key");
    let build_obj = build.as_object().expect("build should be an object");
    assert_eq!(build_obj.get("base_url").unwrap().as_str().unwrap(), "https://myuser.github.io/my-govbot");
    assert_eq!(build_obj.get("output_dir").unwrap().as_str().unwrap(), "docs");
    assert_eq!(build_obj.get("output_file").unwrap().as_str().unwrap(), "feed.xml");
}

#[test]
fn test_generated_yml_is_valid_yaml_without_tag() {
    let yml = generate_govbot_yml(
        &["il".to_string(), "ca".to_string()],
        false,
        "https://example.com",
    );
    let dir = tempfile::tempdir().unwrap();
    let config_path = dir.path().join("govbot.yml");
    std::fs::write(&config_path, &yml).unwrap();

    let config = load_config(&config_path).expect("generated govbot.yml should be valid YAML");

    // Verify repos
    let repos = get_repos_from_config(&config);
    assert_eq!(repos, vec!["il", "ca"]);

    // Verify tags is empty object
    let tags = config.get("tags").expect("should have tags key");
    let tags_obj = tags.as_object().expect("tags should be an object");
    assert!(tags_obj.is_empty(), "tags should be empty when no example tag");

    // Verify build config
    let build = config.get("build").expect("should have build key");
    let build_obj = build.as_object().expect("build should be an object");
    assert_eq!(build_obj.get("base_url").unwrap().as_str().unwrap(), "https://example.com");
}

#[test]
fn test_write_files_creates_govbot_yml() {
    let choices = WizardChoices {
        repos: vec!["wy".to_string()],
        include_example_tag: true,
        base_url: "https://sartaj.me/govbot".to_string(),
    };
    let session = WizardSession::from_choices(&choices);
    let dir = tempfile::tempdir().unwrap();

    session.write_files(dir.path()).expect("write_files should succeed");

    // Verify govbot.yml was created and is parseable
    let config_path = dir.path().join("govbot.yml");
    assert!(config_path.exists(), "govbot.yml should exist");
    let config = load_config(&config_path).expect("written govbot.yml should be valid YAML");
    let repos = get_repos_from_config(&config);
    assert_eq!(repos, vec!["wy"]);

    // Verify .gitignore was created
    let gitignore_path = dir.path().join(".gitignore");
    assert!(gitignore_path.exists(), ".gitignore should exist");
    let gitignore = std::fs::read_to_string(&gitignore_path).unwrap();
    assert!(gitignore.contains(".govbot"), ".gitignore should contain .govbot");

    // Verify workflow was created
    let workflow_path = dir.path().join(".github/workflows/build.yml");
    assert!(workflow_path.exists(), "build.yml workflow should exist");
}
