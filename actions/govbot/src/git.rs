use crate::error::{Error, Result};
use git2::{build::RepoBuilder, FetchOptions, RemoteCallbacks, Repository};
use std::fs;
use std::path::{Path, PathBuf};

// Repository URL template - fully configurable for any git hosting service
//
// This template uses {locale} as a placeholder that will be replaced with the actual locale.
// You can configure it via the GOVBOT_REPO_URL_TEMPLATE environment variable.
//
// Examples:
//   - GitHub: https://github.com/org/{locale}-suffix.git
//   - GitLab: https://gitlab.com/org/{locale}-suffix.git
//   - Bitbucket: https://bitbucket.org/org/{locale}-suffix.git
//   - Self-hosted GitLab: https://git.example.com/group/{locale}-repo.git
//   - Self-hosted Gitea: https://gitea.example.com/org/{locale}-data.git
//
// To use a custom URL template, set the environment variable:
//   export GOVBOT_REPO_URL_TEMPLATE="https://gitlab.com/myorg/{locale}-data.git"
const DEFAULT_REPO_URL_TEMPLATE: &str =
    "https://github.com/chn-openstates-files/{locale}-legislation.git";

/// Get the repository URL template from environment or use default
fn get_repo_url_template() -> String {
    std::env::var("GOVBOT_REPO_URL_TEMPLATE")
        .unwrap_or_else(|_| DEFAULT_REPO_URL_TEMPLATE.to_string())
}

/// Build the clone URL for a repository
pub fn build_clone_url(locale: &str) -> String {
    let template = get_repo_url_template();
    template.replace("{locale}", locale)
}

/// Extract repository name from URL template
/// For example: "https://github.com/org/{locale}-suffix.git" -> "{locale}-suffix"
fn extract_repo_name_pattern(template: &str) -> String {
    // Extract the part after the last / and before .git
    if let Some(start) = template.rfind('/') {
        let after_slash = &template[start + 1..];
        if let Some(end) = after_slash.rfind(".git") {
            after_slash[..end].to_string()
        } else {
            // No .git extension, just take after last /
            after_slash.to_string()
        }
    } else {
        // Fallback: return template as-is (might be just the pattern)
        template.to_string()
    }
}

/// Extract organization/group from URL template
/// For example: "https://github.com/org/{locale}-suffix.git" -> "org"
fn extract_repo_org(template: &str) -> String {
    // Extract the part between domain and repository name
    // Format: https://domain.com/org/{locale}-suffix.git
    if let Some(protocol_pos) = template.find("://") {
        let after_protocol = &template[protocol_pos + 3..];
        if let Some(domain_end) = after_protocol.find('/') {
            let after_domain = &after_protocol[domain_end + 1..];
            // Find the next / which should be before the repo name
            if let Some(org_end) = after_domain.find('/') {
                return after_domain[..org_end].to_string();
            }
            // If no second /, the whole thing might be the org (unlikely but handle it)
            if let Some(repo_start) = after_domain.find('{') {
                return after_domain[..repo_start].trim_end_matches('/').to_string();
            }
        }
    }
    // Fallback: return default org
    "chn-openstates-files".to_string()
}

/// Build the repository name (used for local directory names)
pub fn build_repo_name(locale: &str) -> String {
    let template = get_repo_url_template();
    let pattern = extract_repo_name_pattern(&template);
    pattern.replace("{locale}", locale)
}

/// Build the repository path (org/repo-name format, used for display)
pub fn build_repo_path(locale: &str) -> String {
    let template = get_repo_url_template();
    let org = extract_repo_org(&template);
    let repo_name = build_repo_name(locale);
    format!("{}/{}", org, repo_name)
}

/// Get the default repos directory: $CWD/.govbot/repos
pub fn default_repos_dir() -> Result<PathBuf> {
    let cwd = std::env::current_dir()
        .map_err(|_| Error::Config("Could not determine current working directory.".to_string()))?;

    Ok(cwd.join(".govbot").join("repos"))
}

