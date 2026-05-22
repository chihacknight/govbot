//! The govbot dataset registry — "npm/docker for government data."
//!
//! A registry maps a **dataset identifier** to the git repo holding its data,
//! the data schema it follows, and the glob that locates records within the
//! repo. Datasets are git repos; this index is what lets govbot resolve a
//! dataset at runtime instead of from a compiled enum.
//!
//! ## Identifier scheme
//!
//! A canonical identifier is `namespace/name[@channel]`:
//!   - `namespace` — a grouping (`us-legislation`, a county set, an agency set).
//!   - `name` — the dataset within the namespace (`wy`, `il`, …).
//!   - `@channel` — an optional release channel / branch (defaults to the
//!     repo's default branch).
//!
//! **Plain jurisdiction codes stay valid.** A bare identifier with no `/`
//! (e.g. `wy`) is resolved against the registry's `default_namespace`, so an
//! existing manifest `datasets: [wy]` keeps working unchanged. `all` is a
//! reserved alias meaning "every dataset in the registry."
//!
//! ## Where it lives / how it is fetched
//!
//! The default registry is the JSON file `data/registry.json`, **compiled into
//! the binary** via `include_str!` — so a fresh install resolves the 52 seed
//! jurisdictions with zero network access. A project can override it:
//!   1. `GOVBOT_REGISTRY_URL` — an `http(s)://` URL or a local file path.
//!   2. `<project>/.govbot/registry.json` — a project-local registry file.
//! A fetched registry is cached at `~/.govbot/registry.json`.
//!
//! See `actions/govbot/REGISTRY.md` for the full format documentation.

use crate::error::{Error, Result};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::path::PathBuf;

/// The bundled default registry, compiled into the binary.
const BUNDLED_REGISTRY: &str = include_str!("../data/registry.json");

/// A single dataset entry: where its data lives and how to read it.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DatasetEntry {
    /// The git repository URL the dataset's data is cloned from.
    pub git_url: String,

    /// The data schema the dataset follows (e.g. `ocdfiles`). Informational —
    /// it lets a future `source` projection pick the right reader.
    #[serde(default)]
    pub schema: Option<String>,

    /// A glob, relative to the cloned repo root, that locates the dataset's
    /// records. Replaces the hard-coded `**/logs/*.json` walk.
    #[serde(default)]
    pub path_pattern: Option<String>,

    /// A human-readable display name (`Wyoming`, `Cook County`, …).
    #[serde(default)]
    pub name: Option<String>,
}

/// The parsed registry file.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Registry {
    /// Registry format version, for forward-compatibility.
    #[serde(default, rename = "$schema_version")]
    pub schema_version: Option<String>,

    /// Free-text description of this registry.
    #[serde(default)]
    pub description: Option<String>,

    /// The namespace a bare (slash-free) identifier is resolved against.
    #[serde(default = "default_namespace")]
    pub default_namespace: String,

    /// Canonical `namespace/name` → entry map.
    pub datasets: BTreeMap<String, DatasetEntry>,
}

fn default_namespace() -> String {
    "us-legislation".to_string()
}

/// A resolved dataset: its canonical id plus the entry it points at.
#[derive(Debug, Clone)]
pub struct ResolvedDataset {
    /// The canonical `namespace/name` identifier (channel stripped).
    pub id: String,
    /// The optional channel (branch) requested via `@channel`.
    pub channel: Option<String>,
    /// The registry entry.
    pub entry: DatasetEntry,
}

impl ResolvedDataset {
    /// The short, slash-free name a clone directory is keyed on (`wy`, `il`).
    /// Strips the namespace; this is also the legacy "locale" string.
    pub fn short_name(&self) -> &str {
        self.id.rsplit('/').next().unwrap_or(&self.id)
    }
}

