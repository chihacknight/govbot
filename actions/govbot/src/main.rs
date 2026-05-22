use clap::{Parser, Subcommand};
use futures::stream;
use futures::StreamExt;
use govbot::git;
use govbot::lock::LockFile;
use govbot::publish::{deduplicate_entries, filter_by_tags, load_manifest, sort_by_timestamp};
use govbot::registry::Registry;
use govbot::selectors::ocd_files_select_default;
use govbot::{hash_text, BillTagResult, TagFile, TagFileMetadata};
use jwalk::WalkDir;
use std::collections::HashMap;
use std::fs;
use std::io::{self, BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::Command as ProcessCommand;

/// Write a line to stdout, gracefully handling broken pipe errors
/// This is essential for piping to tools like yq, jq, etc.
fn write_json_line(line: &str) -> io::Result<()> {
    let mut stdout = io::stdout();
    match writeln!(stdout, "{}", line) {
        Ok(_) => {}
        Err(e) if e.kind() == io::ErrorKind::BrokenPipe => {
            // Broken pipe is expected when downstream tool closes early (e.g., yq, head, etc.)
            return Ok(());
        }
        Err(e) => return Err(e),
    }
    match stdout.flush() {
        Ok(_) => {}
        Err(e) if e.kind() == io::ErrorKind::BrokenPipe => {
            // Broken pipe is expected when downstream tool closes early
            return Ok(());
        }
        Err(e) => return Err(e),
    }
    Ok(())
}

#[derive(Debug, Clone)]
struct CloneResult {
    locale: String,
    result: String,   // emoji, or "failed"
    position: String, // "1/37"
    size: Option<String>,
    local_size: Option<String>,
    final_size: Option<String>,
    error: Option<String>,
    /// On success: the canonical registry id, git URL, channel, resolved
    /// commit SHA, and cache key — recorded into `govbot.lock`.
    pin: Option<DatasetPin>,
}

/// A resolved dataset pin, captured during a successful clone/pull for the
/// lockfile.
#[derive(Debug, Clone)]
struct DatasetPin {
    canonical_id: String,
    git_url: String,
    channel: Option<String>,
    commit: String,
    cache_key: String,
}

/// govbot — gov-data package manager and transform/publish orchestrator.
#[derive(Parser, Debug)]
#[command(name = "govbot")]
#[command(
    about = "Government-data tool: pull dataset repositories, run transforms over them, and publish artifacts (RSS / HTML / JSON / DuckDB / Bluesky). Configured by a `govbot.yml` manifest (datasets / transforms / publish / pipelines). See AGENT.md for the end-user playbook."
)]
#[command(version)]
struct Args {
    #[command(subcommand)]
    command: Option<Command>,
}

#[derive(Subcommand, Debug)]
enum Command {
    /// Pull (clone or update) dataset repositories into the shared cache and
    /// link them into the project. Use `govbot pull all` to pull every dataset,
    /// `govbot pull <id>...` for specific ones, or `govbot pull` with no args
    /// to refresh whatever's already linked into the project.
    Pull {
        /// Dataset identifiers to pull (e.g. `wy`, `il`, `us-legislation/ca`, or `all`). With no args, refreshes datasets already linked into the project.
        #[arg(num_args = 0..)]
        repos: Vec<String>,

        /// Directory containing repositories (default: $CWD/.govbot/repos, or GOVBOT_DIR env var)
        #[arg(long = "govbot-dir")]
        govbot_dir: Option<String>,

        /// GitHub token for authentication (can also use TOKEN env var)
        #[arg(long)]
        token: Option<String>,

        /// Number of parallel operations (default: 4, or GOVBOT_JOBS env var)
        #[arg(long)]
        parallel: Option<usize>,

        /// Show verbose git output
        #[arg(long)]
        verbose: bool,

        /// List available datasets instead of pulling
        #[arg(long)]
        list: bool,
    },

    /// Stream dataset records as JSON Lines — the govbot stream-protocol
    /// `source` stage. Pipe into a transform (`fastclass classify -`) or into
    /// `govbot apply` for the persistence sink. See `schemas/STREAM_PROTOCOL.md`.
    Source {
        /// Datasets to emit (default: every linked dataset). Accepts the same
        /// identifiers as `govbot pull` (`wy`, `il`, `us-legislation/ca`).
        #[arg(long = "datasets", visible_alias = "repos", num_args = 0..)]
        repos: Vec<String>,

        /// Per repo limit (default: 100) options: `none` | number
        #[arg(long, default_value = "100")]
        limit: String,

        /// Join additional datasets (default: `bill,tags`) options: `bill`, `tags`, `bill,tags`, etc.
        #[arg(long, default_value = "bill,tags")]
        join: String,

        /// Select/transform fields (default: `default`). `docs` emits one
        /// `{"id","text","kind":"docs"}` JSON object per entry carrying the
        /// FULL bill text — the stream-protocol document `fastclass classify -`
        /// consumes.
        #[arg(long, default_value = "default", value_parser = ["default", "docs"])]
        select: String,

        /// Filter log entries based on per-repo AI generated filters (default: `default`) options: `default` | `none`
        #[arg(long, default_value = "default", value_parser = ["default", "none"])]
        filter: String,

        /// Sort order (default: DESC) options: `ASC` | `DESC`
        #[arg(long, default_value = "DESC", value_parser = ["ASC", "DESC"])]
        sort: String,

        /// Govbot directory (default: $CWD/.govbot/repos, or GOVBOT_DIR env var)
        #[arg(long = "govbot-dir")]
        govbot_dir: Option<String>,
    },

    /// Delete locally-linked dataset clones from the project's `.govbot/repos/`.
    /// Use `govbot delete all` to clear every linked dataset, or
    /// `govbot delete <id>...` for specific ones. The shared cache at
    /// `~/.govbot/cache/` is not touched — a subsequent `pull` re-links instantly.
    Delete {
        /// Dataset identifiers to unlink (e.g. `wy`, `il`, `us-legislation/ca`, or `all`).
        #[arg(num_args = 0..)]
        locales: Vec<String>,

        /// Directory containing repositories (default: $CWD/.govbot/repos, or GOVBOT_DIR env var)
        #[arg(long = "govbot-dir")]
        govbot_dir: Option<String>,

        /// Number of parallel operations (default: 4, or GOVBOT_JOBS env var)
        #[arg(long)]
        parallel: Option<usize>,

        /// Show verbose output
        #[arg(long)]
        verbose: bool,
    },

    /// Load bill metadata into a DuckDB database for SQL analysis. Walks every
    /// linked dataset's `metadata.json` files, creates a `bills` table + a
    /// `bills_summary` view, and writes the database into the base govbot
    /// directory (default `./.govbot/govbot.duckdb`). Requires the `duckdb` CLI
    /// on PATH.
    Load {
        /// Output database filename (default: govbot.duckdb). Saved in the base govbot directory.
        #[arg(long, default_value = "govbot.duckdb")]
        database: String,

        /// Directory containing repositories (default: $CWD/.govbot/repos, or GOVBOT_DIR env var)
        #[arg(long = "govbot-dir")]
        govbot_dir: Option<String>,

        /// Memory limit for DuckDB (e.g., "8GB", "16GB")
        #[arg(long)]
        memory_limit: Option<String>,

        /// Number of threads for DuckDB (default: 4)
        #[arg(long)]
        threads: Option<usize>,
    },

    /// Update the installed govbot binary to the latest nightly build from
    /// GitHub releases. Installs into `~/.govbot/bin/govbot` and prefers the
    /// platform-native `.tar.gz` asset.
    Update,

    /// Run one or more publishers from `govbot.yml: publish:`. A publisher
    /// consumes the tagged result stream and emits artifacts: `rss`/`html`/`json`
    /// write feed/index/dump files, `duckdb` loads records into a database,
    /// `bluesky` posts matches to a Bluesky account (always dry-run first with
    /// `--dry-run`).
    Publish {
        /// Publisher name(s) from govbot.yml `publish:` (default: every publisher)
        #[arg(long = "publisher", num_args = 0..)]
        publishers: Vec<String>,

        /// Limit number of entries per artifact (default: 100, use "none" for all entries)
        #[arg(long)]
        limit: Option<String>,

        /// Output directory override (default: from the publisher's output_dir, or "docs")
        #[arg(long)]
        output_dir: Option<String>,

        /// Output filename override (default: from the publisher's output_file, or "feed.xml")
        #[arg(long)]
        output_file: Option<String>,

        /// Render but do not emit. The `bluesky` publisher honours this by
        /// printing the posts it would send and touching no network/ledger.
        #[arg(long = "dry-run")]
        dry_run: bool,

        /// Govbot directory (default: $CWD/.govbot/repos, or GOVBOT_DIR env var)
        #[arg(long = "govbot-dir")]
        govbot_dir: Option<String>,
    },

    /// Persist fastclass classification results into the dataset as tag files.
    /// Reads `fastclass classify` result JSON from stdin — the apply sink of
    /// `govbot source --select docs | fastclass classify - | govbot apply` —
    /// and writes per-tag `.tag.json` files under each bill's session
    /// directory, the files `govbot publish` turns into feeds. Classification
    /// itself is done by fastclass; `govbot apply` only stores the results.
    Apply {
        /// Optional tag name: persist only this tag's matches
        tag_name: Option<String>,

        /// Output directory (defaults to the directory containing govbot.yml)
        #[arg(long = "output-dir")]
        output_dir: Option<String>,

        /// Overwrite a bill's tag entry even if it is already present
        #[arg(long)]
        overwrite: bool,
    },

    /// Run the full pipeline against the current directory's `govbot.yml`:
    /// pull/update datasets → `source --select docs | fastclass classify - | apply`
    /// (the classify transform) → publish every configured publisher.
    /// `govbot` with no arguments is equivalent (and falls back to `init` if no
    /// `govbot.yml` is present).
    Run {
        /// Govbot directory (default: $CWD/.govbot, or GOVBOT_DIR env var)
        #[arg(long = "govbot-dir")]
        govbot_dir: Option<String>,
    },

    /// Scaffold a new govbot.yml in the current directory (the setup wizard).
    /// Interactive in a TTY; writes sensible defaults when non-interactive.
    Init,