/// Build callbacks for git operations with optional token authentication
fn build_callbacks(token: Option<&str>, show_progress: bool) -> RemoteCallbacks<'_> {
    let mut callbacks = RemoteCallbacks::new();
    let token = token.map(|t| t.to_string());

    callbacks.credentials(move |_url, _username, _allowed| {
        if let Some(ref token) = token {
            // For GitHub, use "x-access-token" as username with token as password
            // This is the standard GitHub PAT authentication method
            git2::Cred::userpass_plaintext("x-access-token", token)
        } else {
            // Try default credentials if no token provided
            git2::Cred::default()
        }
    });

    if show_progress {
        callbacks.transfer_progress(|stats| {
            if stats.total_objects() > 0 {
                let received = stats.received_objects();
                let total = stats.total_objects();
                let percent = if total > 0 {
                    (received * 100) / total
                } else {
                    0
                };

                if received == total {
                    eprint!(
                        "\rReceiving objects: {}/{} (100%)... done.                    \n",
                        received, total
                    );
                } else {
                    eprint!(
                        "\rReceiving objects: {}/{} ({:3}%)",
                        received, total, percent
                    );
                }
            } else {
                eprint!("\rReceiving objects: {}...", stats.received_objects());
            }
            true
        });
    }

    callbacks
}

/// Clone or pull a repository for a given locale with quiet option
/// Returns action: "clone", "pulled", or "no_updates"
pub fn clone_or_pull_repo_quiet(
    locale: &str,
    repos_dir: &Path,
    token: Option<&str>,
    quiet: bool,
) -> Result<&'static str> {
    let clone_url = build_clone_url(locale);
    let repo_name = build_repo_name(locale);
    let repo_path = build_repo_path(locale);
    let target_dir = repos_dir.join(&repo_name);
    let mut is_reclone = false;

    // Check if repository already exists
    if target_dir.exists() && Repository::open(&target_dir).is_ok() {
        // Repository exists, pull instead
        let repo = Repository::open(&target_dir)
            .map_err(|e| Error::Config(format!("Failed to open repository: {}", e)))?;

        // Pull the latest changes (credentials will be used if token is provided)
        match pull_repo_internal(&repo, token, quiet) {
            Ok(had_updates) => {
                // Explicitly drop the repository to ensure all file handles are closed
                drop(repo);

                // Give the file system a moment to release all locks
                std::thread::sleep(std::time::Duration::from_millis(50));

                return Ok(if had_updates { "pulled" } else { "no_updates" });
            }
            Err(e) => {
                // Check if this is a merge analysis error
                let error_msg = e.to_string();
                if error_msg.contains("Failed to analyze merge")
                    || error_msg.contains("object not found")
                {
                    // Close the repository first
                    drop(repo);

                    // Delete the corrupted repository and reclone
                    if !quiet {
                        eprintln!(
                            "Merge analysis failed, deleting and recloning {}...",
                            repo_name
                        );
                    }

                    // Delete the repository
                    delete_repo(locale, repos_dir)?;

                    // Mark that we're doing a reclone
                    is_reclone = true;

                    // Now fall through to clone it fresh
                } else {
                    // For other errors, close repo and return the error
                    drop(repo);
                    return Err(e);
                }
            }
        }
    }

    // Remove existing directory if it exists (but is not a git repo)
    if target_dir.exists() {
        if !quiet {
            eprintln!("Removing existing directory: {}", target_dir.display());
        }
        std::fs::remove_dir_all(&target_dir)?;
    }

    // Repository doesn't exist, clone it

    let mut fetch_options = FetchOptions::new();
    // Use a reasonable depth (50 commits) instead of depth=1
    // This provides enough history for merge analysis while still being faster than full clone
    // 50 commits is typically enough for several weeks/months of history
    fetch_options.depth(50);
    fetch_options.remote_callbacks(build_callbacks(token, !quiet));

    let mut builder = RepoBuilder::new();
    builder.fetch_options(fetch_options);

    builder.clone(&clone_url, &target_dir).map_err(|e| {
        Error::Config(format!(
            "Failed to shallow clone repository {}: {}",
            repo_path, e
        ))
    })?;

    // After cloning, check if we need to set HEAD to main or master
    let repo = Repository::open(&target_dir)
        .map_err(|e| Error::Config(format!("Failed to open cloned repository: {}", e)))?;

    // Try to find the default branch (main or master)
    // Check local branches first
    let default_branch = if repo.find_branch("main", git2::BranchType::Local).is_ok() {
        "main"
    } else if repo.find_branch("master", git2::BranchType::Local).is_ok() {
        "master"
    } else {
        // Check remote branches
        if repo
            .find_branch("origin/main", git2::BranchType::Remote)
            .is_ok()
        {
            // Create local main branch from remote
            let remote_branch = repo.find_branch("origin/main", git2::BranchType::Remote)?;
            let commit = remote_branch.get().target().ok_or_else(|| {
                Error::Config("Failed to get commit from origin/main".to_string())
            })?;
            let commit_obj = repo.find_commit(commit)?;
            repo.branch("main", &commit_obj, false)?;
            "main"
        } else if repo
            .find_branch("origin/master", git2::BranchType::Remote)
            .is_ok()
        {
            // Create local master branch from remote
            let remote_branch = repo.find_branch("origin/master", git2::BranchType::Remote)?;
            let commit = remote_branch.get().target().ok_or_else(|| {
                Error::Config("Failed to get commit from origin/master".to_string())
            })?;
            let commit_obj = repo.find_commit(commit)?;
            repo.branch("master", &commit_obj, false)?;
            "master"
        } else {
            return Err(Error::Config(
                "Neither 'main' nor 'master' branch found in repository".to_string(),
            ));
        }
    };

    // Set HEAD to the default branch if it's not already set correctly
    if let Ok(head) = repo.head() {
        if let Some(head_name) = head.name() {
            if head_name != format!("refs/heads/{}", default_branch) {
                // HEAD points to a different branch, update it
                repo.set_head(&format!("refs/heads/{}", default_branch))
                    .map_err(|e| {
                        Error::Config(format!("Failed to set HEAD to {}: {}", default_branch, e))
                    })?;
                repo.checkout_head(Some(git2::build::CheckoutBuilder::default().force()))
                    .map_err(|e| {
                        Error::Config(format!("Failed to checkout {}: {}", default_branch, e))
                    })?;
            }
        }
    } else {
        // HEAD doesn't exist, set it to the default branch
        repo.set_head(&format!("refs/heads/{}", default_branch))
            .map_err(|e| {
                Error::Config(format!("Failed to set HEAD to {}: {}", default_branch, e))
            })?;
        repo.checkout_head(Some(git2::build::CheckoutBuilder::default().force()))
            .map_err(|e| Error::Config(format!("Failed to checkout {}: {}", default_branch, e)))?;
    }

    // Explicitly drop the repository to ensure all file handles are closed
    // This is important on macOS where file handles can prevent deletion
    drop(repo);

    // Give the file system a moment to release all locks
    // This helps on macOS where file handles might not be released immediately
    std::thread::sleep(std::time::Duration::from_millis(50));

    // Clear any progress line
    if !quiet {
        eprint!(
            "\r                                                                                \r"
        );
    }

    // Return "recloned" if we deleted and recloned, otherwise "clone"
    Ok(if is_reclone { "recloned" } else { "clone" })
}

