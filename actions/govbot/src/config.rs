use crate::error::{Error, Result};
use serde::Deserialize;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

/// A `govbot.yml` project manifest describing a DAG of stages.
///
/// govbot.yml declares the datasets a project consumes, the transforms it runs
/// over them, the publishers that emit artifacts, and named pipelines that wire
/// those stages together. `govbot run <pipeline>` walks a pipeline's stages.
///
/// The manifest is deliberately **not** a classifier: a transform node is a
/// uniform `{ command, reads, writes }`. The built-in tagger fills the classify
/// role as an ordinary transform whose `command` is `govbot classify`; swapping
/// in an external classifier (e.g. `fastclass classify -`) is only a `command`
/// change. There is no classify-specific field.
///
/// Parsing is **additive**: the legacy `repos:` and `tags:` keys still parse so
/// pre-DAG projects and the built-in `govbot classify` node keep working. Unknown
/// keys (e.g. a legacy `build:` block) are ignored rather than rejected.
#[derive(Debug, Clone, Default, Deserialize)]
pub struct Manifest {
    #[serde(default, rename = "$schema")]
    pub schema: Option<String>,

    /// Datasets the project consumes. Additive superset of the legacy `repos:`.
    #[serde(default)]
    pub datasets: Vec<String>,

    /// Legacy dataset list; still honored so old manifests keep working.
    #[serde(default)]
    pub repos: Vec<String>,

    /// Named external-process transform nodes. Uniform shape — no privileged
    /// classify node; `govbot classify` and `fastclass classify -` are peers.
    #[serde(default)]
    pub transforms: BTreeMap<String, Transform>,

    /// Named publisher nodes. Each consumes the result stream and emits one
    /// artifact (an RSS feed or an HTML index in this release).
    #[serde(default)]
    pub publish: BTreeMap<String, Publisher>,

    /// Named `govbot run` targets: each an ordered list of stage names that
    /// reference entries in `transforms` and `publish`.
    #[serde(default)]
    pub pipelines: BTreeMap<String, Vec<String>>,
}

impl Manifest {
    /// Load and parse a `govbot.yml` manifest from disk.
    pub fn load(path: impl AsRef<Path>) -> Result<Self> {
        let contents = std::fs::read_to_string(path.as_ref()).map_err(|e| {
            Error::Config(format!(
                "Failed to read manifest {}: {}",
                path.as_ref().display(),
                e
            ))
        })?;
        serde_yaml::from_str(&contents)
            .map_err(|e| Error::Config(format!("Failed to parse govbot.yml: {}", e)))
    }

    /// The dataset list, preferring `datasets:` and falling back to `repos:`.
    pub fn dataset_list(&self) -> &[String] {
        if !self.datasets.is_empty() {
            &self.datasets
        } else {
            &self.repos
        }
    }
}

/// A single external-process transform stage (a DAG node).
///
/// A transform is a separate program that speaks the govbot stream protocol
/// (newline-delimited JSON on stdio, stable `id`, typed `kind`). govbot streams
/// records of the transform's `reads` kind into it and routes the records of its
/// `writes` kind back by `id`.
#[derive(Debug, Clone, Deserialize)]
pub struct Transform {
    /// The stage command: a shell string (`"govbot classify"`) or an argv array
    /// (`["govbot", "classify"]`).
    pub command: CommandSpec,
    /// The stream record kind this transform consumes (e.g. `docs`).
    pub reads: String,
    /// The stream record kind this transform produces (e.g. `classification`).
    pub writes: String,
}

/// A stage command: either a shell string or an explicit argv array.
#[derive(Debug, Clone, Deserialize)]
#[serde(untagged)]
pub enum CommandSpec {
    /// `command: govbot classify` — split on whitespace.
    Shell(String),
    /// `command: ["govbot", "classify"]` — used verbatim.
    Argv(Vec<String>),
}

