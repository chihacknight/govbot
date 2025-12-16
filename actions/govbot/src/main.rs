use clap::{Parser, Subcommand};
use govbot::git;
use govbot::{TagMatcher, hash_text, TagFile, TagFileMetadata, BillTagResult};
use govbot::selectors::ocd_files_select_default;
use govbot::publish::{load_config, get_repos_from_config, filter_by_tags, deduplicate_entries, sort_by_timestamp};
use govbot::rss;
use futures::StreamExt;
use futures::stream;
use std::io::{self, Write, BufRead, BufReader};
use std::path::PathBuf;
use serde_json;
use jwalk::WalkDir;
use std::fs;
use std::process::Command as ProcessCommand;
use std::collections::HashMap;

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
    result: String, // "cloned", "pulled", "no_updates", "failed"
    position: String, // "1/37"
    size: Option<String>,
    local_size: Option<String>,
    final_size: Option<String>,
    error: Option<String>,
}

/// Type-safe, functional reactive processor for pipeline log files
#[derive(Parser, Debug)]
#[command(name = "govbot")]
#[command(about = "Process pipeline log files with type-safe reactive streams")]
#[command(version)]
struct Args {
    #[command(subcommand)]
    command: Option<Command>,
}

#[derive(Subcommand, Debug)]
enum Command {
    /// Clone or pull data pipeline repositories (default: updates existing repos)
    /// Clones if repository doesn't exist, pulls if it does
    /// Use "govbot clone all" to clone all repos, or "govbot clone <repo>" for specific repos
    Clone {
        /// Repository names to clone/pull (e.g., usa, il, ca, or "all" for all repos). If not specified, updates existing repos.
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

        /// List available repos instead of cloning/pulling
        #[arg(long)]
        list: bool,
    },