/// Clone or pull a repository for a given locale (clones if doesn't exist, pulls if it does)
pub fn clone_or_pull_repo(locale: &str, repos_dir: &Path, token: Option<&str>) -> Result<()> {
    clone_or_pull_repo_quiet(locale, repos_dir, token, false).map(|_| ())
}

/// Clone a repository for a given locale (deprecated - use clone_or_pull_repo)
pub fn clone_repo(locale: &str, repos_dir: &Path, token: Option<&str>) -> Result<()> {
    clone_or_pull_repo(locale, repos_dir, token)
}

/// Clone a repository for a given locale with quiet option (deprecated - use clone_or_pull_repo_quiet)
pub fn clone_repo_quiet(
    locale: &str,
    repos_dir: &Path,
    token: Option<&str>,
    quiet: bool,
) -> Result<()> {
    clone_or_pull_repo_quiet(locale, repos_dir, token, quiet).map(|_| ())
}

/// Internal function to pull changes from a repository
/// Returns true if updates were made, false if already up to date
fn pull_repo_internal(repo: &Repository, token: Option<&str>, quiet: bool) -> Result<bool> {
    // Determine the current local branch name
    let head = repo
        .head()
        .map_err(|e| Error::Config(format!("Failed to get HEAD: {}", e)))?;

    let local_branch_name = head
        .name()
        .and_then(|name| name.strip_prefix("refs/heads/"))
        .ok_or_else(|| Error::Config("Failed to determine local branch name".to_string()))?;

    // Fetch from remote - try both main and master
    let mut remote = repo
        .find_remote("origin")
        .map_err(|e| Error::Config(format!("Failed to find remote 'origin': {}", e)))?;

    // Check if this is a shallow repository by looking for .git/shallow file
    let is_shallow = repo.path().join("shallow").exists();

    let mut fetch_options = FetchOptions::new();
    fetch_options.remote_callbacks(build_callbacks(token, !quiet));

    // If it's a shallow repo, we need to fetch more history for merge analysis to work
    // The issue is that shallow clones only have 1 commit, so merge_analysis can't find
    // the common ancestor. We need to fetch enough history to unshallow the repo.
    if is_shallow {
        // Fetch all refs to get full history - this unshallows the repository
        // This ensures merge_analysis can find the common ancestor between local and remote
        let all_refs = vec!["+refs/*:refs/remotes/origin/*"];
        let _ = remote.fetch(&all_refs, Some(&mut fetch_options), None);
    }

    // Fetch both main and master branches (only fail if both fail)
    let refspecs = vec![
        "refs/heads/main:refs/remotes/origin/main",
        "refs/heads/master:refs/remotes/origin/master",
    ];

    // Try to fetch both branches - ignore errors for individual branches
    let fetch_result = remote.fetch(&refspecs, Some(&mut fetch_options), None);

    // If fetch completely fails, return error
    if fetch_result.is_err() {
        // Check if at least one branch exists remotely by trying to find them
        let has_main = repo
            .find_branch("origin/main", git2::BranchType::Remote)
            .is_ok();
        let has_master = repo
            .find_branch("origin/master", git2::BranchType::Remote)
            .is_ok();

        if !has_main && !has_master {
            return Err(Error::Config(
                "Failed to fetch from remote and neither 'main' nor 'master' branch found"
                    .to_string(),
            ));
        }
        // If at least one exists, continue (fetch might have partially succeeded)
    }

    // Determine which remote branch to use based on local branch
    // If local is main, use origin/main; if local is master, use origin/master
    // Otherwise, prefer main over master
    let (remote_branch_name, target_local_branch) = if local_branch_name == "main" {
        if repo
            .find_branch("origin/main", git2::BranchType::Remote)
            .is_ok()
        {
            ("origin/main", "main")
        } else if repo
            .find_branch("origin/master", git2::BranchType::Remote)
            .is_ok()
        {
            ("origin/master", "master")
        } else {
            return Err(Error::Config(
                "Neither 'main' nor 'master' branch found in remote repository".to_string(),
            ));
        }
    } else if local_branch_name == "master" {
        if repo
            .find_branch("origin/master", git2::BranchType::Remote)
            .is_ok()
        {
            ("origin/master", "master")
        } else if repo
            .find_branch("origin/main", git2::BranchType::Remote)
            .is_ok()
        {
            ("origin/main", "main")
        } else {
            return Err(Error::Config(
                "Neither 'main' nor 'master' branch found in remote repository".to_string(),
            ));
        }
    } else {
        // Local branch is neither main nor master - prefer main, fallback to master
        if repo
            .find_branch("origin/main", git2::BranchType::Remote)
            .is_ok()
        {
            ("origin/main", "main")
        } else if repo
            .find_branch("origin/master", git2::BranchType::Remote)
            .is_ok()
        {
            ("origin/master", "master")
        } else {
            return Err(Error::Config(
                "Neither 'main' nor 'master' branch found in remote repository".to_string(),
            ));
        }
    };

    let remote_branch = repo
        .find_branch(remote_branch_name, git2::BranchType::Remote)
        .map_err(|e| {
            Error::Config(format!(
                "Failed to find remote branch {}: {}",
                remote_branch_name, e
            ))
        })?;

    let remote_commit = remote_branch.get().target().ok_or_else(|| {
        Error::Config(format!("Failed to get commit from {}", remote_branch_name))
    })?;

    let fetch_commit = repo
        .find_annotated_commit(remote_commit)
        .map_err(|e| Error::Config(format!("Failed to get annotated commit: {}", e)))?;

    // If local branch doesn't match the target, switch to it
    if local_branch_name != target_local_branch {
        // Check if local branch exists, if not create it
        if repo
            .find_branch(target_local_branch, git2::BranchType::Local)
            .is_err()
        {
            let commit_obj = repo.find_commit(remote_commit)?;
            repo.branch(target_local_branch, &commit_obj, false)?;
        }

        repo.set_head(&format!("refs/heads/{}", target_local_branch))
            .map_err(|e| {
                Error::Config(format!(
                    "Failed to set HEAD to {}: {}",
                    target_local_branch, e
                ))
            })?;
        repo.checkout_head(Some(git2::build::CheckoutBuilder::default().force()))
            .map_err(|e| {
                Error::Config(format!("Failed to checkout {}: {}", target_local_branch, e))
            })?;
    }

    let analysis = repo
        .merge_analysis(&[&fetch_commit])
        .map_err(|e| Error::Config(format!("Failed to analyze merge: {}", e)))?;

    if analysis.0.is_up_to_date() {
        // Already up to date
        return Ok(false);
    } else if analysis.0.is_fast_forward() {
        // Fast-forward merge
        let mut reference = head
            .resolve()
            .map_err(|e| Error::Config(format!("Failed to resolve HEAD: {}", e)))?;
        reference
            .set_target(fetch_commit.id(), "Fast-forward")
            .map_err(|e| Error::Config(format!("Failed to update reference: {}", e)))?;
        repo.set_head(reference.name().unwrap())
            .map_err(|e| Error::Config(format!("Failed to set HEAD: {}", e)))?;
        repo.checkout_head(Some(git2::build::CheckoutBuilder::default().force()))
            .map_err(|e| Error::Config(format!("Failed to checkout: {}", e)))?;

        // Updates were made
        return Ok(true);
    } else {
        // Need to merge
        return Err(Error::Config(
            "Repository has diverged and cannot be fast-forwarded. Please resolve manually."
                .to_string(),
        ));
    }
}

