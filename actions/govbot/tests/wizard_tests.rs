use govbot::wizard::generate_govbot_yml;

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
