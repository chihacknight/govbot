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
use std::path::{Path, PathBuf};
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

        /// Per-repo log filter (default: `default`). Options: `default` |
        /// `none`. `default` applies the per-dataset filter under
        /// `src/filters/<dataset>/default.rs` — it drops *routine* log
        /// actions (introductions, committee referrals, "Bill Number
        /// Assigned", "Placed on General File", boilerplate "President
        /// Signed" log lines, etc.) so the stream emits only **substantive**
        /// events: passage votes, executive signatures, amendments, defeats.
        /// `none` keeps every log entry. The default filter is action-based,
        /// not date-based: a bill whose only logs are routine actions
        /// (e.g. a freshly-filed bill with just an "Introduction" log) will
        /// emit zero records under `--filter default` until a substantive
        /// event lands. Use `--filter none` to confirm a bill is missing
        /// because of the filter rather than a data problem.
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

    /// Persist fastclass classification results as tag files under the
    /// project's `tags/` output directory. Reads `fastclass classify` result
    /// JSON from stdin — the apply sink of
    /// `govbot source --select docs | fastclass classify - | govbot apply` —
    /// and writes per-tag `.tag.json` files under
    /// `<project>/tags/<dataset>/country:.../sessions/<id>/`, the files
    /// `govbot publish` turns into feeds. Classification itself is done by
    /// fastclass; `govbot apply` only stores the results. `tags/` is a
    /// project-rooted classification-output dir — peer to `dist/` (publisher
    /// output) and distinct from `.govbot/` (the tool's regenerable cache).
    Apply {
        /// Optional tag name: persist only this tag's matches
        tag_name: Option<String>,

        /// Output directory (default: `<project>/tags/`). Overrides the
        /// default routing entirely — the dataset short-name is dropped and
        /// tag files land under `<output-dir>/country:.../sessions/.../tags/`.
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

        /// Render but do not emit. Propagates to every publisher — the
        /// `bluesky` publisher honours this by printing the posts it would
        /// send and touching no network/ledger. Recommended for first runs:
        /// a missing-cred `bluesky` publisher already auto-skips with a
        /// WARN, but `--dry-run` makes it explicit.
        #[arg(long = "dry-run")]
        dry_run: bool,
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

    /// Check that the project's pulled datasets are coherent. A data-integrity smoke test, runnable after `govbot pull all` or before `govbot run` in production. Walks every linked dataset and verifies that the `govbot source --select docs` stream is well-formed: every linked dataset entry resolves to a real directory, per-dataset ids don't collapse onto a handful (the bug-7592418 signature), every sampled `id` resolves to a present and parseable `metadata.json`, and every sampled `text` is non-trivial. Zero-record datasets are surfaced as warnings rather than errors — `--filter default` can legitimately drop every routine log. Exits non-zero on any failure so it can drop straight into a CI step. Skips cleanly when the cache is empty — this is a smoke test, not a unit test.
    Doctor {
        /// Govbot directory (default: $CWD/.govbot, or GOVBOT_DIR env var)
        #[arg(long = "govbot-dir")]
        govbot_dir: Option<String>,

        /// Records to sample per dataset for the metadata.json and
        /// text-length checks (default: 20). The id-distinctness and
        /// coverage checks always cover every emitted record.
        #[arg(long = "sample", default_value_t = 20)]
        sample: usize,

        /// Per-dataset emit limit fed through to `govbot source --limit`
        /// (default: 100, matching the source default — the smoke-test
        /// sweet spot for a typical 55-state pull in <60s). Use "none"
        /// for an exhaustive sweep at the cost of runtime.
        #[arg(long = "limit", default_value = "100")]
        limit: String,

        /// Emit a machine-readable JSON report instead of the human summary.
        /// Suitable for piping into a CI step.
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
/// `id` is the bill's dataset-relative directory path of the form
/// `<dataset>/country:<c>/state:<s>/sessions/<id>/bills/<bill_id>` so the
/// classified result can be routed back to the right *bill* (not session)
/// when `govbot apply` writes it. Two real-world dataset layouts feed into
/// this:
///
///   1. **Per-bill log directory** — `sources.log` is already
///      `<dataset>/.../sessions/<id>/bills/<bill_id>/logs/<file>.json`.
///      Stripping the `/logs/...` tail yields the bill path directly.
///   2. **Session-level log directory** (the common case for OCD-files
///      datasets cloned from windycivi) — the on-disk log lives at
///      `<dataset>/.../sessions/<id>/logs/<file>.json` and is a *symlink*
///      to `.../sessions/<id>/bills/<bill_id>/logs/<file>.json`. The walker
///      reports the symlink path, so stripping `/logs/...` would stop at
///      the *session* and collide every bill in that session onto one id
///      (real bug surfaced by `govbot pull all` over the 55-state corpus:
///      4916 records collapsed to 97 ids). The fix appends the bill_id
///      whenever the stripped path doesn't already end in `/bills/<id>`.
///
/// **Bill-id source of truth.** The on-disk bill directory name (e.g.
/// `HB5109`) does **not** always equal the `log.bill_id` field (e.g.
/// `"HB 5109"`). MI/WV/ND/PA logs carry a *display* bill id with a space
/// between the chamber prefix and the number; the actual `bills/<dir>/`
/// directory has no space. Using `log.bill_id` verbatim produces an `id`
/// like `.../bills/HB 5109` that no `os.path.join(REPOS, doc,
/// "metadata.json")` can resolve. The fix is to take the canonical bill
/// dir name from `sources.bill` (the parent dir of `metadata.json` — the
/// *resolved* on-disk path, set during the `bill` join) whenever
/// available, and fall back to `log.bill_id` only when the bill join is
/// absent. Layout 1 (suffix already present in `sources.log`) is left
/// untouched — that path is itself the canonical on-disk path, so the
/// bill segment is correct by construction.
///
/// `text` is the **full** bill text assembled from `metadata.json` (not just
/// titles) — the `docs` projection joins the complete bill so this is whole.
fn ocd_entry_to_doc(entry: &serde_json::Value) -> serde_json::Value {
    let bill_id = entry
        .get("log")
        .and_then(|l| l.get("bill_id").or_else(|| l.get("bill_identifier")))
        .and_then(|v| v.as_str())
        .map(|s| s.to_string());

    // Canonical on-disk bill directory name, derived from `sources.bill`
    // (the path to `metadata.json`, which the bill join resolves to the
    // real `bills/<dir>/metadata.json` on disk — even when the log was a
    // session-level symlink). This is the authoritative source for the
    // `/bills/<dir>` segment because `log.bill_id` may carry a display
    // form (e.g. `"HB 5109"`) that differs from the directory (`HB5109`).
    let canonical_bill_dir = entry
        .get("sources")
        .and_then(|s| s.get("bill"))
        .and_then(|v| v.as_str())
        .and_then(bill_dir_from_metadata_path)
        .map(|s| s.to_string());

    let stripped = entry
        .get("sources")
        .and_then(|s| s.get("log"))
        .and_then(|v| v.as_str())
        .and_then(|log_path| log_path.split("/logs/").next())
        .map(|s| s.to_string());

    // Layout 1 still trusts the stripped log path: when `sources.log`
    // already ends in `/bills/<dir>` that dir name is itself canonical
    // (it came from the on-disk walk). Layout 2 must prefer the
    // `sources.bill`-derived dir name; only fall back to `log.bill_id`
    // when the bill join wasn't requested.
    //
    // The Layout-1 test must consider BOTH the canonical bill dir (from
    // `sources.bill`) AND `log.bill_id`. If we only checked
    // `log.bill_id`, then MI/WV/ND/PA — whose log carries `"HB 0163"`
    // but on-disk dir is `HB0163` — would fail the Layout-1 test even
    // when `sources.log` already ends in `/bills/HB0163`, and we'd
    // double-append, producing `.../bills/HB0163/bills/HB0163`.
    let id = match stripped {
        Some(path) => {
            let already_ends_in_bill_dir = canonical_bill_dir
                .as_deref()
                .map(|d| path.ends_with(&format!("/bills/{}", d)))
                .unwrap_or(false)
                || bill_id
                    .as_deref()
                    .map(|d| path.ends_with(&format!("/bills/{}", d)))
                    .unwrap_or(false);
            if already_ends_in_bill_dir {
                // Layout 1: log lived under bills/<id>/logs/. The stripped
                // path is already the canonical bill dir.
                path
            } else if let Some(canon) = canonical_bill_dir.as_deref() {
                // Layout 2 (preferred): use the on-disk dir name from the
                // resolved metadata.json path, so display-form bill ids
                // with whitespace (e.g. `"HB 5109"`) don't bleed into the
                // doc id and break sibling-file lookups.
                format!("{}/bills/{}", path, canon)
            } else if let Some(bid) = bill_id.as_deref() {
                // Layout 2 fallback: no bill join, so the best we have is
                // the log's `bill_id`. This may be a display form; callers
                // doing path lookups should treat it as advisory.
                format!("{}/bills/{}", path, bid)
            } else {
                path
            }
        }
        None => canonical_bill_dir.or(bill_id).unwrap_or_else(String::new),
    };
    serde_json::json!({ "id": id, "text": ocd_files_select_default(entry), "kind": "docs" })
}

/// Given a `sources.bill` path (`<...>/bills/<dir>/metadata.json`,
/// possibly with `..` prefixes from a cache-symlinked repo), return the
/// `<dir>` segment — the canonical on-disk bill directory name. Returns
/// `None` if the path doesn't end in `bills/<dir>/metadata.json`.
fn bill_dir_from_metadata_path(metadata_path: &str) -> Option<&str> {
    // Strip the trailing filename.
    let without_file = metadata_path.strip_suffix("/metadata.json")?;
    // Take the last path segment — that's the bill dir.
    let last_slash = without_file.rfind('/')?;
    let dir = &without_file[last_slash + 1..];
    // Sanity check: the segment before that should be `bills`. If not,
    // the path doesn't look like a bill metadata path; refuse to guess.
    let before_dir = &without_file[..last_slash];
    if !before_dir.ends_with("/bills") && before_dir != "bills" {
        return None;
    }
    if dir.is_empty() {
        None
    } else {
        Some(dir)
    }
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

                                    // Join tags if requested.
                                    //
                                    // `.govbot/` is the tool's cache — tag
                                    // files no longer live inside it. The
                                    // primary lookup is the project-rooted
                                    // `<project>/tags/<dataset>/...` layout
                                    // `govbot apply` writes today. Two
                                    // read-only fallbacks stay live for
                                    // migration: the in-cache `<session>/
                                    // tags/` location Bug 6 added, and the
                                    // cwd-rooted `country:.../sessions/<id>/
                                    // tags/` layout that pre-dates Bug 1.
                                    // First non-empty match wins; an empty
                                    // result on every candidate is silent.
                                    if join_tags {
                                        if let Some(ref bill_id) = bill_id_opt {
                                            let mut matched_tags: serde_json::Map<
                                                String,
                                                serde_json::Value,
                                            > = serde_json::Map::new();

                                            let cwd = std::env::current_dir()
                                                .unwrap_or_else(|_| PathBuf::from("."));
                                            for candidate in
                                                resolve_tags_dir_candidates(&path, &cwd)
                                            {
                                                matched_tags =
                                                    match_tags_in_dir(&candidate, bill_id);
                                                if !matched_tags.is_empty() {
                                                    break;
                                                }
                                            }

                                            // Final fallback: pre-Bug-1
                                            // cwd-rooted layout. Only
                                            // consulted when the dataset-
                                            // aware candidates all came up
                                            // empty.
                                            if matched_tags.is_empty() {
                                                if let Some((country, state, session_id)) =
                                                    extract_path_info(&source_path_str)
                                                {
                                                    let legacy_tags_dir = cwd
                                                        .join(format!("country:{}", country))
                                                        .join(format!("state:{}", state))
                                                        .join("sessions")
                                                        .join(&session_id)
                                                        .join("tags");
                                                    matched_tags = match_tags_in_dir(
                                                        &legacy_tags_dir,
                                                        bill_id,
                                                    );
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

/// The session directory of a log file path — the ancestor whose immediate
/// child is `bills/` — together with the path segments that uniquely place it
/// inside its dataset.
///
/// Why pulled out: `resolve_tags_dir` needs the path twice, once to look at
/// the project-rooted `tags/<dataset>/...` layout and once for the in-cache
/// `<session>/tags/` fallback. Computing it in one place keeps both lookups
/// in sync with the canonical dataset layout.
struct SessionAnchor {
    /// The session directory itself (the `bills/`-bearing ancestor).
    session_dir: PathBuf,
    /// The dataset's `short_name` — the first path segment under the repos
    /// dir (e.g. `wy-legislation`). `None` if the path is not inside a
    /// recognisable `<repos>/<short>/country:.../sessions/...` layout, in
    /// which case the project-rooted lookup is skipped.
    dataset: Option<String>,
    /// The `country:<c>` segment as-is (e.g. `country:us`).
    country_segment: String,
    /// The `state:<s>` segment as-is (e.g. `state:wy`).
    state_segment: String,
    /// The session id (the segment after `sessions/`).
    session_id: String,
}

/// Walk up from `log_path` to its session directory (the `bills/`-bearing
/// ancestor) and capture every segment needed to plant a tag file under
/// `<project>/tags/<dataset>/country:.../state:.../sessions/<id>/`. Returns
/// `None` when the path is not inside the canonical dataset layout.
fn parse_session_anchor(log_path: &Path) -> Option<SessionAnchor> {
    let mut cursor = log_path.parent();
    while let Some(dir) = cursor {
        if dir.join("bills").is_dir() {
            // Found the session dir. Walk *down* its components to recover
            // the dataset short_name and jurisdiction segments — they are
            // the same segments `parse_doc_route` extracts on the writer
            // side, so the two halves stay symmetric.
            let mut country_segment: Option<String> = None;
            let mut state_segment: Option<String> = None;
            let mut session_id: Option<String> = None;
            let mut dataset: Option<String> = None;
            let mut prev_was_sessions = false;
            let mut country_seen = false;
            for component in dir.components() {
                let seg = component.as_os_str().to_string_lossy().to_string();
                if seg.starts_with("country:") {
                    country_segment = Some(seg.clone());
                    country_seen = true;
                } else if seg.starts_with("state:") {
                    state_segment = Some(seg.clone());
                } else if seg == "sessions" {
                    prev_was_sessions = true;
                    continue;
                } else if prev_was_sessions {
                    session_id = Some(seg.clone());
                }
                // The dataset short_name is the path segment immediately
                // before the first `country:` segment. For typical layouts
                // (`<repos>/<short>/country:.../...`) that is one segment;
                // we only need the most recent non-pathy segment before
                // `country:` was first seen.
                if !country_seen
                    && !seg.is_empty()
                    && seg != "/"
                    && !seg.starts_with("country:")
                    && !seg.starts_with("state:")
                    && seg != "sessions"
                    && seg != "bills"
                {
                    dataset = Some(seg);
                }
                prev_was_sessions = false;
            }
            return Some(SessionAnchor {
                session_dir: dir.to_path_buf(),
                dataset,
                country_segment: country_segment?,
                state_segment: state_segment?,
                session_id: session_id?,
            });
        }
        cursor = dir.parent();
    }
    None
}

/// Resolve every `tags/`-equivalent directory we are willing to read a tag
/// file from, in the order the caller should consult them.
///
/// `.govbot/` is the tool's cache (the `node_modules/` equivalent) — tag
/// files belong outside it, in a project-rooted classification-output dir.
/// The primary lookup is therefore `<project>/tags/<dataset>/country:.../
/// state:.../sessions/<id>/`. Two fallbacks stay live for migration:
///
/// 1. **Primary**: `<project>/tags/<dataset>/country:.../sessions/<id>/`
///    — where `govbot apply` writes today.
/// 2. **Fallback A** (Bug 6 / `6cbb12e`): the in-cache
///    `<session_dir>/tags/` sibling-of-`bills/` — kept read-only so a
///    working tree mid-migration still resolves.
/// 3. **Fallback B** (pre-Bug-1): the cwd-rooted
///    `<cwd>/country:.../state:.../sessions/<id>/tags/` — kept for layouts
///    that pre-date the dataset-rooted move (and for explicit
///    `--output-dir` overrides that landed there).
///
/// The chain is read-only — `apply` itself never touches anything but the
/// primary location.
fn resolve_tags_dir_candidates(log_path: &Path, project_dir: &Path) -> Vec<PathBuf> {
    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Some(anchor) = parse_session_anchor(log_path) {
        // Primary: <project>/tags/<dataset>/country:.../state:.../sessions/<id>/
        if let Some(ref dataset) = anchor.dataset {
            candidates.push(
                project_dir
                    .join("tags")
                    .join(dataset)
                    .join(&anchor.country_segment)
                    .join(&anchor.state_segment)
                    .join("sessions")
                    .join(&anchor.session_id),
            );
        }
        // Fallback A: in-cache session/tags/ (Bug 6 layout, read-only).
        candidates.push(anchor.session_dir.join("tags"));
    }
    candidates
}

/// Read every `*.json` / `*.tag.json` file in `tags_dir`, parse each as a
/// `TagFile`, and return the subset whose `bills` map contains `bill_id`,
/// keyed by tag name (file stem with any `.tag` suffix stripped). Returns an
/// empty map if `tags_dir` does not exist or contains no matching tags.
///
/// Pulled out so the same logic serves the dataset-rooted lookup *and* the
/// project-root fallback below without duplication.
fn match_tags_in_dir(tags_dir: &Path, bill_id: &str) -> serde_json::Map<String, serde_json::Value> {
    let mut matched = serde_json::Map::new();
    if !tags_dir.is_dir() {
        return matched;
    }
    let entries = match fs::read_dir(tags_dir) {
        Ok(e) => e,
        Err(_) => return matched,
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.extension().and_then(|s| s.to_str()) != Some("json") {
            continue;
        }
        let stem = match path.file_stem().and_then(|s| s.to_str()) {
            Some(s) => s,
            None => continue,
        };
        // `budget.tag.json` -> `budget`; plain `budget.json` -> `budget`.
        let tag_name = stem.strip_suffix(".tag").unwrap_or(stem);
        let contents = match fs::read_to_string(&path) {
            Ok(c) => c,
            Err(_) => continue,
        };
        let tag_file: govbot::TagFile = match serde_json::from_str(&contents) {
            Ok(t) => t,
            Err(_) => continue,
        };
        if let Some(bill_result) = tag_file.bills.get(bill_id) {
            matched.insert(
                tag_name.to_string(),
                serde_json::to_value(&bill_result.score).unwrap_or(serde_json::Value::Null),
            );
        }
    }
    matched
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
    /// The dataset's `short_name` — the path segment before `country:<c>` in
    /// the doc id (e.g. `wy-legislation`). `None` if the doc id has no
    /// recognisable prefix.
    dataset: Option<String>,
    country: String,
    state: String,
    session: String,
    bill_id: String,
}

/// Parse a `doc` id of the form
/// `<dataset>/country:<c>/state:<s>/sessions/<session>/bills/<bill_id>` into the
/// pieces needed to place its `.tag.json` file. Returns `None` for any id that
/// is not a dataset bill path (e.g. a document from a non-govbot source).
///
/// The leading `<dataset>` segment is the dataset's `short_name` (e.g.
/// `wy-legislation`); it is what lets `govbot apply` route each tag file under
/// `<project>/tags/<dataset>/...` by default — the dataset prefix is what
/// disambiguates same-named tag files across jurisdictions in a multi-dataset
/// project.
fn parse_doc_route(doc: &str) -> Option<BillRoute> {
    let segments: Vec<&str> = doc.split('/').collect();
    let (mut country, mut state, mut session, mut bill_id) = (None, None, None, None);
    let mut country_idx: Option<usize> = None;
    for (i, seg) in segments.iter().enumerate() {
        if let Some(c) = seg.strip_prefix("country:") {
            country = Some(c.to_string());
            if country_idx.is_none() {
                country_idx = Some(i);
            }
        } else if let Some(s) = seg.strip_prefix("state:") {
            state = Some(s.to_string());
        } else if *seg == "sessions" {
            session = segments.get(i + 1).map(|s| s.to_string());
        } else if *seg == "bills" {
            bill_id = segments.get(i + 1).map(|s| s.to_string());
        }
    }
    // Anything sitting in front of `country:<c>` is the dataset short_name.
    // For today's `<dataset>/country:<c>/...` shape that is exactly one
    // segment, but tolerate nested prefixes by joining everything before the
    // `country:` segment (skipping empties from a leading `/`).
    let dataset = country_idx.and_then(|i| {
        let prefix: Vec<&str> = segments[..i]
            .iter()
            .copied()
            .filter(|s| !s.is_empty())
            .collect();
        if prefix.is_empty() {
            None
        } else {
            Some(prefix.join("/"))
        }
    });
    Some(BillRoute {
        dataset,
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
/// under `<project>/tags/<dataset>/country:.../sessions/<id>/`. Those are the
/// files `govbot publish` later turns into feeds.
///
/// **Why `tags/` and not `.govbot/`:** `.govbot/` is the tool's cache — the
/// equivalent of `node_modules/` — and must stay user-edit-free so a fresh
/// `rm -rf .govbot/` never destroys the bot's classification work. Tag files
/// are derived classification *outputs*, not cache contents; they live in
/// their own dedicated, project-rooted directory peer to `dist/`.
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
    // Tag files land under --output-dir when given. When unset, each tag file
    // is routed under the project's classification-output directory
    // `<project>/tags/<dataset>/country:.../sessions/.../<tag>.tag.json`
    // — the dataset short_name comes from the first segment of the fastclass
    // result's `doc` field, mirroring where the bill's `metadata.json` came
    // from. The explicit `--output-dir` override stays a verbatim root (the
    // dataset prefix is dropped), which is the back-compat escape hatch for
    // callers that want to write into a custom layout.
    let explicit_output_dir = output_dir.as_ref().map(PathBuf::from);
    let default_tags_root = current_dir.join("tags");

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
    // Track per-dataset write counts so the final summary reflects where the
    // tag files actually landed.
    let mut written_dirs: std::collections::BTreeSet<PathBuf> = Default::default();
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

        // Resolve where this bill's tag files land. With an explicit
        // `--output-dir`, that path is the root and the dataset short_name is
        // dropped (back-compat escape hatch). With no override, route the file
        // under the project's `tags/<dataset>/...` output dir so the dataset
        // prefix disambiguates same-named tags across jurisdictions. If the
        // `doc` id lacks a recognisable dataset prefix (a non-govbot source),
        // fall back to a no-prefix `tags/` so the record is still persisted —
        // never write into `.govbot/`, which is the tool's cache.
        let base_output_dir = match (&explicit_output_dir, &route.dataset) {
            (Some(root), _) => root.clone(),
            (None, Some(dataset)) => default_tags_root.join(dataset),
            (None, None) => default_tags_root.clone(),
        };
        // Inside the dataset prefix, mirror the source's jurisdiction path
        // exactly — no trailing `/tags/` segment, because the project-level
        // `tags/` directory already names the kind. The shape on disk is
        // `<root>/<dataset>/country:.../state:.../sessions/<id>/<tag>.tag.json`.
        let tags_dir = base_output_dir
            .join(format!("country:{}", route.country))
            .join(format!("state:{}", route.state))
            .join("sessions")
            .join(&route.session);
        fs::create_dir_all(&tags_dir)?;
        written_dirs.insert(base_output_dir.clone());

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

    let dirs_summary = if written_dirs.is_empty() {
        explicit_output_dir
            .as_ref()
            .map(|d| d.display().to_string())
            .unwrap_or_else(|| default_tags_root.display().to_string())
    } else {
        written_dirs
            .iter()
            .map(|p| p.display().to_string())
            .collect::<Vec<_>>()
            .join(", ")
    };
    eprintln!(
        "\n✅ Persisted {} tagged bill(s) under {}; skipped {} entr(ies).",
        written, dirs_summary, skipped
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

    // Resolve the companion html-publisher landing URL once: the bluesky
    // publisher uses it as the default for `{link}` so a post links to the
    // human-readable HTML index, not the raw metadata.json path under its
    // own `base_url`. None when the manifest has no html publisher.
    let html_entry_url: Option<String> = manifest
        .publish
        .values()
        .find(|p| p.kind == govbot::PublisherKind::Html)
        .and_then(|p| p.base_url.clone())
        .filter(|u| !u.trim().is_empty());

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
            html_entry_url: html_entry_url.clone(),
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
        println!(
            "Registry ({} dataset(s) — run `govbot search` to filter):",
            registry.datasets.len()
        );
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

// ---------------------------------------------------------------------------
// `govbot doctor` — corpus-level data-integrity smoke test.
//
// Why this exists: two real-data bugs (7592418, 5ab6d3c) shipped because the
// only test harness was the mock dataset, which happened to fit a single
// happy-path layout. Both bugs would have been caught by a five-line check —
// "every emitted doc id is unique" and "every id resolves to a present
// metadata.json" — over a real pulled cache. `doctor` is that check, wired
// to a CLI verb activists can run after `pull all` to confirm the project
// is coherent before flipping `bluesky` off `--dry-run`.
//
// This is a smoke test, not a unit test. It assumes pulled data and skips
// cleanly when the cache is empty.
// ---------------------------------------------------------------------------

/// Per-record sample, captured during the source walk so the metadata.json
/// and text checks can run after the stream is fully drained.
#[derive(Debug, Clone)]
struct DoctorSample {
    id: String,
    text_len: usize,
}

/// Per-dataset rollup used to build the doctor report.
#[derive(Debug, Default)]
struct DatasetSummary {
    record_count: usize,
    distinct_ids: std::collections::HashSet<String>,
    samples: Vec<DoctorSample>,
}

/// Outcome of one assertion bucket for one dataset — a short label, a
/// pass flag, an optional warn flag, and the detail lines (capped so a
/// broken dataset doesn't drown the report). A `warned` check still
/// counts as passing for the overall exit code — it surfaces noteworthy
/// state (e.g. zero records under `--filter default`) without failing CI.
#[derive(Debug, Clone)]
struct DoctorCheck {
    name: &'static str,
    passed: bool,
    warned: bool,
    detail: Vec<String>,
}

#[derive(Debug)]
struct DatasetReport {
    dataset: String,
    record_count: usize,
    distinct_ids: usize,
    sampled: usize,
    checks: Vec<DoctorCheck>,
}

impl DatasetReport {
    fn passed(&self) -> bool {
        self.checks.iter().all(|c| c.passed)
    }
    fn warned(&self) -> bool {
        self.checks.iter().any(|c| c.warned)
    }
}

/// Cap how many failing ids we print per check — keeps the report scannable
/// when an entire dataset is broken.
const MAX_FAIL_DETAIL: usize = 5;

/// Default minimum acceptable `text` length per record. Anything shorter
/// is almost certainly a join failure (metadata.json missing or empty), not
/// a legitimate short bill.
const MIN_TEXT_LEN: usize = 50;

/// Per-dataset distinct-id / record-count ratio floor. Bug 7592418
/// collapsed 4916 records onto 97 ids (ratio 0.02). The floor is set
/// at 0.03 — high enough to flag a 100x collision, low enough to
/// accept a dataset where a handful of active bills emit many
/// substantive log records each (e.g. a state with sustained voting
/// activity on the same few bills). Drop it further if a clean cache
/// shows legitimate sub-0.03 ratios.
const MIN_DISTINCT_RATIO: f64 = 0.03;

/// Map a parsed `parse_doc_route` dataset prefix (e.g. `nj-legislation`)
/// to the bare short_name (`nj`) that `git::get_local_datasets` returns.
/// This is the only place where doc-id prefixes and on-disk dataset
/// short names meet; getting it wrong silently breaks the per-dataset
/// bucketing.
fn dataset_short_name(prefix: &str, suffix: &str) -> String {
    if let Some(s) = prefix.strip_suffix(suffix) {
        s.to_string()
    } else if let Some(s) = prefix.strip_suffix("-data-pipeline") {
        s.to_string()
    } else {
        prefix.to_string()
    }
}

fn run_doctor_command(cmd: Command) -> anyhow::Result<()> {
    let Command::Doctor {
        govbot_dir,
        sample,
        limit,
        output,
    } = cmd
    else {
        unreachable!()
    };

    let repos_dir = get_govbot_dir(govbot_dir.clone())?;

    // Skip-cleanly contract: an empty or absent cache is not a failure.
    // `doctor` is a smoke test, not a unit test — it has nothing to check
    // until data is pulled. Exit 0 with a clear note.
    if !repos_dir.exists() {
        let note = format!(
            "doctor: no cache at {} — run `govbot pull all` first. Skipping.",
            repos_dir.display()
        );
        if output == "json" {
            println!(
                "{}",
                serde_json::json!({ "status": "skipped", "reason": note })
            );
        } else {
            eprintln!("{}", note);
        }
        return Ok(());
    }

    let datasets = match git::get_local_datasets(&repos_dir) {
        Ok(d) => d,
        Err(e) => anyhow::bail!("doctor: failed to enumerate cached datasets: {}", e),
    };

    // Stale or broken entries in `repos/` — names that look like dataset
    // links (matching the configured suffix) but don't resolve to a real
    // directory. A broken symlink is the canonical case; the entry sits
    // in `repos/` but `get_local_datasets` filtered it out because
    // `is_dir()` follows the link and returns false. Surface these so
    // they're not invisible — they break `govbot source` for that state
    // without any other signal.
    let broken_dataset_entries = enumerate_broken_dataset_entries(&repos_dir);

    if datasets.is_empty() {
        let note = format!(
            "doctor: {} is empty — run `govbot pull all` first. Skipping.",
            repos_dir.display()
        );
        if output == "json" {
            println!(
                "{}",
                serde_json::json!({ "status": "skipped", "reason": note })
            );
        } else {
            eprintln!("{}", note);
        }
        return Ok(());
    }

    // Resolve the parent govbot-dir for the subprocess `--govbot-dir` arg.
    // `get_govbot_dir` appends `/repos`; we pass the parent so the child
    // appends its own `/repos` and lands on the same path.
    let govbot_dir_arg = repos_dir
        .parent()
        .map(|p| p.to_string_lossy().to_string())
        .unwrap_or_else(|| ".govbot".to_string());

    let started = std::time::Instant::now();

    // Stream every record once, in --select docs --limit none mode. We use a
    // subprocess so we exercise the same code path activists hit; doctor is
    // a "what does `govbot source` actually emit?" check, not a re-derivation.
    let stream = collect_doc_stream(&govbot_dir_arg, &limit)
        .map_err(|e| anyhow::anyhow!("doctor: source stream failed: {}", e))?;

    // Bucket records by dataset short_name. The doc id carries the full
    // `<short>-legislation` (or legacy `<short>-data-pipeline`) repo dir
    // prefix; `get_local_datasets` returns the bare short_name, so we
    // normalise both to the short form before keying.
    let mut per_dataset: HashMap<String, DatasetSummary> = HashMap::new();
    let mut unrouted: Vec<String> = Vec::new();

    let suffix = std::env::var("GOVBOT_REPO_SUFFIX").unwrap_or_else(|_| "-legislation".to_string());

    for rec in &stream {
        let id = rec.id.clone();

        // Route to a dataset via the `<dataset>/country:...` prefix in the
        // id. A record we can't route is recorded for the global report; it
        // can't contribute to per-dataset coverage.
        let dataset_short = parse_doc_route(&id)
            .and_then(|r| r.dataset)
            .map(|d| dataset_short_name(&d, &suffix));
        match dataset_short {
            Some(d) => {
                let entry = per_dataset.entry(d).or_default();
                entry.record_count += 1;
                entry.distinct_ids.insert(id.clone());
                if entry.samples.len() < sample {
                    entry.samples.push(DoctorSample {
                        id,
                        text_len: rec.text_len,
                    });
                }
            }
            None => {
                if unrouted.len() < MAX_FAIL_DETAIL {
                    unrouted.push(id);
                }
            }
        }
    }

    // Build per-dataset reports. The four per-dataset checks are: coverage
    // (≥1 record), id-distinctness (the bug 7592418 signature — many
    // records collapsing onto one id), sampled-metadata-json-resolves,
    // and sampled-text-length.
    let mut dataset_reports: Vec<DatasetReport> = Vec::with_capacity(datasets.len());
    for dataset in &datasets {
        let prefix = git::repo_dir_name(dataset);
        let dataset_repo_dir = repos_dir.join(&prefix);
        let summary = per_dataset.remove(dataset.as_str()).unwrap_or_default();

        let mut checks = Vec::new();

        // Coverage — a zero-record dataset is reported as a warning,
        // not a failure: `--filter default` legitimately drops every
        // record in a dataset whose only recent logs are routine
        // (introductions, committee referrals). That state is normal
        // for a freshly-cloned session early in its calendar. Doctor
        // surfaces it so the activist can notice — pulled but silent —
        // without failing the overall smoke test.
        let coverage_warned = summary.record_count == 0;
        let coverage_detail = if coverage_warned {
            vec![format!(
                "{} is linked but produced 0 records (likely an empty session or `--filter default` dropping every log — not necessarily broken)",
                prefix
            )]
        } else {
            Vec::new()
        };
        checks.push(DoctorCheck {
            name: "coverage",
            passed: true,
            warned: coverage_warned,
            detail: coverage_detail,
        });

        // ID distinctness — bug 7592418 collapsed 4916 records onto 97
        // ids (ratio 0.02). After the fix it's ~0.81. A per-log emission
        // pattern legitimately produces some duplicate ids (the same
        // bill emitting multiple substantive log events), so we don't
        // demand uniqueness — but we do demand the ratio stay well
        // above the bug-case floor. Below MIN_DISTINCT_RATIO is the
        // smoking gun.
        let distinct = summary.distinct_ids.len();
        let total = summary.record_count;
        let ratio = if total == 0 {
            1.0
        } else {
            distinct as f64 / total as f64
        };
        let distinctness_passed = total == 0 || ratio >= MIN_DISTINCT_RATIO;
        let distinctness_detail = if distinctness_passed {
            Vec::new()
        } else {
            vec![format!(
                "{}/{} distinct ids (ratio {:.2}) — below the {:.2} floor; ids are likely collapsing across distinct bills (the bug-7592418 signature)",
                distinct, total, ratio, MIN_DISTINCT_RATIO
            )]
        };
        checks.push(DoctorCheck {
            name: "id_distinctness",
            passed: distinctness_passed,
            warned: false,
            detail: distinctness_detail,
        });

        // Metadata.json resolves
        let mut metadata_failures: Vec<String> = Vec::new();
        for s in &summary.samples {
            if let Err(reason) = check_metadata_json(&s.id, &dataset_repo_dir) {
                if metadata_failures.len() < MAX_FAIL_DETAIL {
                    metadata_failures.push(format!("{} :: {}", s.id, reason));
                }
            }
        }
        checks.push(DoctorCheck {
            name: "metadata_sampleable",
            passed: metadata_failures.is_empty(),
            warned: false,
            detail: metadata_failures,
        });

        // Text length
        let mut text_failures: Vec<String> = Vec::new();
        for s in &summary.samples {
            if s.text_len < MIN_TEXT_LEN && text_failures.len() < MAX_FAIL_DETAIL {
                text_failures.push(format!(
                    "{} :: text length {} < {}",
                    s.id, s.text_len, MIN_TEXT_LEN
                ));
            }
        }
        checks.push(DoctorCheck {
            name: "text_non_empty",
            passed: text_failures.is_empty(),
            warned: false,
            detail: text_failures,
        });

        dataset_reports.push(DatasetReport {
            dataset: dataset.clone(),
            record_count: summary.record_count,
            distinct_ids: summary.distinct_ids.len(),
            sampled: summary.samples.len(),
            checks,
        });
    }

    // Build the global report. Global "duplicate ids" check is gone —
    // per-log emission legitimately produces some duplicates. The id
    // collapse bug (7592418) is caught per-dataset by id_distinctness.
    let elapsed = started.elapsed();
    let total_records: usize = dataset_reports.iter().map(|r| r.record_count).sum();
    let total_distinct: usize = dataset_reports.iter().map(|r| r.distinct_ids).sum();
    let all_passed = unrouted.is_empty()
        && broken_dataset_entries.is_empty()
        && dataset_reports.iter().all(|r| r.passed());

    if output == "json" {
        emit_doctor_json(
            &dataset_reports,
            total_records,
            total_distinct,
            &unrouted,
            &broken_dataset_entries,
            elapsed,
            all_passed,
        );
    } else {
        emit_doctor_text(
            &dataset_reports,
            total_records,
            total_distinct,
            &unrouted,
            &broken_dataset_entries,
            elapsed,
            all_passed,
        );
    }

    if !all_passed {
        // Non-zero exit so a CI step `govbot doctor` fails the pipeline.
        std::process::exit(1);
    }
    Ok(())
}

/// Names sitting in `<repos_dir>/` that look like dataset entries (matching
/// the configured suffix) but don't resolve to a real directory — e.g. a
/// dangling symlink left over from a hand-edited cache, or a broken
/// pull. `get_local_datasets` silently filters these out; doctor surfaces
/// them as a global failure so they don't go unnoticed.
fn enumerate_broken_dataset_entries(repos_dir: &Path) -> Vec<String> {
    let suffix = std::env::var("GOVBOT_REPO_SUFFIX").unwrap_or_else(|_| "-legislation".to_string());
    let mut broken = Vec::new();
    let read = match std::fs::read_dir(repos_dir) {
        Ok(r) => r,
        Err(_) => return broken,
    };
    for entry in read.flatten() {
        let path = entry.path();
        let Some(name) = path.file_name().and_then(|n| n.to_str()) else {
            continue;
        };
        let looks_like_dataset = name.ends_with(&suffix) || name.ends_with("-data-pipeline");
        if !looks_like_dataset {
            continue;
        }
        // `is_dir()` follows symlinks, so a dangling symlink reads false.
        if !path.is_dir() {
            broken.push(name.to_string());
        }
    }
    broken.sort();
    broken
}

/// Minimal `{id,text,kind}` record drained from `govbot source --select docs`.
#[derive(Debug)]
struct DocRecord {
    id: String,
    text_len: usize,
}

/// Invoke `govbot source --select docs --limit <limit>` against the given
/// cache and return one `DocRecord` per emitted JSON line. We materialise
/// fully rather than streaming — the assertion set needs the whole corpus
/// before per-dataset ratios mean anything, and at the smoke-test limit
/// (default 100/repo, ~5000 records total) memory is a non-issue.
fn collect_doc_stream(govbot_dir: &str, limit: &str) -> std::io::Result<Vec<DocRecord>> {
    let exe = std::env::current_exe().unwrap_or_else(|_| PathBuf::from("govbot"));
    let mut source_cmd = ProcessCommand::new(&exe);
    source_cmd
        .arg("source")
        .arg("--select")
        .arg("docs")
        .arg("--limit")
        .arg(limit)
        .arg("--filter")
        .arg("default")
        .arg("--join")
        .arg("bill")
        .arg("--sort")
        .arg("DESC")
        .arg("--govbot-dir")
        .arg(govbot_dir);

    let output = source_cmd.output()?;
    if !output.status.success() {
        let stderr_str = String::from_utf8_lossy(&output.stderr);
        return Err(std::io::Error::other(format!(
            "source exited with status {:?}: {}",
            output.status.code(),
            stderr_str
        )));
    }

    let mut records = Vec::new();
    for line in output.stdout.split(|b| *b == b'\n') {
        if line.is_empty() {
            continue;
        }
        let v: serde_json::Value = match serde_json::from_slice(line) {
            Ok(v) => v,
            Err(_) => continue, // Best-effort — source itself logs the parse failure.
        };
        let id = v
            .get("id")
            .and_then(|x| x.as_str())
            .unwrap_or("")
            .to_string();
        let text_len = v
            .get("text")
            .and_then(|x| x.as_str())
            .map(|s| s.len())
            .unwrap_or(0);
        // A record without an id will fail the per-dataset `unrouted`
        // bucket (`parse_doc_route` returns None for the empty string),
        // surfacing as a global routability failure.
        records.push(DocRecord { id, text_len });
    }
    Ok(records)
}

/// Translate a doc id back to its on-disk `metadata.json` and confirm it
/// (a) exists, (b) parses as JSON, (c) has at least a `title` or `identifier`
/// field. The third leg is what would have caught 5ab6d3c — a dir-name vs
/// `log.bill_id` whitespace mismatch produces an id whose metadata.json
/// path simply doesn't exist on disk.
fn check_metadata_json(doc_id: &str, dataset_repo_dir: &Path) -> Result<(), String> {
    let route = parse_doc_route(doc_id).ok_or_else(|| {
        "id does not match expected `country:.../bills/<bill_id>` shape".to_string()
    })?;
    // Path: <dataset_repo_dir>/country:<c>/state:<s>/sessions/<session>/bills/<bill_id>/metadata.json
    let metadata_path = dataset_repo_dir
        .join(format!("country:{}", route.country))
        .join(format!("state:{}", route.state))
        .join("sessions")
        .join(&route.session)
        .join("bills")
        .join(&route.bill_id)
        .join("metadata.json");

    if !metadata_path.exists() {
        return Err(format!(
            "metadata.json not found at {}",
            metadata_path.display()
        ));
    }
    let contents = fs::read_to_string(&metadata_path)
        .map_err(|e| format!("cannot read {}: {}", metadata_path.display(), e))?;
    let value: serde_json::Value = serde_json::from_str(&contents)
        .map_err(|e| format!("invalid JSON in {}: {}", metadata_path.display(), e))?;
    let has_title = value
        .get("title")
        .and_then(|v| v.as_str())
        .map(|s| !s.is_empty())
        .unwrap_or(false);
    let has_identifier = value
        .get("identifier")
        .and_then(|v| v.as_str())
        .map(|s| !s.is_empty())
        .unwrap_or(false);
    if !has_title && !has_identifier {
        return Err(format!(
            "metadata.json at {} has neither `title` nor `identifier`",
            metadata_path.display()
        ));
    }
    Ok(())
}

/// Human-readable doctor report. Per-dataset one-liners followed by the
/// global summary; failures get an indented detail block.
fn emit_doctor_text(
    dataset_reports: &[DatasetReport],
    total_records: usize,
    total_distinct: usize,
    unrouted: &[String],
    broken_entries: &[String],
    elapsed: std::time::Duration,
    all_passed: bool,
) {
    println!(
        "govbot doctor — {} dataset(s), {} record(s), {} distinct id(s), {:.2}s",
        dataset_reports.len(),
        total_records,
        total_distinct,
        elapsed.as_secs_f64()
    );
    println!();

    for r in dataset_reports {
        let status = if !r.passed() {
            "FAIL"
        } else if r.warned() {
            "WARN"
        } else {
            "PASS"
        };
        println!(
            "  [{}] {:<22}  records={:<5} distinct={:<5} sampled={}",
            status, r.dataset, r.record_count, r.distinct_ids, r.sampled
        );
        for c in &r.checks {
            if !c.passed {
                println!("        - {}: FAIL", c.name);
                for d in &c.detail {
                    println!("            • {}", d);
                }
            } else if c.warned {
                println!("        - {}: WARN", c.name);
                for d in &c.detail {
                    println!("            • {}", d);
                }
            }
        }
    }

    println!();
    if !broken_entries.is_empty() {
        println!(
            "  [FAIL] global.dataset_links  {} broken or non-dir entry/entries in repos/:",
            broken_entries.len()
        );
        for name in broken_entries.iter().take(MAX_FAIL_DETAIL) {
            println!(
                "            • {} (likely a dangling symlink or non-directory)",
                name
            );
        }
        if broken_entries.len() > MAX_FAIL_DETAIL {
            println!(
                "            • ...and {} more",
                broken_entries.len() - MAX_FAIL_DETAIL
            );
        }
    } else {
        println!("  [PASS] global.dataset_links");
    }

    if !unrouted.is_empty() {
        println!(
            "  [FAIL] global.routable_ids  {} id(s) without a `<dataset>/country:...` prefix:",
            unrouted.len()
        );
        for id in unrouted.iter().take(MAX_FAIL_DETAIL) {
            println!("            • {}", id);
        }
    } else {
        println!("  [PASS] global.routable_ids");
    }

    println!();
    if all_passed {
        println!("doctor: PASS");
    } else {
        println!("doctor: FAIL");
    }
}

/// Machine-readable doctor report. Stable enough to pipe into CI.
fn emit_doctor_json(
    dataset_reports: &[DatasetReport],
    total_records: usize,
    total_distinct: usize,
    unrouted: &[String],
    broken_entries: &[String],
    elapsed: std::time::Duration,
    all_passed: bool,
) {
    let datasets: Vec<serde_json::Value> = dataset_reports
        .iter()
        .map(|r| {
            let checks: Vec<serde_json::Value> = r
                .checks
                .iter()
                .map(|c| {
                    serde_json::json!({
                        "name": c.name,
                        "passed": c.passed,
                        "warned": c.warned,
                        "detail": c.detail,
                    })
                })
                .collect();
            serde_json::json!({
                "dataset": r.dataset,
                "passed": r.passed(),
                "record_count": r.record_count,
                "distinct_ids": r.distinct_ids,
                "sampled": r.sampled,
                "checks": checks,
            })
        })
        .collect();
    let report = serde_json::json!({
        "status": if all_passed { "pass" } else { "fail" },
        "elapsed_secs": elapsed.as_secs_f64(),
        "total_records": total_records,
        "total_distinct_ids": total_distinct,
        "unrouted_ids": unrouted,
        "broken_dataset_entries": broken_entries,
        "datasets": datasets,
    });
    println!("{}", serde_json::to_string_pretty(&report).unwrap());
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
        Some(Command::Run {
            govbot_dir,
            dry_run,
        }) => {
            let cwd = std::env::current_dir()?;
            let config_path = cwd.join("govbot.yml");
            if !config_path.exists() {
                anyhow::bail!(
                    "No govbot.yml in {}. Run `govbot init` to scaffold one, then `govbot run`.",
                    cwd.display()
                );
            }
            govbot::pipeline::run_pipeline(&config_path, govbot_dir.as_deref(), dry_run)
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
        Some(cmd @ Command::Doctor { .. }) => run_doctor_command(cmd),
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
            govbot::pipeline::run_pipeline(&config_path, None, false)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A typical `govbot source --select docs` id — the leading dataset
    /// `short_name` is what `govbot apply` uses to route the `.tag.json` under
    /// `<project>/tags/<dataset>/...` by default.
    #[test]
    fn parse_doc_route_extracts_dataset_prefix() {
        let route =
            parse_doc_route("wy-legislation/country:us/state:wy/sessions/2025/bills/HB0001")
                .expect("dataset path should parse");
        assert_eq!(route.dataset.as_deref(), Some("wy-legislation"));
        assert_eq!(route.country, "us");
        assert_eq!(route.state, "wy");
        assert_eq!(route.session, "2025");
        assert_eq!(route.bill_id, "HB0001");
    }

    /// A doc id with no dataset prefix — `apply` falls back to the project
    /// dir rather than dropping the record on the floor.
    #[test]
    fn parse_doc_route_handles_missing_dataset_prefix() {
        let route = parse_doc_route("country:us/state:wy/sessions/2025/bills/HB0001")
            .expect("dataset path without prefix should still parse");
        assert!(route.dataset.is_none());
        assert_eq!(route.bill_id, "HB0001");
    }

    /// A non-bill doc id (e.g. a future stream-kind) — `None` so `apply`
    /// skips the record with a warning.
    #[test]
    fn parse_doc_route_rejects_non_bill_ids() {
        assert!(parse_doc_route("just-some-other-id").is_none());
        assert!(parse_doc_route("wy-legislation/country:us").is_none());
    }

    /// The mock layout — logs already live under `bills/<id>/logs/` — so
    /// stripping `/logs/...` from `sources.log` directly yields the bill
    /// path. The `id` must be that full dataset-rooted bill path, ready
    /// for `parse_doc_route` to find a `bills` segment and route the
    /// `.tag.json` back to the correct bill.
    #[test]
    fn ocd_entry_to_doc_per_bill_log_layout_keeps_bill_suffix() {
        let entry = serde_json::json!({
            "log": { "bill_id": "HB0001", "action": { "description": "ANY" } },
            "bill": { "title": "Mock bill", "identifier": "HB0001" },
            "sources": {
                "log": "wy-legislation/country:us/state:wy/sessions/2025/bills/HB0001/logs/20250101T000000Z_foo.json",
                "bill": "wy-legislation/country:us/state:wy/sessions/2025/bills/HB0001/metadata.json"
            }
        });
        let doc = ocd_entry_to_doc(&entry);
        assert_eq!(
            doc.get("id").and_then(|v| v.as_str()),
            Some("wy-legislation/country:us/state:wy/sessions/2025/bills/HB0001")
        );
        // And it must round-trip through `parse_doc_route` — the contract
        // `govbot apply` depends on.
        assert_eq!(
            parse_doc_route(doc.get("id").unwrap().as_str().unwrap())
                .expect("route")
                .bill_id,
            "HB0001"
        );
    }

    /// REGRESSION (real-data bug): `govbot pull all` clones OCD-files-shaped
    /// datasets whose on-disk logs live at `sessions/<id>/logs/<file>.json`
    /// as *symlinks* into per-bill `bills/<id>/logs/<file>.json`. The walker
    /// reports the symlink path, so `sources.log` does NOT contain `/bills/
    /// <id>/` and the old `log_path.split("/logs/").next()` builder dropped
    /// the bill_id, collapsing every bill in a session onto one id. Over the
    /// 55-state corpus that compressed 4916 distinct bill records into 97
    /// session ids; `apply` then overwrote every tag file's `bills` map
    /// repeatedly and the bluesky ledger silently marked one bill per
    /// session as "done." The id must carry `/bills/<bill_id>` so each bill
    /// hashes to a distinct slot.
    #[test]
    fn ocd_entry_to_doc_session_level_log_layout_appends_bill_id() {
        let entry = serde_json::json!({
            "log": { "bill_id": "SB50", "action": { "description": "PASSED" } },
            "bill": { "title": "Mock bill", "identifier": "SB50" },
            "sources": {
                // Realistic shape from `govbot pull ak`: session-level log
                // path, no `/bills/<id>/` segment because the walker
                // followed the symlink-source view, not the canonical
                // target.
                "log": "ak-legislation/country:us/state:ak/sessions/34/logs/20250317T000000Z.vote_event.pass.upper_SB50.json",
                "bill": "../../../../.govbot/cache/ak-abc123/country:us/state:ak/sessions/34/bills/SB50/metadata.json"
            }
        });
        let doc = ocd_entry_to_doc(&entry);
        assert_eq!(
            doc.get("id").and_then(|v| v.as_str()),
            Some("ak-legislation/country:us/state:ak/sessions/34/bills/SB50"),
            "id must include /bills/<bill_id> for session-level log layouts"
        );
        // The whole point: this id must round-trip through `parse_doc_route`
        // so `govbot apply` keys per-bill, not per-session.
        let route = parse_doc_route(doc.get("id").unwrap().as_str().unwrap())
            .expect("session-level layout must still produce a routable doc id");
        assert_eq!(route.bill_id, "SB50");
        assert_eq!(route.session, "34");
    }

    /// Two distinct bills from the same session must yield two distinct ids —
    /// the precondition the apply layer and the bluesky publisher's ledger
    /// rely on. This is the unit-level expression of the corpus check
    /// `len(ids) == len(set(ids))`.
    #[test]
    fn ocd_entry_to_doc_distinct_bills_same_session_get_distinct_ids() {
        let make = |bill_id: &str, log_file: &str| {
            serde_json::json!({
                "log": { "bill_id": bill_id, "action": { "description": "PASSED" } },
                "bill": { "title": "Mock", "identifier": bill_id },
                "sources": {
                    "log": format!(
                        "ak-legislation/country:us/state:ak/sessions/34/logs/{}",
                        log_file
                    ),
                    "bill": format!(
                        "../../../../.govbot/cache/ak-x/country:us/state:ak/sessions/34/bills/{}/metadata.json",
                        bill_id
                    )
                }
            })
        };
        let entries = vec![
            make("SB50", "20250317T000000Z.vote_event.pass.upper_SB50.json"),
            make("HR2", "20250121T000000Z.vote_event.pass.lower_HR2.json"),
            make("HJR20", "20250514T000000Z_h_fn1_zeroleg_HJR20.json"),
            make("HB55", "20250306T000000Z_h_heard_held_HB55.json"),
        ];
        let ids: Vec<String> = entries
            .iter()
            .map(|e| {
                ocd_entry_to_doc(e)
                    .get("id")
                    .and_then(|v| v.as_str())
                    .unwrap()
                    .to_string()
            })
            .collect();
        let unique: std::collections::HashSet<&String> = ids.iter().collect();
        assert_eq!(
            ids.len(),
            unique.len(),
            "4 bills under one session must produce 4 distinct ids; got: {:?}",
            ids
        );
    }

    /// REGRESSION (real-data bug, 55-state corpus): MI/WV/ND/PA legislature
    /// logs ship a `bill_id` field with a *display* space — e.g.
    /// `"HB 5077"`, `"SB 0001"` — even though the corresponding on-disk
    /// directory is `bills/HB5077/`, `bills/SB0001/` (no space). The
    /// pre-fix `ocd_entry_to_doc` for the Layout-2 (session-level symlink)
    /// case appended `log.bill_id` verbatim, producing ids like
    /// `mi-legislation/.../bills/SB 0001`. Downstream consumers doing a
    /// sibling `metadata.json` lookup via path joining
    /// (`os.path.join(REPOS, doc, "metadata.json")`) then 404'd because no
    /// such directory exists on disk. The architect saw "(no metadata.json)"
    /// for ~30% of bills.
    ///
    /// The fix sources the `/bills/<dir>` segment from the resolved
    /// `sources.bill` path (the parent dir of `metadata.json`, which the
    /// `bill` join produced from the canonicalized log path) — that is the
    /// authoritative on-disk dir name. The id must NOT contain whitespace
    /// in the bill segment, and it must point to a directory that exists.
    #[test]
    fn ocd_entry_to_doc_uses_canonical_bill_dir_when_log_bill_id_has_whitespace() {
        let entry = serde_json::json!({
            "log": {
                // Display form with a space — this is what MI/WV/ND/PA emit.
                "bill_id": "SB 0001",
                "action": { "description": "PASSED" }
            },
            "bill": { "title": "Mock", "identifier": "SB 0001" },
            "sources": {
                // Session-level symlink layout (Layout 2). `sources.log`
                // stops at the session because the walker reported the
                // symlink, not the canonical target.
                "log": "mi-legislation/country:us/state:mi/sessions/2025-2026/logs/20250108T000000Z_referred_to_committee_of_the_whole_SB0001.json",
                // `sources.bill` points at the *resolved* on-disk
                // metadata.json — the parent dir is the canonical bill dir
                // name (no whitespace).
                "bill": "../../../../.govbot/cache/mi-ad5ea7bbd548/country:us/state:mi/sessions/2025-2026/bills/SB0001/metadata.json"
            }
        });
        let doc = ocd_entry_to_doc(&entry);
        let id = doc
            .get("id")
            .and_then(|v| v.as_str())
            .expect("doc id must be a string");
        // The id must end at the on-disk dir, not the display bill_id.
        assert_eq!(
            id, "mi-legislation/country:us/state:mi/sessions/2025-2026/bills/SB0001",
            "id must use the canonical on-disk bill dir name (no whitespace)"
        );
        // No whitespace anywhere in the id — that's what makes
        // `os.path.join(REPOS, doc, \"metadata.json\")` resolve to a real
        // file on a real filesystem.
        assert!(
            !id.contains(' '),
            "id must not carry display-form whitespace; got: {}",
            id
        );
    }

    /// Same data shape, all four affected states (MI/WV/ND/PA) — pins that
    /// the fix isn't accidentally specific to one state's path shape.
    #[test]
    fn ocd_entry_to_doc_uses_canonical_bill_dir_for_all_affected_states() {
        // (display_bill_id, on_disk_dir, dataset, session, log_filename)
        let cases = [
            (
                "SB 0001",
                "SB0001",
                "mi-legislation",
                "mi",
                "2025-2026",
                "20250108T000000Z_referred_to_committee_of_the_whole_SB0001.json",
            ),
            (
                "SB 458",
                "SB458",
                "wv-legislation",
                "wv",
                "2025",
                "20250307T000000Z_read_2nd_time_SB458.json",
            ),
            (
                "SB 2262",
                "SB2262",
                "nd-legislation",
                "nd",
                "69",
                "20250501T000000Z_signed_by_governor_0429_SB2262.json",
            ),
            (
                "HB 1271",
                "HB1271",
                "pa-legislation",
                "pa",
                "2025-2026",
                "20250421T040000Z_referred_to_education_HB1271.json",
            ),
        ];
        for (display_id, on_disk_dir, dataset, state, session, log_file) in cases {
            let entry = serde_json::json!({
                "log": { "bill_id": display_id, "action": { "description": "PASSED" } },
                "bill": { "title": "Mock", "identifier": display_id },
                "sources": {
                    "log": format!(
                        "{}/country:us/state:{}/sessions/{}/logs/{}",
                        dataset, state, session, log_file
                    ),
                    "bill": format!(
                        "../../../../.govbot/cache/{}-deadbeef/country:us/state:{}/sessions/{}/bills/{}/metadata.json",
                        state, state, session, on_disk_dir
                    )
                }
            });
            let doc = ocd_entry_to_doc(&entry);
            let id = doc
                .get("id")
                .and_then(|v| v.as_str())
                .unwrap_or_default()
                .to_string();
            assert_eq!(
                id,
                format!(
                    "{}/country:us/state:{}/sessions/{}/bills/{}",
                    dataset, state, session, on_disk_dir
                ),
                "{}: id must use the on-disk dir `{}`, not the log's display id `{}`",
                state,
                on_disk_dir,
                display_id
            );
            assert!(
                !id.contains(' '),
                "{}: id contains whitespace; got: {}",
                state,
                id
            );
            // Round-trip: the route's bill_id must be the on-disk dir
            // name, because that's what every downstream path lookup
            // (`os.path.join(REPOS, doc, ...)`) is going to hit.
            let route =
                parse_doc_route(&id).expect("routable doc id even for spaced bill_id inputs");
            assert_eq!(
                route.bill_id, on_disk_dir,
                "{}: parsed bill_id must be the on-disk dir",
                state
            );
        }
    }

    /// REGRESSION (real-data follow-on of the whitespace fix): MI/ND/PA
    /// also publish a Layout-1 view for some bills — `sources.log` is
    /// `.../sessions/<id>/bills/<canonical_dir>/logs/<file>.json` because
    /// the walker happened to land on the per-bill log directly. In that
    /// case the stripped path already ends in `/bills/<canonical_dir>`
    /// (e.g. `bills/HR0163`). But `log.bill_id` is `"HR 0163"` (display
    /// form). The pre-fix Layout-1 detector compared the stripped path's
    /// suffix to `log.bill_id` verbatim, which DID NOT match (no space
    /// vs space), so the code fell through to the Layout-2 branch and
    /// appended `/bills/HR0163` *again*, producing
    /// `mi-legislation/.../bills/HR0163/bills/HR0163`. Sample over the
    /// 55-state corpus: ~50% of mi/nd/pa records exhibited the
    /// doubled-bills id. The Layout-1 detector must therefore consider
    /// both the canonical dir name (from `sources.bill`) and
    /// `log.bill_id`; a match on either means the path already names
    /// the bill.
    #[test]
    fn ocd_entry_to_doc_layout1_with_spaced_log_bill_id_does_not_double_bills_segment() {
        let entry = serde_json::json!({
            "log": {
                // Display form with a space — what MI/ND/PA emit.
                "bill_id": "HR 0163",
                "action": { "description": "ANY" }
            },
            "bill": { "title": "Mock", "identifier": "HR 0163" },
            "sources": {
                // Layout 1 — the walker landed on the per-bill log dir.
                // The stripped path will end in `/bills/HR0163` (no space).
                "log": "mi-legislation/country:us/state:mi/sessions/2025-2026/bills/HR0163/logs/20250101T000000Z_foo.json",
                "bill": "../../../../.govbot/cache/mi-x/country:us/state:mi/sessions/2025-2026/bills/HR0163/metadata.json"
            }
        });
        let doc = ocd_entry_to_doc(&entry);
        let id = doc.get("id").and_then(|v| v.as_str()).unwrap_or_default();
        assert_eq!(
            id, "mi-legislation/country:us/state:mi/sessions/2025-2026/bills/HR0163",
            "Layout 1 with spaced log.bill_id must not double-append the /bills/<dir> segment"
        );
        // The cardinal symptom of the bug: a doubled `bills/<dir>/bills/<dir>` tail.
        assert!(
            !id.contains("/bills/HR0163/bills/"),
            "id must not double the bills segment; got: {}",
            id
        );
        assert!(
            !id.contains(' '),
            "id must not contain whitespace; got: {}",
            id
        );
    }

    /// `bill_dir_from_metadata_path` is the helper the fix relies on. Unit-
    /// test the shape boundary so future refactors don't silently break it.
    #[test]
    fn bill_dir_from_metadata_path_extracts_dir_segment() {
        assert_eq!(
            bill_dir_from_metadata_path(
                "../../../../.govbot/cache/mi-x/country:us/state:mi/sessions/2025-2026/bills/HB5109/metadata.json"
            ),
            Some("HB5109")
        );
        assert_eq!(
            bill_dir_from_metadata_path(
                "wy-legislation/country:us/state:wy/sessions/2025/bills/HB0001/metadata.json"
            ),
            Some("HB0001")
        );
        // Not a bill metadata path — refuse to guess.
        assert_eq!(
            bill_dir_from_metadata_path("country:us/state:wy/sessions/2025/metadata.json"),
            None
        );
        assert_eq!(bill_dir_from_metadata_path("metadata.json"), None);
        assert_eq!(bill_dir_from_metadata_path(""), None);
    }

    /// When the consumer ran `govbot source --select docs` *without*
    /// `--join bill`, `sources.bill` is absent and we have no canonical
    /// dir to lean on. Fall back to `log.bill_id` so the id is still
    /// routable — even if it carries display-form whitespace. Document
    /// that this is the advisory path; the production `source --select
    /// docs` invocation always joins `bill`, so this branch only fires
    /// for ad-hoc invocations.
    #[test]
    fn ocd_entry_to_doc_falls_back_to_log_bill_id_when_bill_join_absent() {
        let entry = serde_json::json!({
            "log": { "bill_id": "SB 0001", "action": { "description": "PASSED" } },
            "sources": {
                "log": "mi-legislation/country:us/state:mi/sessions/2025-2026/logs/20250108T000000Z_x.json"
                // No `sources.bill` — `--join bill` was not requested.
            }
        });
        let doc = ocd_entry_to_doc(&entry);
        assert_eq!(
            doc.get("id").and_then(|v| v.as_str()),
            Some("mi-legislation/country:us/state:mi/sessions/2025-2026/bills/SB 0001"),
            "without sources.bill we fall back to log.bill_id (advisory; may carry whitespace)"
        );
    }

    /// `.govbot/` is the cache; tag files belong outside it in the project-
    /// rooted `tags/` output dir. The resolver's primary candidate must
    /// therefore be `<project>/tags/<dataset>/country:.../state:.../sessions/
    /// <id>/`, with the in-cache `<session>/tags/` location kept only as a
    /// read-only fallback for working trees mid-migration. This regression
    /// pins both — Bug 1's revisit must not silently restore the cache as
    /// the primary location.
    #[test]
    fn resolve_tags_dir_candidates_prefer_project_tags_then_cache_fallback() {
        let tmp = tempfile::tempdir().expect("tempdir");
        let project = tmp.path().join("project");
        let session = project
            .join(".govbot")
            .join("repos")
            .join("wy-legislation")
            .join("country:us")
            .join("state:wy")
            .join("sessions")
            .join("2025");
        let log_path = session
            .join("bills")
            .join("HB0001")
            .join("logs")
            .join("2025-01-15T12:00:00Z.json");
        fs::create_dir_all(log_path.parent().unwrap()).unwrap();
        fs::write(&log_path, "{}").unwrap();

        let candidates = resolve_tags_dir_candidates(&log_path, &project);
        // Primary is the project-rooted output dir.
        assert_eq!(
            candidates.first().expect("primary candidate"),
            &project
                .join("tags")
                .join("wy-legislation")
                .join("country:us")
                .join("state:wy")
                .join("sessions")
                .join("2025"),
        );
        // Fallback A is the Bug-6 in-cache layout — read-only for migration.
        assert!(candidates.iter().any(|c| c == &session.join("tags")));
        // And critically: the cache is NOT the primary location.
        assert_ne!(candidates.first().unwrap(), &session.join("tags"));
    }

    /// A log file outside any dataset layout (no `bills/` ancestor) yields
    /// no candidates, letting the caller fall back to the legacy cwd-rooted
    /// lookup.
    #[test]
    fn resolve_tags_dir_candidates_empty_outside_dataset_layout() {
        let tmp = tempfile::tempdir().expect("tempdir");
        let stray = tmp.path().join("loose").join("file.json");
        fs::create_dir_all(stray.parent().unwrap()).unwrap();
        fs::write(&stray, "{}").unwrap();
        assert!(resolve_tags_dir_candidates(&stray, tmp.path()).is_empty());
    }

    /// Dataset isolation — the whole reason the `<short>` segment lives at
    /// the top of `tags/`. Two datasets sharing a `country:us/state:xx`
    /// jurisdiction must write the same-named tag file to *different* files
    /// on disk, keyed by short_name, so a project tracking multiple
    /// jurisdictions never has one dataset's classification clobber
    /// another's.
    #[test]
    fn tag_paths_are_dataset_isolated() {
        // Synthesise the per-dataset destinations the way `run_apply_command`
        // does, against two short_names that share a country/state/session.
        let project = std::path::PathBuf::from("/tmp/project");
        let tags_root = project.join("tags");

        let short_a = "wy-legislation";
        let short_b = "wy-counties";
        let country = "country:us";
        let state = "state:wy";
        let session = "2025";
        let tag = "clean_energy";

        let path_a = tags_root
            .join(short_a)
            .join(country)
            .join(state)
            .join("sessions")
            .join(session)
            .join(format!("{}.tag.json", tag));
        let path_b = tags_root
            .join(short_b)
            .join(country)
            .join(state)
            .join("sessions")
            .join(session)
            .join(format!("{}.tag.json", tag));

        assert_ne!(path_a, path_b, "dataset prefix must split the tag file");
        // Both must share the `tags/` prefix — the project's
        // classification-output dir — never `.govbot/`.
        assert!(path_a.starts_with(&tags_root));
        assert!(path_b.starts_with(&tags_root));
        let govbot_cache = project.join(".govbot");
        assert!(!path_a.starts_with(&govbot_cache));
        assert!(!path_b.starts_with(&govbot_cache));
    }

    /// End-to-end of the helper: a tag file in the dataset-rooted `tags/`
    /// dir produces a `{tag_name: score}` map for the bill it lists, and an
    /// empty map for a bill it does not list.
    #[test]
    fn match_tags_in_dir_returns_scores_for_matching_bill() {
        let tmp = tempfile::tempdir().expect("tempdir");
        let tags_dir = tmp.path().join("tags");
        fs::create_dir_all(&tags_dir).unwrap();
        let tag_file = serde_json::json!({
            "metadata": {
                "last_run": "2025-01-15T12:00:00Z",
                "model": "fastclass-test",
                "tag_config_hash": "abc123"
            },
            "tag_config": {
                "name": "clean_energy"
            },
            "bills": {
                "HB0001": {
                    "text_hash": "deadbeef",
                    "score": {
                        "final_score": 0.92,
                        "base_embedding": null,
                        "example_similarity": null,
                        "keyword_match": [],
                        "negative_penalty": 0.0
                    }
                }
            }
        });
        fs::write(tags_dir.join("clean_energy.tag.json"), tag_file.to_string()).unwrap();

        let matched = match_tags_in_dir(&tags_dir, "HB0001");
        assert_eq!(matched.len(), 1);
        assert!(matched.contains_key("clean_energy"));

        let missing = match_tags_in_dir(&tags_dir, "HB9999");
        assert!(missing.is_empty());

        // Missing dir is not an error — callers chain dataset-rooted then
        // cwd-rooted lookups, and a non-existent dir is the common case.
        let absent = match_tags_in_dir(&tmp.path().join("no-such-dir"), "HB0001");
        assert!(absent.is_empty());
    }

    // -----------------------------------------------------------------
    // `govbot doctor` — the corpus-level smoke test. The full end-to-end
    // path is exercised against real pulled data (see commit message for
    // run details); these unit tests pin the failure-detection legs that
    // would have caught bugs 7592418 and 5ab6d3c.
    // -----------------------------------------------------------------

    /// The metadata.json check is the leg that would have flagged 5ab6d3c
    /// — a doc id whose dir-name was wrong (display form, with whitespace)
    /// resolves to a non-existent metadata.json path.
    #[test]
    fn doctor_check_metadata_json_flags_missing_file() {
        let tmp = tempfile::TempDir::new().unwrap();
        let dataset_dir = tmp.path().join("mi-legislation");
        let bill_dir = dataset_dir
            .join("country:us")
            .join("state:mi")
            .join("sessions")
            .join("2025-2026_103rd_Legislature")
            .join("bills")
            .join("HB4027");
        fs::create_dir_all(&bill_dir).unwrap();
        // Write a well-formed metadata.json — happy path.
        fs::write(
            bill_dir.join("metadata.json"),
            serde_json::to_string(&serde_json::json!({
                "title": "An Act…",
                "identifier": "HB 4027",
            }))
            .unwrap(),
        )
        .unwrap();

        // A clean id resolves.
        let good_id =
            "mi-legislation/country:us/state:mi/sessions/2025-2026_103rd_Legislature/bills/HB4027";
        assert!(check_metadata_json(good_id, &dataset_dir).is_ok());

        // The exact pre-5ab6d3c failure: log.bill_id `"HB 4027"` (with
        // whitespace) bleeds into the doc id, and the on-disk dir is
        // `HB4027` — so the metadata.json path doesn't exist.
        let broken_id =
            "mi-legislation/country:us/state:mi/sessions/2025-2026_103rd_Legislature/bills/HB 4027";
        let err = check_metadata_json(broken_id, &dataset_dir).unwrap_err();
        assert!(
            err.contains("not found"),
            "expected 'not found' in error, got: {}",
            err
        );
    }

    /// metadata.json present but lacking both `title` and `identifier` —
    /// counts as a fail. This catches stub/empty-bill clones where the
    /// scraper landed but populated nothing usable.
    #[test]
    fn doctor_check_metadata_json_requires_title_or_identifier() {
        let tmp = tempfile::TempDir::new().unwrap();
        let dataset_dir = tmp.path().join("wy-legislation");
        let bill_dir = dataset_dir
            .join("country:us")
            .join("state:wy")
            .join("sessions")
            .join("2025")
            .join("bills")
            .join("HB0001");
        fs::create_dir_all(&bill_dir).unwrap();
        fs::write(
            bill_dir.join("metadata.json"),
            // Neither title nor identifier — both empty / absent.
            serde_json::to_string(&serde_json::json!({"description": "..."})).unwrap(),
        )
        .unwrap();

        let id = "wy-legislation/country:us/state:wy/sessions/2025/bills/HB0001";
        let err = check_metadata_json(id, &dataset_dir).unwrap_err();
        assert!(err.contains("neither `title` nor `identifier`"));
    }

    /// `dataset_short_name` is the only place where the dataset prefix
    /// in a doc id (`<short>-legislation`) and the short_name returned by
    /// `get_local_datasets` (`<short>`) meet. Getting this wrong silently
    /// breaks per-dataset bucketing — every dataset shows zero coverage
    /// even though records were emitted. Pin both common suffixes.
    #[test]
    fn doctor_dataset_short_name_strips_known_suffixes() {
        assert_eq!(dataset_short_name("nj-legislation", "-legislation"), "nj");
        assert_eq!(dataset_short_name("usa-legislation", "-legislation"), "usa");
        // Legacy `<short>-data-pipeline` layout — strip it too.
        assert_eq!(dataset_short_name("wy-data-pipeline", "-legislation"), "wy");
        // Custom suffix from GOVBOT_REPO_SUFFIX is honoured.
        assert_eq!(dataset_short_name("nj-pkg", "-pkg"), "nj");
        // Bare short_name (no suffix at all) passes through.
        assert_eq!(dataset_short_name("wy", "-legislation"), "wy");
    }

    /// metadata.json is unreadable JSON — that's still a fail (we can't
    /// trust a record whose bill metadata won't even parse).
    #[test]
    fn doctor_check_metadata_json_flags_unparseable() {
        let tmp = tempfile::TempDir::new().unwrap();
        let dataset_dir = tmp.path().join("ca-legislation");
        let bill_dir = dataset_dir
            .join("country:us")
            .join("state:ca")
            .join("sessions")
            .join("2025-2026")
            .join("bills")
            .join("AB100");
        fs::create_dir_all(&bill_dir).unwrap();
        fs::write(bill_dir.join("metadata.json"), b"{ this is not json").unwrap();
        let id = "ca-legislation/country:us/state:ca/sessions/2025-2026/bills/AB100";
        let err = check_metadata_json(id, &dataset_dir).unwrap_err();
        assert!(err.contains("invalid JSON"));
    }
}