/// Pull a repository for a given locale
pub fn pull_repo(locale: &str, repos_dir: &Path, token: Option<&str>) -> Result<()> {
    pull_repo_quiet(locale, repos_dir, token, false)
}

/// Pull a repository for a given locale with quiet option
pub fn pull_repo_quiet(
    locale: &str,
    repos_dir: &Path,
    token: Option<&str>,
    quiet: bool,
) -> Result<()> {
    let repo_name = build_repo_name(locale);
    let repo_path = build_repo_path(locale);
    let target_dir = repos_dir.join(&repo_name);

    let repo = match Repository::open(&target_dir) {
        Ok(repo) => repo,
        Err(_) => {
            if !quiet {
                eprintln!("Repository does not exist: {}. Skipping.", repo_path);
            }
            return Ok(());
        }
    };

    // Pull the latest changes (credentials will be used if token is provided)
    if !quiet {
        eprintln!("Pulling repository: {}", repo_path);
    }

    pull_repo_internal(&repo, token, quiet)?;

    // Explicitly drop the repository to ensure all file handles are closed
    drop(repo);

    // Give the file system a moment to release all locks
    std::thread::sleep(std::time::Duration::from_millis(50));

    // Clear any progress line
    if !quiet {
        eprint!(
            "\r                                                                                \r"
        );
        eprintln!("Successfully pulled {}", repo_path);
    }
    Ok(())
}

