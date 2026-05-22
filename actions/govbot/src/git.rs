use crate::error::{Error, Result};
use crate::registry::ResolvedDataset;
use git2::{build::RepoBuilder, FetchOptions, RemoteCallbacks, Repository};
use std::fs;
use std::path::{Path, PathBuf};

// ============================================================
// Dataset git operations.
//
// Datasets are git repos. Their URLs are NOT derived from a compiled locale
// enum or a `{locale}` URL template anymore — they are looked up at runtime in
// the dataset *registry* (`registry.rs`). A dataset is cloned ONCE per machine
// into the shared content-addressed cache (`cache.rs`); a project's
// `.govbot/repos/<short_name>` is a symlink into that cache.
// ============================================================

/// The local directory name a dataset's clone is stored under, within a
/// project's `repos/` directory. This is the dataset's short (slash-free)
/// name plus the legacy `-legislation` data-repo suffix, so existing on-disk
/// layouts and downstream walkers (`source`, `load`) are unchanged.
///
/// `wy` → `wy-legislation`. The suffix is overridable for tests/mocks via
/// `GOVBOT_REPO_SUFFIX` (the mock data uses `-data-pipeline`).
pub fn repo_dir_name(short_name: &str) -> String {
    let suffix = std::env::var("GOVBOT_REPO_SUFFIX").unwrap_or_else(|_| "-legislation".to_string());
    format!("{}{}", short_name, suffix)
}

/// Get the default repos directory: `$CWD/.govbot/repos`.
pub fn default_repos_dir() -> Result<PathBuf> {
    let cwd = std::env::current_dir()
        .map_err(|_| Error::Config("Could not determine current working directory.".to_string()))?;

    Ok(cwd.join(".govbot").join("repos"))
}