    /// Add one or more datasets to the project's `govbot.yml` `datasets:` list.
    /// Each id is validated against the registry before it is added.
    Add {
        /// Dataset identifiers to add (e.g. `wy`, `il`, `us-legislation/ca`).
        #[arg(num_args = 1..)]
        datasets: Vec<String>,
    },

    /// Remove one or more datasets from the project's `govbot.yml`.
    Remove {
        /// Dataset identifiers to remove from `datasets:`.
        #[arg(num_args = 1..)]
        datasets: Vec<String>,
    },

    /// List datasets — the project's manifest datasets and the ones cached
    /// locally. With no manifest, lists every dataset in the registry.
    Ls {
        /// Govbot directory (default: $CWD/.govbot/repos, or GOVBOT_DIR env var)
        #[arg(long = "govbot-dir")]
        govbot_dir: Option<String>,

        /// Emit machine-readable JSON instead of a human table.
        #[arg(long = "output", value_parser = ["text", "json"], default_value = "text")]
        output: String,
    },

    /// Search the dataset registry. A blank query lists every dataset.
    Search {
        /// Query matched against dataset ids and names (case-insensitive).
        #[arg(num_args = 0..)]
        query: Vec<String>,

        /// Emit machine-readable JSON instead of a human table.
        #[arg(long = "output", value_parser = ["text", "json"], default_value = "text")]
        output: String,
    },
}

fn get_govbot_dir(govbot_dir: Option<String>) -> anyhow::Result<PathBuf> {
    // Check flag first, then environment variable, then default
    if let Some(govbot_dir) = govbot_dir {
        // Append /repos to custom govbot-dir (default already includes /repos)
        Ok(PathBuf::from(govbot_dir).join("repos"))
    } else if let Ok(govbot_dir) = std::env::var("GOVBOT_DIR") {
        // Append /repos to custom govbot-dir from env var
        Ok(PathBuf::from(govbot_dir).join("repos"))
    } else {
        // Fall back to default: $CWD/.govbot/repos
        git::default_repos_dir().map_err(|e| anyhow::anyhow!("{}", e))
    }
}

/// The directory holding the project's `govbot.yml` (and where `govbot.lock`
/// is written) — the current working directory.
fn project_dir() -> anyhow::Result<PathBuf> {
    std::env::current_dir().map_err(|e| anyhow::anyhow!("Could not determine cwd: {}", e))
}

/// Load the active dataset registry for the current project.
fn load_registry() -> anyhow::Result<Registry> {
    let dir = project_dir()?;
    Registry::load(&dir).map_err(|e| anyhow::anyhow!("{}", e))
}

/// Process a single dataset clone/pull operation.
///
/// Resolution is registry-driven: the dataset is cloned once into the shared
/// `~/.govbot/cache/` and linked into the project's `repos/`. The resolved
/// commit SHA is captured for `govbot.lock`.
fn process_single_dataset(
    dataset: &govbot::ResolvedDataset,
    repos_dir: &PathBuf,
    token_str: Option<&str>,
    verbose: bool,
) -> CloneResult {
    let short = dataset.short_name().to_string();
    let target_dir = repos_dir.join(git::repo_dir_name(&short));

    let local_size = if target_dir.exists() {
        git::get_directory_size(&target_dir).unwrap_or(0)
    } else {
        0
    };

    match git::clone_or_pull_dataset(dataset, repos_dir, token_str, !verbose) {
        Ok(outcome) => {
            let final_size = if target_dir.exists() {
                git::get_directory_size(&target_dir).unwrap_or(0)
            } else {
                0
            };

            let result = match outcome.action {
                "clone" => "🆕",
                "pulled" => "⬇️",
                "no_updates" => "✅",
                "recloned" => "🔄",
                _ => "processed",
            };

            let mut clone_result = CloneResult {
                locale: short.clone(),
                result: result.to_string(),
                position: String::new(),
                size: None,
                local_size: None,
                final_size: None,
                error: None,
                pin: Some(DatasetPin {
                    canonical_id: dataset.id.clone(),
                    git_url: dataset.entry.git_url.clone(),
                    channel: dataset.channel.clone(),
                    commit: outcome.commit.clone(),
                    cache_key: outcome.cache_key.clone(),
                }),
            };

            if outcome.action == "clone"
                || outcome.action == "recloned"
                || outcome.action == "no_updates"
            {
                clone_result.size = Some(git::format_size(final_size));
            } else {
                clone_result.local_size = Some(git::format_size(local_size));
                clone_result.final_size = Some(git::format_size(final_size));
            }

            clone_result
        }
        Err(e) => CloneResult {
            locale: short,
            result: "failed".to_string(),
            position: String::new(),
            size: None,
            local_size: None,
            final_size: None,
            error: Some(e.to_string()),
            pin: None,
        },
    }
}

/// Print a single clone result
fn print_result(result: &CloneResult) {
    use std::io::Write;
    if result.result == "failed" {
        if let Some(ref error) = result.error {
            eprintln!("❌  {:<6}  {}", result.locale, error);
        } else {
            eprintln!("❌  {:<6}", result.locale);
        }
    } else {
        let size_str = if let Some(ref size) = result.size {
            size.clone()
        } else if let (Some(ref local), Some(ref final_size)) =
            (&result.local_size, &result.final_size)
        {
            format!("{} -> {}", local, final_size)
        } else {
            String::new()
        };

        // result.result now contains the emoji directly (🆕, ⬇️, ✅, 🔄)
        let action_emoji = &result.result;

        if !size_str.is_empty() {
            eprintln!("{}  {:<6}  [{}]", action_emoji, result.locale, size_str);
        } else {
            eprintln!("{}  {:<6}", action_emoji, result.locale);
        }
    }
    // Force flush stderr to ensure immediate output
    let _ = std::io::stderr().flush();
}

/// Perform clone/pull operations and print results as they complete
async fn perform_clone_operations(
    datasets: Vec<govbot::ResolvedDataset>,
    repos_dir: PathBuf,
    token_str: Option<&str>,
    num_jobs: usize,
    verbose: bool,
) -> anyhow::Result<Vec<CloneResult>> {
    let total = datasets.len();
    let mut all_results = Vec::new();

    if total == 1 || num_jobs == 1 {
        // Sequential clone/pull - print as we go
        for (idx, dataset) in datasets.iter().enumerate() {
            let mut result = process_single_dataset(dataset, &repos_dir, token_str, verbose);
            result.position = format!("{}/{}", idx + 1, total);
            print_result(&result);
            all_results.push(result);
        }
    } else {
        // Parallel clone/pull - print as results come in
        use std::sync::{Arc, Mutex};
        let completed = Arc::new(Mutex::new(0usize));

        let clone_futures = stream::iter(datasets.into_iter())
            .map(|dataset| {
                let repos_dir = repos_dir.clone();
                let token = token_str.map(|s| s.to_string());
                let completed = completed.clone();
                let total = total;
                let verbose_flag = verbose;

                tokio::task::spawn_blocking(move || {
                    let mut result = process_single_dataset(
                        &dataset,
                        &repos_dir,
                        token.as_deref(),
                        verbose_flag,
                    );
                    let mut count = completed.lock().unwrap();
                    *count += 1;
                    result.position = format!("{}/{}", *count, total);
                    result
                })
            })
            .buffer_unordered(num_jobs);

        let mut stream = clone_futures;

        while let Some(result) = stream.next().await {
            match result {
                Ok(data) => {
                    print_result(&data);
                    all_results.push(data);
                }
                Err(e) => {
                    let error_result = CloneResult {
                        locale: "unknown".to_string(),
                        result: "failed".to_string(),
                        position: "?".to_string(),
                        size: None,
                        local_size: None,
                        final_size: None,
                        error: Some(format!("Task error: {}", e)),
                        pin: None,
                    };
                    print_result(&error_result);
                    all_results.push(error_result);
                }
            }
            // Force flush after each result to ensure immediate output
            use std::io::Write;
            let _ = std::io::stderr().flush();
        }
    }

    Ok(all_results)
}

/// Write/update `govbot.lock` from a batch of successful clone/pull results.
/// Non-fatal: a lockfile-write failure prints a warning but does not abort.
fn update_lockfile(project_dir: &std::path::Path, results: &[CloneResult]) {
    let mut lock = match LockFile::load_or_default(project_dir) {
        Ok(l) => l,
        Err(e) => {
            eprintln!(
                "⚠️  Could not read govbot.lock ({}); skipping pin update",
                e
            );
            return;
        }
    };
    let mut pinned = 0usize;
    for r in results {
        if let Some(pin) = &r.pin {
            lock.pin(
                &pin.canonical_id,
                &pin.git_url,
                pin.channel.as_deref(),
                &pin.commit,
                &pin.cache_key,
            );
            pinned += 1;
        }
    }
    if pinned == 0 {
        return;
    }
    match lock.save(project_dir) {
        Ok(()) => eprintln!("🔒 Updated govbot.lock ({} datasets pinned)", pinned),
        Err(e) => eprintln!("⚠️  Could not write govbot.lock: {}", e),
    }
}