/// Calculate the size of a directory in bytes
pub fn get_directory_size(path: &Path) -> Result<u64> {
    if !path.exists() {
        return Ok(0);
    }

    let mut total_size = 0u64;

    fn calculate_size(entry: &fs::DirEntry, total: &mut u64) -> Result<()> {
        let metadata = entry.metadata()?;
        if metadata.is_file() {
            *total += metadata.len();
        } else if metadata.is_dir() {
            // Recursively calculate size of subdirectories
            for sub_entry in fs::read_dir(entry.path())? {
                let sub_entry = sub_entry?;
                calculate_size(&sub_entry, total)?;
            }
        }
        Ok(())
    }

    for entry in fs::read_dir(path)? {
        let entry = entry?;
        calculate_size(&entry, &mut total_size)?;
    }

    Ok(total_size)
}

/// Format bytes into human-readable format
pub fn format_size(bytes: u64) -> String {
    const UNITS: &[&str] = &["B", "KB", "MB", "GB", "TB"];
    const THRESHOLD: f64 = 1024.0;

    if bytes == 0 {
        return "0 B".to_string();
    }

    let bytes_f = bytes as f64;
    let exp = (bytes_f.ln() / THRESHOLD.ln()).floor() as usize;
    let exp = exp.min(UNITS.len() - 1);

    let size = bytes_f / THRESHOLD.powi(exp as i32);

    if exp == 0 {
        format!("{} {}", bytes, UNITS[exp])
    } else {
        format!("{:.1} {}", size, UNITS[exp])
    }
}

