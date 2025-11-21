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
        .args(&["build", "--bin", "from-chn-distributed-gov"])
        .current_dir(&manifest_dir)
        .status()
        .expect("Failed to run cargo build");

    if !status.success() {
        panic!("Failed to build binary");
    }

    // Use debug build for tests (faster to build, and cargo test uses debug by default)
    let debug_path = manifest_dir
        .join("target")
        .join("debug")
        .join("from-chn-distributed-gov");

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
        .join("tmp")
        .join("git")
        .join("windy-civi-pipelines")
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
    if !args.is_empty() && args[0] == "from-chn-distributed-gov" {
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

    let output = Command::new(&binary)
        .args(&args)
        .current_dir(env!("CARGO_MANIFEST_DIR"))
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

/// Test runner that discovers and runs all example scripts
#[test]
fn test_all_examples() {
    if !test_data_exists() {
        eprintln!("Skipping test_all_examples: test data directory not found");
        return;
    }

    let example_scripts = get_example_scripts().expect("Failed to read examples directory");

    if example_scripts.is_empty() {
        eprintln!("No example scripts found in examples/ directory");
        return;
    }

    for script_path in example_scripts {
        let script_name = script_path
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("unknown");

        eprintln!("Testing example: {}", script_name);

        let (stdout, stderr, exit_code) = run_example_script(&script_path);

        // Create snapshot name from script filename
        let snapshot_name = snapshot_name_from_path(&script_path);

        // Snapshot stdout (which is the main output)
        // Use insta's Settings API - set snapshot directory and use custom snapshot name
        let mut settings = insta::Settings::clone_current();
        settings.set_snapshot_path("snapshots");
        settings.set_snapshot_suffix(&format!(
            "cli_snapshots_from_examples__{}_stdout",
            snapshot_name
        ));
        settings.bind(|| {
            insta::assert_snapshot!("stdout", &stdout);
        });

        // If there's stderr, snapshot it separately
        if !stderr.is_empty() {
            let mut settings = insta::Settings::clone_current();
            settings.set_snapshot_path("snapshots");
            settings.set_snapshot_suffix(&format!(
                "cli_snapshots_from_examples__{}_stderr",
                snapshot_name
            ));
            settings.bind(|| {
                insta::assert_snapshot!("stderr", &stderr);
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

/// Individual test for basic.sh example (for easier debugging)
///
/// This test runs the command from examples/basic.sh and snapshots the output.
/// To update snapshots after making changes, run:
///   cargo insta review
#[test]
fn test_basic_example() {
    if !test_data_exists() {
        eprintln!("Skipping test_basic_example: test data directory not found");
        return;
    }

    let script_path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("examples")
        .join("basic.sh");

    if !script_path.exists() {
        eprintln!("Skipping test_basic_example: basic.sh not found");
        return;
    }

    let (stdout, stderr, exit_code) = run_example_script(&script_path);

    // Snapshot stdout (main output)
    let mut settings = insta::Settings::clone_current();
    settings.set_snapshot_path("snapshots");
    settings.set_snapshot_suffix("cli_snapshots_from_examples__basic_stdout");
    settings.bind(|| {
        insta::assert_snapshot!("stdout", &stdout);
    });

    // Snapshot stderr if present
    if !stderr.is_empty() {
        let mut settings = insta::Settings::clone_current();
        settings.set_snapshot_path("snapshots");
        settings.set_snapshot_suffix("cli_snapshots_from_examples__basic_stderr");
        settings.bind(|| {
            insta::assert_snapshot!("stderr", &stderr);
        });
    }

    // Verify exit code
    assert_eq!(exit_code, 0, "Command should exit with code 0");
}
