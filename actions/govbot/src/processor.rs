use crate::config::Config;
use crate::error::{Error, Result};
use crate::git;
use crate::types::{
    FileWithTimestamp, LogContent, LogEntry, Metadata,
    VoteEventResult,
};
use crate::logs_jsonl::{self, LogKind, LogRecord};
use async_stream::stream;
use futures::Stream;
use jwalk::WalkDir;
use std::path::Path;

/// Main processor for pipeline log files
pub struct PipelineProcessor {
    config: Config,
}

impl PipelineProcessor {
    /// Create a new processor with the given configuration
    pub fn new(config: Config) -> Self {
        Self { config }
    }

    /// Process log files and return a reactive stream of log entries
    /// Uses jwalk for fast parallel filesystem traversal
    pub fn process(&self) -> impl Stream<Item = Result<LogEntry>> {
        let config = self.config.clone();
        let config_for_discovery = config.clone();
        Box::pin(stream! {
            // Step 1: Discover files (run in blocking thread pool for async compatibility)
            // jwalk is fast but synchronous, so we run it in spawn_blocking
            let files = match tokio::task::spawn_blocking(move || {
                Self::discover_files_internal(&config_for_discovery)
            }).await {
                Ok(Ok(files)) => files,
                Ok(Err(e)) => {
                    yield Err(e);
                    return;
                }
                Err(e) => {
                    yield Err(Error::Io(std::io::Error::new(
                        std::io::ErrorKind::Other,
                        format!("Task join error: {}", e)
                    )));
                    return;
                }
            };

            // Step 2: Sort files
            let sorted_files = Self::sort_files_internal(&config, files);

            // Step 3: Apply limit
            let limited_files = Self::apply_limit_internal(&config, sorted_files);

            // Step 4: Process each file and yield log entries
            for file in limited_files {
                match Self::process_file_internal(&config, &file).await {
                    Ok(Some(entry)) => yield Ok(entry),
                    Ok(None) => continue,
                    Err(e) => yield Err(e),
                }
            }
        })
    }

    /// Discover every bill log entry, in either layout (see `crate::logs_jsonl`).
    /// Uses jwalk for fast parallel filesystem traversal.
    fn discover_files_internal(config: &Config) -> Result<Vec<FileWithTimestamp>> {
        let mut files = Vec::new();
        let search_dir = &config.git_dir;

        // If repos are specified, search only in those directories
        let search_paths = if config.repos.is_empty() {
            vec![search_dir.clone()]
        } else {
            // Every repo folder of each locale (old repo + session pairs)
            config
                .repos
                .iter()
                .flat_map(|repo| git::repo_folders(repo))
                .map(|folder| search_dir.join(folder))
                .collect()
        };
        let shadowed = git::shadowed_session_dirs(search_dir);

        for search_path in search_paths {
            if !search_path.exists() {
                eprintln!("Warning: Expected repository directory does not exist: {}", search_path.display());
                continue;
            }

            for entry_result in WalkDir::new(&search_path).into_iter() {
                let entry = match entry_result {
                    Ok(e) => e,
                    Err(_) => continue,
                };
                // Real files only (jwalk doesn't follow symlinks): skips the old
                // sessions/{s}/logs/ symlinks to the bill-level files.
                if !entry.file_type().is_file() {
                    continue;
                }
                let path = entry.path();
                if git::is_shadowed(&path, &shadowed) {
                    continue;
                }
                let Some(records) = logs_jsonl::read_log_records(&path) else {
                    continue;
                };
                let relative_path = Self::calculate_relative_path(&path, search_dir)?;
                files.extend(records.into_iter().map(|record| Self::with_record(&path, &relative_path, record)));
            }
        }

        Ok(files)
    }

    /// One discovered entry. A `.jsonl` line's relative path gets `#{id}`, so each
    /// entry keeps its own stable name.
    fn with_record(path: &Path, relative_path: &str, record: LogRecord) -> FileWithTimestamp {
        FileWithTimestamp {
            path: path.to_path_buf(),
            timestamp: record.timestamp.clone(),
            relative_path: match &record.anchor {
                Some(id) => format!("{relative_path}#{id}"),
                None => relative_path.to_string(),
            },
            record: Some(record),
        }
    }

    /// Process files from stdin (one path per line)
    /// Useful for stdio pipelines: `find ... | govbot --stdin`
    pub fn process_from_stdin(
        config: &Config,
        paths: impl Iterator<Item = String>,
    ) -> impl Stream<Item = Result<LogEntry>> {
        let config = config.clone();
        Box::pin(stream! {
            let mut files_with_timestamps = Vec::new();

            // Collect and parse all paths from stdin
            for path_str in paths {
                let path = Path::new(&path_str);
                let is_real_file = std::fs::symlink_metadata(path).is_ok_and(|m| m.is_file());
                if !is_real_file {
                    continue;
                }
                let Some(records) = logs_jsonl::read_log_records(path) else {
                    continue;
                };

                // For stdin mode, use the path as-is or make it relative to git_dir
                let git_dir_str = config.git_dir.to_string_lossy();
                let relative_path = if path_str.starts_with(&*git_dir_str) {
                    path.strip_prefix(&config.git_dir)
                        .ok()
                        .map(|p| p.to_string_lossy().to_string())
                        .unwrap_or_else(|| path_str.clone())
                } else {
                    path_str.clone()
                };
                files_with_timestamps.extend(
                    records.into_iter().map(|record| Self::with_record(path, &relative_path, record)),
                );
            }

            // Sort files
            let sorted_files = Self::sort_files_internal(&config, files_with_timestamps);
            let limited_files = Self::apply_limit_internal(&config, sorted_files);

            // Process each file
            for file in limited_files {
                match Self::process_file_internal(&config, &file).await {
                    Ok(Some(entry)) => yield Ok(entry),
                    Ok(None) => continue,
                    Err(e) => yield Err(e),
                }
            }
        })
    }