async fn run_pull_command(cmd: Command) -> anyhow::Result<()> {
    let Command::Pull {
        repos,
        govbot_dir,
        token,
        parallel,
        verbose,
        list,
    } = cmd
    else {
        unreachable!()
    };

    let registry = load_registry()?;

    // If --list flag is set, show the list
    if list {
        println!("Available datasets:");
        for d in registry.all() {
            println!("  {}", d.short_name());
        }
        println!("  all (pull every dataset)");
        return Ok(());
    }

    let repos_dir = get_govbot_dir(govbot_dir)?;
    let proj_dir = project_dir()?;

    // Get token from argument or environment variable
    let env_token = std::env::var("TOKEN").ok();
    let token_str = token.as_deref().or(env_token.as_deref());

    // Get parallelization setting
    let num_jobs = parallel
        .or_else(|| {
            std::env::var("GOVBOT_JOBS")
                .ok()
                .and_then(|s| s.parse().ok())
        })
        .unwrap_or(4);

    // Resolve which datasets to pull.
    let datasets_to_pull: Vec<govbot::ResolvedDataset> = if repos.is_empty() {
        // No datasets specified: update whatever is already cloned locally.
        // A locally-present dataset that is no longer in the registry is
        // skipped with a warning rather than aborting the whole update.
        let local = git::get_local_datasets(&repos_dir).unwrap_or_default();
        if local.is_empty() {
            eprintln!("No datasets downloaded yet in this directory");
            eprintln!("to download all gov data, do `govbot pull all`. future syncs are just `govbot pull`");
            return Ok(());
        }
        std::fs::create_dir_all(&repos_dir)?;
        let mut resolved = Vec::new();
        for short in &local {
            match registry.resolve(short) {
                Ok(d) => resolved.push(d),
                Err(_) => eprintln!("⚠️  Skipping '{}' — not in the registry", short),
            }
        }
        resolved
    } else {
        std::fs::create_dir_all(&repos_dir)?;
        registry
            .resolve_all(&repos)
            .map_err(|e| anyhow::anyhow!("{}", e))?
    };

    if datasets_to_pull.is_empty() {
        return Ok(());
    }

    // Print initial message with count
    eprintln!("🔁 Syncing {} datasets\n", datasets_to_pull.len());

    // Perform clone operations and print results as they complete
    let results =
        perform_clone_operations(datasets_to_pull, repos_dir, token_str, num_jobs, verbose).await?;

    // Pin resolved SHAs into govbot.lock for reproducibility.
    update_lockfile(&proj_dir, &results);

    // Show summary
    let errors: Vec<_> = results.iter().filter(|r| r.result == "failed").collect();

    if !errors.is_empty() {
        eprintln!("\n❌ Errors occurred: {}/{}", errors.len(), results.len());
    } else if !results.is_empty() {
        eprintln!(
            "\n✅ Successfully processed all {} datasets!",
            results.len()
        );
    }

    Ok(())
}

async fn run_delete_command(cmd: Command) -> anyhow::Result<()> {
    let Command::Delete {
        locales,
        govbot_dir,
        parallel,
        verbose,
    } = cmd
    else {
        unreachable!()
    };

    // If no locales specified, show help message
    if locales.is_empty() {
        eprintln!("Error: No locales specified.");
        eprintln!();
        eprintln!("To delete all repositories, use: govbot delete all");
        eprintln!("To delete specific locales, use: govbot delete <locale1> <locale2> ...");
        eprintln!();
        eprintln!("Available options:");
        eprintln!("  --govbot-dir <dir>    Directory containing repositories");
        eprintln!("  --parallel <num>      Number of parallel operations (default: 4)");
        eprintln!("  --verbose             Show verbose output");
        return Ok(());
    }

    let repos_dir = get_govbot_dir(govbot_dir)?;

    // Get parallelization setting
    let num_jobs = parallel
        .or_else(|| {
            std::env::var("GOVBOT_JOBS")
                .ok()
                .and_then(|s| s.parse().ok())
        })
        .unwrap_or(4);

    // Parse datasets and handle "all". `all` expands to whatever is cloned
    // locally — there is nothing to delete that is not on disk.
    let mut locales_to_delete = Vec::new();
    for locale in locales {
        let locale = locale.trim().to_lowercase();
        if locale.is_empty() {
            continue;
        }

        if locale == "all" {
            for short in git::get_local_datasets(&repos_dir).unwrap_or_default() {
                locales_to_delete.push(short);
            }
        } else {
            // A dataset identifier may be namespaced; delete keys on the short
            // (slash-free) name the clone directory uses.
            let short = locale.rsplit('/').next().unwrap_or(&locale).to_string();
            let short = short.split('@').next().unwrap_or(&short).to_string();
            locales_to_delete.push(short);
        }
    }

    if locales_to_delete.is_empty() {
        return Ok(());
    }

    // Print initial message with count
    eprintln!("🗑️  Deleting {} repos\n", locales_to_delete.len());

    // Perform delete operations
    let total = locales_to_delete.len();
    let mut deleted_count = 0;
    let mut failed_count = 0;

    if total == 1 || num_jobs == 1 {
        // Sequential delete
        for (idx, locale) in locales_to_delete.iter().enumerate() {
            let repo_name = git::repo_dir_name(locale);
            let target_dir = repos_dir.join(&repo_name);
            let existed = target_dir.exists() || std::fs::symlink_metadata(&target_dir).is_ok();

            if verbose {
                eprintln!("[{}/{}] Deleting {}...", idx + 1, total, locale);
            }

            match git::delete_dataset(locale, &repos_dir) {
                Ok(_) => {
                    if existed {
                        eprintln!("{:<4}  deleted", locale);
                        deleted_count += 1;
                    } else {
                        eprintln!("{:<4}  not_found", locale);
                    }
                }
                Err(e) => {
                    eprintln!("{:<4}  failed     {}", locale, e);
                    failed_count += 1;
                }
            }
        }
    } else {
        // Parallel delete
        use std::sync::{Arc, Mutex};
        let deleted = Arc::new(Mutex::new(0usize));
        let failed = Arc::new(Mutex::new(0usize));

        let delete_futures = stream::iter(locales_to_delete.iter())
            .map(|locale| {
                let locale = locale.clone();
                let repos_dir = repos_dir.clone();
                let deleted = deleted.clone();
                let failed = failed.clone();
                let total = total;
                let verbose_flag = verbose;

                tokio::task::spawn_blocking(move || {
                    let repo_name = git::repo_dir_name(&locale);
                    let target_dir = repos_dir.join(&repo_name);

                    if verbose_flag {
                        let d = deleted.lock().unwrap();
                        let f = failed.lock().unwrap();
                        let current = *d + *f + 1;
                        eprintln!("[{}/{}] Deleting {}...", current, total, locale);
                    }

                    let existed =
                        target_dir.exists() || std::fs::symlink_metadata(&target_dir).is_ok();
                    match git::delete_dataset(&locale, &repos_dir) {
                        Ok(_) => {
                            if existed {
                                let mut d = deleted.lock().unwrap();
                                *d += 1;
                                (locale, Ok("deleted".to_string()))
                            } else {
                                (locale, Ok("not_found".to_string()))
                            }
                        }
                        Err(e) => {
                            let mut f = failed.lock().unwrap();
                            *f += 1;
                            (locale, Err(e.to_string()))
                        }
                    }
                })
            })
            .buffer_unordered(num_jobs);

        let mut stream = delete_futures;

        while let Some(result) = stream.next().await {
            match result {
                Ok((locale, Ok(status))) => {
                    eprintln!("{:<4}  {}", locale, status);
                }
                Ok((locale, Err(error))) => {
                    eprintln!("{:<4}  failed     {}", locale, error);
                }
                Err(e) => {
                    eprintln!("unknown  failed     Task error: {}", e);
                    let mut f = failed.lock().unwrap();
                    *f += 1;
                }
            }
        }

        deleted_count = *deleted.lock().unwrap();
        failed_count = *failed.lock().unwrap();
    }

    // Show summary
    if failed_count > 0 {
        eprintln!("\n❌ Errors occurred: {}/{}", failed_count, total);
    } else if deleted_count > 0 {
        eprintln!("\n✅ Successfully deleted {} repositories!", deleted_count);
    } else {
        eprintln!("\n✅ No repositories found to delete.");
    }

    Ok(())
}

/// Collapse a fully-joined `govbot source` entry into the
/// `{"id","text","kind":"docs"}` document the govbot stream protocol defines
/// (`STREAM_PROTOCOL.md` §1) — the record `fastclass classify -` consumes.
///
/// `id` is the bill's dataset-relative directory path (derived from
/// `sources.log` by dropping the `/logs/<file>.json` tail), so a classified
/// result can be routed back to the right place when `govbot apply` writes it.
/// `text` is the **full** bill text assembled from `metadata.json` (not just
/// titles) — the `docs` projection joins the complete bill so this is whole.
fn ocd_entry_to_doc(entry: &serde_json::Value) -> serde_json::Value {
    let id = entry
        .get("sources")
        .and_then(|s| s.get("log"))
        .and_then(|v| v.as_str())
        .and_then(|log_path| log_path.split("/logs/").next())
        .map(|s| s.to_string())
        .or_else(|| {
            entry
                .get("log")
                .and_then(|l| l.get("bill_id").or_else(|| l.get("bill_identifier")))
                .and_then(|v| v.as_str())
                .map(|s| s.to_string())
        })
        .unwrap_or_default();
    serde_json::json!({ "id": id, "text": ocd_files_select_default(entry), "kind": "docs" })
}

