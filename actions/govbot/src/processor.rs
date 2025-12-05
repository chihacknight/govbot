use crate::config::{Config, JoinOption};
use crate::error::{Error, Result};
use crate::git;
use crate::types::{
    FileWithTimestamp, LogContent, LogEntry, Metadata, MinimalMetadata, Sponsors,
    VoteEventResult,
};
use async_stream::stream;
use futures::Stream;
use jwalk::WalkDir;
use regex::Regex;
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

    /// Discover all JSON files with 'logs/' in their path
    /// Uses jwalk for fast parallel filesystem traversal
    fn discover_files_internal(config: &Config) -> Result<Vec<FileWithTimestamp>> {
        let timestamp_regex = Regex::new(r"/logs/(\d{8}T\d{6}Z)_")?;
        let mut files = Vec::new();
        let search_dir = &config.git_dir;

        // If sources are specified, search only in those directories
        let search_paths = if config.sources.is_empty() {
            vec![search_dir.clone()]
        } else {
            config
                .sources
                .iter()
                .map(|source| search_dir.join(git::build_repo_name(source)))
                .collect()
        };

        for search_path in search_paths {
            if !search_path.exists() {
                eprintln!("Warning: Expected repository directory does not exist: {}", search_path.display());
                continue;
            }

            // Use jwalk for fast parallel traversal
            // jwalk uses rayon internally for parallel processing
            for entry_result in WalkDir::new(&search_path)
                .process_read_dir(|_depth, _path, _read_dir_state, _children| {
                    // Optional: customize directory reading behavior
                })
                .into_iter()
            {
                let entry = match entry_result {
                    Ok(e) => e,
                    Err(_) => continue,
                };

                if !entry.file_type().is_file() {
                    continue;
                }

                let path = entry.path();
                if let Some(ext) = path.extension() {
                    if ext == "json" {
                        let path_str = path.to_string_lossy();
                        if path_str.contains("/logs/") {
                            // Extract timestamp
                            let timestamp = timestamp_regex
                                .captures(&path_str)
                                .and_then(|caps| caps.get(1))
                                .map(|m| m.as_str().to_string());

                            // Calculate relative path
                            let relative_path = Self::calculate_relative_path(&path, search_dir)?;

                            files.push(FileWithTimestamp {
                                path: path.to_path_buf(),
                                timestamp,
                                relative_path,
                            });
                        }
                    }
                }
            }
        }

        Ok(files)
    }

    /// Process files from stdin (one path per line)
    /// Useful for stdio pipelines: `find ... | govbot --stdin`
    pub fn process_from_stdin(
        config: &Config,
        paths: impl Iterator<Item = String>,
    ) -> impl Stream<Item = Result<LogEntry>> {
        let config = config.clone();
        Box::pin(stream! {
            let timestamp_regex = match Regex::new(r"/logs/(\d{8}T\d{6}Z)_") {
                Ok(r) => r,
                Err(e) => {
                    yield Err(Error::Regex(e));
                    return;
                }
            };

            let mut files_with_timestamps = Vec::new();

            // Collect and parse all paths from stdin
            for path_str in paths {
                let path = Path::new(&path_str);
                if !path.exists() || !path.is_file() {
                    continue;
                }

                if path.extension().map(|e| e == "json").unwrap_or(false) {
                    let path_str_lossy = path.to_string_lossy();
                    if path_str_lossy.contains("/logs/") {
                        let timestamp = timestamp_regex
                            .captures(&path_str_lossy)
                            .and_then(|caps| caps.get(1))
                            .map(|m| m.as_str().to_string());

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

                        files_with_timestamps.push(FileWithTimestamp {
                            path: path.to_path_buf(),
                            timestamp,
                            relative_path,
                        });
                    }
                }
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

    /// Process a single file and return a log entry
    async fn process_file_internal(config: &Config, file: &FileWithTimestamp) -> Result<Option<LogEntry>> {
        // Check if it's a vote event file
        let is_vote_event = file.relative_path.contains(".vote_event.");

        if is_vote_event {
            Self::process_vote_event_file_internal(config, file).await
        } else {
            Self::process_regular_file_internal(config, file).await
        }
    }

    /// Process a vote event file
    async fn process_vote_event_file_internal(config: &Config, file: &FileWithTimestamp) -> Result<Option<LogEntry>> {
        // Extract vote event result from filename
        let vote_event_regex = Regex::new(r"\.vote_event\.([^.]+)\.")?;
        let result = vote_event_regex
            .captures(&file.relative_path)
            .and_then(|caps| caps.get(1))
            .map(|m| VoteEventResult::from(m.as_str()))
            .unwrap_or(VoteEventResult::Unknown);

        let log_content = LogContent::VoteEvent { result };

        // Try to load metadata if join options require it
        let metadata = Self::load_metadata_if_needed(config, &file.path).await?;

        let mut entry = LogEntry {
            log: log_content,
            filename: file.relative_path.clone(),
            minimal_metadata: None,
            sponsors: None,
        };

        // Apply join options
        if let Some(meta) = metadata {
            if config.join_options.contains(&JoinOption::MinimalMetadata) {
                entry.minimal_metadata = Some(MinimalMetadata {
                    title: meta.title,
                    description: meta.description,
                    sources: meta.sources,
                });
            }

            if config.join_options.contains(&JoinOption::Sponsors) {
                entry.sponsors = meta.sponsors.map(|sponsors| Sponsors { sponsors: Some(sponsors) });
            }
        }

        Ok(Some(entry))
    }

    /// Process a regular (non-vote-event) file
    async fn process_regular_file_internal(config: &Config, file: &FileWithTimestamp) -> Result<Option<LogEntry>> {
        // Read and parse JSON content
        let json_content = tokio::fs::read_to_string(&file.path).await?;
        let log_value: serde_json::Value = serde_json::from_str(&json_content)?;

        let log_content = LogContent::Full(log_value);

        // Try to load metadata if join options require it
        let metadata = Self::load_metadata_if_needed(config, &file.path).await?;

        let mut entry = LogEntry {
            log: log_content,
            filename: file.relative_path.clone(),
            minimal_metadata: None,
            sponsors: None,
        };

        // Apply join options
        if let Some(meta) = metadata {
            if config.join_options.contains(&JoinOption::MinimalMetadata) {
                entry.minimal_metadata = Some(MinimalMetadata {
                    title: meta.title,
                    description: meta.description,
                    sources: meta.sources,
                });
            }

            if config.join_options.contains(&JoinOption::Sponsors) {
                entry.sponsors = meta.sponsors.map(|sponsors| Sponsors { sponsors: Some(sponsors) });
            }
        }

        Ok(Some(entry))
    }

    /// Load metadata from metadata.json if it exists and join options require it
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

