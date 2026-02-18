use govbot::wizard::{generate_govbot_yml, WizardChoices, WizardSession};

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