async fn run_source_command(cmd: Command) -> anyhow::Result<()> {
    let Command::Source {
        govbot_dir,
        repos,
        sort: _sort,
        limit,
        join,
        select,
        filter,
    } = cmd
    else {
        unreachable!()
    };

    // Parse join options - now supports field paths like "bill.title" and special "tags"
    let mut join_specs: Vec<(String, Vec<String>)> = Vec::new();
    let mut join_tags = false;
    if !join.is_empty() {
        for part in join.split(',').map(|s| s.trim()).filter(|s| !s.is_empty()) {
            if part == "tags" {
                join_tags = true;
            } else if let Some(spec) = parse_join_string(part) {
                join_specs.push(spec);
            }
        }
    }

    let git_dir = get_govbot_dir(govbot_dir)?;

    // Parse limit: "none" means no limit, otherwise parse as usize
    let limit_parsed: Option<usize> = if limit.to_lowercase() == "none" {
        None
    } else {
        Some(
            limit
                .parse()
                .map_err(|e| anyhow::anyhow!("Invalid limit value '{}': {}", limit, e))?,
        )
    };

    // Parse comma-separated repos if provided as single string
    let mut repo_list: Vec<String> = if repos.len() == 1 && repos[0].contains(',') {
        repos[0]
            .split(',')
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .collect()
    } else {
        repos
    };

    // Default to "all" if no repos specified
    if repo_list.is_empty() {
        repo_list.push("all".to_string());
    }

    // Expand "all" to the datasets cloned in the directory, or map dataset
    // identifiers to their on-disk repo directory names.
    let mut repos_to_process = Vec::new();
    for locale in repo_list {
        let locale = locale.trim().to_lowercase();
        if locale.is_empty() {
            continue;
        }

        if locale == "all" {
            // Every dataset cloned locally — registry membership is not
            // required here, only on-disk presence.
            if git_dir.exists() {
                for short in git::get_local_datasets(&git_dir).unwrap_or_default() {
                    repos_to_process.push(git::repo_dir_name(&short));
                }
            }
        } else {
            // A dataset identifier may be namespaced; the clone directory is
            // keyed on the short (slash-free) name.
            let short = locale.rsplit('/').next().unwrap_or(&locale);
            let short = short.split('@').next().unwrap_or(short);
            repos_to_process.push(git::repo_dir_name(short));
        }
    }

    // Per-repo limit
    let per_repo_limit = limit_parsed;

    // Initialize filter (now has default value "default")
    let filter_manager = govbot::FilterManager::new(govbot::FilterAlias::from(filter.as_str()));

    // Process each repo (with optional filtering)
    for repo_name in repos_to_process {
        // A project's repo entry may be a symlink into the shared dataset
        // cache. The walker reads through it transparently and reports child
        // paths under `git_dir`, so `sources.log` stays project-relative.
        let repo_path = git_dir.join(&repo_name);

        if !repo_path.exists() {
            eprintln!("Warning: Repository not found: {}", repo_path.display());
            continue;
        }

        // Walk the repo directory to find log files matching the pattern:
        // repo_name/country:{country}/state:{state}/sessions/{session_name}/logs/*.json
        let mut file_count = 0;

        for entry_result in WalkDir::new(&repo_path)
            .process_read_dir(|_depth, _path, _read_dir_state, _children| {
                // Optional: customize directory reading behavior
            })
            .into_iter()
        {
            let entry = match entry_result {
                Ok(e) => e,
                Err(_) => continue,
            };

            // Check per-repo limit
            if let Some(limit) = per_repo_limit {
                if file_count >= limit {
                    break;
                }
            }

            let path = entry.path();

            // Check if it's a JSON file in a logs directory
            if !path.is_file() {
                continue;
            }

            if path.extension().and_then(|s| s.to_str()) != Some("json") {
                continue;
            }

            // Check if path matches: country:{country}/state:{state}/sessions/{session_name}/logs/*.json
            let path_str = path.to_string_lossy();
            let repo_prefix = repo_path.to_string_lossy();

            // Get relative path by stripping the repo prefix
            // Handle both absolute and relative paths
            let relative_path = if let Some(stripped) = path_str.strip_prefix(&*repo_prefix) {
                // Remove leading slash if present
                stripped.strip_prefix('/').unwrap_or(stripped)
            } else {
                // If prefix doesn't match, skip this file
                continue;
            };

            // Match pattern: country:*/state:*/sessions/*/logs/*.json
            // Use a simple regex-like check: must have these components in order
            if relative_path.starts_with("country:")
                && relative_path.contains("/state:")
                && relative_path.contains("/sessions/")
                && relative_path.contains("/logs/")
                && relative_path.ends_with(".json")
            {
                // Verify order by checking positions
                let country_pos = relative_path.find("country:").unwrap_or(0);
                let state_pos = relative_path.find("/state:").unwrap_or(usize::MAX);
                let sessions_pos = relative_path.find("/sessions/").unwrap_or(usize::MAX);
                let logs_pos = relative_path.find("/logs/").unwrap_or(usize::MAX);

                // Verify order: country < state < sessions < logs
                if country_pos < state_pos && state_pos < sessions_pos && sessions_pos < logs_pos {
                    // Compute relative source path
                    let source_path_str = compute_relative_source_path(&path, &git_dir);

                    // Read JSON file, parse it, and build extensible output structure
                    match fs::read_to_string(&path) {
                        Ok(contents) => {
                            // Parse JSON
                            match serde_json::from_str::<serde_json::Value>(&contents) {
                                Ok(json_value) => {
                                    // Extract bill_id early (before moving json_value)
                                    // The json_value IS the log data, so bill_id is at the top level
                                    let bill_id_opt = json_value
                                        .get("bill_id")
                                        .or_else(|| json_value.get("bill_identifier"))
                                        .and_then(|id| id.as_str())
                                        .map(|s| s.to_string());

                                    // Build output with extensible structure:
                                    // - Data keys (log, bill, etc.) are singular entity names matching source keys
                                    // - sources object automatically tracks all data sources
                                    let mut output = serde_json::Map::new();

                                    // Add the log data with key "log" (matching sources.log)
                                    output.insert("log".to_string(), json_value);

                                    // Add sources with the log path
                                    let mut sources = serde_json::Map::new();
                                    sources.insert(
                                        "log".to_string(),
                                        serde_json::Value::String(source_path_str.clone()),
                                    );

                                    // Join additional datasets if requested
                                    for (dataset_name, field_path) in &join_specs {
                                        match dataset_name.as_str() {
                                            "bill" => {
                                                // Hardcoded: metadata.json is in the parent directory of logs/
                                                // log path: .../bills/{bill_id}/logs/file.json
                                                // metadata path: .../bills/{bill_id}/metadata.json
                                                let canonical_log_path = match path.canonicalize() {
                                                    Ok(p) => p,
                                                    Err(_) => path.clone(),
                                                };

                                                let metadata_path = canonical_log_path
                                                    .parent()
                                                    .and_then(|logs_dir| {
                                                        logs_dir.parent().map(|bill_dir| {
                                                            bill_dir.join("metadata.json")
                                                        })
                                                    });

                                                if let Some(ref metadata_path) = metadata_path {
                                                    if metadata_path.exists() {
                                                        match fs::read_to_string(metadata_path) {
                                                            Ok(metadata_contents) => {
                                                                match serde_json::from_str::<
                                                                    serde_json::Value,
                                                                >(
                                                                    &metadata_contents
                                                                ) {
                                                                    Ok(metadata_value) => {
                                                                        // If field_path is specified, extract just that field
                                                                        // Otherwise, include the full bill data
                                                                        if field_path.is_empty() {
                                                                            // No field path specified, include full bill data
                                                                            output.insert(
                                                                                "bill".to_string(),
                                                                                metadata_value,
                                                                            );
                                                                        } else {
                                                                            // Extract specific field(s) from bill data
                                                                            if let Some(
                                                                                field_value,
                                                                            ) =
                                                                                extract_json_field(
                                                                                    &metadata_value,
                                                                                    field_path,
                                                                                )
                                                                            {
                                                                                // Use the full join path as the key (e.g., "bill.title")
                                                                                let output_key = format!(
                                                                                    "{}.{}",
                                                                                    dataset_name,
                                                                                    field_path
                                                                                        .join(".")
                                                                                );
                                                                                output.insert(
                                                                                    output_key,
                                                                                    field_value,
                                                                                );
                                                                            } else {
                                                                                eprintln!("Warning: Field path {:?} not found in metadata from {}", field_path, metadata_path.display());
                                                                            }
                                                                        }

                                                                        // Add bill source path
                                                                        let bill_source_path = compute_relative_source_path(metadata_path, &git_dir);
                                                                        sources.insert("bill".to_string(), serde_json::Value::String(bill_source_path));
                                                                    }
                                                                    Err(e) => {
                                                                        eprintln!("Error parsing metadata JSON from {}: {}", metadata_path.display(), e);
                                                                    }
                                                                }
                                                            }
                                                            Err(e) => {
                                                                eprintln!("Error reading metadata from {}: {}", metadata_path.display(), e);
                                                            }
                                                        }
                                                    } else {
                                                        eprintln!("Warning: Metadata file does not exist: {}", metadata_path.display());
                                                    }
                                                } else {
                                                    eprintln!("Warning: Could not determine metadata path for log file: {}", relative_path);
                                                }
                                            }
                                            _ => {
                                                eprintln!(
                                                    "Warning: Unknown join dataset: {}",
                                                    dataset_name
                                                );
                                            }
                                        }
                                    }

                                    // Join tags if requested
                                    if join_tags {
                                        // Extract country, state, session_id from the path
                                        if let Some((country, state, session_id)) =
                                            extract_path_info(&source_path_str)
                                        {
                                            // Use bill_id extracted earlier
                                            if let Some(ref bill_id) = bill_id_opt {
                                                // Look for tags in cwd/country:us/state:{state}/sessions/{session_id}/tags/
                                                let cwd = std::env::current_dir()
                                                    .unwrap_or_else(|_| PathBuf::from("."));
                                                let tags_dir = cwd
                                                    .join(&format!("country:{}", country))
                                                    .join(&format!("state:{}", state))
                                                    .join("sessions")
                                                    .join(&session_id)
                                                    .join("tags");

                                                if tags_dir.exists() && tags_dir.is_dir() {
                                                    let mut matched_tags = serde_json::Map::new();
                                                    if let Ok(entries) = fs::read_dir(&tags_dir) {
                                                        for entry in entries.flatten() {
                                                            let path = entry.path();
                                                            // Check for both .tag.json and .json files
                                                            if let Some(ext) = path
                                                                .extension()
                                                                .and_then(|s| s.to_str())
                                                            {
                                                                if ext == "json" {
                                                                    if let Some(stem) = path
                                                                        .file_stem()
                                                                        .and_then(|s| s.to_str())
                                                                    {
                                                                        // Remove .tag suffix if present (e.g., "budget.tag" -> "budget")
                                                                        let tag_name = stem
                                                                            .strip_suffix(".tag")
                                                                            .unwrap_or(stem);
                                                                        match fs::read_to_string(
                                                                            &path,
                                                                        ) {
                                                                            Ok(contents) => {
                                                                                if let Ok(tag_file) = serde_json::from_str::<govbot::TagFile>(&contents) {
                                                                                    // Check if bill_id exists in bills map
                                                                                    if let Some(bill_result) = tag_file.bills.get(bill_id) {
                                                                                        // Return the score breakdown
                                                                                        matched_tags.insert(tag_name.to_string(), serde_json::to_value(&bill_result.score).unwrap_or(serde_json::Value::Null));
                                                                                    }
                                                                                }
                                                                            }
                                                                            Err(_) => {}
                                                                        }
                                                                    }
                                                                }
                                                            }
                                                        }
                                                    }
                                                    if !matched_tags.is_empty() {
                                                        output.insert(
                                                            "tags".to_string(),
                                                            serde_json::Value::Object(matched_tags),
                                                        );
                                                    }
                                                }
                                            }
                                        }
                                    }

                                    output.insert(
                                        "sources".to_string(),
                                        serde_json::Value::Object(sources),
                                    );

                                    // Extract timestamp from sources.log path (after "logs/" and before "_")
                                    // Do this after sources is inserted so we can use the final sources.log value
                                    let timestamp = extract_timestamp_from_path(&source_path_str);
                                    if let Some(ref ts) = timestamp {
                                        output.insert(
                                            "timestamp".to_string(),
                                            serde_json::Value::String(ts.clone()),
                                        );
                                    }

                                    let mut output_value = serde_json::Value::Object(output);

                                    // Apply select transformation if requested.
                                    // `default` trims each entry to the familiar
                                    // title/abstracts/subject shape. `docs` deliberately
                                    // does NOT trim — it keeps the full joined `bill`
                                    // (the whole metadata.json) so the {id,text,kind}
                                    // document carries the FULL bill text per
                                    // STREAM_PROTOCOL §1. The collapse to {id,text,kind}
                                    // happens after the entry survives the filter.
                                    if select == "default" {
                                        // Select specific keys from nested objects, preserving structure
                                        let mut selected_output = serde_json::Map::new();

                                        // Top: id (from log.bill_id), then log object with selected fields
                                        if let Some(id) = output_value
                                            .get("log")
                                            .and_then(|l| {
                                                l.get("bill_id")
                                                    .or_else(|| l.get("bill_identifier"))
                                            })
                                            .and_then(|v| v.as_str())
                                        {
                                            selected_output.insert(
                                                "id".to_string(),
                                                serde_json::Value::String(id.to_string()),
                                            );
                                        }

                                        // Create log object with only action and bill_id
                                        if let Some(log) = output_value.get("log") {
                                            let mut log_obj = serde_json::Map::new();
                                            if let Some(action) = log.get("action") {
                                                log_obj
                                                    .insert("action".to_string(), action.clone());
                                            }
                                            if let Some(bill_id) = log
                                                .get("bill_id")
                                                .or_else(|| log.get("bill_identifier"))
                                            {
                                                log_obj
                                                    .insert("bill_id".to_string(), bill_id.clone());
                                            }
                                            if !log_obj.is_empty() {
                                                selected_output.insert(
                                                    "log".to_string(),
                                                    serde_json::Value::Object(log_obj),
                                                );
                                            }
                                        }

                                        // Create bill object with only selected fields
                                        if let Some(bill) = output_value.get("bill") {
                                            let mut bill_obj = serde_json::Map::new();
                                            if let Some(title) = bill.get("title") {
                                                bill_obj.insert("title".to_string(), title.clone());
                                            }
                                            if let Some(abstracts) = bill.get("abstracts") {
                                                bill_obj.insert(
                                                    "abstracts".to_string(),
                                                    abstracts.clone(),
                                                );
                                            }
                                            if let Some(subject) = bill.get("subject") {
                                                bill_obj
                                                    .insert("subject".to_string(), subject.clone());
                                            }
                                            if let Some(identifier) = bill.get("identifier") {
                                                bill_obj.insert(
                                                    "identifier".to_string(),
                                                    identifier.clone(),
                                                );
                                            }
                                            if let Some(session) = bill.get("legislative_session") {
                                                bill_obj.insert(
                                                    "legislative_session".to_string(),
                                                    session.clone(),
                                                );
                                            }
                                            if let Some(org) = bill.get("from_organization") {
                                                bill_obj.insert(
                                                    "from_organization".to_string(),
                                                    org.clone(),
                                                );
                                            }
                                            if !bill_obj.is_empty() {
                                                selected_output.insert(
                                                    "bill".to_string(),
                                                    serde_json::Value::Object(bill_obj),
                                                );
                                            }
                                        }

                                        // Always include tags (even if empty/null) since it's part of the default selector
                                        if let Some(tags) = output_value.get("tags") {
                                            selected_output
                                                .insert("tags".to_string(), tags.clone());
                                        } else {
                                            // Include empty tags object if not present
                                            selected_output.insert(
                                                "tags".to_string(),
                                                serde_json::Value::Null,
                                            );
                                        }

                                        // Bottom: sources, timestamp
                                        if let Some(sources) = output_value.get("sources") {
                                            selected_output
                                                .insert("sources".to_string(), sources.clone());
                                        }
                                        if let Some(timestamp) = output_value.get("timestamp") {
                                            selected_output
                                                .insert("timestamp".to_string(), timestamp.clone());
                                        }

                                        output_value = serde_json::Value::Object(selected_output);
                                    }

                                    // Apply filter
                                    let should_output = match filter_manager
                                        .should_keep(&output_value, &repo_name)
                                    {
                                        govbot::FilterResult::Keep => true,
                                        govbot::FilterResult::FilterOut => false,
                                    };

                                    if should_output {
                                        // `docs` mode: collapse the surviving entry to the
                                        // {id,text} document shape fastclass consumes.
                                        let output_value = if select == "docs" {
                                            ocd_entry_to_doc(&output_value)
                                        } else {
                                            output_value
                                        };
                                        // Deep prune empty/null values before serialization
                                        let pruned_value = deep_prune_json(output_value);

                                        // Serialize as compact JSON (single line)
                                        match serde_json::to_string(&pruned_value) {
                                            Ok(json_line) => {
                                                // Ignore broken pipe errors (e.g., when piped to yq/jq that closes early)
                                                if write_json_line(&json_line).is_ok() {
                                                    file_count += 1;
                                                }
                                            }
                                            Err(e) => {
                                                eprintln!(
                                                    "Error serializing JSON from {}: {}",
                                                    path.display(),
                                                    e
                                                );
                                            }
                                        }
                                    }
                                }
                                Err(e) => {
                                    eprintln!("Error parsing JSON from {}: {}", path.display(), e);
                                }
                            }
                        }
                        Err(e) => {
                            eprintln!("Error reading {}: {}", path.display(), e);
                        }
                    }
                }
            }
        }
    }

    Ok(())
}