/// Get estimated remote repository size by doing a lightweight fetch
/// This fetches only refs and estimates size from transfer progress
pub fn get_remote_repo_size_estimate(
    repo: &Repository,
    token: Option<&str>,
    _quiet: bool,
) -> Result<u64> {
    use std::sync::{Arc, Mutex};

    let mut remote = repo
        .find_remote("origin")
        .map_err(|e| Error::Config(format!("Failed to find remote 'origin': {}", e)))?;

    let size_estimate = Arc::new(Mutex::new(0u64));
    let size_estimate_clone = size_estimate.clone();

    let mut fetch_options = FetchOptions::new();
    let token = token.map(|t| t.to_string());

    let mut callbacks = RemoteCallbacks::new();
    callbacks.credentials(move |_url, _username, _allowed| {
        if let Some(ref token) = token {
            git2::Cred::userpass_plaintext("x-access-token", token)
        } else {
            git2::Cred::default()
        }
    });

    // Track transfer progress to estimate size
    callbacks.transfer_progress(move |stats| {
        // received_bytes() gives us the total bytes received so far
        let bytes = stats.received_bytes() as u64;
        let mut size = size_estimate_clone.lock().unwrap();
        *size = bytes;
        true
    });

    fetch_options.remote_callbacks(callbacks);

    // Do a lightweight fetch - fetch refs only, not objects
    // This will give us size information without downloading everything
    let _fetch_result = remote.fetch(
        &["refs/heads/*:refs/remotes/origin/*"],
        Some(&mut fetch_options),
        None,
    );

    // Even if fetch fails, we might have gotten some size info
    let estimated_size = *size_estimate.lock().unwrap();

    if estimated_size > 0 {
        Ok(estimated_size)
    } else {
        // Fallback: estimate from local pack files if they exist
        let pack_dir = repo.path().join("objects").join("pack");
        if pack_dir.exists() {
            Ok(get_directory_size(&pack_dir).unwrap_or(0))
        } else {
            Ok(0)
        }
    }
}

/// Extract suffix from URL template (everything after {locale})
/// For example: "{locale}-legislation" -> "-legislation"
fn extract_repo_suffix(template: &str) -> String {
    let pattern = extract_repo_name_pattern(template);
    if let Some(locale_pos) = pattern.find("{locale}") {
        // Get everything after {locale}
        pattern[locale_pos + 8..].to_string() // 8 is length of "{locale}"
    } else {
        // Fallback: try common patterns
        "-legislation".to_string()
    }
}

/// Get all available locale repositories in the repos directory
pub fn get_available_locales(repos_dir: &Path) -> Result<Vec<String>> {
    if !repos_dir.exists() {
        return Ok(Vec::new());
    }

    let template = get_repo_url_template();
    let suffix = extract_repo_suffix(&template);
    let mut locales = Vec::new();

    for entry in std::fs::read_dir(repos_dir)? {
        let entry = entry?;
        let path = entry.path();

        if path.is_dir() && Repository::open(&path).is_ok() {
            if let Some(dir_name) = path.file_name().and_then(|n| n.to_str()) {
                // Check for current format first, then old format for backward compatibility
                if !suffix.is_empty() {
                    if let Some(locale) = dir_name.strip_suffix(&suffix) {
                        locales.push(locale.to_string());
                        continue;
                    }
                }
                // Fallback to old format for backward compatibility
                if let Some(locale) = dir_name.strip_suffix("-data-pipeline") {
                    locales.push(locale.to_string());
                }
            }
        }
    }

    Ok(locales)
}