impl CommandSpec {
    /// The command split into program + arguments.
    pub fn argv(&self) -> Vec<String> {
        match self {
            CommandSpec::Shell(s) => s.split_whitespace().map(|s| s.to_string()).collect(),
            CommandSpec::Argv(v) => v.clone(),
        }
    }
}

/// The kind of artifact a publisher emits. Each kind emits exactly one artifact.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum PublisherKind {
    /// Writes the RSS feed (default `feed.xml`).
    Rss,
    /// Writes the HTML index (default `index.html`).
    Html,
}

/// A single publisher node.
#[derive(Debug, Clone, Deserialize)]
pub struct Publisher {
    #[serde(rename = "type")]
    pub kind: PublisherKind,

    /// Tag names to include; if omitted, all tagged records are published.
    #[serde(default)]
    pub select: Option<Vec<String>>,

    /// Base URL for generated links (e.g. the GitHub Pages URL).
    #[serde(default)]
    pub base_url: Option<String>,

    /// Directory the publisher writes its artifact to.
    #[serde(default)]
    pub output_dir: Option<String>,

    /// Output filename; defaults by kind (`rss` -> feed.xml, `html` -> index.html).
    #[serde(default)]
    pub output_file: Option<String>,

    #[serde(default)]
    pub title: Option<String>,

    #[serde(default)]
    pub description: Option<String>,

    /// Max entries; a number, or the string `none` for all.
    #[serde(default)]
    pub limit: Option<serde_yaml::Value>,
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
            "DESC" | _ => SortOrder::Descending,
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

#[cfg(test)]
mod manifest_tests {
    use super::*;

    const DAG_YML: &str = r#"
datasets: [wy, il]
tags:
  clean_energy:
    description: energy bills
transforms:
  classify:
    command: govbot classify
    reads: docs
    writes: classification
  summarize:
    command: ["fastclass", "summarize", "-"]
    reads: docs
    writes: summary
publish:
  feed:
    type: rss
    base_url: https://example.org
pipelines:
  default: [classify, feed]
build:
  base_url: https://legacy.example
"#;

    #[test]
    fn parses_dag_manifest() {
        let m: Manifest = serde_yaml::from_str(DAG_YML).unwrap();
        assert_eq!(m.datasets, vec!["wy", "il"]);
        assert_eq!(m.transforms.len(), 2);
        assert_eq!(m.transforms["classify"].reads, "docs");
        assert_eq!(m.transforms["classify"].writes, "classification");
        assert_eq!(m.publish["feed"].kind, PublisherKind::Rss);
        assert_eq!(m.pipelines["default"], vec!["classify", "feed"]);
    }

    #[test]
    fn command_spec_shell_and_argv_normalize() {
        let m: Manifest = serde_yaml::from_str(DAG_YML).unwrap();
        // A shell string splits on whitespace…
        assert_eq!(
            m.transforms["classify"].command.argv(),
            vec!["govbot", "classify"]
        );
        // …and an explicit argv array is used verbatim.
        assert_eq!(
            m.transforms["summarize"].command.argv(),
            vec!["fastclass", "summarize", "-"]
        );
    }

    #[test]
    fn legacy_repos_only_manifest_still_parses() {
        // A pre-DAG manifest (repos + tags, no transforms) must remain valid,
        // and unknown keys like `build:` are ignored, not rejected.
        let m: Manifest = serde_yaml::from_str(
            "repos: [wy]\ntags:\n  x:\n    description: y\nbuild:\n  base_url: z\n",
        )
        .unwrap();
        assert!(m.datasets.is_empty());
        assert_eq!(m.dataset_list(), &["wy".to_string()]);
        assert!(m.transforms.is_empty());
    }

    #[test]
    fn dataset_list_prefers_datasets_over_repos() {
        let m: Manifest = serde_yaml::from_str("datasets: [a]\nrepos: [b]\n").unwrap();
        assert_eq!(m.dataset_list(), &["a".to_string()]);
    }
}
