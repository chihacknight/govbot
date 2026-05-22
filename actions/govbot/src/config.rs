use crate::error::{Error, Result};
use serde::Deserialize;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

// ============================================================
// govbot.yml — the project manifest (datasets / transforms /
// publish / pipelines). This is the typed view of the schema in
// `schemas/govbot.schema.json`. It is the layer-2 contract config
// and is distinct from the pipeline-processor `Config` below
// (whose `repos` is CLI-arg state, not manifest state).
// ============================================================

/// A `govbot.yml` manifest. `additionalProperties: false` in the schema —
/// an unknown top-level key (notably the retired `tags:`) fails to parse.
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Manifest {
    /// Optional `$schema` reference for editor autocomplete; ignored at runtime.
    #[serde(default, rename = "$schema")]
    pub schema: Option<String>,

    /// Government-data sources the project pulls and processes.
    pub datasets: Vec<String>,

    /// Named external-process transforms, keyed by name.
    #[serde(default)]
    pub transforms: BTreeMap<String, Transform>,

    /// Named publishers, keyed by name.
    #[serde(default)]
    pub publish: BTreeMap<String, Publisher>,

    /// Named `govbot run` targets — ordered lists of transform/publisher names.
    #[serde(default)]
    pub pipelines: BTreeMap<String, Vec<String>>,
}

/// A single external-process transform stage.
#[derive(Debug, Clone, Deserialize)]
pub struct Transform {
    /// The external process to run. Either a shell-style string or an argv array.
    pub command: Command_,

    /// The stream record kind this transform consumes (e.g. `docs`).
    pub reads: String,

    /// The stream record kind this transform produces (e.g. `classification`).
    pub writes: String,

    /// For a classify-style transform: the path to the fastclass classifier
    /// bundle directory. govbot passes this path through unchanged.
    #[serde(default)]
    pub classifier: Option<String>,
}

/// A transform `command`: either a single shell-style string or an argv array.
#[derive(Debug, Clone, Deserialize)]
#[serde(untagged)]
pub enum Command_ {
    /// A single string, split on whitespace into argv.
    Shell(String),
    /// An explicit argv array (first element is the executable).
    Argv(Vec<String>),
}

impl Command_ {
    /// Resolve to an argv vector. A `Shell` string is whitespace-split.
    pub fn argv(&self) -> Vec<String> {
        match self {
            Command_::Shell(s) => s.split_whitespace().map(|s| s.to_string()).collect(),
            Command_::Argv(v) => v.clone(),
        }
    }
}

/// The publisher kind. Mirrors `govbot.schema.json`'s `publisher.type` enum.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum PublisherKind {
    Rss,
    Html,
    Json,
    Duckdb,
    /// Bluesky publisher — the extension point for Wave 3 (not yet implemented).
    Bluesky,
}

/// A single publisher stage. Required fields depend on `type`.
#[derive(Debug, Clone, Deserialize)]
pub struct Publisher {
    /// The publisher kind (`rss` / `html` / `json` / `duckdb` / `bluesky`).
    #[serde(rename = "type")]
    pub kind: PublisherKind,

    /// Tag names to include. Only records carrying one of these tags are
    /// published; if omitted, all tagged records are published.
    #[serde(default)]
    pub select: Option<Vec<String>>,

    /// Base URL for generated links (required for `rss`/`html`).
    #[serde(default)]
    pub base_url: Option<String>,

    /// Directory the publisher writes artifacts into (used by rss/html/json).
    #[serde(default)]
    pub output_dir: Option<String>,

    /// Output filename for the primary artifact.
    #[serde(default)]
    pub output_file: Option<String>,

    /// Custom feed/index title.
    #[serde(default)]
    pub title: Option<String>,

    /// Custom feed/index description.
    #[serde(default)]
    pub description: Option<String>,

    /// Maximum number of entries. The string `"none"` means no limit.
    #[serde(default)]
    pub limit: Option<serde_yaml::Value>,

    // ---- bluesky-publisher fields ----------------------------------------
    // These configure the `bluesky` publisher only; other kinds ignore them.
    // Credentials are NOT here — they are read from the environment
    // (`BLUESKY_HANDLE` / `BLUESKY_APP_PASSWORD` / `BLUESKY_SERVICE`).
    /// Minimum calibrated `final_score` a matched tag must reach for a record
    /// to be posted. `final_score` is the contractually calibrated probability
    /// from the fastclass result (STREAM_PROTOCOL §5).
    #[serde(default)]
    pub min_score: Option<f64>,

    /// Path to the append-only posted-state ledger that makes the publisher
    /// idempotent — re-runs never double-post. Relative to the project
    /// directory; defaults to `.govbot/bluesky-<publisher>.ledger`.
    #[serde(default)]
    pub ledger: Option<String>,

    /// Post-text template. `{placeholders}` are substituted per record:
    /// `{title}`, `{tags}`, `{link}`, `{identifier}`, `{session}`, `{score}`.
    /// If omitted, a sensible default template is used.
    #[serde(default)]
    pub post_template: Option<String>,
}

impl Publisher {
    /// Resolve the calibrated-score threshold for the `bluesky` publisher.
    /// Falls back to a conservative default so a misconfigured manifest does
    /// not flood a feed with low-confidence matches.
    pub fn resolved_min_score(&self) -> f64 {
        self.min_score.unwrap_or(0.6)
    }

