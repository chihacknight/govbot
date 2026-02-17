use anyhow::{Context, Result};
use std::path::Path;
use std::process::{Command, Stdio};

/// Run the full govbot pipeline: clone/update → tag → build.
///
/// Smart update behavior:
/// - If `.govbot/repos/` exists with repos: just update existing repos (git pull)
/// - If `.govbot/repos/` does not exist: clone repos based on govbot.yml config
pub fn run_pipeline(config_path: &Path) -> Result<()> {
    let govbot_bin = std::env::current_exe()
        .context("Failed to determine govbot binary path")?;

    let cwd = config_path
        .parent()
        .unwrap_or_else(|| Path::new("."));

    let repos_dir = cwd.join(".govbot").join("repos");
    let has_repos = repos_dir.exists()
        && std::fs::read_dir(&repos_dir)
            .map(|mut d| d.next().is_some())
            .unwrap_or(false);

    // Step 1: Clone or update repos
    eprintln!();
    eprintln!("=== Step 1/3: {} repositories ===", if has_repos { "Updating" } else { "Cloning" });
    eprintln!();

    let clone_status = if has_repos {
        // Update existing repos only
        Command::new(&govbot_bin)
            .arg("clone")
            .current_dir(cwd)
            .stdin(Stdio::inherit())
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit())
            .status()
    } else {
        // First run: clone based on config
        let config = crate::publish::load_config(config_path)?;
        let repos = crate::publish::get_repos_from_config(&config);

        let mut cmd = Command::new(&govbot_bin);
        cmd.arg("clone");
        for repo in &repos {
            cmd.arg(repo);
        }
        cmd.current_dir(cwd)
            .stdin(Stdio::inherit())
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit())
            .status()
    };

    match clone_status {
        Ok(status) if !status.success() => {
            eprintln!("⚠️  Clone/update had errors (continuing anyway)");
        }
        Err(e) => {
            eprintln!("⚠️  Failed to run clone: {} (continuing anyway)", e);
        }
        _ => {}
    }

    // Step 2: Tag bills (govbot logs | govbot tag)
    eprintln!();
    eprintln!("=== Step 2/3: Tagging bills ===");
    eprintln!();

    let tag_result = run_logs_pipe_tag(&govbot_bin, cwd);
    match tag_result {
        Ok(false) => {
            eprintln!("⚠️  Tagging had errors (continuing anyway)");
        }
        Err(e) => {
            eprintln!("⚠️  Failed to run tagging: {} (continuing anyway)", e);
        }
        _ => {}
    }

    // Step 3: Build RSS feeds
    eprintln!();
    eprintln!("=== Step 3/3: Building RSS feeds ===");
    eprintln!();

    let build_status = Command::new(&govbot_bin)
        .arg("build")
        .current_dir(cwd)
        .stdin(Stdio::inherit())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .status()
        .context("Failed to run govbot build")?;

    if !build_status.success() {
        anyhow::bail!("Build step failed with exit code: {}", build_status.code().unwrap_or(-1));
    }

    eprintln!();
    eprintln!("Pipeline complete!");

    Ok(())
}

/// Run `govbot logs | govbot tag` by piping stdout of logs into stdin of tag.
/// Returns Ok(true) if both succeeded, Ok(false) if either failed.
fn run_logs_pipe_tag(govbot_bin: &Path, cwd: &Path) -> Result<bool> {
    let mut logs_child = Command::new(govbot_bin)
        .arg("logs")
        .current_dir(cwd)
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        .spawn()
        .context("Failed to spawn govbot logs")?;

    let logs_stdout = logs_child
        .stdout
        .take()
        .context("Failed to capture logs stdout")?;

    let tag_child = Command::new(govbot_bin)
        .arg("tag")
        .current_dir(cwd)
        .stdin(logs_stdout)
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .spawn()
        .context("Failed to spawn govbot tag")?;

    let tag_output = tag_child
        .wait_with_output()
        .context("Failed to wait for govbot tag")?;

    let logs_status = logs_child.wait().context("Failed to wait for govbot logs")?;

    Ok(logs_status.success() && tag_output.status.success())
}