/// Recursively remove a directory and all its contents
/// This is more robust than remove_dir_all on macOS
fn remove_dir_all_robust(path: &Path) -> std::io::Result<()> {
    if !path.exists() {
        return Ok(());
    }

    if path.is_file() {
        // Make file writable before removing
        let _ = std::fs::metadata(path).and_then(|m| {
            use std::os::unix::fs::PermissionsExt;
            let mut perms = m.permissions();
            perms.set_mode(0o777);
            std::fs::set_permissions(path, perms)
        });
        return std::fs::remove_file(path);
    }

    // For directories, recursively remove contents first
    let entries: Vec<_> = std::fs::read_dir(path)?.collect();

    for entry_result in entries {
        let entry = entry_result?;
        let entry_path = entry.path();

        // Make writable before trying to remove
        let _ = std::fs::metadata(&entry_path).and_then(|m| {
            use std::os::unix::fs::PermissionsExt;
            let mut perms = m.permissions();
            perms.set_mode(0o777);
            std::fs::set_permissions(&entry_path, perms)
        });

        if entry_path.is_dir() {
            // Recursively remove subdirectory
            if remove_dir_all_robust(&entry_path).is_err() {
                // If recursive removal fails, try a few more times
                for _ in 0..3 {
                    std::thread::sleep(std::time::Duration::from_millis(100));
                    if remove_dir_all_robust(&entry_path).is_ok() {
                        break;
                    }
                }
                // If still failing, try direct removal
                let _ = std::fs::remove_dir_all(&entry_path);
            }
        } else {
            // Try to remove file multiple times
            let mut removed = false;
            for _ in 0..3 {
                if std::fs::remove_file(&entry_path).is_ok() {
                    removed = true;
                    break;
                }
                std::thread::sleep(std::time::Duration::from_millis(50));
            }
            if !removed {
                // Last resort: try to make it writable again and remove
                let _ = std::fs::metadata(&entry_path).and_then(|m| {
                    use std::os::unix::fs::PermissionsExt;
                    let mut perms = m.permissions();
                    perms.set_mode(0o777);
                    std::fs::set_permissions(&entry_path, perms)
                });
                let _ = std::fs::remove_file(&entry_path);
            }
        }
    }

    // Make directory writable before removing
    let _ = std::fs::metadata(path).and_then(|m| {
        use std::os::unix::fs::PermissionsExt;
        let mut perms = m.permissions();
        perms.set_mode(0o777);
        std::fs::set_permissions(path, perms)
    });

    // Now try to remove the directory itself
    // Retry multiple times for macOS
    let mut last_error = None;
    for _ in 0..5 {
        match std::fs::remove_dir(path) {
            Ok(_) => return Ok(()),
            Err(e) => {
                last_error = Some(e);
                std::thread::sleep(std::time::Duration::from_millis(100));
            }
        }
    }

    // Final attempt with remove_dir_all
    match std::fs::remove_dir_all(path) {
        Ok(_) => Ok(()),
        Err(e) => {
            // Return the more specific error if available
            if let Some(prev_error) = last_error {
                Err(prev_error)
            } else {
                Err(e)
            }
        }
    }
}

/// Delete a repository for a given locale
pub fn delete_repo(locale: &str, repos_dir: &Path) -> Result<()> {
    let repo_name = build_repo_name(locale);
    let target_dir = repos_dir.join(&repo_name);

    if !target_dir.exists() {
        return Ok(()); // Repository doesn't exist, nothing to delete
    }

    // Try to open and close the repository first to release any locks
    // This helps on macOS where git files might be locked
    if let Ok(repo) = Repository::open(&target_dir) {
        // Try to close the index explicitly if possible
        // The index file is often the one that gets locked
        let git_dir = repo.path();
        let index_path = git_dir.join("index");

        // Force close the repository to release file handles
        drop(repo);

        // Give it a moment for file handles to be released
        std::thread::sleep(std::time::Duration::from_millis(100));

        // Try to remove the index file explicitly if it exists
        // This often helps on macOS
        if index_path.exists() {
            let _ = std::fs::remove_file(&index_path);
        }
    }

    // Use robust removal that handles macOS edge cases
    if let Err(e) = remove_dir_all_robust(&target_dir) {
        // If robust removal fails, try using shell command as fallback
        // This is often more reliable on macOS for stubborn directories
        let output = std::process::Command::new("rm")
            .arg("-rf")
            .arg(&target_dir)
            .output();

        match output {
            Ok(result) if result.status.success() => {
                // Successfully removed via shell command
                Ok(())
            }
            Ok(result) => {
                // Shell command failed, return original error with shell error info
                let shell_err = String::from_utf8_lossy(&result.stderr);
                Err(Error::Config(format!(
                    "Failed to delete repository {}: {} (shell fallback also failed: {})",
                    repo_name, e, shell_err
                )))
            }
            Err(shell_err) => {
                // Couldn't execute shell command, return original error
                Err(Error::Config(format!(
                    "Failed to delete repository {}: {} (shell fallback unavailable: {})",
                    repo_name, e, shell_err
                )))
            }
        }
    } else {
        Ok(())
    }
}