/// Parse a join string like "bill.title" into (dataset_name, field_path)
fn parse_join_string(join_str: &str) -> Option<(String, Vec<String>)> {
    let parts: Vec<&str> = join_str.split('.').collect();
    if parts.is_empty() {
        return None;
    }

    let dataset_name = parts[0].to_string();
    let field_path = if parts.len() > 1 {
        parts[1..].iter().map(|s| s.to_string()).collect()
    } else {
        Vec::new()
    };

    Some((dataset_name, field_path))
}

/// Extract a value from JSON using a field path (e.g., ["title"] or ["bill", "title"])
fn extract_json_field(
    value: &serde_json::Value,
    field_path: &[String],
) -> Option<serde_json::Value> {
    let mut current = value;

    for field in field_path {
        match current {
            serde_json::Value::Object(map) => {
                current = map.get(field)?;
            }
            serde_json::Value::Array(arr) => {
                if let Ok(idx) = field.parse::<usize>() {
                    current = arr.get(idx)?;
                } else {
                    return None;
                }
            }
            _ => return None,
        }
    }

    Some(current.clone())
}

/// Deep prune JSON value by removing null, empty strings, empty arrays, and empty objects
/// This recursively processes the entire JSON structure
fn deep_prune_json(value: serde_json::Value) -> serde_json::Value {
    match value {
        serde_json::Value::Null => serde_json::Value::Null, // Will be filtered out by parent
        serde_json::Value::String(s) => {
            if s.is_empty() {
                serde_json::Value::Null
            } else {
                serde_json::Value::String(s)
            }
        }
        serde_json::Value::Array(arr) => {
            let pruned: Vec<serde_json::Value> = arr
                .into_iter()
                .map(deep_prune_json)
                .filter(|v| !v.is_null())
                .collect();
            if pruned.is_empty() {
                serde_json::Value::Null
            } else {
                serde_json::Value::Array(pruned)
            }
        }
        serde_json::Value::Object(map) => {
            let mut pruned = serde_json::Map::new();
            for (k, v) in map {
                let pruned_value = deep_prune_json(v);
                // Only include non-null values
                if !pruned_value.is_null() {
                    pruned.insert(k, pruned_value);
                }
            }
            if pruned.is_empty() {
                serde_json::Value::Null
            } else {
                serde_json::Value::Object(pruned)
            }
        }
        // For numbers, booleans, keep as-is
        other => other,
    }
}

/// Extract timestamp from a path string (after "logs/" and before "_")
/// Example: "path/to/logs/20250121T000000Z_filename.json" -> "20250121T000000Z"
fn extract_timestamp_from_path(path: &str) -> Option<String> {
    // Find the position of "/logs/"
    if let Some(logs_pos) = path.find("/logs/") {
        // Get the substring after "/logs/"
        let after_logs = &path[logs_pos + 6..];
        // Find the position of "_" after "logs/"
        if let Some(underscore_pos) = after_logs.find('_') {
            // Extract the timestamp (between "logs/" and "_")
            let timestamp = &after_logs[..underscore_pos];
            if !timestamp.is_empty() {
                return Some(timestamp.to_string());
            }
        }
    }
    None
}

/// Compute the relative path from `git_dir` to a walked file.
///
/// Files are walked as `git_dir/<repo>/...` — including through a `<repo>`
/// symlink into the shared dataset cache — so the direct (non-canonicalized)
/// diff is what keeps `sources.log` project-relative. Canonicalizing here
/// would resolve a cached dataset to `~/.govbot/cache/...` and escape
/// `git_dir`; it is used only as a last-resort fallback.
fn compute_relative_source_path(file_path: &PathBuf, git_dir: &PathBuf) -> String {
    // Preferred: the path as walked, relative to git_dir.
    if let Some(rel) = pathdiff::diff_paths(file_path, git_dir) {
        if !rel.starts_with("..") {
            return rel.to_string_lossy().replace('\\', "/");
        }
    }

    // Fallback: canonicalize both ends and diff.
    let canonical_file = file_path
        .canonicalize()
        .unwrap_or_else(|_| file_path.clone());
    let canonical_git_dir = git_dir.canonicalize().unwrap_or_else(|_| git_dir.clone());
    match pathdiff::diff_paths(&canonical_file, &canonical_git_dir) {
        Some(rel_path) => rel_path.to_string_lossy().replace('\\', "/"),
        None => pathdiff::diff_paths(file_path, git_dir)
            .map(|p| p.to_string_lossy().replace('\\', "/"))
            .unwrap_or_else(|| file_path.to_string_lossy().replace('\\', "/")),
    }
}

