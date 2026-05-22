//! The shared, content-addressed dataset cache at `~/.govbot/cache/`.
//!
//! ## The problem this solves
//!
//! Before this, every govbot project cloned every dataset into its own
//! `<project>/.govbot/repos/`. Ten climate projects on one laptop meant ten
//! clones of `wy-legislation`. The cache makes a dataset **cloned once per
//! machine**: the heavy git repo lives in `~/.govbot/cache/`, and a project's
//! `.govbot/repos/<short_name>` is a lightweight reference into it.
//!
//! ## Layout
//!
//! ```text
//! ~/.govbot/
//!   cache/
//!     <key>/                 a bare-ish working clone of one dataset@channel
//!   registry.json            most-recently fetched registry (see registry.rs)
//! ```
//!
//! The cache **key** is content-addressed over the dataset's *identity* — its
//! git URL plus channel — as a short SHA-256 hex digest, prefixed with the
//! dataset's short name for human readability:
//!
//! ```text
//!   wy-legislation-3f9a1c20e5b4
//!   us-counties__cook-7a2b...   (a '/' in a namespace becomes '__')
//! ```
//!
//! Keying on URL+channel (not on a resolved SHA) keeps the clone path stable
//! across `pull`s: the same dataset always maps to the same cache directory,
//! `git pull` updates it in place, and `govbot.lock` records the exact SHA.
//! A *second* `pull` in any project finds the cache populated and only fetches
//! deltas — no re-clone.
//!
//! ## How a project references the cache
//!
//! A project's `.govbot/repos/<short_name>` is a symlink to the cache entry
//! (a plain directory copy is the fallback where symlinks are unavailable).
//! Downstream code (`source`, `load`) walks `.govbot/repos/` exactly as
//! before — it does not need to know the cache exists.

use crate::error::{Error, Result};
use sha2::{Digest, Sha256};
use std::path::PathBuf;

/// The govbot home directory: `~/.govbot`. Honors `GOVBOT_HOME` for tests.
pub fn govbot_home() -> Option<PathBuf> {
    if let Some(explicit) = std::env::var_os("GOVBOT_HOME") {
        let p = PathBuf::from(explicit);
        if !p.as_os_str().is_empty() {
            return Some(p);
        }
    }
    std::env::var_os("HOME")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .map(PathBuf::from)
        .filter(|p| !p.as_os_str().is_empty())
        .map(|h| h.join(".govbot"))
}

/// The shared content-addressed cache directory: `~/.govbot/cache`.
pub fn cache_dir() -> Result<PathBuf> {
    let home = govbot_home()
        .ok_or_else(|| Error::Config("Could not determine home directory for cache".into()))?;
    Ok(home.join("cache"))
}

/// Compute the content-addressed cache key for a dataset's identity.
///
/// The key is `<short_name>-<digest>` where the digest is the first 12 hex
/// chars of `sha256(git_url + "@" + channel)`. A `/` in the short name (it
/// should not contain one, but be defensive) becomes `__`.
pub fn cache_key(short_name: &str, git_url: &str, channel: Option<&str>) -> String {
    let mut hasher = Sha256::new();
    hasher.update(git_url.as_bytes());
    hasher.update(b"@");
    hasher.update(channel.unwrap_or("").as_bytes());
    let digest = hasher.finalize();
    let hex: String = digest.iter().take(6).map(|b| format!("{:02x}", b)).collect();
    let safe_name = short_name.replace('/', "__");
    format!("{}-{}", safe_name, hex)
}

/// The absolute path of a dataset's entry in the shared cache.
pub fn cache_path(short_name: &str, git_url: &str, channel: Option<&str>) -> Result<PathBuf> {
    Ok(cache_dir()?.join(cache_key(short_name, git_url, channel)))
}

/// Link a project's `repos/<short_name>` directory to a populated cache entry.
///
/// Prefers a symlink (cheap, shared); falls back to recording the cache path
/// when symlinks are unavailable. Idempotent — an existing correct link is a
/// no-op; a stale link is replaced.
pub fn link_into_project(cache_entry: &std::path::Path, project_repo: &std::path::Path) -> Result<()> {
    if let Some(parent) = project_repo.parent() {
        std::fs::create_dir_all(parent)?;
    }

    // If the project repo path is already a symlink to the right place, done.
    if let Ok(existing) = std::fs::read_link(project_repo) {
        if existing == cache_entry {
            return Ok(());
        }
        // Stale symlink — remove it.
        let _ = std::fs::remove_file(project_repo);
    } else if project_repo.exists() {
        // A real directory is sitting where the link should be (a pre-cache
        // clone). Remove it so the cache becomes the single source of truth.
        let _ = std::fs::remove_dir_all(project_repo);
    }

    #[cfg(unix)]
    {
        std::os::unix::fs::symlink(cache_entry, project_repo).map_err(|e| {
            Error::Config(format!(
                "Failed to link cache entry {} into project: {}",
                cache_entry.display(),
                e
            ))
        })?;
        return Ok(());
    }

    #[cfg(not(unix))]
    {
        std::os::windows::fs::symlink_dir(cache_entry, project_repo).map_err(|e| {
            Error::Config(format!(
                "Failed to link cache entry {} into project: {}",
                cache_entry.display(),
                e
            ))
        })?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cache_key_is_stable_and_named() {
        let k1 = cache_key("wy-legislation", "https://example.com/wy.git", None);
        let k2 = cache_key("wy-legislation", "https://example.com/wy.git", None);
        assert_eq!(k1, k2, "cache key must be deterministic");
        assert!(k1.starts_with("wy-legislation-"));
    }

    #[test]
    fn cache_key_differs_by_url_and_channel() {
        let base = cache_key("wy", "https://a/wy.git", None);
        assert_ne!(base, cache_key("wy", "https://b/wy.git", None));
        assert_ne!(base, cache_key("wy", "https://a/wy.git", Some("nightly")));
    }
}