    /// Calculate relative path from search directory
    fn calculate_relative_path(path: &Path, search_dir: &Path) -> Result<String> {
        let search_dir_abs = search_dir.canonicalize().map_err(|_| {
            Error::Path(format!("Failed to canonicalize search directory: {}", search_dir.display()))
        })?;
        
        let path_abs = path.parent()
            .ok_or_else(|| Error::Path(format!("Failed to get parent of path: {}", path.display())))?
            .canonicalize()
            .map_err(|_| {
                Error::Path(format!("Failed to canonicalize path: {}", path.display()))
            })?;

        let relative = pathdiff::diff_paths(&path_abs, &search_dir_abs)
            .ok_or_else(|| Error::Path("Failed to calculate relative path".to_string()))?;

        // Reconstruct the full relative path including the filename
        let filename = path.file_name()
            .ok_or_else(|| Error::Path(format!("Failed to get filename: {}", path.display())))?;
        
        Ok(relative.join(filename).to_string_lossy().to_string())
    }

    /// Sort files by timestamp according to sort order
    /// Uses relative_path as a secondary sort key to ensure deterministic ordering
    fn sort_files_internal(config: &Config, mut files: Vec<FileWithTimestamp>) -> Vec<FileWithTimestamp> {
        match config.sort_order {
            crate::config::SortOrder::Descending => {
                files.sort_by(|a, b| {
                    match (&a.timestamp, &b.timestamp) {
                        (Some(ts_a), Some(ts_b)) => {
                            // Primary sort: timestamp descending
                            let timestamp_cmp = ts_b.cmp(ts_a);
                            // Secondary sort: path ascending (for deterministic ordering when timestamps are equal)
                            if timestamp_cmp == std::cmp::Ordering::Equal {
                                a.relative_path.cmp(&b.relative_path)
                            } else {
                                timestamp_cmp
                            }
                        }
                        (Some(_), None) => std::cmp::Ordering::Less,
                        (None, Some(_)) => std::cmp::Ordering::Greater,
                        (None, None) => a.relative_path.cmp(&b.relative_path), // Sort by path when both have no timestamp
                    }
                });
            }
            crate::config::SortOrder::Ascending => {
                files.sort_by(|a, b| {
                    match (&a.timestamp, &b.timestamp) {
                        (Some(ts_a), Some(ts_b)) => {
                            // Primary sort: timestamp ascending
                            let timestamp_cmp = ts_a.cmp(ts_b);
                            // Secondary sort: path ascending (for deterministic ordering when timestamps are equal)
                            if timestamp_cmp == std::cmp::Ordering::Equal {
                                a.relative_path.cmp(&b.relative_path)
                            } else {
                                timestamp_cmp
                            }
                        }
                        (Some(_), None) => std::cmp::Ordering::Less,
                        (None, Some(_)) => std::cmp::Ordering::Greater,
                        (None, None) => a.relative_path.cmp(&b.relative_path), // Sort by path when both have no timestamp
                    }
                });
            }
        }
        files
    }

    /// Apply limit to files
    fn apply_limit_internal(config: &Config, files: Vec<FileWithTimestamp>) -> Vec<FileWithTimestamp> {
        if let Some(limit) = config.limit {
            files.into_iter().take(limit).collect()
        } else {
            files
        }
    }

    /// Turn one discovered entry into a log entry. A vote event carries just its
    /// result; anything else carries its full JSON.
    async fn process_file_internal(_config: &Config, file: &FileWithTimestamp) -> Result<Option<LogEntry>> {
        let record = match &file.record {
            Some(record) => record.clone(),
            None => {
                let Some(mut records) = logs_jsonl::read_log_records(&file.path) else {
                    return Ok(None);
                };
                if records.is_empty() {
                    return Ok(None);
                }
                records.remove(0)
            }
        };
        let log = match record.kind {
            LogKind::VoteEvent => LogContent::VoteEvent {
                result: VoteEventResult::from(record.value.get("result").and_then(|r| r.as_str()).unwrap_or("unknown")),
            },
            LogKind::Action => LogContent::Full(record.value),
        };
        Ok(Some(LogEntry {
            log,
            filename: file.relative_path.clone(),
        }))
    }

    /// Load metadata from metadata.json if it exists and join options require it
    /// Note: Currently not used since join_options are empty, but kept for potential future use
    #[allow(dead_code)]
    async fn load_metadata_if_needed(config: &Config, log_path: &Path) -> Result<Option<Metadata>> {
        // Check if we need metadata at all
        if config.join_options.is_empty() {
            return Ok(None);
        }

        // Find metadata.json one directory above the log file
        let metadata_path = log_path
            .parent()
            .and_then(|p| p.parent())
            .map(|p| p.join("metadata.json"));

        let metadata_path = match metadata_path {
            Some(p) => p,
            None => return Ok(None),
        };

        if !metadata_path.exists() {
            return Ok(None);
        }

        // Read and parse metadata
        let metadata_content = tokio::fs::read_to_string(&metadata_path).await?;
        let metadata: Metadata = serde_json::from_str(&metadata_content)?;

        Ok(Some(metadata))
    }
}

