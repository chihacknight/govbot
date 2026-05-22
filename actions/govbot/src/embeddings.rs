//! Per-bill tag-file persistence types.
//!
//! govbot no longer classifies bills itself — classification is delegated to
//! `fastclass` (an external transform). What remains here is the on-disk
//! `.tag.json` format: `govbot apply` deserializes a `fastclass classify`
//! result and writes these structs into the dataset; `govbot publish` reads
//! them back. The ONNX embedding machinery that used to live in this module
//! has been removed.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::HashMap;

/// Breakdown of scoring components for a tag match.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScoreBreakdown {
    pub final_score: f64,
    pub base_embedding: Option<f64>,
    pub example_similarity: Option<f64>,
    /// Keywords from include_keywords that matched in the text.
    #[serde(default)]
    pub keyword_match: Vec<String>,
    pub negative_penalty: f64,
}

/// A per-tag `.tag.json` file: metadata, an optional text cache, and the
/// bills that matched the tag.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TagFile {
    pub metadata: TagFileMetadata,
    pub tag_config: TagDefinition,
    #[serde(default)]
    pub text_cache: HashMap<String, String>,
    pub bills: HashMap<String, BillTagResult>,
}

/// Metadata about a tag file.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TagFileMetadata {
    pub last_run: String,
    pub model: String,
    pub tag_config_hash: String,
}

/// Result for a single bill within a tag file.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BillTagResult {
    pub text_hash: String,
    pub score: ScoreBreakdown,
}

/// Hash text (SHA-256 hex) for deduplication / `tag_config` stamping.
pub fn hash_text(text: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(text.as_bytes());
    format!("{:x}", hasher.finalize())
}

/// A stub tag definition stamped into each tag file. The real taxonomy lives
/// in the fastclass classifier bundle, not here — `govbot apply` only records
/// the tag name.
#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct TagDefinition {
    pub name: String,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub examples: Vec<String>,
    #[serde(default)]
    pub include_keywords: Vec<String>,
    #[serde(default)]
    pub exclude_keywords: Vec<String>,
    #[serde(default)]
    pub negative_examples: Vec<String>,
    /// Minimum similarity score (0.0 - 1.0). Defaults to 0.5.
    #[serde(default = "default_threshold")]
    pub threshold: f32,
}

fn default_threshold() -> f32 {
    0.5
}