/// The outcome of a clone/pull, plus the commit it landed on.
#[derive(Debug, Clone)]
pub struct PullOutcome {
    /// `"clone"`, `"pulled"`, `"no_updates"`, or `"recloned"`.
    pub action: &'static str,
    /// The commit SHA the dataset is now checked out at.
    pub commit: String,
    /// The shared-cache key the dataset's clone lives under.
    pub cache_key: String,
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

/// Read the commit SHA `HEAD` currently resolves to in an open repository.
fn head_commit(repo: &Repository) -> Result<String> {
    let head = repo
        .head()
        .map_err(|e| Error::Config(format!("Failed to read HEAD: {}", e)))?;
    let oid = head
        .target()
        .ok_or_else(|| Error::Config("HEAD has no commit target".to_string()))?;
    Ok(oid.to_string())
}

/// Clone-or-pull a dataset into the shared content-addressed cache, then link
/// the cache entry into the project's `repos/` directory.
///
/// This is the registry-driven replacement for the old locale-keyed
/// `clone_or_pull_repo_quiet`. It:
///   1. resolves the dataset's cache key (URL + channel),
///   2. clones into `~/.govbot/cache/<key>` once, or `git pull`s it if present,
///   3. symlinks `<repos_dir>/<repo_dir_name>` to that cache entry,
///   4. returns the action taken plus the resolved commit SHA (for the lock).
///
/// A second `pull` of the same dataset — in this or any other project — finds
/// the cache populated and only fetches deltas.
pub fn clone_or_pull_dataset(
    dataset: &ResolvedDataset,
    repos_dir: &Path,
    token: Option<&str>,
    quiet: bool,
) -> Result<PullOutcome> {
    let short = dataset.short_name();
    let git_url = &dataset.entry.git_url;
    let channel = dataset.channel.as_deref();

    let cache_entry = crate::cache::cache_path(short, git_url, channel)?;
    let cache_key = crate::cache::cache_key(short, git_url, channel);

    let mut is_reclone = false;

    let outcome_action: &'static str = if cache_entry.exists()
        && Repository::open(&cache_entry).is_ok()
    {
        // Cached already — pull deltas.
        let repo = Repository::open(&cache_entry)
            .map_err(|e| Error::Config(format!("Failed to open cached repository: {}", e)))?;
        match pull_repo_internal(&repo, token, quiet) {
            Ok(had_updates) => {
                drop(repo);
                std::thread::sleep(std::time::Duration::from_millis(50));
                if had_updates {
                    "pulled"
                } else {
                    "no_updates"
                }
            }
            Err(e) => {
                let error_msg = e.to_string();
                if error_msg.contains("Failed to analyze merge")
                    || error_msg.contains("object not found")
                {
                    drop(repo);
                    if !quiet {
                        eprintln!("Merge analysis failed, deleting and recloning {}...", short);
                    }
                    remove_dir_all_robust(&cache_entry).map_err(|e| {
                        Error::Config(format!("Failed to clear corrupt cache entry: {}", e))
                    })?;
                    is_reclone = true;
                    // fall through to clone
                    ""
                } else {
                    drop(repo);
                    return Err(e);
                }
            }
        }
    } else {
        ""
    };

    // If the cache entry is populated and we already pulled, we are done with
    // the heavy step — just link and report.
    if !outcome_action.is_empty() {
        link_dataset(&cache_entry, repos_dir, short)?;
        let repo = Repository::open(&cache_entry)
            .map_err(|e| Error::Config(format!("Failed to reopen cached repository: {}", e)))?;
        let commit = head_commit(&repo)?;
        return Ok(PullOutcome {
            action: outcome_action,
            commit,
            cache_key,
        });
    }

    // Clone into the cache.
    if cache_entry.exists() {
        // A non-repo directory is squatting the cache slot — clear it.
        let _ = std::fs::remove_dir_all(&cache_entry);
    }
    if let Some(parent) = cache_entry.parent() {
        std::fs::create_dir_all(parent)?;
    }

    let mut fetch_options = FetchOptions::new();
    // A 50-commit depth: enough history for merge analysis, faster than a
    // full clone.
    fetch_options.depth(50);
    fetch_options.remote_callbacks(build_callbacks(token, !quiet));

    let mut builder = RepoBuilder::new();
    builder.fetch_options(fetch_options);
    if let Some(channel) = channel {
        builder.branch(channel);
    }

    builder.clone(git_url, &cache_entry).map_err(|e| {
        Error::Config(format!("Failed to clone dataset {}: {}", dataset.id, e))
    })?;

    let repo = Repository::open(&cache_entry)
        .map_err(|e| Error::Config(format!("Failed to open cloned repository: {}", e)))?;

    // Resolve to a sensible default branch (main/master) if no channel given.
    if channel.is_none() {
        ensure_default_branch(&repo)?;
    }

    let commit = head_commit(&repo)?;
    drop(repo);
    std::thread::sleep(std::time::Duration::from_millis(50));

    if !quiet {
        eprint!(
            "\r                                                                                \r"
        );
    }

    link_dataset(&cache_entry, repos_dir, short)?;

    Ok(PullOutcome {
        action: if is_reclone { "recloned" } else { "clone" },
        commit,
        cache_key,
    })
}

/// Link a populated cache entry into a project's `repos/` directory under the
/// dataset's `repo_dir_name`.
fn link_dataset(cache_entry: &Path, repos_dir: &Path, short_name: &str) -> Result<()> {
    let project_repo = repos_dir.join(repo_dir_name(short_name));
    crate::cache::link_into_project(cache_entry, &project_repo)
}

/// Ensure a freshly cloned repo's HEAD points at `main` or `master`.
fn ensure_default_branch(repo: &Repository) -> Result<()> {
    let default_branch = if repo.find_branch("main", git2::BranchType::Local).is_ok() {
        "main"
    } else if repo.find_branch("master", git2::BranchType::Local).is_ok() {
        "master"
    } else if repo
        .find_branch("origin/main", git2::BranchType::Remote)
        .is_ok()
    {
        let remote_branch = repo.find_branch("origin/main", git2::BranchType::Remote)?;
        let commit = remote_branch
            .get()
            .target()
            .ok_or_else(|| Error::Config("Failed to get commit from origin/main".to_string()))?;
        let commit_obj = repo.find_commit(commit)?;
        repo.branch("main", &commit_obj, false)?;
        "main"
    } else if repo
        .find_branch("origin/master", git2::BranchType::Remote)
        .is_ok()
    {
        let remote_branch = repo.find_branch("origin/master", git2::BranchType::Remote)?;
        let commit = remote_branch
            .get()
            .target()
            .ok_or_else(|| Error::Config("Failed to get commit from origin/master".to_string()))?;
        let commit_obj = repo.find_commit(commit)?;
        repo.branch("master", &commit_obj, false)?;
        "master"
    } else {
        return Err(Error::Config(
            "Neither 'main' nor 'master' branch found in repository".to_string(),
        ));
    };

    let needs_set = match repo.head() {
        Ok(head) => head.name() != Some(&format!("refs/heads/{}", default_branch)[..]),
        Err(_) => true,
    };
    if needs_set {
        repo.set_head(&format!("refs/heads/{}", default_branch))
            .map_err(|e| Error::Config(format!("Failed to set HEAD to {}: {}", default_branch, e)))?;
        repo.checkout_head(Some(git2::build::CheckoutBuilder::default().force()))
            .map_err(|e| Error::Config(format!("Failed to checkout {}: {}", default_branch, e)))?;
    }
    Ok(())
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
        .ok_or_else(|| Error::Config("Failed to determine local branch name".to_string()))?
        .to_string();

    // Fetch from remote - try both main and master
    let mut remote = repo
        .find_remote("origin")
        .map_err(|e| Error::Config(format!("Failed to find remote 'origin': {}", e)))?;

    // Check if this is a shallow repository by looking for .git/shallow file
    let is_shallow = repo.path().join("shallow").exists();

    let mut fetch_options = FetchOptions::new();
    fetch_options.remote_callbacks(build_callbacks(token, !quiet));

    // If it's a shallow repo, fetch more history so merge analysis can find the
    // common ancestor — a shallow clone of 1 commit has none.
    if is_shallow {
        let all_refs = vec!["+refs/*:refs/remotes/origin/*"];
        let _ = remote.fetch(&all_refs, Some(&mut fetch_options), None);
    }

    // Fetch the current branch plus the usual defaults.
    let branch_refspec = format!(
        "refs/heads/{0}:refs/remotes/origin/{0}",
        local_branch_name
    );
    let refspecs = vec![
        branch_refspec.as_str(),
        "refs/heads/main:refs/remotes/origin/main",
        "refs/heads/master:refs/remotes/origin/master",
    ];

    let fetch_result = remote.fetch(&refspecs, Some(&mut fetch_options), None);

    if fetch_result.is_err() {
        let has_branch = repo
            .find_branch(
                &format!("origin/{}", local_branch_name),
                git2::BranchType::Remote,
            )
            .is_ok();
        if !has_branch {
            return Err(Error::Config(
                "Failed to fetch from remote and the tracked branch was not found".to_string(),
            ));
        }
    }

    // Track the branch we are on; fall back to main/master if it's gone.
    let (remote_branch_name, target_local_branch) = if repo
        .find_branch(
            &format!("origin/{}", local_branch_name),
            git2::BranchType::Remote,
        )
        .is_ok()
    {
        (
            format!("origin/{}", local_branch_name),
            local_branch_name.clone(),
        )
    } else if repo
        .find_branch("origin/main", git2::BranchType::Remote)
        .is_ok()
    {
        ("origin/main".to_string(), "main".to_string())
    } else if repo
        .find_branch("origin/master", git2::BranchType::Remote)
        .is_ok()
    {
        ("origin/master".to_string(), "master".to_string())
    } else {
        return Err(Error::Config(
            "No tracked branch found in remote repository".to_string(),
        ));
    };

    let remote_branch = repo
        .find_branch(&remote_branch_name, git2::BranchType::Remote)
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
        if repo
            .find_branch(&target_local_branch, git2::BranchType::Local)
            .is_err()
        {
            let commit_obj = repo.find_commit(remote_commit)?;
            repo.branch(&target_local_branch, &commit_obj, false)?;
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
        Ok(false)
    } else if analysis.0.is_fast_forward() {
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
        Ok(true)
    } else {
        Err(Error::Config(
            "Repository has diverged and cannot be fast-forwarded. Please resolve manually."
                .to_string(),
        ))
    }
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

/// List the datasets locally present in a project's `repos/` directory,
/// returned as short names (the registry/manifest identifier form).
///
/// A "dataset directory" is any directory (or symlink-to-directory) whose name
/// carries the dataset suffix — it need not be a live git repo, so mock data
/// and non-git extracts are listed too.
pub fn get_local_datasets(repos_dir: &Path) -> Result<Vec<String>> {
    if !repos_dir.exists() {
        return Ok(Vec::new());
    }

    let suffix = std::env::var("GOVBOT_REPO_SUFFIX").unwrap_or_else(|_| "-legislation".to_string());
    let mut datasets = Vec::new();

    for entry in std::fs::read_dir(repos_dir)? {
        let entry = entry?;
        let path = entry.path();

        // A symlink into the cache or a real clone — both count. `is_dir()`
        // follows a symlink, so a cache symlink resolves correctly.
        if path.is_dir() {
            if let Some(dir_name) = path.file_name().and_then(|n| n.to_str()) {
                if let Some(short) = dir_name.strip_suffix(&suffix) {
                    datasets.push(short.to_string());
                    continue;
                }
                // Legacy layout fallback.
                if let Some(short) = dir_name.strip_suffix("-data-pipeline") {
                    datasets.push(short.to_string());
                }
            }
        }
    }
    datasets.sort();
    Ok(datasets)
}

/// Recursively remove a directory and all its contents.
/// More robust than `remove_dir_all` on macOS.
fn remove_dir_all_robust(path: &Path) -> std::io::Result<()> {
    if !path.exists() {
        return Ok(());
    }

    if path.is_file() || path.is_symlink() {
        let _ = std::fs::metadata(path).and_then(|m| {
            use std::os::unix::fs::PermissionsExt;
            let mut perms = m.permissions();
            perms.set_mode(0o777);
            std::fs::set_permissions(path, perms)
        });
        return std::fs::remove_file(path);
    }

    let entries: Vec<_> = std::fs::read_dir(path)?.collect();

    for entry_result in entries {
        let entry = entry_result?;
        let entry_path = entry.path();

        let _ = std::fs::metadata(&entry_path).and_then(|m| {
            use std::os::unix::fs::PermissionsExt;
            let mut perms = m.permissions();
            perms.set_mode(0o777);
            std::fs::set_permissions(&entry_path, perms)
        });

        if entry_path.is_dir() {
            if remove_dir_all_robust(&entry_path).is_err() {
                for _ in 0..3 {
                    std::thread::sleep(std::time::Duration::from_millis(100));
                    if remove_dir_all_robust(&entry_path).is_ok() {
                        break;
                    }
                }
                let _ = std::fs::remove_dir_all(&entry_path);
            }
        } else {
            let mut removed = false;
            for _ in 0..3 {
                if std::fs::remove_file(&entry_path).is_ok() {
                    removed = true;
                    break;
                }
                std::thread::sleep(std::time::Duration::from_millis(50));
            }
            if !removed {
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

    let _ = std::fs::metadata(path).and_then(|m| {
        use std::os::unix::fs::PermissionsExt;
        let mut perms = m.permissions();
        perms.set_mode(0o777);
        std::fs::set_permissions(path, perms)
    });

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

    match std::fs::remove_dir_all(path) {
        Ok(_) => Ok(()),
        Err(e) => {
            if let Some(prev_error) = last_error {
                Err(prev_error)
            } else {
                Err(e)
            }
        }
    }
}

/// Remove a dataset's clone from a project's `repos/` directory.
///
/// This unlinks the project's reference (the symlink into the shared cache);
/// the cache entry itself is left intact, since other projects may use it.
pub fn delete_dataset(short_name: &str, repos_dir: &Path) -> Result<()> {
    let target_dir = repos_dir.join(repo_dir_name(short_name));

    if !target_dir.exists() && std::fs::symlink_metadata(&target_dir).is_err() {
        return Ok(()); // Nothing to delete.
    }

    // A symlink into the cache: unlink it, leave the cache entry.
    if let Ok(meta) = std::fs::symlink_metadata(&target_dir) {
        if meta.file_type().is_symlink() {
            return std::fs::remove_file(&target_dir).map_err(|e| {
                Error::Config(format!(
                    "Failed to unlink dataset {}: {}",
                    short_name, e
                ))
            });
        }
    }

    // A real directory (a pre-cache clone): remove it.
    if let Ok(repo) = Repository::open(&target_dir) {
        let git_dir = repo.path().to_path_buf();
        let index_path = git_dir.join("index");
        drop(repo);
        std::thread::sleep(std::time::Duration::from_millis(100));
        if index_path.exists() {
            let _ = std::fs::remove_file(&index_path);
        }
    }

    if let Err(e) = remove_dir_all_robust(&target_dir) {
        let output = std::process::Command::new("rm")
            .arg("-rf")
            .arg(&target_dir)
            .output();
        match output {
            Ok(result) if result.status.success() => Ok(()),
            Ok(result) => {
                let shell_err = String::from_utf8_lossy(&result.stderr);
                Err(Error::Config(format!(
                    "Failed to delete dataset {}: {} (shell fallback also failed: {})",
                    short_name, e, shell_err
                )))
            }
            Err(shell_err) => Err(Error::Config(format!(
                "Failed to delete dataset {}: {} (shell fallback unavailable: {})",
                short_name, e, shell_err
            ))),
        }
    } else {
        Ok(())
    }
}