async fn run_load_command(cmd: Command) -> anyhow::Result<()> {
    let Command::Load {
        database,
        govbot_dir,
        memory_limit,
        threads,
    } = cmd
    else {
        unreachable!()
    };

    let repos_dir = get_govbot_dir(govbot_dir)?;

    // Check if directory exists
    if !repos_dir.exists() {
        eprintln!(
            "Error: Govbot repos directory not found: {}",
            repos_dir.display()
        );
        eprintln!("Run 'govbot pull all' first to pull datasets.");
        return Ok(());
    }

    // Get base govbot directory (parent of repos)
    // e.g., if repos_dir is ./.govbot/repos, base_dir is ./.govbot
    let base_govbot_dir = repos_dir
        .parent()
        .ok_or_else(|| anyhow::anyhow!("Could not determine base govbot directory"))?;

    // Ensure base directory exists
    std::fs::create_dir_all(base_govbot_dir)?;

    // Check if duckdb is available
    let duckdb_check = ProcessCommand::new("duckdb").arg("--version").output();

    if duckdb_check.is_err() {
        eprintln!("Error: 'duckdb' command not found.");
        eprintln!("Please install DuckDB: https://duckdb.org/docs/installation/");
        return Ok(());
    }

    // Database file goes in the base govbot directory
    // Resolve to absolute path to ensure it's created in the right location
    let db_path = base_govbot_dir
        .canonicalize()
        .unwrap_or_else(|_| base_govbot_dir.to_path_buf())
        .join(&database);
    let db_path_str = db_path.to_string_lossy().to_string();

    // Remove existing database if it exists
    if db_path.exists() {
        eprintln!("Removing existing database: {}", db_path.display());
        std::fs::remove_file(&db_path)?;
    }

    eprintln!("Loading data into {}...", db_path.display());
    eprintln!("This may take a few minutes depending on the number of files...");

    // Create SQL script
    let mut sql_script = String::new();
    sql_script.push_str("-- Load JSON extension\n");
    sql_script.push_str("INSTALL json;\n");
    sql_script.push_str("LOAD json;\n");
    sql_script.push_str("\n");

    // Set memory limit if provided
    if let Some(ref mem_limit) = memory_limit {
        sql_script.push_str(&format!("SET memory_limit='{}';\n", mem_limit));
    } else {
        // Default to 16GB if not specified
        sql_script.push_str("SET memory_limit='16GB';\n");
    }

    // Set thread count
    let num_threads = threads.unwrap_or(4);
    sql_script.push_str(&format!("SET threads={};\n", num_threads));
    sql_script.push_str("SET preserve_insertion_order=false;\n");
    sql_script.push_str("\n");

    // Create table from metadata.json files
    let repos_dir_str = repos_dir.to_string_lossy();
    sql_script.push_str("-- Create table from metadata.json files only\n");
    sql_script.push_str("-- Using union_by_name to handle schema variations across files\n");
    sql_script.push_str("CREATE TABLE bills AS\n");
    sql_script.push_str("SELECT \n");
    sql_script.push_str("    *,\n");
    sql_script.push_str("    filename as source_file\n");
    sql_script.push_str(&format!(
        "FROM read_json_auto('{}/**/bills/*/metadata.json', \n",
        repos_dir_str
    ));
    sql_script.push_str("    filename=true, \n");
    sql_script.push_str("    union_by_name=true);\n");
    sql_script.push_str("\n");

    // Create summary view
    sql_script.push_str("-- Create some useful views\n");
    sql_script.push_str("CREATE VIEW bills_summary AS\n");
    sql_script.push_str("SELECT \n");
    sql_script.push_str("    identifier,\n");
    sql_script.push_str("    title,\n");
    sql_script.push_str("    legislative_session,\n");
    sql_script.push_str("    jurisdiction->>'id' as jurisdiction_id,\n");
    sql_script.push_str("    jurisdiction->>'name' as jurisdiction_name,\n");
    sql_script.push_str("    json_array_length(actions) as action_count,\n");
    sql_script.push_str("    json_array_length(sponsorships) as sponsor_count,\n");
    sql_script.push_str("    source_file\n");
    sql_script.push_str("FROM bills;\n");
    sql_script.push_str("\n");

    // Show summary
    sql_script.push_str("-- Show summary\n");
    sql_script.push_str("SELECT 'Bills loaded:' as info, COUNT(*) as count FROM bills;\n");

    // Run duckdb as subprocess
    let mut duckdb_cmd = ProcessCommand::new("duckdb");
    duckdb_cmd.arg(&db_path_str);
    duckdb_cmd.stdin(std::process::Stdio::piped());
    duckdb_cmd.stdout(std::process::Stdio::piped());
    duckdb_cmd.stderr(std::process::Stdio::piped());

    let mut child = duckdb_cmd.spawn()?;

    // Write SQL to stdin
    if let Some(mut stdin) = child.stdin.take() {
        stdin.write_all(sql_script.as_bytes())?;
        stdin.flush()?;
    }

    // Wait for completion and capture output
    let output = child.wait_with_output()?;

    if !output.status.success() {
        eprintln!("Error loading data into DuckDB:");
        eprintln!("{}", String::from_utf8_lossy(&output.stderr));
        return Err(anyhow::anyhow!("DuckDB command failed"));
    }

    // Print stdout (summary)
    let stdout = String::from_utf8_lossy(&output.stdout);
    if !stdout.trim().is_empty() {
        print!("{}", stdout);
    }

    eprintln!("\n✅ Database created: {}", db_path.display());
    eprintln!("\nTo open in DuckDB UI, run:");
    eprintln!("  duckdb --ui {}", db_path.display());
    eprintln!("\nOr query from command line:");
    eprintln!("  duckdb {}", db_path.display());
    eprintln!("\nAvailable tables:");
    eprintln!("  - bills (bill metadata from metadata.json files)");
    eprintln!("  - bills_summary (summary view)");

    Ok(())
}

/// Extract country, state, and session_id from a log path
/// Path format: .../country:us/state:il/sessions/104th/bills/...
fn extract_path_info(path: &str) -> Option<(String, String, String)> {
    // Find country: pattern
    let country_start = path.find("country:")?;
    let country_end = path[country_start + 8..]
        .find('/')
        .unwrap_or(path.len() - country_start - 8);
    let country = path[country_start + 8..country_start + 8 + country_end].to_string();

    // Find state: pattern
    let state_start = path.find("/state:")?;
    let state_end = path[state_start + 7..]
        .find('/')
        .unwrap_or(path.len() - state_start - 7);
    let state = path[state_start + 7..state_start + 7 + state_end].to_string();

    // Find sessions/ pattern
    let sessions_start = path.find("/sessions/")?;
    let session_end = path[sessions_start + 10..]
        .find('/')
        .unwrap_or(path.len() - sessions_start - 10);
    let session_id = path[sessions_start + 10..sessions_start + 10 + session_end].to_string();

    Some((country, state, session_id))
}

/// The slice of a `fastclass classify` result that `govbot apply` consumes.
/// Unknown fields are ignored, so fastclass may evolve its output freely.
#[derive(serde::Deserialize)]
struct FastclassResult {
    doc: String,
    #[serde(default)]
    text_hash: String,
    #[serde(default)]
    tags: HashMap<String, FastclassTag>,
}

#[derive(serde::Deserialize)]
struct FastclassTag {
    #[serde(default)]
    matched: bool,
    #[serde(default)]
    fusion: FastclassFusion,
}

#[derive(serde::Deserialize, Default)]
struct FastclassFusion {
    #[serde(default)]
    final_score: f64,
}

/// A bill's location in the dataset, parsed from a fastclass result's `doc`
/// id — which `govbot source --select docs` set to the bill's directory path.
struct BillRoute {
    country: String,
    state: String,
    session: String,
    bill_id: String,
}

/// Parse a `doc` id of the form
/// `<repo>/country:<c>/state:<s>/sessions/<session>/bills/<bill_id>` into the
/// pieces needed to place its `.tag.json` file. Returns `None` for any id that
/// is not a dataset bill path (e.g. a document from a non-govbot source).
fn parse_doc_route(doc: &str) -> Option<BillRoute> {
    let segments: Vec<&str> = doc.split('/').collect();
    let (mut country, mut state, mut session, mut bill_id) = (None, None, None, None);
    for (i, seg) in segments.iter().enumerate() {
        if let Some(c) = seg.strip_prefix("country:") {
            country = Some(c.to_string());
        } else if let Some(s) = seg.strip_prefix("state:") {
            state = Some(s.to_string());
        } else if *seg == "sessions" {
            session = segments.get(i + 1).map(|s| s.to_string());
        } else if *seg == "bills" {
            bill_id = segments.get(i + 1).map(|s| s.to_string());
        }
    }
    Some(BillRoute {
        country: country?,
        state: state?,
        session: session?,
        bill_id: bill_id?,
    })
}

/// Build a fresh `TagFile` for `tag_key`. The taxonomy now lives in a fastclass
/// classifier bundle, not in `govbot.yml`, so `tag_defs` is normally empty and
/// each tag file gets a minimal stub `tag_config` derived from the tag name.
fn new_tag_file(tag_key: &str, tag_defs: &[govbot::TagDefinition], now: &str) -> TagFile {
    let tag_def = tag_defs
        .iter()
        .find(|td| td.name == tag_key)
        .cloned()
        .unwrap_or_else(|| govbot::TagDefinition {
            name: tag_key.to_string(),
            description: String::new(),
            examples: Vec::new(),
            include_keywords: Vec::new(),
            exclude_keywords: Vec::new(),
            negative_examples: Vec::new(),
            threshold: 0.5,
        });
    let tag_config_hash = hash_text(&serde_json::to_string(&tag_def).unwrap_or_default());
    TagFile {
        metadata: TagFileMetadata {
            last_run: now.to_string(),
            model: "fastclass".to_string(),
            tag_config_hash,
        },
        tag_config: tag_def,
        text_cache: HashMap::new(),
        bills: HashMap::new(),
    }
}