    /// Process and display pipeline log files
    Logs {
        /// Repos to output (default: `all`) `--repos="il,ca"`
        #[arg(long, num_args = 0..)]
        repos: Vec<String>,
    
        /// Per repo limit (default: 100) options: `none` | number
        #[arg(long, default_value = "100")]
        limit: String,

        /// Join additional datasets (default: `bill,tags`) options: `bill`, `tags`, `bill,tags`, etc.
        #[arg(long, default_value = "bill,tags")]
        join: String,

        /// Select/transform fields (default: `default`) - applies extract_text_from_json transformation
        #[arg(long, default_value = "default", value_parser = ["default"])]
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

    /// Delete data pipeline repositories
    /// Deletes local repository directories for specified locales
    Delete {
        /// Locale names to delete (e.g., usa, il, ca, or "all" for all locales). Use "all" to delete all repositories.
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

    /// Load bill metadata into a DuckDB database file
    /// Loads all metadata.json files from cloned repos into a DuckDB database for analysis.
    /// The database file is saved in the base govbot directory (e.g., ./.govbot/govbot.duckdb)
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

    /// Update govbot to the latest nightly version
    /// Downloads and installs the latest nightly build from GitHub releases
    Update,

    /// Initialize a new govbot project
    /// Creates govbot.yml, .gitignore, and GitHub Actions workflow
    Init {
        /// Force overwrite existing files
        #[arg(long)]
        force: bool,
    },

    /// Publish RSS feed from govbot.yml configuration
    /// Generates a combined RSS feed from logs filtered by tags in govbot.yml
    Publish {
        /// Specific tags to include in feed (default: all tags from govbot.yml)
        #[arg(long, num_args = 0..)]
        tags: Vec<String>,
        
        /// Limit number of entries per feed (default: 15, use "none" for all entries)
        #[arg(long)]
        limit: Option<String>,
        
        /// Output directory for RSS feed (default: from govbot.yml publish.output_dir)
        #[arg(long)]
        output_dir: Option<String>,
        
        /// Output filename for RSS feed (default: from govbot.yml publish.output_file)
        #[arg(long)]
        output_file: Option<String>,
        
        /// Govbot directory (default: $CWD/.govbot/repos, or GOVBOT_DIR env var)
        #[arg(long = "govbot-dir")]
        govbot_dir: Option<String>,
    },

    /// Tag bills using semantic or built-in similarity based on govbot.yml in the current directory.
    /// Reads JSON lines from stdin (from `govbot logs`), processes entries with bill identifiers,
    /// and writes per-tag files under the directory containing govbot.yml.
    /// By default, acts as a filter: only outputs lines that match tags.
    /// If a tag name is provided, only processes and outputs lines matching that specific tag.
    Tag {
        /// Optional tag name to filter to a specific tag (e.g., "lgbtq", "budget")
        tag_name: Option<String>,

        /// Output directory (defaults to the directory containing govbot.yml)
        #[arg(long = "output-dir")]
        output_dir: Option<String>,

        /// Govbot directory (default: $CWD/.govbot/repos, or GOVBOT_DIR env var)
        #[arg(long = "govbot-dir")]
        govbot_dir: Option<String>,

        /// Force re-tagging even if bill already exists in tag files
        #[arg(long)]
        overwrite: bool,
    },
}

fn print_available_commands() {
    println!("Available commands:");
    println!("  init    Initialize a new govbot project (creates govbot.yml, .gitignore, and GitHub Actions workflow)");
    println!("  clone   Clone or pull data pipeline repositories (default: updates existing repos, use 'clone all' to clone all)");
    println!("  delete  Delete data pipeline repositories (use 'delete all' to delete all)");
    println!("  logs    Process and display pipeline log files");
    println!("  load    Load bill metadata into a DuckDB database file");
    println!("  publish Generate RSS feed from govbot.yml configuration");
    println!("  tag     Tag bills using AI based on log entries");
    println!("  update  Update govbot to the latest nightly version");
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

/// Process a single locale clone/pull operation
fn process_single_locale(
    locale: &str,
    repos_dir: &PathBuf,
    token_str: Option<&str>,
    verbose: bool,
) -> CloneResult {
    let repo_name = git::build_repo_name(locale);
    let target_dir = repos_dir.join(&repo_name);
    
    let local_size = if target_dir.exists() {
        git::get_directory_size(&target_dir).unwrap_or(0)
    } else {
        0
    };
    
    match git::clone_or_pull_repo_quiet(locale, repos_dir, token_str, !verbose) {
        Ok(action) => {
            let final_size = if target_dir.exists() {
                git::get_directory_size(&target_dir).unwrap_or(0)
            } else {
                0
            };
            
            let result = match action {
                "clone" => "🆕",
                "pulled" => "⬇️",
                "no_updates" => "✅",
                "recloned" => "🔄",
                _ => "processed",
            };
            
            let mut clone_result = CloneResult {
                locale: locale.to_string(),
                result: result.to_string(),
                position: String::new(), // Will be set by caller
                size: None,
                local_size: None,
                final_size: None,
                error: None,
            };
            
            if action == "clone" || action == "recloned" || action == "no_updates" {
                clone_result.size = Some(git::format_size(final_size));
            } else {
                clone_result.local_size = Some(git::format_size(local_size));
                clone_result.final_size = Some(git::format_size(final_size));
            }
            
            clone_result
        }
        Err(e) => CloneResult {
            locale: locale.to_string(),
            result: "failed".to_string(),
            position: String::new(), // Will be set by caller
            size: None,
            local_size: None,
            final_size: None,
            error: Some(e.to_string()),
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
        } else if let (Some(ref local), Some(ref final_size)) = (&result.local_size, &result.final_size) {
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
    repos_to_clone: Vec<String>,
    repos_dir: PathBuf,
    token_str: Option<&str>,
    num_jobs: usize,
    verbose: bool,
) -> anyhow::Result<Vec<CloneResult>> {
    let total = repos_to_clone.len();
    let mut all_results = Vec::new();
    
    if total == 1 || num_jobs == 1 {
        // Sequential clone/pull - print as we go
        for (idx, locale) in repos_to_clone.iter().enumerate() {
            let mut result = process_single_locale(locale, &repos_dir, token_str, verbose);
            result.position = format!("{}/{}", idx + 1, total);
            print_result(&result);
            all_results.push(result);
        }
    } else {
        // Parallel clone/pull - print as results come in
        use std::sync::{Arc, Mutex};
        let completed = Arc::new(Mutex::new(0usize));
        
        let clone_futures = stream::iter(repos_to_clone.iter())
            .map(|locale| {
                let locale = locale.clone();
                let repos_dir = repos_dir.clone();
                let token = token_str.map(|s| s.to_string());
                let completed = completed.clone();
                let total = total;
                let verbose_flag = verbose;
                
                tokio::task::spawn_blocking(move || {
                    let mut result = process_single_locale(&locale, &repos_dir, token.as_deref(), verbose_flag);
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


async fn run_clone_command(cmd: Command) -> anyhow::Result<()> {
    let Command::Clone {
        repos,
        govbot_dir,
        token,
        parallel,
        verbose,
        list,
    } = cmd else {
        unreachable!()
    };

    // If --list flag is set, show the list
    if list {
        println!("Available repos:");
        let all_locales = govbot::locale::WorkingLocale::all();
        for locale in all_locales {
            println!("  {}", locale.as_lowercase());
        }
        println!("  all (clone all repos)");
        return Ok(());
    }

    let repos_dir = get_govbot_dir(govbot_dir)?;
    
    // Get token from argument or environment variable
    let env_token = std::env::var("TOKEN").ok();
    let token_str = token.as_deref().or(env_token.as_deref());
    
    // Get parallelization setting
    let num_jobs = parallel
        .or_else(|| std::env::var("GOVBOT_JOBS").ok().and_then(|s| s.parse().ok()))
        .unwrap_or(4);

    // Parse repos and handle "all"
    let mut repos_to_clone = Vec::new();
    
    if repos.is_empty() {
        // No repos specified: find existing repos to update
        // Check all known locales to see which repos exist
        let all_locales = govbot::locale::WorkingLocale::all();
        for locale in all_locales {
            let locale_str = locale.as_lowercase();
            let repo_name = git::build_repo_name(&locale_str);
            let repo_path = repos_dir.join(&repo_name);
            
            // Check if this is a git repository
            if repo_path.exists() && repo_path.join(".git").exists() {
                repos_to_clone.push(locale_str.to_string());
            }
        }
        
        if repos_to_clone.is_empty() {
            eprintln!("No repos downloaded yet in this directory");
            eprintln!("to download all gov data, do `govbot clone all`. future syncs are just `govbot clone`");
            return Ok(());
        }
        
        // Create directory if it doesn't exist (needed for the clone operations)
        std::fs::create_dir_all(&repos_dir)?;
    } else {
        // Create directory if it doesn't exist (needed for the clone operations)
        std::fs::create_dir_all(&repos_dir)?;
        
        // Parse specified repos
        for repo in repos {
            let repo = repo.trim().to_lowercase();
            if repo.is_empty() {
                continue;
            }
            
            if repo == "all" {
                // Add all working locales
                let all_locales = govbot::locale::WorkingLocale::all();
                for loc in all_locales {
                    repos_to_clone.push(loc.as_lowercase().to_string());
                }
            } else {
                // Validate locale
                let _ = govbot::locale::WorkingLocale::from(repo.as_str());
                repos_to_clone.push(repo);
            }
        }
    }

    if repos_to_clone.is_empty() {
        return Ok(());
}

    // Print initial message with count
    eprintln!("🔁 Syncing {} repos\n", repos_to_clone.len());

    // Perform clone operations and print results as they complete
    let results = perform_clone_operations(
        repos_to_clone,
        repos_dir,
        token_str,
        num_jobs,
        verbose,
    ).await?;
    
    // Show summary
    let errors: Vec<_> = results.iter()
        .filter(|r| r.result == "failed")
        .collect();
    
    if !errors.is_empty() {
        eprintln!("\n❌ Errors occurred: {}/{}", errors.len(), results.len());
    } else if !results.is_empty() {
        eprintln!("\n✅ Successfully processed all {} repos!", results.len());
    }
    
    Ok(())
}


async fn run_delete_command(cmd: Command) -> anyhow::Result<()> {
    let Command::Delete {
        locales,
        govbot_dir,
        parallel,
        verbose,
    } = cmd else {
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
        .or_else(|| std::env::var("GOVBOT_JOBS").ok().and_then(|s| s.parse().ok()))
        .unwrap_or(4);

    // Parse locales and handle "all"
    let mut locales_to_delete = Vec::new();
    for locale in locales {
        let locale = locale.trim().to_lowercase();
        if locale.is_empty() {
            continue;
        }
        
        if locale == "all" {
            // Add all working locales
            let all_locales = govbot::locale::WorkingLocale::all();
            for loc in all_locales {
                locales_to_delete.push(loc.as_lowercase().to_string());
            }
        } else {
            // Validate locale
            let _ = govbot::locale::WorkingLocale::from(locale.as_str());
            locales_to_delete.push(locale);
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
            let repo_name = format!("{}-data-pipeline", locale);
            let target_dir = repos_dir.join(&repo_name);
            let existed = target_dir.exists();
            
            if verbose {
                eprintln!("[{}/{}] Deleting {}...", idx + 1, total, locale);
            }
            
            match git::delete_repo(locale, &repos_dir) {
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
                    let repo_name = format!("{}-data-pipeline", locale);
                    let target_dir = repos_dir.join(&repo_name);
                    
                    if verbose_flag {
                        let d = deleted.lock().unwrap();
                        let f = failed.lock().unwrap();
                        let current = *d + *f + 1;
                        eprintln!("[{}/{}] Deleting {}...", current, total, locale);
                    }
                    
                    let existed = target_dir.exists();
                    match git::delete_repo(&locale, &repos_dir) {
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

async fn run_logs_command(cmd: Command) -> anyhow::Result<()> {
    let Command::Logs {
        govbot_dir,
        repos,
        sort: _sort,
        limit,
        join,
        select,
        filter,
    } = cmd else {
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
        Some(limit.parse().map_err(|e| anyhow::anyhow!("Invalid limit value '{}': {}", limit, e))?)
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

    // Expand "all" to existing repos in the directory, or convert locale names to repo names
    let mut repos_to_process = Vec::new();
    for locale in repo_list {
        let locale = locale.trim().to_lowercase();
        if locale.is_empty() {
            continue;
        }
        
        if locale == "all" {
            // Find all existing repos in the directory
            if git_dir.exists() {
                let all_locales = govbot::locale::WorkingLocale::all();
                for loc in all_locales {
                    let locale_str = loc.as_lowercase();
                    let repo_name = git::build_repo_name(&locale_str);
                    let repo_path = git_dir.join(&repo_name);
                    
                    // Only add repos that actually exist (for logs, we don't need .git, just the directory)
                    if repo_path.exists() && repo_path.is_dir() {
                        repos_to_process.push(repo_name);
                    }
                }
            }
        } else {
            // Convert locale name to repo name using build_repo_name
            repos_to_process.push(git::build_repo_name(&locale));
        }
    }

    // Per-repo limit
    let per_repo_limit = limit_parsed;

    // Initialize filter (now has default value "default")
    let filter_manager = govbot::FilterManager::new(govbot::FilterAlias::from(filter.as_str()));

    // Process each repo (with optional filtering)
    for repo_name in repos_to_process {
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
                                    sources.insert("log".to_string(), serde_json::Value::String(source_path_str.clone()));
                                    
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
                                                
                                                let metadata_path = canonical_log_path.parent()
                                                    .and_then(|logs_dir| {
                                                        logs_dir.parent().map(|bill_dir| {
                                                            bill_dir.join("metadata.json")
                                                        })
                                                    });
                                                
                                                if let Some(ref metadata_path) = metadata_path {
                                                    if metadata_path.exists() {
                                                        match fs::read_to_string(metadata_path) {
                                                            Ok(metadata_contents) => {
                                                                match serde_json::from_str::<serde_json::Value>(&metadata_contents) {
                                                                    Ok(metadata_value) => {
                                                                        // If field_path is specified, extract just that field
                                                                        // Otherwise, include the full bill data
                                                                        if field_path.is_empty() {
                                                                            // No field path specified, include full bill data
                                                                            output.insert("bill".to_string(), metadata_value);
                                                                        } else {
                                                                            // Extract specific field(s) from bill data
                                                                            if let Some(field_value) = extract_json_field(&metadata_value, field_path) {
                                                                                // Use the full join path as the key (e.g., "bill.title")
                                                                                let output_key = format!("{}.{}", dataset_name, field_path.join("."));
                                                                                output.insert(output_key, field_value);
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
                                                eprintln!("Warning: Unknown join dataset: {}", dataset_name);
                                            }
                                        }
                                    }
                                    
                                    // Join tags if requested
                                    if join_tags {
                                        // Extract country, state, session_id from the path
                                        if let Some((country, state, session_id)) = extract_path_info(&source_path_str) {
                                            // Use bill_id extracted earlier
                                            if let Some(ref bill_id) = bill_id_opt {
                                                // Look for tags in cwd/country:us/state:{state}/sessions/{session_id}/tags/
                                                let cwd = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
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
                                                            if let Some(ext) = path.extension().and_then(|s| s.to_str()) {
                                                                if ext == "json" {
                                                                    if let Some(stem) = path.file_stem().and_then(|s| s.to_str()) {
                                                                        // Remove .tag suffix if present (e.g., "budget.tag" -> "budget")
                                                                        let tag_name = stem.strip_suffix(".tag").unwrap_or(stem);
                                                                        match fs::read_to_string(&path) {
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
                                                        output.insert("tags".to_string(), serde_json::Value::Object(matched_tags));
                                                    }
                                                }
                                            }
                                        }
                                    }
                                    
                                    output.insert("sources".to_string(), serde_json::Value::Object(sources));
                                    
                                    // Extract timestamp from sources.log path (after "logs/" and before "_")
                                    // Do this after sources is inserted so we can use the final sources.log value
                                    let timestamp = extract_timestamp_from_path(&source_path_str);
                                    if let Some(ref ts) = timestamp {
                                        output.insert("timestamp".to_string(), serde_json::Value::String(ts.clone()));
                                    }
                                    
                                    let mut output_value = serde_json::Value::Object(output);
                                    
                                    // Apply select transformation if requested
                                    if select == "default" {
                                        // Select specific keys from nested objects, preserving structure
                                        let mut selected_output = serde_json::Map::new();
                                        
                                        // Top: id (from log.bill_id), then log object with selected fields
                                        if let Some(id) = output_value.get("log").and_then(|l| l.get("bill_id").or_else(|| l.get("bill_identifier"))).and_then(|v| v.as_str()) {
                                            selected_output.insert("id".to_string(), serde_json::Value::String(id.to_string()));
                                        }
                                        
                                        // Create log object with only action and bill_id
                                        if let Some(log) = output_value.get("log") {
                                            let mut log_obj = serde_json::Map::new();
                                            if let Some(action) = log.get("action") {
                                                log_obj.insert("action".to_string(), action.clone());
                                            }
                                            if let Some(bill_id) = log.get("bill_id").or_else(|| log.get("bill_identifier")) {
                                                log_obj.insert("bill_id".to_string(), bill_id.clone());
                                            }
                                            if !log_obj.is_empty() {
                                                selected_output.insert("log".to_string(), serde_json::Value::Object(log_obj));
                                            }
                                        }
                                        
                                        // Create bill object with only selected fields
                                        if let Some(bill) = output_value.get("bill") {
                                            let mut bill_obj = serde_json::Map::new();
                                            if let Some(title) = bill.get("title") {
                                                bill_obj.insert("title".to_string(), title.clone());
                                            }
                                            if let Some(abstracts) = bill.get("abstracts") {
                                                bill_obj.insert("abstracts".to_string(), abstracts.clone());
                                            }
                                            if let Some(subject) = bill.get("subject") {
                                                bill_obj.insert("subject".to_string(), subject.clone());
                                            }
                                            if let Some(identifier) = bill.get("identifier") {
                                                bill_obj.insert("identifier".to_string(), identifier.clone());
                                            }
                                            if let Some(session) = bill.get("legislative_session") {
                                                bill_obj.insert("legislative_session".to_string(), session.clone());
                                            }
                                            if let Some(org) = bill.get("from_organization") {
                                                bill_obj.insert("from_organization".to_string(), org.clone());
                                            }
                                            if !bill_obj.is_empty() {
                                                selected_output.insert("bill".to_string(), serde_json::Value::Object(bill_obj));
                                            }
                                        }
                                        
                                        // Always include tags (even if empty/null) since it's part of the default selector
                                        if let Some(tags) = output_value.get("tags") {
                                            selected_output.insert("tags".to_string(), tags.clone());
                                        } else {
                                            // Include empty tags object if not present
                                            selected_output.insert("tags".to_string(), serde_json::Value::Null);
                                        }
                                        
                                        // Bottom: sources, timestamp
                                        if let Some(sources) = output_value.get("sources") {
                                            selected_output.insert("sources".to_string(), sources.clone());
                                        }
                                        if let Some(timestamp) = output_value.get("timestamp") {
                                            selected_output.insert("timestamp".to_string(), timestamp.clone());
                                        }
                                        
                                        output_value = serde_json::Value::Object(selected_output);
                                    }
                                    
                                    // Apply filter
                                    let should_output = match filter_manager.should_keep(&output_value, &repo_name) {
                                        govbot::FilterResult::Keep => true,
                                        govbot::FilterResult::FilterOut => false,
                                    };
                                    
                                    if should_output {
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
                                                eprintln!("Error serializing JSON from {}: {}", path.display(), e);
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
fn extract_json_field(value: &serde_json::Value, field_path: &[String]) -> Option<serde_json::Value> {
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

/// Compute relative path from git_dir to a file, following symlinks
fn compute_relative_source_path(file_path: &PathBuf, git_dir: &PathBuf) -> String {
    // Canonicalize the file path to follow symlinks
    let canonical_file = match file_path.canonicalize() {
        Ok(p) => p,
        Err(_) => file_path.clone(),
    };
    
    // Canonicalize git_dir for proper relative path calculation
    let canonical_git_dir = match git_dir.canonicalize() {
        Ok(p) => p,
        Err(_) => git_dir.clone(),
    };
    
    // Get relative path from git_dir to the file
    match pathdiff::diff_paths(&canonical_file, &canonical_git_dir) {
        Some(rel_path) => rel_path.to_string_lossy().replace('\\', "/"),
        None => {
            // Fallback: use path relative to git_dir directly
            pathdiff::diff_paths(file_path, git_dir)
                .map(|p| p.to_string_lossy().replace('\\', "/"))
                .unwrap_or_else(|| file_path.to_string_lossy().replace('\\', "/"))
        }
    }
}

async fn run_load_command(cmd: Command) -> anyhow::Result<()> {
    let Command::Load {
        database,
        govbot_dir,
        memory_limit,
        threads,
    } = cmd else {
        unreachable!()
    };

    let repos_dir = get_govbot_dir(govbot_dir)?;

    // Check if directory exists
    if !repos_dir.exists() {
        eprintln!("Error: Govbot repos directory not found: {}", repos_dir.display());
        eprintln!("Run 'govbot clone all' first to clone repositories.");
        return Ok(());
    }

    // Get base govbot directory (parent of repos)
    // e.g., if repos_dir is ./.govbot/repos, base_dir is ./.govbot
    let base_govbot_dir = repos_dir.parent()
        .ok_or_else(|| anyhow::anyhow!("Could not determine base govbot directory"))?;
    
    // Ensure base directory exists
    std::fs::create_dir_all(base_govbot_dir)?;

    // Check if duckdb is available
    let duckdb_check = ProcessCommand::new("duckdb")
        .arg("--version")
        .output();

    if duckdb_check.is_err() {
        eprintln!("Error: 'duckdb' command not found.");
        eprintln!("Please install DuckDB: https://duckdb.org/docs/installation/");
        return Ok(());
    }

    // Database file goes in the base govbot directory
    // Resolve to absolute path to ensure it's created in the right location
    let db_path = base_govbot_dir.canonicalize()
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
    sql_script.push_str(&format!("FROM read_json_auto('{}/**/bills/*/metadata.json', \n", repos_dir_str));
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
    let country_end = path[country_start + 8..].find('/').unwrap_or(path.len() - country_start - 8);
    let country = path[country_start + 8..country_start + 8 + country_end].to_string();
    
    // Find state: pattern
    let state_start = path.find("/state:")?;
    let state_end = path[state_start + 7..].find('/').unwrap_or(path.len() - state_start - 7);
    let state = path[state_start + 7..state_start + 7 + state_end].to_string();
    
    // Find sessions/ pattern
    let sessions_start = path.find("/sessions/")?;
    let session_end = path[sessions_start + 10..].find('/').unwrap_or(path.len() - sessions_start - 10);
    let session_id = path[sessions_start + 10..sessions_start + 10 + session_end].to_string();
    
    Some((country, state, session_id))
}

/// Download a file from a URL to a local path
fn download_file(url: &str, path: &std::path::Path) -> anyhow::Result<()> {
    eprintln!("Downloading {}...", url);
    let response = reqwest::blocking::get(url)?;
    if !response.status().is_success() {
        return Err(anyhow::anyhow!("Failed to download {}: HTTP {}", url, response.status()));
    }
    let mut file = std::fs::File::create(path)?;
    std::io::copy(&mut response.bytes()?.as_ref(), &mut file)?;
    Ok(())
}

/// Ensure embedding model and tokenizer exist; if missing, download them from Hugging Face.
/// Returns true if files are present/ready, false otherwise.
fn ensure_embedding_files(model_dir: &std::path::Path) -> bool {
    let model_path = model_dir.join("model.onnx");
    let tokenizer_path = model_dir.join("tokenizer.json");
    let _vocab_path = model_dir.join("vocab.txt");

    if model_path.exists() && tokenizer_path.exists() {
        return true;
    }

    eprintln!("Embedding files not found. Downloading all-MiniLM-L6-v2 (ONNX) to {}...", model_dir.display());

    // Use Xenova ONNX exports
    let onnx_url = "https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main/onnx/model.onnx";
    let tokenizer_url = "https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main/tokenizer.json";

    // Download tokenizer.json
    if !tokenizer_path.exists() {
        if let Err(e) = download_file(tokenizer_url, &tokenizer_path) {
            eprintln!("Failed to download tokenizer.json: {}", e);
            return false;
        }
    }

    // Download ONNX model
    if !model_path.exists() {
        if let Err(e) = download_file(onnx_url, &model_path) {
            eprintln!("Failed to download ONNX model: {}", e);
            return false;
        }
    }

    if !model_path.exists() || !tokenizer_path.exists() {
        eprintln!(
            "Download completed but model.onnx or tokenizer.json not found in {}",
            model_dir.display()
        );
        return false;
    }

    eprintln!("✅ Successfully downloaded embedding files!");
    true
}

/// Tag result structure: (tag_key, score_breakdown)
type TagResult = (String, govbot::ScoreBreakdown);

/// Check if a bill is already tagged in tag file(s) for the given session
/// If tag_name is Some, only checks that specific tag file
/// Returns a list of tag names that contain this bill
fn check_existing_tags(
    tags_dir: &PathBuf,
    bill_id: &str,
    tag_name: Option<&str>,
) -> anyhow::Result<Vec<String>> {
    let mut matched_tags = Vec::new();
    
    if !tags_dir.exists() {
        return Ok(matched_tags);
    }
    
    // If a specific tag is requested, only check that tag file
    if let Some(requested_tag) = tag_name {
        let tag_path = tags_dir.join(format!("{}.tag.json", requested_tag));
        if tag_path.exists() {
            match fs::read_to_string(&tag_path) {
                Ok(contents) => {
                    if let Ok(tag_file) = serde_json::from_str::<TagFile>(&contents) {
                        if tag_file.bills.contains_key(bill_id) {
                            matched_tags.push(requested_tag.to_string());
                        }
                    }
                }
                Err(_) => {
                    // Tag file exists but can't be read - return empty
                }
            }
        }
        return Ok(matched_tags);
    }
    
    // Otherwise, scan all .tag.json files in the tags directory
    for entry in fs::read_dir(tags_dir)? {
        let entry = entry?;
        let path = entry.path();
        
        if let Some(ext) = path.extension() {
            if ext == "json" {
                if let Some(stem) = path.file_stem().and_then(|s| s.to_str()) {
                    // Remove .tag suffix if present (e.g., "budget.tag" -> "budget")
                    let tag_name = stem.strip_suffix(".tag").unwrap_or(stem);
                    
                    match fs::read_to_string(&path) {
                        Ok(contents) => {
                            if let Ok(tag_file) = serde_json::from_str::<TagFile>(&contents) {
                                // Check if bill_id exists in bills map
                                if tag_file.bills.contains_key(bill_id) {
                                    matched_tags.push(tag_name.to_string());
                                }
                            }
                        }
                        Err(_) => {
                            // Skip files that can't be read
                            continue;
                        }
                    }
                }
            }
        }
    }
    
    Ok(matched_tags)
}

async fn run_tag_command(cmd: Command) -> anyhow::Result<()> {
    let Command::Tag {
        tag_name,
        output_dir,
        govbot_dir,
        overwrite,
    } = cmd else {
        unreachable!()
    };

    // Check if govbot.yml exists in current directory
    let current_dir = std::env::current_dir()?;
    let default_tags_cfg = current_dir.join("govbot.yml");

    // Model/tokenizer directory: prefer user-specified govbot-dir or env GOVBOT_DIR, else default .govbot
    let model_dir: PathBuf = if let Some(ref dir) = govbot_dir {
        PathBuf::from(dir)
    } else if let Ok(dir) = std::env::var("GOVBOT_DIR") {
        PathBuf::from(dir)
    } else {
        current_dir.join(".govbot")
    };
    fs::create_dir_all(&model_dir)?;
    let model_path = model_dir.join("model.onnx");
    let tokenizer_path = model_dir.join("tokenizer.json");
    
    // Require govbot.yml
    if !default_tags_cfg.exists() {
        return Err(anyhow::anyhow!(
            "govbot.yml not found in current directory"
        ));
    }

    // Load tag definitions (needed for both embedding and keyword fallback)
    let tag_defs = govbot::embeddings::load_tags_config(&default_tags_cfg)
        .map_err(|e| anyhow::anyhow!("Failed to parse govbot.yml: {}", e))?;

    // Try embedding mode first
    let embedding_matcher = if ensure_embedding_files(&model_dir) {
        let tags_path = default_tags_cfg.clone();

        eprintln!("Using embedding mode:");
        eprintln!("  Model: {}", model_path.display());
        eprintln!("  Tokenizer: {}", tokenizer_path.display());
        eprintln!("  Tags config: {}", tags_path.display());

        match TagMatcher::from_files(&model_path, &tokenizer_path, &tags_path) {
            Ok(matcher) => Some(matcher),
            Err(e) => {
                eprintln!("Warning: Failed to initialize embedding matcher: {}", e);
                eprintln!("Falling back to keyword-based matching.");
                None
            }
        }
    } else {
        eprintln!("Embedding files not available; using keyword-based matching.");
        eprintln!("  Tags config: {}", default_tags_cfg.display());
        None
    };
    
    // Determine output directory
    // If govbot.yml exists, use its directory as the base output directory
    let base_output_dir = if default_tags_cfg.exists() {
        // Use the directory containing govbot.yml
        default_tags_cfg.parent()
            .unwrap_or(&current_dir)
            .to_path_buf()
    } else if let Some(ref dir) = output_dir {
        PathBuf::from(dir)
    } else if let Some(ref dir) = govbot_dir {
        PathBuf::from(dir)
    } else if let Ok(dir) = std::env::var("GOVBOT_DIR") {
        PathBuf::from(dir)
    } else {
        // Default to current directory
        current_dir
    };
    
    // Read JSON lines from stdin
    let stdin = io::stdin();
    let reader = BufReader::new(stdin.lock());
    
    let mut processed_count = 0;
    let mut skipped_count = 0;
    let mut read_count: usize = 0;
    
    eprintln!("Reading JSON lines from stdin...");
    
    for line_result in reader.lines() {
        let line = line_result?;
        let line = line.trim();
        if line.is_empty() {
            read_count += 1;
            if read_count % 100 == 0 {
                eprintln!("Read {} lines (processed {}, skipped {})...", read_count, processed_count, skipped_count);
            }
            continue;
        }
        
        read_count += 1;
        // Parse JSON line (assumes default selector format)
        match serde_json::from_str::<serde_json::Value>(line) {
            Ok(json_value) => {
                // Extract bill_id from top-level "id" field (default selector format)
                let bill_id_opt = json_value
                    .get("id")
                    .and_then(|id| id.as_str());

                // Extract text from JSON for embedding comparison
                let bill_text = ocd_files_select_default(&json_value);
                
                // Extract path info from sources.log (default selector format)
                let path_info = json_value
                    .get("sources")
                    .and_then(|sources| sources.get("log"))
                    .and_then(|path| path.as_str())
                    .and_then(|log_path| extract_path_info(log_path))
                    .or_else(|| {
                        // Fallback: use default values if we can't determine
                        Some(("us".to_string(), "unknown".to_string(), "unknown".to_string()))
                    });

                // Process if we have path info (from sources.log in default selector format)
                if let Some((country, state, session_id)) = path_info {
                    // Get bill_id - use "id" from default selector, or generate from text hash if missing
                    let bill_id = bill_id_opt.map(|s| s.to_string()).unwrap_or_else(|| {
                        let text_hash = hash_text(&bill_text);
                        format!("entry_{}", &text_hash[..8])
                    });
                    
                    // Determine tags directory
                    let tags_dir = base_output_dir
                        .join(&format!("country:{}", country))
                        .join(&format!("state:{}", state))
                        .join("sessions")
                        .join(&session_id)
                        .join("tags");
                    
                    // Validate tag_name if provided
                    if let Some(ref requested_tag) = tag_name {
                        if !tag_defs.iter().any(|td| td.name == *requested_tag) {
                            return Err(anyhow::anyhow!(
                                "Tag '{}' not found in govbot.yml. Available tags: {}",
                                requested_tag,
                                tag_defs.iter().map(|td| td.name.clone()).collect::<Vec<_>>().join(", ")
                            ));
                        }
                    }
                    
                    // Fast path: check if bill is already tagged (unless overwrite is set)
                    let mut matched_tags: Vec<String> = Vec::new();
                    let mut should_run_tagging = overwrite;
                    
                    if !overwrite {
                        match check_existing_tags(&tags_dir, &bill_id, tag_name.as_deref()) {
                            Ok(existing_tags) => {
                                if !existing_tags.is_empty() {
                                    // Bill is already tagged - output the line and skip tagging
                                    matched_tags = existing_tags;
                                    should_run_tagging = false;
                                } else {
                                    // Bill not found in tag file(s) - need to run tagging
                                    should_run_tagging = true;
                                }
                            }
                            Err(e) => {
                                // Error checking tags - run tagging to be safe
                                eprintln!("Warning: Error checking existing tags for {}: {}", bill_id, e);
                                should_run_tagging = true;
                            }
                        }
                    }
                    
                    // Run tagging logic if needed
                    if should_run_tagging {
                        // Choose strategy based on mode
                        let mut tags: Vec<TagResult> = if let Some(matcher) = embedding_matcher.as_ref() {
                            match matcher.match_json_value(&json_value) {
                                Ok(results) => results,
                                Err(e) => {
                                    eprintln!("Error running embedding matcher for bill {}: {}", bill_id, e);
                                    eprintln!("Falling back to keyword-based matching for this entry.");
                                    // Fall back to keyword matching for this entry
                                    govbot::embeddings::match_tags_keywords(&tag_defs, &json_value)
                                }
                            }
                        } else {
                            // Use keyword-based fallback matcher
                            govbot::embeddings::match_tags_keywords(&tag_defs, &json_value)
                        };
                        
                        // Filter to specific tag if requested
                        if let Some(ref requested_tag) = tag_name {
                            tags.retain(|(tag, _)| tag == requested_tag);
                        }
                        
                        // Extract tag names from results
                        matched_tags = tags.iter().map(|(tag_name, _)| tag_name.clone()).collect();
                        
                        // Save tags to files if we found matches
                        if !tags.is_empty() {
                            let text_hash = hash_text(&bill_text);
                            
                            // Write per-tag files immediately
                            fs::create_dir_all(&tags_dir)?;

                            // Get current timestamp for metadata
                            let now = chrono::Utc::now().to_rfc3339();
                            let model_path_str = if embedding_matcher.is_some() {
                                model_path.to_string_lossy().to_string()
                            } else {
                                "keyword-fallback".to_string()
                            };

                            for (tag_key, score_breakdown) in tags {
                                let tag_path = tags_dir.join(format!("{}.tag.json", tag_key));

                                // Load or create TagFile structure
                                let mut tag_file: TagFile = if tag_path.exists() {
                                        match fs::read_to_string(&tag_path) {
                                            Ok(contents) => {
                                                serde_json::from_str(&contents).unwrap_or_else(|_| {
                                                    // If parsing fails, create a new TagFile
                                                    let tag_def = tag_defs
                                                        .iter()
                                                        .find(|td| td.name == tag_key)
                                                        .cloned()
                                                        .unwrap_or_else(|| govbot::TagDefinition {
                                                            name: tag_key.clone(),
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
                                                            last_run: now.clone(),
                                                            model: model_path_str.clone(),
                                                            tag_config_hash,
                                                        },
                                                        tag_config: tag_def,
                                                        text_cache: HashMap::new(),
                                                        bills: HashMap::new(),
                                                    }
                                                })
                                            }
                                            Err(_) => {
                                                // Create new TagFile
                                                let tag_def = tag_defs
                                                    .iter()
                                                    .find(|td| td.name == tag_key)
                                                    .cloned()
                                                    .unwrap_or_else(|| govbot::TagDefinition {
                                                        name: tag_key.clone(),
                                                        description: String::new(),
                                                        examples: Vec::new(),
                                                        include_keywords: Vec::new(),
                                                        exclude_keywords: Vec::new(),
                                                        negative_examples: Vec::new(),
                                                        threshold: 0.5,
                                                    });
                                                
                                                let tag_config_hash = hash_text(&serde_json::to_string(&tag_def)?);
                                                
                                                TagFile {
                                                    metadata: TagFileMetadata {
                                                        last_run: now.clone(),
                                                        model: model_path_str.clone(),
                                                        tag_config_hash,
                                                    },
                                                    tag_config: tag_def,
                                                    text_cache: HashMap::new(),
                                                    bills: HashMap::new(),
                                                }
                                            }
                                        }
                                    } else {
                                        // Create new TagFile
                                        let tag_def = tag_defs
                                            .iter()
                                            .find(|td| td.name == tag_key)
                                            .cloned()
                                            .unwrap_or_else(|| govbot::TagDefinition {
                                                name: tag_key.clone(),
                                                description: String::new(),
                                                examples: Vec::new(),
                                                include_keywords: Vec::new(),
                                                exclude_keywords: Vec::new(),
                                                negative_examples: Vec::new(),
                                                threshold: 0.5,
                                            });
                                        
                                        let tag_config_hash = hash_text(&serde_json::to_string(&tag_def)?);
                                        
                                        TagFile {
                                            metadata: TagFileMetadata {
                                                last_run: now.clone(),
                                                model: model_path_str.clone(),
                                                tag_config_hash,
                                            },
                                            tag_config: tag_def,
                                            text_cache: HashMap::new(),
                                            bills: HashMap::new(),
                                        }
                                    };

                                // Update metadata
                                tag_file.metadata.last_run = now.clone();
                                tag_file.metadata.model = model_path_str.clone();
                                
                                // Update tag config if it changed
                                let current_tag_def = tag_defs
                                    .iter()
                                    .find(|td| td.name == tag_key)
                                    .cloned()
                                    .unwrap_or_else(|| tag_file.tag_config.clone());
                                
                                let current_config_hash = hash_text(&serde_json::to_string(&current_tag_def)?);
                                if current_config_hash != tag_file.metadata.tag_config_hash {
                                    tag_file.tag_config = current_tag_def;
                                    tag_file.metadata.tag_config_hash = current_config_hash;
                                }
                                
                                // Add text to cache if not present
                                if !tag_file.text_cache.contains_key(&text_hash) {
                                    tag_file.text_cache.insert(text_hash.clone(), bill_text.clone());
                                }
                                
                                // Add/update bill result
                                tag_file.bills.insert(bill_id.to_string(), BillTagResult {
                                    text_hash: text_hash.clone(),
                                    score: score_breakdown,
                                });

                                // Write updated TagFile
                                let json_string = serde_json::to_string_pretty(&tag_file)?;
                                fs::write(&tag_path, json_string)?;
                            }
                        }
                    }
                    
                    // Output the line if it matches tags (filter mode)
                    // If a specific tag was requested, only output if that tag matches
                    // Otherwise, output if any tag matches
                    let should_output = if let Some(ref requested_tag) = tag_name {
                        matched_tags.contains(requested_tag)
                    } else {
                        !matched_tags.is_empty()
                    };
                    
                    if should_output {
                        write_json_line(line)?;
                    }
                    
                    processed_count += 1;
                    if processed_count % 50 == 0 {
                        eprintln!("Processed {} entries (matched: {} tags)...", processed_count, matched_tags.len());
                    }
                } else {
                    // No path info - skip this entry (default selector should always provide sources.log)
                    skipped_count += 1;
                }
            }
            Err(_e) => {
                // Skip malformed/empty lines quietly
                skipped_count += 1;
            }
        }

        if read_count % 100 == 0 {
            eprintln!("Read {} lines (processed {}, skipped {})...", read_count, processed_count, skipped_count);
        }
    }
    
    eprintln!("\nProcessed: {}, Skipped: {}", processed_count, skipped_count);
    eprintln!("\n✅ Tagging complete!");
    
    Ok(())
}

async fn run_init_command(cmd: Command) -> anyhow::Result<()> {
    let Command::Init { force } = cmd else {
        unreachable!()
    };
    
    let cwd = std::env::current_dir()?;
    
    // Create govbot.yml
    let govbot_yml_path = cwd.join("govbot.yml");
    if govbot_yml_path.exists() && !force {
        eprintln!("⚠️  govbot.yml already exists. Use --force to overwrite.");
    } else {
        let govbot_yml_content = r#"# Govbot Configuration
# Schema: https://raw.githubusercontent.com/windy-civi/toolkit/main/schemas/govbot.schema.json
$schema: https://raw.githubusercontent.com/windy-civi/toolkit/main/schemas/govbot.schema.json

repos:
  - all

tags:
  education:
    description: |
      Legislation related to schools, education funding, curriculum standards, and educational policy, including:
      - K-12 public school funding, budgets, and resource allocation
      - Curriculum standards, content requirements, and academic programs
      - Teacher certification, training, professional development, and compensation
      - Higher education policy, tuition, financial aid, and student loans
      - Charter schools, school choice, vouchers, and alternative education models
      - Special education services, accommodations, and individualized education plans
      - School safety, security measures, and student discipline policies
      - Early childhood education, pre-K programs, and childcare
      - Standardized testing, assessments, and accountability measures
      - School district governance, administration, and oversight
      - Educational technology, digital learning, and online education
      - Career and technical education, vocational training, and workforce development
    examples:
      - "Increases per-pupil funding for public schools and establishes minimum teacher salary requirements"
      - "Mandates comprehensive sex education curriculum in all public schools"
      - "Expands eligibility for state financial aid programs to include part-time students"

publish:
  base_url: "https://yourusername.github.io/your-repo-name"
  output_dir: "feeds"
  output_file: "feed.xml"
  # Optional: limit number of entries (default: 15, use "none" for all)
  # limit: 15
"#;
        fs::write(&govbot_yml_path, govbot_yml_content)?;
        println!("✓ Created govbot.yml");
    }
    
    // Create or update .gitignore
    let gitignore_path = cwd.join(".gitignore");
    let gitignore_entry = ".govbot\n";
    
    if gitignore_path.exists() {
        let mut content = fs::read_to_string(&gitignore_path)?;
        if content.contains(".govbot") {
            println!("✓ .gitignore already contains .govbot");
        } else {
            // Add .govbot if not present
            if !content.ends_with('\n') {
                content.push('\n');
            }
            content.push_str(gitignore_entry);
            fs::write(&gitignore_path, content)?;
            println!("✓ Updated .gitignore to include .govbot");
        }
    } else {
        fs::write(&gitignore_path, gitignore_entry)?;
        println!("✓ Created .gitignore with .govbot");
    }
    
    // Create GitHub Actions workflow
    let workflows_dir = cwd.join(".github").join("workflows");
    fs::create_dir_all(&workflows_dir)?;
    
    let workflow_path = workflows_dir.join("publish-rss.yml");
    if workflow_path.exists() && !force {
        eprintln!("⚠️  .github/workflows/publish-rss.yml already exists. Use --force to overwrite.");
    } else {
        let workflow_content = r#"# Run Govbot
# Runs govbot to tag bills, push tags, and publish to endpoints.

name: Publish Govbot

on:
  push:
    branches:
      - main
      - master
  schedule:
    - cron: '0 0 * * *'
  workflow_dispatch:
    inputs:
      tags:
        description: 'Comma-separated list of tags to include (leave empty for all tags)'
        required: false
        type: string
      limit:
        description: 'Limit number of entries per feed (default: 15, use "none" for all)'
        required: false
        type: string

jobs:
  govbot:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pages: write
      id-token: write
    
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
      
      - name: Run Govbot
        uses: windy-civi/toolkit/actions/govbot@main
        with:
          tags: ${{ inputs.tags }}
          limit: ${{ inputs.limit }}
"#;
        fs::write(&workflow_path, workflow_content)?;
        println!("✓ Created .github/workflows/publish-rss.yml");
    }
    
    println!("\n✅ Govbot project initialized!");
    println!("\nNext steps:");
    println!("  1. Edit govbot.yml to customize tags and publish settings");
    println!("  2. Update the base_url in govbot.yml to match your GitHub Pages URL");
    println!("  3. Run 'govbot clone' to download legislation repositories");
    println!("  4. Push to GitHub - the workflow will automatically:");
    println!("     - Tag bills and commit/push tag files to the repository");
    println!("     - Generate and publish RSS feeds to GitHub Pages");
    
    Ok(())
}

async fn run_publish_command(cmd: Command) -> anyhow::Result<()> {
    let Command::Publish {
        tags,
        limit,
        output_dir,
        output_file,
        govbot_dir,
    } = cmd else {
        unreachable!()
    };
    
    // Check if govbot.yml exists in current directory
    let current_dir = std::env::current_dir()?;
    let config_path = current_dir.join("govbot.yml");
    
    if !config_path.exists() {
        return Err(anyhow::anyhow!("govbot.yml not found in current directory"));
    }
    
    // Load configuration
    let config = load_config(&config_path)?;
    
    // Get tags configuration
    let tags_config = config.get("tags")
        .and_then(|t| t.as_object())
        .ok_or_else(|| anyhow::anyhow!("No tags found in configuration"))?;
    
    // Determine which tags to use
    let tags_to_use: Vec<String> = if tags.is_empty() {
        // Use tags from publish config, or all tags
        if let Some(publish_tags) = config.get("publish")
            .and_then(|p| p.get("tags"))
            .and_then(|t| t.as_array())
        {
            publish_tags
                .iter()
                .filter_map(|v| v.as_str().map(|s| s.to_string()))
                .collect()
        } else {
            tags_config.keys().cloned().collect()
        }
    } else {
        tags
    };
    
    // Validate tags exist
    for tag in &tags_to_use {
        if !tags_config.contains_key(tag) {
            return Err(anyhow::anyhow!("Tag '{}' not found in configuration", tag));
        }
    }
    
    if tags_to_use.is_empty() {
        return Err(anyhow::anyhow!("No valid tags to process"));
    }
    
    // Get publish configuration
    let publish_config = config.get("publish").and_then(|p| p.as_object());
    
    // Get output directory
    let output_dir_path = if let Some(dir) = output_dir {
        PathBuf::from(dir)
    } else {
        let dir_str = publish_config
            .and_then(|p| p.get("output_dir"))
            .and_then(|d| d.as_str())
            .unwrap_or("feeds");
        PathBuf::from(dir_str)
    };
    
    // Get output filename
    let output_filename = if let Some(file) = output_file {
        file
    } else {
        publish_config
            .and_then(|p| p.get("output_file"))
            .and_then(|f| f.as_str())
            .unwrap_or("feed.xml")
            .to_string()
    };
    
    // Get feed metadata
    let feed_title = publish_config
        .and_then(|p| p.get("title"))
        .and_then(|t| t.as_str())
        .map(|s| s.to_string())
        .unwrap_or_else(|| {
            format!("{} Legislation", tags_to_use.iter()
                .map(|t| t.replace('_', " ").split_whitespace()
                    .map(|w| {
                        let mut chars = w.chars();
                        match chars.next() {
                            None => String::new(),
                            Some(f) => f.to_uppercase().collect::<String>() + chars.as_str(),
                        }
                    })
                    .collect::<Vec<_>>()
                    .join(" "))
                .collect::<Vec<_>>()
                .join(" & "))
        });
    
    let feed_description = publish_config
        .and_then(|p| p.get("description"))
        .and_then(|d| d.as_str())
        .map(|s| s.to_string())
        .unwrap_or_else(|| {
            let mut descs = Vec::new();
            for tag_name in &tags_to_use {
                if let Some(tag_obj) = tags_config.get(tag_name).and_then(|t| t.as_object()) {
                    if let Some(desc) = tag_obj.get("description").and_then(|d| d.as_str()) {
                        let tag_title = tag_name.replace('_', " ").split_whitespace()
                            .map(|w| {
                                let mut chars = w.chars();
                                match chars.next() {
                                    None => String::new(),
                                    Some(f) => f.to_uppercase().collect::<String>() + chars.as_str(),
                                }
                            })
                            .collect::<Vec<_>>()
                            .join(" ");
                        descs.push(format!("{}: {}", tag_title, &desc[..desc.len().min(200)]));
                    }
                }
            }
            if descs.is_empty() {
                "Legislative updates".to_string()
            } else {
                descs.join(" | ")
            }
        });
    
    let feed_link = publish_config
        .and_then(|p| p.get("base_url"))
        .and_then(|u| u.as_str())
        .unwrap_or("https://example.com");
    
    let base_url = Some(feed_link);
    
    // Get repos
    let repos = get_repos_from_config(&config);
    
    // Get repos to process
    let repos_to_process: Vec<String> = if repos == vec!["all".to_string()] {
        Vec::new() // Empty means all repos
    } else {
        repos
    };
    
    // Get limit - parse "none" as no limit, otherwise parse as usize
    // Default to 15 (RSS standard) if not specified
    let limit_str_opt = limit.or_else(|| {
        publish_config
            .and_then(|p| p.get("limit"))
            .and_then(|l| {
                if let Some(s) = l.as_str() {
                    Some(s.to_string())
                } else if let Some(n) = l.as_u64() {
                    Some(n.to_string())
                } else {
                    None
                }
            })
    });
    
    let limit_value: Option<usize> = if let Some(limit_str) = limit_str_opt {
        if limit_str.to_lowercase() == "none" {
            None // No limit
        } else {
            limit_str.parse().ok()
        }
    } else {
        Some(15) // Default to 15 items (RSS standard)
    };
    
    // Run logs command and collect entries
    eprintln!("Collecting log entries for tags: {}", tags_to_use.join(", "));
    let mut entries = Vec::new();
    
    // Get the base govbot directory (not the repos subdirectory)
    // The logs command expects the base directory and will append /repos itself
    let base_govbot_dir = if let Some(ref gd) = govbot_dir {
        gd.clone()
    } else if let Ok(gd) = std::env::var("GOVBOT_DIR") {
        gd
    } else {
        // Default: $CWD/.govbot
        std::env::current_dir()
            .unwrap_or_else(|_| PathBuf::from("."))
            .join(".govbot")
            .to_string_lossy()
            .to_string()
    };
    
    // Call logs command as subprocess and parse JSON output
    // Use current executable (govbot binary)
    let exe = std::env::current_exe()
        .unwrap_or_else(|_| PathBuf::from("govbot"));
    
    let mut cmd = ProcessCommand::new(exe);
    cmd.arg("logs")
        .arg("--join")
        .arg("bill,tags")
        .arg("--select")
        .arg("default")
        .arg("--filter")
        .arg("default")
        .arg("--sort")
        .arg("DESC");
    
    // Only add --govbot-dir if it's not the default
    if !base_govbot_dir.is_empty() && base_govbot_dir != ".govbot" {
        cmd.arg("--govbot-dir").arg(&base_govbot_dir);
    }
    
    if !repos_to_process.is_empty() {
        cmd.arg("--repos");
        for repo in &repos_to_process {
            cmd.arg(repo);
        }
    }
    
    // Don't pass limit to logs command - we'll limit after filtering/sorting
    // This ensures we get the best entries, not just the first N from each repo
    
    let output = cmd.output()?;
    
    // Check return code
    if !output.status.success() {
        let stderr_str = String::from_utf8_lossy(&output.stderr);
        eprintln!("Error: logs command failed with exit code: {:?}", output.status.code());
        eprintln!("Stderr: {}", stderr_str);
        return Err(anyhow::anyhow!("Failed to collect log entries"));
    }
    
    // Check if there were any errors in stderr (but compilation messages are OK)
    if !output.stderr.is_empty() {
        let stderr_str = String::from_utf8_lossy(&output.stderr);
        // Filter out compilation messages
        let filtered_stderr: Vec<&str> = stderr_str
            .lines()
            .filter(|line| !line.contains("Compiling") && !line.contains("Finished"))
            .collect();
        if !filtered_stderr.is_empty() {
            eprintln!("Warning from logs command: {}", filtered_stderr.join("\n"));
        }
    }
    
    // Parse JSON lines from output
    let mut total_entries = 0;
    let mut filtered_entries = 0;
    let stdout_str = String::from_utf8_lossy(&output.stdout);
    
    if stdout_str.trim().is_empty() {
        eprintln!("Warning: logs command returned no output. Make sure repositories are cloned and contain log files.");
    }
    
    for line in stdout_str.lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        match serde_json::from_str::<serde_json::Value>(line) {
            Ok(entry) => {
                total_entries += 1;
                if filter_by_tags(&entry, &tags_to_use) {
                    entries.push(entry);
                    filtered_entries += 1;
                }
            }
            Err(e) => {
                // Skip invalid JSON lines (might be compilation output that leaked through)
                if !line.contains("Compiling") && !line.contains("Finished") {
                    eprintln!("Warning: Failed to parse JSON line: {}", e);
                }
            }
        }
    }
    
    if total_entries == 0 {
        eprintln!("Warning: No log entries found. Make sure repositories are cloned and contain log files.");
    } else if filtered_entries == 0 && !tags_to_use.is_empty() {
        eprintln!("Warning: Found {} entries but none matched the specified tags. Entries may not have tags yet - consider running 'govbot tag' first, or publish without --tags to include all entries.", total_entries);
    }
    
    // Deduplicate and sort
    entries = deduplicate_entries(entries);
    entries = sort_by_timestamp(entries);
    
    // Apply limit (default is 15, RSS standard)
    let original_count = entries.len();
    if let Some(lim) = limit_value {
        entries.truncate(lim);
        if original_count > lim {
            eprintln!("Limited feed to {} entries (RSS standard). Use --limit none to include all {} entries.", lim, original_count);
        }
    }
    
    // Generate RSS
    eprintln!("Generating RSS feed with {} entries...", entries.len());
    let rss_xml = rss::json_to_rss(
        entries,
        &feed_title,
        &feed_description,
        feed_link,
        base_url.as_deref(),
        "en-us",
        Some(&tags_to_use),
    );
    
    // Create output directory
    fs::create_dir_all(&output_dir_path)?;
    
    // Write RSS feed
    let output_path = output_dir_path.join(&output_filename);
    fs::write(&output_path, rss_xml)?;
    
    eprintln!("✓ Generated RSS feed: {}", output_path.display());
    eprintln!("  Tags included: {}", tags_to_use.join(", "));
    
    Ok(())
}

async fn run_update_command() -> anyhow::Result<()> {
    let install_script_url = "https://raw.githubusercontent.com/windy-civi/toolkit/main/actions/govbot/scripts/install-nightly.sh";
    
    eprintln!("🔄 Updating govbot to latest nightly version...");
    eprintln!("Downloading and running install script from: {}", install_script_url);
    
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
        return Err(anyhow::anyhow!("Update failed with exit code: {}", status.code().unwrap_or(-1)));
    }
    
    Ok(())
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let args = Args::parse();

    match args.command {
        Some(cmd @ Command::Clone { .. }) => {
            run_clone_command(cmd).await
        }
        Some(cmd @ Command::Delete { .. }) => {
            run_delete_command(cmd).await
        }
        Some(cmd @ Command::Logs { .. }) => {
            run_logs_command(cmd).await
        }
        Some(cmd @ Command::Load { .. }) => {
            run_load_command(cmd).await
        }
        Some(Command::Update) => {
            run_update_command().await
        }
        Some(cmd @ Command::Tag { .. }) => {
            run_tag_command(cmd).await
        }
        Some(cmd @ Command::Publish { .. }) => {
            run_publish_command(cmd).await
        }
        Some(cmd @ Command::Init { .. }) => {
            run_init_command(cmd).await
        }
        None => {
            print_available_commands();
            Ok(())
        }
    }
}