    /// Resolve `limit` to an `Option<usize>`: `None` means unlimited, the
    /// string `"none"` also means unlimited, an integer is the cap.
    pub fn resolved_limit(&self, default: Option<usize>) -> Option<usize> {
        match &self.limit {
            None => default,
            Some(serde_yaml::Value::String(s)) if s.eq_ignore_ascii_case("none") => None,
            Some(serde_yaml::Value::String(s)) => s.parse().ok().or(default),
            Some(serde_yaml::Value::Number(n)) => n.as_u64().map(|n| n as usize).or(default),
            Some(_) => default,
        }
    }
}

impl Manifest {
    /// Load and parse a `govbot.yml` manifest. A manifest carrying the retired
    /// `tags:` block (or any other unknown key) fails here via
    /// `deny_unknown_fields`.
    pub fn load(path: &Path) -> anyhow::Result<Manifest> {
        use anyhow::Context;
        let contents = std::fs::read_to_string(path)
            .with_context(|| format!("Failed to read manifest: {}", path.display()))?;
        let manifest: Manifest = serde_yaml::from_str(&contents)
            .with_context(|| format!("Failed to parse govbot.yml manifest: {}", path.display()))?;
        Ok(manifest)
    }
}

/// Sort order for log entries
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SortOrder {
    Ascending,
    Descending,
}

impl From<&str> for SortOrder {
    fn from(s: &str) -> Self {
        match s.to_uppercase().as_str() {
            "ASC" => SortOrder::Ascending,
            _ => SortOrder::Descending,
        }
    }
}

/// Join options for metadata
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum JoinOption {
    Bill,
}

/// Configuration for the pipeline processor
#[derive(Debug, Clone)]
pub struct Config {
    pub git_dir: PathBuf,
    pub repos: Vec<String>,
    pub sort_order: SortOrder,
    pub limit: Option<usize>,
    pub join_options: Vec<JoinOption>,
}

impl Config {
    /// Create a new default configuration
    pub fn new(git_dir: impl Into<PathBuf>) -> Self {
        Self {
            git_dir: git_dir.into(),
            repos: Vec::new(),
            sort_order: SortOrder::Descending,
            limit: None,
            join_options: vec![],
        }
    }

    /// Validate the configuration
    pub fn validate(&self) -> Result<()> {
        if !self.git_dir.exists() {
            return Err(Error::Config(format!(
                "Git directory does not exist: {}",
                self.git_dir.display()
            )));
        }

        if !self.git_dir.is_dir() {
            return Err(Error::Config(format!(
                "Git directory is not a directory: {}",
                self.git_dir.display()
            )));
        }

        Ok(())
    }
}

/// Builder for creating configurations
#[derive(Debug, Clone)]
pub struct ConfigBuilder {
    config: Config,
}

impl ConfigBuilder {
    /// Create a new builder with default settings
    pub fn new(git_dir: impl Into<PathBuf>) -> Self {
        Self {
            config: Config::new(git_dir),
        }
    }

    /// Set the git directory
    pub fn git_dir(mut self, dir: impl Into<PathBuf>) -> Self {
        self.config.git_dir = dir.into();
        self
    }

    /// Add a repository to filter by
    pub fn add_repo(mut self, repo: impl Into<String>) -> Self {
        self.config.repos.push(repo.into());
        self
    }

    /// Set multiple repositories
    pub fn repos(mut self, repos: Vec<String>) -> Self {
        self.config.repos = repos;
        self
    }

    /// Set the sort order
    pub fn sort_order(mut self, order: SortOrder) -> Self {
        self.config.sort_order = order;
        self
    }

    /// Set sort order from string
    pub fn sort_order_str(mut self, order: &str) -> Result<Self> {
        self.config.sort_order = SortOrder::from(order);
        Ok(self)
    }

    /// Set the limit
    pub fn limit(mut self, limit: usize) -> Self {
        self.config.limit = Some(limit);
        self
    }

    /// Clear the limit
    pub fn no_limit(mut self) -> Self {
        self.config.limit = None;
        self
    }

    /// Add a join option
    pub fn add_join_option(mut self, option: JoinOption) -> Self {
        if !self.config.join_options.contains(&option) {
            self.config.join_options.push(option);
        }
        self
    }

    /// Set join options from comma-separated string
    pub fn join_options_str(mut self, options: &str) -> Result<Self> {
        if options.is_empty() {
            self.config.join_options = vec![];
            return Ok(self);
        }

        let opts: Result<Vec<JoinOption>> = options
            .split(',')
            .map(|s| {
                let trimmed = s.trim();
                if trimmed.is_empty() {
                    return Err(Error::Config("Empty join option".to_string()));
                }
                match trimmed {
                    "bill" => Ok(JoinOption::Bill),
                    _ => Err(Error::Config(format!(
                        "Invalid join value '{}'. Allowed values are: bill",
                        trimmed
                    ))),
                }
            })
            .collect();

        self.config.join_options = opts?;
        Ok(self)
    }

    /// Build the final configuration
    pub fn build(self) -> Result<Config> {
        self.config.validate()?;
        Ok(self.config)
    }
}

impl Default for Config {
    fn default() -> Self {
        Self::new("tmp/repos")
    }
}