/// `govbot apply` — the persistence sink of the tagging pipeline.
///
/// It classifies nothing. It reads `fastclass classify` result JSON from
/// stdin — the apply sink of
/// `govbot source --select docs | fastclass classify - | govbot apply` — and
/// for every matched tag writes the bill into the per-tag `.tag.json` file
/// under the dataset's `sessions/<session>/tags/` directory. Those are the
/// files `govbot publish` later turns into feeds.
async fn run_apply_command(cmd: Command) -> anyhow::Result<()> {
    let Command::Apply {
        tag_name,
        output_dir,
        overwrite,
    } = cmd
    else {
        unreachable!()
    };

    let current_dir = std::env::current_dir()?;
    // Tag files land under --output-dir when given, otherwise the current
    // directory (which, for a govbot project, holds govbot.yml).
    let base_output_dir = output_dir
        .as_ref()
        .map(PathBuf::from)
        .unwrap_or_else(|| current_dir.clone());

    // The taxonomy now lives in a fastclass classifier bundle, not in
    // govbot.yml — each `.tag.json` is stamped with a stub `tag_config`
    // derived only from the matched tag name.
    let tag_defs: Vec<govbot::TagDefinition> = Vec::new();

    let stdin = io::stdin();
    let reader = BufReader::new(stdin.lock());
    let now = chrono::Utc::now().to_rfc3339();
    let mut written = 0usize;
    let mut skipped = 0usize;

    eprintln!("Reading fastclass classification results from stdin...");
    for line_result in reader.lines() {
        let line = line_result?;
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let result: FastclassResult = match serde_json::from_str(line) {
            Ok(r) => r,
            Err(e) => {
                eprintln!("Warning: skipping unparseable result line: {}", e);
                skipped += 1;
                continue;
            }
        };
        let Some(route) = parse_doc_route(&result.doc) else {
            eprintln!(
                "Warning: skipping '{}' — its id is not a dataset bill path. \
                 Stream documents in with `govbot source --select docs`.",
                result.doc
            );
            skipped += 1;
            continue;
        };

        // The tags this bill matched, optionally narrowed to one requested tag.
        let mut matched: Vec<(String, f64)> = Vec::new();
        for (name, tag) in &result.tags {
            if !tag.matched {
                continue;
            }
            if let Some(req) = &tag_name {
                if req != name {
                    continue;
                }
            }
            matched.push((name.clone(), tag.fusion.final_score));
        }
        if matched.is_empty() {
            continue;
        }

        let tags_dir = base_output_dir
            .join(format!("country:{}", route.country))
            .join(format!("state:{}", route.state))
            .join("sessions")
            .join(&route.session)
            .join("tags");
        fs::create_dir_all(&tags_dir)?;

        for (tag_key, final_score) in matched {
            let tag_path = tags_dir.join(format!("{}.tag.json", tag_key));

            // Update the existing tag file, or start a fresh one.
            let mut tag_file: TagFile = fs::read_to_string(&tag_path)
                .ok()
                .and_then(|c| serde_json::from_str(&c).ok())
                .unwrap_or_else(|| new_tag_file(&tag_key, &tag_defs, &now));

            // With --overwrite off, an already-tagged bill is left untouched.
            if !overwrite && tag_file.bills.contains_key(&route.bill_id) {
                continue;
            }

            tag_file.metadata.last_run = now.clone();
            tag_file.metadata.model = "fastclass".to_string();
            tag_file.bills.insert(
                route.bill_id.clone(),
                BillTagResult {
                    text_hash: result.text_hash.clone(),
                    score: govbot::ScoreBreakdown {
                        final_score,
                        base_embedding: None,
                        example_similarity: None,
                        keyword_match: Vec::new(),
                        negative_penalty: 0.0,
                    },
                },
            );
            fs::write(&tag_path, serde_json::to_string_pretty(&tag_file)?)?;
        }
        written += 1;
    }

    eprintln!(
        "\n✅ Persisted {} tagged bill(s) under {}; skipped {} entr(ies).",
        written,
        base_output_dir.display(),
        skipped
    );
    Ok(())
}

/// `govbot publish` — run the manifest's publishers.
///
/// Reads `govbot.yml`'s typed `publish:` map, collects the tagged result
/// stream from `govbot source`, and runs each named publisher (`rss`/`html`/
/// `json`/`duckdb`) against it. The publisher's tag list comes from
/// `publish.<name>.select`; the retired `tags:` manifest block is gone.
async fn run_publish_command(cmd: Command) -> anyhow::Result<()> {
    let Command::Publish {
        publishers,
        limit,
        output_dir,
        output_file,
        dry_run,
        govbot_dir,
    } = cmd
    else {
        unreachable!()
    };

    let current_dir = std::env::current_dir()?;
    let config_path = current_dir.join("govbot.yml");
    if !config_path.exists() {
        return Err(anyhow::anyhow!("govbot.yml not found in current directory"));
    }

    // Typed manifest — `publish:` is the publisher map.
    let manifest = load_manifest(&config_path)?;
    if manifest.publish.is_empty() {
        return Err(anyhow::anyhow!(
            "govbot.yml has no `publish:` publishers to run"
        ));
    }

    // Which publishers to run: all of them, or the requested subset.
    let names_to_run: Vec<String> = if publishers.is_empty() {
        manifest.publish.keys().cloned().collect()
    } else {
        for name in &publishers {
            if !manifest.publish.contains_key(name) {
                return Err(anyhow::anyhow!(
                    "publisher '{}' not found in govbot.yml `publish:`",
                    name
                ));
            }
        }
        publishers
    };

    // Resolve the base govbot directory for the `source` subprocess.
    let base_govbot_dir = if let Some(ref gd) = govbot_dir {
        gd.clone()
    } else if let Ok(gd) = std::env::var("GOVBOT_DIR") {
        gd
    } else {
        std::env::current_dir()
            .unwrap_or_else(|_| PathBuf::from("."))
            .join(".govbot")
            .to_string_lossy()
            .to_string()
    };

    // Collect the dataset record stream once: `govbot source` over all
    // datasets (an empty `--repos` means every dataset).
    let datasets_to_process: Vec<String> = if manifest.datasets == vec!["all".to_string()] {
        Vec::new()
    } else {
        manifest.datasets.clone()
    };

    let exe = std::env::current_exe().unwrap_or_else(|_| PathBuf::from("govbot"));
    let mut source_cmd = ProcessCommand::new(exe);
    source_cmd
        .arg("source")
        .arg("--join")
        .arg("bill,tags")
        .arg("--select")
        .arg("default")
        .arg("--filter")
        .arg("default")
        .arg("--sort")
        .arg("DESC");
    if !base_govbot_dir.is_empty() && base_govbot_dir != ".govbot" {
        source_cmd.arg("--govbot-dir").arg(&base_govbot_dir);
    }
    if !datasets_to_process.is_empty() {
        source_cmd.arg("--repos");
        for d in &datasets_to_process {
            source_cmd.arg(d);
        }
    }

    let output = source_cmd.output()?;
    if !output.status.success() {
        let stderr_str = String::from_utf8_lossy(&output.stderr);
        eprintln!("Error: source command failed: {:?}", output.status.code());
        eprintln!("Stderr: {}", stderr_str);
        return Err(anyhow::anyhow!("Failed to collect dataset records"));
    }

    let stdout_str = String::from_utf8_lossy(&output.stdout);
    if stdout_str.trim().is_empty() {
        eprintln!(
            "Warning: source returned no output. Make sure datasets are pulled \
             and contain records."
        );
    }
    let mut all_entries: Vec<serde_json::Value> = Vec::new();
    for line in stdout_str.lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        match serde_json::from_str::<serde_json::Value>(line) {
            Ok(entry) => all_entries.push(entry),
            Err(e) => {
                if !line.contains("Compiling") && !line.contains("Finished") {
                    eprintln!("Warning: Failed to parse JSON line: {}", e);
                }
            }
        }
    }

    // CLI `--limit` overrides every publisher's configured limit.
    let cli_limit: Option<Option<usize>> = limit.map(|s| {
        if s.eq_ignore_ascii_case("none") {
            None
        } else {
            s.parse().ok()
        }
    });

    // Run each named publisher against its filtered/sorted/limited stream.
    for name in &names_to_run {
        let publisher = manifest.publish.get(name).expect("checked above");
        let select = publisher.select.clone().unwrap_or_default();

        eprintln!(
            "\n=== Publisher '{}' ({:?}) — selecting tags: {} ===",
            name,
            publisher.kind,
            if select.is_empty() {
                "<all tagged>".to_string()
            } else {
                select.join(", ")
            }
        );

        // Filter to the publisher's selected tags, dedup, sort.
        let mut entries: Vec<serde_json::Value> = all_entries
            .iter()
            .filter(|e| filter_by_tags(e, &select))
            .cloned()
            .collect();
        entries = deduplicate_entries(entries);
        entries = sort_by_timestamp(entries);

        // Apply the limit: CLI override, else the publisher's, else 100.
        let limit_value: Option<usize> = match cli_limit {
            Some(v) => v,
            None => publisher.resolved_limit(Some(100)),
        };
        let original_count = entries.len();
        if let Some(lim) = limit_value {
            entries.truncate(lim);
            if original_count > lim {
                eprintln!(
                    "Limited '{}' to {} entries. Use --limit none for all {}.",
                    name, lim, original_count
                );
            }
        }

        let job = govbot::publish::PublishJob {
            name,
            publisher,
            entries,
            output_dir_override: output_dir.clone(),
            output_file_override: output_file.clone(),
            project_dir: current_dir.clone(),
            dry_run,
        };
        govbot::publish::run_publisher(&job)?;
    }

    Ok(())
}

async fn run_update_command() -> anyhow::Result<()> {
    let install_script_url = "https://raw.githubusercontent.com/chihacknight/govbot/main/actions/govbot/scripts/install-nightly.sh";

    eprintln!("🔄 Updating govbot to latest nightly version...");
    eprintln!(
        "Downloading and running install script from: {}",
        install_script_url
    );

    // Execute the install script by piping curl directly to sh
    // This avoids issues with shebang lines being interpreted as commands
    let mut cmd = ProcessCommand::new("sh");
    cmd.arg("-c");
    cmd.arg(&format!("curl -fsSL {} | sh", install_script_url));

    // Inherit stdin/stdout/stderr so the install script can interact with the user
    cmd.stdin(std::process::Stdio::inherit());
    cmd.stdout(std::process::Stdio::inherit());
    cmd.stderr(std::process::Stdio::inherit());

    let status = cmd.status()?;

    if status.success() {
        eprintln!("\n✅ Update completed successfully!");
        eprintln!("You may need to restart your terminal or run 'source ~/.zshrc' (or your shell profile) to use the updated version.");
    } else {
        return Err(anyhow::anyhow!(
            "Update failed with exit code: {}",
            status.code().unwrap_or(-1)
        ));
    }

    Ok(())
}

