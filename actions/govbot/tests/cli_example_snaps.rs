use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::process::Command;

use insta;

/// Helper function to get the path to the built binary
/// Always builds the binary to ensure we're using the latest version
fn get_binary_path() -> PathBuf {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));

    // Always build the binary to ensure we're using the latest code
    // Cargo will handle incremental builds, so this is fast if nothing changed
    eprintln!("Building binary to ensure latest version...");
    let status = Command::new("cargo")
        .args(&["build", "--bin", "govbot"])
        .current_dir(&manifest_dir)
        .status()
        .expect("Failed to run cargo build");

    if !status.success() {
        panic!("Failed to build binary");
    }

    // Use debug build for tests (faster to build, and cargo test uses debug by default)
    let debug_path = manifest_dir.join("target").join("debug").join("govbot");

    // Verify the binary exists after building
    if !debug_path.exists() {
        panic!(
            "Binary was not created at expected path: {}",
            debug_path.display()
        );
    }

    debug_path
}

/// Helper to check if test data exists
fn test_data_exists() -> bool {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("mocks")
        .join(".govbot")
        .join("repos")
        .exists()
}

/// Parse a shell script to extract the command
/// Handles line continuations with backslashes
fn parse_shell_script(script_content: &str) -> Vec<String> {
    // Remove comments and empty lines
    let lines: Vec<&str> = script_content
        .lines()
        .map(|line| line.trim())
        .filter(|line| !line.is_empty() && !line.starts_with('#'))
        .collect();

    // Join lines with backslash continuations
    let mut command_line = String::new();
    for (i, line) in lines.iter().enumerate() {
        let trimmed = line.trim_end_matches('\\').trim();
        command_line.push_str(trimmed);
        // Add space after each line (except the last)
        if i < lines.len() - 1 {
            command_line.push(' ');
        }
    }

    // Split into arguments (simple shell-like parsing)
    // This handles quoted strings and basic word splitting
    let mut args = Vec::new();
    let mut current = String::new();
    let mut in_quotes = false;
    let mut quote_char = '\0';

    for ch in command_line.chars() {
        match ch {
            '"' | '\'' if !in_quotes => {
                in_quotes = true;
                quote_char = ch;
            }
            ch if ch == quote_char && in_quotes => {
                in_quotes = false;
                quote_char = '\0';
            }
            ' ' | '\t' if !in_quotes => {
                if !current.is_empty() {
                    args.push(current.clone());
                    current.clear();
                }
            }
            _ => {
                current.push(ch);
            }
        }
    }

    if !current.is_empty() {
        args.push(current);
    }

    // Remove the binary name (first argument) since we'll use get_binary_path()
    if !args.is_empty() && args[0] == "govbot" {
        args.remove(0);
    }

    args
}

/// Execute a shell script example and capture stdout
fn run_example_script(script_path: &Path) -> (String, String, i32) {
    let binary = get_binary_path();
    let script_content = fs::read_to_string(script_path)
        .expect(&format!("Failed to read script: {}", script_path.display()));

    let args = parse_shell_script(&script_content);

    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let govbot_dir = manifest_dir.join("mocks").join(".govbot");

    // Set URL template to match existing mock data (uses -data-pipeline suffix)
    let repo_url_template = "https://github.com/chn-openstates-files/{locale}-data-pipeline.git";

    let output = Command::new(&binary)
        .args(&args)
        .current_dir(&manifest_dir)
        .env("GOVBOT_DIR", govbot_dir.to_string_lossy().as_ref())
        .env("GOVBOT_REPO_URL_TEMPLATE", repo_url_template)
        .output()
        .expect("Failed to execute command");

    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).to_string();
    let exit_code = output.status.code().unwrap_or(-1);

    (stdout, stderr, exit_code)
}

/// Get all .sh example files from the examples directory
fn get_example_scripts() -> io::Result<Vec<PathBuf>> {
    let examples_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("examples");
    let mut scripts = Vec::new();

    if examples_dir.exists() {
        for entry in fs::read_dir(&examples_dir)? {
            let entry = entry?;
            let path = entry.path();
            if path.extension().and_then(|s| s.to_str()) == Some("sh") {
                scripts.push(path);
            }
        }
    }

    scripts.sort();
    Ok(scripts)
}

/// Generate a snapshot name from a script path
fn snapshot_name_from_path(path: &Path) -> String {
    path.file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("unknown")
        .replace('-', "_")
        .replace('.', "_")
}

/// Format output with script contents for snapshot
fn format_snapshot_with_script(script_path: &Path, output: &str) -> String {
    let script_content = fs::read_to_string(script_path)
        .expect(&format!("Failed to read script: {}", script_path.display()));

    // Remove trailing newlines from script content
    let script_content = script_content.trim_end();

    format!("Command:\n{}\n\nOutput:\n{}", script_content, output)
}

/// Check if a script requires test data to run
fn script_requires_test_data(script_path: &Path) -> bool {
    if let Ok(content) = fs::read_to_string(script_path) {
        // Commands that need test data (repos directory)
        content.contains("govbot logs")
    } else {
        false
    }
}

/// Test runner that discovers and runs all example scripts
#[test]
fn cli_example_snaps() {
    let example_scripts = get_example_scripts().expect("Failed to read examples directory");

    if example_scripts.is_empty() {
        eprintln!("No example scripts found in examples/ directory");
        return;
    }

    let has_test_data = test_data_exists();

    for script_path in example_scripts {
        let script_name = script_path
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("unknown");

        // Skip scripts that require test data if it doesn't exist
        if script_requires_test_data(&script_path) && !has_test_data {
            eprintln!("Skipping {}: test data directory not found", script_name);
            continue;
        }

        eprintln!("Testing example: {}", script_name);

        let (stdout, stderr, exit_code) = run_example_script(&script_path);

        // Create snapshot name from script filename
        let snapshot_name = snapshot_name_from_path(&script_path);

        // Format stdout with script contents for snapshot
        let formatted_stdout = format_snapshot_with_script(&script_path, &stdout);

        // Snapshot stdout (which is the main output)
        // Use insta's Settings API - set snapshot directory and use custom snapshot name
        // The format will be: {test_function_name}__{suffix}.snap
        // With test function name "cli_example_snaps" and suffix "{snapshot_name}",
        // this creates: cli_example_snaps__{snapshot_name}.snap
        let mut settings = insta::Settings::clone_current();
        settings.set_snapshot_path("snapshots");
        settings.set_snapshot_suffix(&snapshot_name);
        settings.bind(|| {
            insta::assert_snapshot!("snapshot", &formatted_stdout);
        });

        // If there's stderr, snapshot it separately
        if !stderr.is_empty() {
            let mut settings = insta::Settings::clone_current();
            settings.set_snapshot_path("snapshots");
            settings.set_snapshot_suffix(&format!("{}_stderr", snapshot_name));
            settings.bind(|| {
                insta::assert_snapshot!("snapshot", &stderr);
            });
        }

        // Verify exit code is success
        assert_eq!(
            exit_code, 0,
            "Example script '{}' should exit with code 0, got {}",
            script_name, exit_code
        );
    }
}