impl Registry {
    /// Parse the bundled default registry. Infallible in practice — the file
    /// is validated at build time — but surfaces a `Config` error if not.
    pub fn bundled() -> Result<Registry> {
        serde_json::from_str(BUNDLED_REGISTRY)
            .map_err(|e| Error::Config(format!("Bundled registry is invalid: {}", e)))
    }

    /// Load the active registry, honoring overrides in priority order:
    ///   1. `GOVBOT_REGISTRY_URL` (an `http(s)://` URL or a filesystem path).
    ///   2. `<project>/.govbot/registry.json` — a project-local registry.
    ///   3. The bundled default.
    ///
    /// `project_dir` is the directory holding `govbot.yml` (or the cwd).
    pub fn load(project_dir: &std::path::Path) -> Result<Registry> {
        if let Ok(src) = std::env::var("GOVBOT_REGISTRY_URL") {
            if !src.trim().is_empty() {
                return Registry::from_source(&src);
            }
        }
        let project_registry = project_dir.join(".govbot").join("registry.json");
        if project_registry.is_file() {
            return Registry::from_file(&project_registry);
        }
        Registry::bundled()
    }

    /// Load a registry from a source string: an `http(s)://` URL is fetched
    /// (and cached at `~/.govbot/registry.json`), anything else is a file path.
    pub fn from_source(src: &str) -> Result<Registry> {
        if src.starts_with("http://") || src.starts_with("https://") {
            Registry::fetch(src)
        } else {
            Registry::from_file(std::path::Path::new(src))
        }
    }

    /// Parse a registry from a JSON file on disk.
    pub fn from_file(path: &std::path::Path) -> Result<Registry> {
        let contents = std::fs::read_to_string(path).map_err(|e| {
            Error::Config(format!("Failed to read registry {}: {}", path.display(), e))
        })?;
        serde_json::from_str(&contents)
            .map_err(|e| Error::Config(format!("Invalid registry {}: {}", path.display(), e)))
    }

    /// Fetch a registry over HTTP and cache it at `~/.govbot/registry.json`.
    pub fn fetch(url: &str) -> Result<Registry> {
        let body = ureq::get(url)
            .call()
            .map_err(|e| Error::Config(format!("Failed to fetch registry {}: {}", url, e)))?
            .into_body()
            .read_to_string()
            .map_err(|e| Error::Config(format!("Failed to read registry body: {}", e)))?;
        let registry: Registry = serde_json::from_str(&body)
            .map_err(|e| Error::Config(format!("Fetched registry {} is invalid: {}", url, e)))?;
        // Best-effort cache write — a failure here is non-fatal.
        if let Some(cache) = registry_cache_path() {
            if let Some(parent) = cache.parent() {
                let _ = std::fs::create_dir_all(parent);
            }
            let _ = std::fs::write(&cache, &body);
        }
        Ok(registry)
    }

    /// Canonicalize a dataset identifier to `namespace/name` (channel stripped).
    ///
    /// `wy` → `<default_namespace>/wy`; `us-counties/cook` is returned as-is;
    /// `wy@nightly` → `<default_namespace>/wy`. The channel is returned
    /// separately by [`Registry::resolve`].
    pub fn canonical_id(&self, identifier: &str) -> (String, Option<String>) {
        let (base, channel) = match identifier.split_once('@') {
            Some((b, c)) => (b, Some(c.to_string())),
            None => (identifier, None),
        };
        let id = if base.contains('/') {
            base.to_string()
        } else {
            format!("{}/{}", self.default_namespace, base)
        };
        (id, channel)
    }

    /// Resolve a dataset identifier to its registry entry.
    ///
    /// Accepts a canonical `namespace/name[@channel]` id or a bare jurisdiction
    /// code (resolved against `default_namespace`). Returns a `Config` error if
    /// the identifier is not in the registry.
    pub fn resolve(&self, identifier: &str) -> Result<ResolvedDataset> {
        let (id, channel) = self.canonical_id(identifier);
        let entry = self.datasets.get(&id).ok_or_else(|| {
            Error::Config(format!(
                "Unknown dataset '{}'. It is not in the registry. \
                 Run `govbot search` to list available datasets.",
                identifier
            ))
        })?;
        Ok(ResolvedDataset {
            id,
            channel,
            entry: entry.clone(),
        })
    }