/// Locate the project's `govbot.yml`, erroring if there is none.
fn require_manifest_path() -> anyhow::Result<PathBuf> {
    let path = project_dir()?.join("govbot.yml");
    if !path.exists() {
        anyhow::bail!(
            "No govbot.yml in {}. Run `govbot init` to scaffold one.",
            project_dir()?.display()
        );
    }
    Ok(path)
}

/// `govbot add` — append validated dataset ids to `govbot.yml`'s `datasets:`.
fn run_add_command(cmd: Command) -> anyhow::Result<()> {
    let Command::Add { datasets } = cmd else {
        unreachable!()
    };
    let manifest_path = require_manifest_path()?;
    let registry = load_registry()?;

    // Validate every id against the registry before touching the file.
    let mut to_add = Vec::new();
    for id in &datasets {
        let id = id.trim();
        if id.is_empty() {
            continue;
        }
        if id.eq_ignore_ascii_case("all") {
            to_add.push("all".to_string());
            continue;
        }
        let resolved = registry.resolve(id).map_err(|e| anyhow::anyhow!("{}", e))?;
        // Add the identifier the user typed (keeps `wy` short and familiar);
        // resolution proved it valid.
        let _ = resolved;
        to_add.push(id.to_string());
    }

    // Parse the manifest, mutate `datasets`, write it back.
    let contents = std::fs::read_to_string(&manifest_path)?;
    let mut doc: serde_yaml::Value = serde_yaml::from_str(&contents)
        .map_err(|e| anyhow::anyhow!("Failed to parse govbot.yml: {}", e))?;

    let datasets_node = doc
        .get_mut("datasets")
        .and_then(|v| v.as_sequence_mut())
        .ok_or_else(|| anyhow::anyhow!("govbot.yml has no `datasets:` list"))?;

    let mut added = Vec::new();
    for id in to_add {
        let already = datasets_node
            .iter()
            .any(|v| v.as_str() == Some(id.as_str()));
        if already {
            eprintln!("  · {} already in datasets", id);
        } else {
            datasets_node.push(serde_yaml::Value::String(id.clone()));
            added.push(id);
        }
    }

    if added.is_empty() {
        eprintln!("Nothing to add.");
        return Ok(());
    }

    let yaml = serde_yaml::to_string(&doc)
        .map_err(|e| anyhow::anyhow!("Failed to serialize govbot.yml: {}", e))?;
    std::fs::write(&manifest_path, yaml)?;
    for id in &added {
        eprintln!("  + added {}", id);
    }
    eprintln!(
        "✅ Updated {}. Run `govbot pull` to fetch.",
        manifest_path.display()
    );
    Ok(())
}

/// `govbot remove` — drop dataset ids from `govbot.yml`'s `datasets:`.
fn run_remove_command(cmd: Command) -> anyhow::Result<()> {
    let Command::Remove { datasets } = cmd else {
        unreachable!()
    };
    let manifest_path = require_manifest_path()?;

    let contents = std::fs::read_to_string(&manifest_path)?;
    let mut doc: serde_yaml::Value = serde_yaml::from_str(&contents)
        .map_err(|e| anyhow::anyhow!("Failed to parse govbot.yml: {}", e))?;

    let datasets_node = doc
        .get_mut("datasets")
        .and_then(|v| v.as_sequence_mut())
        .ok_or_else(|| anyhow::anyhow!("govbot.yml has no `datasets:` list"))?;

    let targets: Vec<String> = datasets
        .iter()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .collect();

    let before = datasets_node.len();
    let mut removed = Vec::new();
    datasets_node.retain(|v| {
        if let Some(s) = v.as_str() {
            if targets.iter().any(|t| t == s) {
                removed.push(s.to_string());
                return false;
            }
        }
        true
    });

    if datasets_node.len() == before {
        eprintln!("No matching datasets found in govbot.yml.");
        return Ok(());
    }

    let yaml = serde_yaml::to_string(&doc)
        .map_err(|e| anyhow::anyhow!("Failed to serialize govbot.yml: {}", e))?;
    std::fs::write(&manifest_path, yaml)?;
    for id in &removed {
        eprintln!("  - removed {}", id);
    }
    eprintln!("✅ Updated {}.", manifest_path.display());
    Ok(())
}

/// `govbot ls` — list the project's manifest datasets and locally-cached ones.
fn run_ls_command(cmd: Command) -> anyhow::Result<()> {
    let Command::Ls { govbot_dir, output } = cmd else {
        unreachable!()
    };
    let registry = load_registry()?;
    let repos_dir = get_govbot_dir(govbot_dir)?;
    let local: Vec<String> = git::get_local_datasets(&repos_dir).unwrap_or_default();

    // The manifest's declared datasets, if a govbot.yml exists.
    let manifest_path = project_dir()?.join("govbot.yml");
    let manifest_datasets: Vec<String> = if manifest_path.exists() {
        match govbot::Manifest::load(&manifest_path) {
            Ok(m) => m.datasets,
            Err(_) => Vec::new(),
        }
    } else {
        Vec::new()
    };

    if output == "json" {
        let out = serde_json::json!({
            "manifest": manifest_datasets,
            "cached": local,
            "registry_total": registry.datasets.len(),
        });
        println!("{}", serde_json::to_string_pretty(&out)?);
        return Ok(());
    }

    if !manifest_datasets.is_empty() {
        println!("Manifest datasets (govbot.yml):");
        for d in &manifest_datasets {
            let cached = local.iter().any(|c| c == d) || d == "all";
            let mark = if cached { "✓" } else { "·" };
            println!("  {} {}", mark, d);
        }
        println!();
    }

    println!("Cached locally ({}):", local.len());
    if local.is_empty() {
        println!("  (none — run `govbot pull` to fetch)");
    } else {
        for d in &local {
            println!("  {}", d);
        }
    }

    // With no project manifest, list the registry — the help promises this so
    // `govbot ls` in a bare directory is genuinely useful for discovery.
    if manifest_datasets.is_empty() {
        println!();
        println!("Registry ({} dataset(s) — run `govbot search` to filter):", registry.datasets.len());
        for d in registry.all() {
            let name = d.entry.name.as_deref().unwrap_or("");
            println!("  {:<28}  {}", d.id, name);
        }
    }
    Ok(())
}

/// `govbot search` — query the dataset registry.
fn run_search_command(cmd: Command) -> anyhow::Result<()> {
    let Command::Search { query, output } = cmd else {
        unreachable!()
    };
    let registry = load_registry()?;
    let query_str = query.join(" ");
    let hits = registry.search(&query_str);

    if output == "json" {
        let rows: Vec<_> = hits
            .iter()
            .map(|d| {
                serde_json::json!({
                    "id": d.id,
                    "name": d.entry.name,
                    "git_url": d.entry.git_url,
                    "schema": d.entry.schema,
                    "path_pattern": d.entry.path_pattern,
                })
            })
            .collect();
        println!("{}", serde_json::to_string_pretty(&rows)?);
        return Ok(());
    }

    if hits.is_empty() {
        eprintln!("No datasets match '{}'.", query_str);
        return Ok(());
    }
    println!("{} dataset(s):", hits.len());
    for d in &hits {
        let name = d.entry.name.as_deref().unwrap_or("");
        println!("  {:<28}  {}", d.id, name);
    }
    Ok(())
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let args = Args::parse();

    match args.command {
        Some(cmd @ Command::Pull { .. }) => run_pull_command(cmd).await,
        Some(cmd @ Command::Delete { .. }) => run_delete_command(cmd).await,
        Some(cmd @ Command::Source { .. }) => run_source_command(cmd).await,
        Some(cmd @ Command::Load { .. }) => run_load_command(cmd).await,
        Some(Command::Update) => run_update_command().await,
        Some(cmd @ Command::Apply { .. }) => run_apply_command(cmd).await,
        Some(cmd @ Command::Publish { .. }) => run_publish_command(cmd).await,
        Some(Command::Run { govbot_dir }) => {
            let cwd = std::env::current_dir()?;
            let config_path = cwd.join("govbot.yml");
            if !config_path.exists() {
                anyhow::bail!(
                    "No govbot.yml in {}. Run `govbot init` to scaffold one, then `govbot run`.",
                    cwd.display()
                );
            }
            govbot::pipeline::run_pipeline(&config_path, govbot_dir.as_deref())
        }
        Some(Command::Init) => {
            let cwd = std::env::current_dir()?;
            let config_path = cwd.join("govbot.yml");
            if config_path.exists() {
                eprintln!("govbot.yml already exists in {}.", cwd.display());
                return Ok(());
            }
            if std::io::IsTerminal::is_terminal(&std::io::stdin()) {
                govbot::wizard::run_wizard()
            } else {
                govbot::wizard::write_default_files(&cwd)
            }
        }
        Some(cmd @ Command::Add { .. }) => run_add_command(cmd),
        Some(cmd @ Command::Remove { .. }) => run_remove_command(cmd),
        Some(cmd @ Command::Ls { .. }) => run_ls_command(cmd),
        Some(cmd @ Command::Search { .. }) => run_search_command(cmd),
        None => {
            let cwd = std::env::current_dir()?;
            let config_path = cwd.join("govbot.yml");
            if !config_path.exists() {
                // Generate govbot.yml: interactive wizard or defaults
                if std::io::IsTerminal::is_terminal(&std::io::stdin()) {
                    govbot::wizard::run_wizard()?;
                } else {
                    govbot::wizard::write_default_files(&cwd)?;
                }
                // Exit after generating config; user runs `govbot` again
                // to start the pipeline (matches the wizard's own message).
                return Ok(());
            }
            govbot::pipeline::run_pipeline(&config_path, None)
        }
    }
}
