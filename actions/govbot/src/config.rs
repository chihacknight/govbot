use crate::error::{Error, Result};
use std::path::PathBuf;

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
