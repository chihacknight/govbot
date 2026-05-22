//! `govbot.lock` — the dataset lockfile, for reproducible runs.
//!
//! `govbot.yml` declares *which* datasets a project wants; `govbot.lock`
//! records the *exact git commit* each resolved to, so a run on another
//! machine (or a re-run weeks later) processes byte-identical data. It is the
//! `package-lock.json` / `Cargo.lock` of govbot.
//!
//! ## When it is written
//!
//! `govbot pull` and `govbot run` write/update `govbot.lock` next to
//! `govbot.yml` after resolving and fetching datasets — recording each
//! dataset's canonical id, git URL, channel, the cloned commit SHA, the
//! content-addressed cache key, and the resolve timestamp.
//!
//! ## Format
//!
//! `govbot.lock` is JSON (stable, diff-friendly, no YAML ambiguity):
//!
//! ```json
//! {
//!   "lockfile_version": 1,
//!   "generated_at": "2026-05-22T12:00:00Z",
//!   "datasets": {
//!     "us-legislation/wy": {
//!       "git_url": "https://github.com/chn-openstates-files/wy-legislation.git",
//!       "channel": null,
//!       "commit": "a1b2c3d4e5f6...",
//!       "cache_key": "wy-legislation-3f9a1c20e5b4",
//!       "resolved_at": "2026-05-22T12:00:00Z"
//!     }
//!   }
//! }
//! ```
//!
//! Keys are canonical `namespace/name` ids; the map is sorted for a stable
//! diff. The lockfile SHOULD be committed to a project's git repo.

use crate::error::{Error, Result};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

/// The current lockfile format version.
pub const LOCKFILE_VERSION: u32 = 1;

/// The lockfile filename, written next to `govbot.yml`.
pub const LOCKFILE_NAME: &str = "govbot.lock";

/// One pinned dataset.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LockedDataset {
    /// The git URL the dataset was cloned from.
    pub git_url: String,
    /// The requested channel (branch), if any.
    pub channel: Option<String>,
    /// The exact commit SHA the dataset is pinned to.
    pub commit: String,
    /// The shared-cache key the dataset's clone lives under.
    pub cache_key: String,
    /// When this dataset was last resolved (RFC 3339 UTC).
    pub resolved_at: String,
}

/// The whole `govbot.lock` file.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LockFile {
    /// Lockfile format version.
    pub lockfile_version: u32,
    /// When the lockfile was last written (RFC 3339 UTC).
    pub generated_at: String,
    /// Canonical `namespace/name` → pin. Sorted for a stable diff.
    pub datasets: BTreeMap<String, LockedDataset>,
}

impl Default for LockFile {
    fn default() -> Self {
        LockFile {
            lockfile_version: LOCKFILE_VERSION,
            generated_at: now_rfc3339(),
            datasets: BTreeMap::new(),
        }
    }
}

impl LockFile {
    /// The lockfile path for a project (the directory holding `govbot.yml`).
    pub fn path_for(project_dir: &Path) -> PathBuf {
        project_dir.join(LOCKFILE_NAME)
    }

    /// Load an existing lockfile, or an empty one if none exists yet.
    pub fn load_or_default(project_dir: &Path) -> Result<LockFile> {
        let path = LockFile::path_for(project_dir);
        if !path.is_file() {
            return Ok(LockFile::default());
        }
        let contents = std::fs::read_to_string(&path).map_err(|e| {
            Error::Config(format!("Failed to read {}: {}", path.display(), e))
        })?;
        serde_json::from_str(&contents)
            .map_err(|e| Error::Config(format!("Invalid {}: {}", path.display(), e)))
    }

    /// Record (or overwrite) a dataset's pin.
    pub fn pin(
        &mut self,
        canonical_id: &str,
        git_url: &str,
        channel: Option<&str>,
        commit: &str,
        cache_key: &str,
    ) {
        self.datasets.insert(
            canonical_id.to_string(),
            LockedDataset {
                git_url: git_url.to_string(),
                channel: channel.map(|c| c.to_string()),
                commit: commit.to_string(),
                cache_key: cache_key.to_string(),
                resolved_at: now_rfc3339(),
            },
        );
    }

    /// Write the lockfile to `<project_dir>/govbot.lock`, pretty-printed,
    /// refreshing `generated_at`.
    pub fn save(&mut self, project_dir: &Path) -> Result<()> {
        self.lockfile_version = LOCKFILE_VERSION;
        self.generated_at = now_rfc3339();
        let path = LockFile::path_for(project_dir);
        let json = serde_json::to_string_pretty(self)
            .map_err(|e| Error::Config(format!("Failed to serialize lockfile: {}", e)))?;
        std::fs::write(&path, format!("{}\n", json)).map_err(|e| {
            Error::Config(format!("Failed to write {}: {}", path.display(), e))
        })?;
        Ok(())
    }
}

/// The current time as an RFC 3339 UTC string.
fn now_rfc3339() -> String {
    chrono::Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Secs, true)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trips_through_disk() {
        let dir = tempfile::tempdir().unwrap();
        let mut lock = LockFile::default();
        lock.pin(
            "us-legislation/wy",
            "https://example.com/wy.git",
            None,
            "abc123",
            "wy-legislation-deadbeef",
        );
        lock.save(dir.path()).unwrap();

        let reloaded = LockFile::load_or_default(dir.path()).unwrap();
        assert_eq!(reloaded.lockfile_version, LOCKFILE_VERSION);
        let wy = reloaded.datasets.get("us-legislation/wy").unwrap();
        assert_eq!(wy.commit, "abc123");
        assert_eq!(wy.cache_key, "wy-legislation-deadbeef");
    }

    #[test]
    fn missing_lockfile_is_empty_default() {
        let dir = tempfile::tempdir().unwrap();
        let lock = LockFile::load_or_default(dir.path()).unwrap();
        assert!(lock.datasets.is_empty());
    }
}