    /// Resolve a list of identifiers, expanding the `all` alias to every
    /// dataset in the registry. Order is preserved; `all` expands in
    /// canonical (sorted) order.
    pub fn resolve_all(&self, identifiers: &[String]) -> Result<Vec<ResolvedDataset>> {
        let mut out = Vec::new();
        for ident in identifiers {
            let ident = ident.trim();
            if ident.is_empty() {
                continue;
            }
            if ident.eq_ignore_ascii_case("all") {
                for id in self.datasets.keys() {
                    out.push(self.resolve(id)?);
                }
            } else {
                out.push(self.resolve(ident)?);
            }
        }
        Ok(out)
    }

    /// Every dataset in the registry, in canonical id order.
    pub fn all(&self) -> Vec<ResolvedDataset> {
        self.datasets
            .iter()
            .map(|(id, entry)| ResolvedDataset {
                id: id.clone(),
                channel: None,
                entry: entry.clone(),
            })
            .collect()
    }

    /// Search the registry. A blank query matches everything; otherwise the
    /// query is matched case-insensitively against the id and the name.
    pub fn search(&self, query: &str) -> Vec<ResolvedDataset> {
        let q = query.trim().to_lowercase();
        self.all()
            .into_iter()
            .filter(|d| {
                if q.is_empty() {
                    return true;
                }
                d.id.to_lowercase().contains(&q)
                    || d.entry
                        .name
                        .as_deref()
                        .map(|n| n.to_lowercase().contains(&q))
                        .unwrap_or(false)
            })
            .collect()
    }
}

/// The path the most recently fetched registry is cached at:
/// `~/.govbot/registry.json`.
pub fn registry_cache_path() -> Option<PathBuf> {
    crate::cache::govbot_home().map(|h| h.join("registry.json"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bundled_registry_parses_and_has_seed_jurisdictions() {
        let reg = Registry::bundled().expect("bundled registry must parse");
        assert!(reg.datasets.len() >= 52, "expected the 52-jurisdiction seed");
        assert!(reg.datasets.contains_key("us-legislation/wy"));
    }

    #[test]
    fn bare_code_resolves_via_default_namespace() {
        let reg = Registry::bundled().unwrap();
        let d = reg.resolve("wy").expect("`wy` must resolve");
        assert_eq!(d.id, "us-legislation/wy");
        assert_eq!(d.short_name(), "wy");
        assert!(d.entry.git_url.contains("wy-legislation"));
    }

    #[test]
    fn canonical_id_and_channel_split() {
        let reg = Registry::bundled().unwrap();
        let d = reg.resolve("wy@nightly").unwrap();
        assert_eq!(d.id, "us-legislation/wy");
        assert_eq!(d.channel.as_deref(), Some("nightly"));
    }

    #[test]
    fn namespaced_id_resolves_directly() {
        let reg = Registry::bundled().unwrap();
        let d = reg.resolve("us-legislation/il").unwrap();
        assert_eq!(d.id, "us-legislation/il");
    }

    #[test]
    fn unknown_dataset_errors() {
        let reg = Registry::bundled().unwrap();
        assert!(reg.resolve("atlantis").is_err());
    }

    #[test]
    fn all_alias_expands_to_every_dataset() {
        let reg = Registry::bundled().unwrap();
        let resolved = reg.resolve_all(&["all".to_string()]).unwrap();
        assert_eq!(resolved.len(), reg.datasets.len());
    }

    #[test]
    fn search_matches_id_and_name() {
        let reg = Registry::bundled().unwrap();
        assert!(!reg.search("wyoming").is_empty());
        assert!(!reg.search("wy").is_empty());
        assert_eq!(reg.search("").len(), reg.datasets.len());
    }
}
