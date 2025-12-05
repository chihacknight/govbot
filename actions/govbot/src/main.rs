use clap::{Parser, Subcommand};
use govbot::prelude::*;
use govbot::git;
use futures::StreamExt;
use futures::stream;
use std::io::{self, BufRead};
use std::path::PathBuf;
use serde_json;

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
    /// Clone or pull data pipeline repositories (default: all locales)
    /// Clones if repository doesn't exist, pulls if it does
    Clone {
        /// Locale names to clone/pull (e.g., usa, il, ca, or "all" for all locales). If not specified, processes all locales.
        #[arg(num_args = 0..)]
        locales: Vec<String>,

        /// Directory containing repositories (default: $HOME/.govbot/repos, or GOVBOT_DIR env var)
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

        /// List available locales instead of cloning/pulling
        #[arg(long)]
        list: bool,
    },

    /// Process and display pipeline log files
    Logs {
        /// Directory containing cloned repositories (default: $HOME/.govbot/repos, or GOVBOT_DIR env var)
        #[arg(long = "govbot-dir")]
        govbot_dir: Option<String>,


        /// Source names to filter (space-separated)
        #[arg(short, long, num_args = 0..)]
        sources: Vec<String>,

        /// Sort order: ASC or DESC
        #[arg(long, default_value = "DESC", value_parser = ["ASC", "DESC"])]
        sort: String,

        /// Limit number of results
        #[arg(long)]
        limit: Option<usize>,

        /// Join options: minimal_metadata,sponsors
        #[arg(long, default_value = "minimal_metadata")]
        join: String,

        /// Read file paths from stdin instead of discovering files
        /// Useful for stdio pipelines: find ... | govbot logs --stdin
        #[arg(long)]
        stdin: bool,
    },

    /// Delete data pipeline repositories
    /// Deletes local repository directories for specified locales
    Delete {
        /// Locale names to delete (e.g., usa, il, ca, or "all" for all locales). Use "all" to delete all repositories.
        #[arg(num_args = 0..)]
        locales: Vec<String>,

        /// Directory containing repositories (default: $HOME/.govbot/repos, or GOVBOT_DIR env var)
        #[arg(long = "govbot-dir")]
        govbot_dir: Option<String>,

        /// Number of parallel operations (default: 4, or GOVBOT_JOBS env var)
        #[arg(long)]
        parallel: Option<usize>,

        /// Show verbose output
        #[arg(long)]
        verbose: bool,
    },
}

fn print_available_commands() {
    println!("Available commands:");
    println!("  clone   Clone or pull data pipeline repositories (default: all locales)");
    println!("  delete  Delete data pipeline repositories (use 'delete all' to delete all)");
    println!("  logs    Process and display pipeline log files");
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
        // Fall back to default: $HOME/.govbot/repos
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
    locales_to_clone: Vec<String>,
    repos_dir: PathBuf,
    token_str: Option<&str>,
    num_jobs: usize,
    verbose: bool,
) -> anyhow::Result<Vec<CloneResult>> {
    let total = locales_to_clone.len();
    let mut all_results = Vec::new();
    
    if total == 1 || num_jobs == 1 {
        // Sequential clone/pull - print as we go
        for (idx, locale) in locales_to_clone.iter().enumerate() {
            let mut result = process_single_locale(locale, &repos_dir, token_str, verbose);
            result.position = format!("{}/{}", idx + 1, total);
            print_result(&result);
            all_results.push(result);
        }
    } else {
        // Parallel clone/pull - print as results come in
        use std::sync::{Arc, Mutex};
        let completed = Arc::new(Mutex::new(0usize));
        
        let clone_futures = stream::iter(locales_to_clone.iter())
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
        locales,
        govbot_dir,
        token,
        parallel,
        verbose,
        list,
    } = cmd else {
        unreachable!()
    };

    if list {
        println!("Available locales:");
        let all_locales = govbot::locale::WorkingLocale::all();
        for locale in all_locales {
            println!("  {}", locale.as_lowercase());
        }
        println!("  all (clone all locales)");
        return Ok(());
    }

    // If no locales specified, default to "all"
    let locales = if locales.is_empty() {
        vec!["all".to_string()]
    } else {
        locales
    };

    let repos_dir = get_govbot_dir(govbot_dir)?;
    
    // Create directory if it doesn't exist
    std::fs::create_dir_all(&repos_dir)?;

    // Get token from argument or environment variable
    let env_token = std::env::var("TOKEN").ok();
    let token_str = token.as_deref().or(env_token.as_deref());
    
    // Get parallelization setting
    let num_jobs = parallel
        .or_else(|| std::env::var("GOVBOT_JOBS").ok().and_then(|s| s.parse().ok()))
        .unwrap_or(4);

    // Parse locales and handle "all"
    let mut locales_to_clone = Vec::new();
    for locale in locales {
        let locale = locale.trim().to_lowercase();
        if locale.is_empty() {
            continue;
        }
        
        if locale == "all" {
            // Add all working locales
            let all_locales = govbot::locale::WorkingLocale::all();
            for loc in all_locales {
                locales_to_clone.push(loc.as_lowercase().to_string());
            }
        } else {
            // Validate locale
            let _ = govbot::locale::WorkingLocale::from(locale.as_str());
            locales_to_clone.push(locale);
        }
    }

    if locales_to_clone.is_empty() {
        return Ok(());
}

    // Print initial message with count
    eprintln!("🔁 Syncing {} repos\n", locales_to_clone.len());

    // Perform clone operations and print results as they complete
    let results = perform_clone_operations(
        locales_to_clone,
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
        eprintln!("\n✅ Successfully processed all {} locales!", results.len());
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
        sources,
        sort,
        limit,
        join,
        stdin,
    } = cmd else {
        unreachable!()
    };

    let git_dir = get_govbot_dir(govbot_dir)?;

    // Build configuration
    let mut builder = ConfigBuilder::new(&git_dir)
        .sort_order_str(&sort)?;

    if let Some(limit) = limit {
        builder = builder.limit(limit);
    }

    if !sources.is_empty() {
        builder = builder.sources(sources);
    }

    let config = builder.join_options_str(&join)?.build()?;

    let processor = PipelineProcessor::new(config.clone());

    if stdin {
        // Read paths from stdin (one per line)
        let stdin = io::stdin();
        let paths = stdin
            .lock()
            .lines()
            .filter_map(|line| line.ok())
            .filter(|line| !line.trim().is_empty());

        let mut stream = PipelineProcessor::process_from_stdin(&config, paths);

        // Write JSON to stdout (one per line)
        while let Some(result) = stream.next().await {
            match result {
                Ok(entry) => {
                    let json = serde_json::to_string(&entry)?;
                    println!("{}", json);
                }
                Err(e) => {
                    eprintln!("Error: {}", e);
                }
            }
        }
    } else {
        // Discover and process files from directory
        let mut stream = processor.process();

        // Write JSON to stdout (one per line)
        while let Some(result) = stream.next().await {
            match result {
                Ok(entry) => {
                    let json = serde_json::to_string(&entry)?;
                    println!("{}", json);
                }
                Err(e) => {
                    eprintln!("Error: {}", e);
                }
            }
        }
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
        None => {
            print_available_commands();
            Ok(())
        }
    }
}
