use ort::inputs;
use ort::session::Session;
use ort::value::Value;
use std::collections::HashMap;
use std::path::Path;
use tokenizers::Tokenizer;

use ndarray::Array1;
use regex::Regex;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::selectors::ocd_files_select_default;

/// Breakdown of scoring components for a tag match
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScoreBreakdown {
    pub final_score: f64,
    pub base_embedding: Option<f64>,
    pub example_similarity: Option<f64>,
    /// Keywords from include_keywords that matched in the text
    #[serde(default)]
    pub keyword_match: Vec<String>,
    pub negative_penalty: f64,
}

/// Tag file structure with metadata, text cache, and bill results
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TagFile {
    pub metadata: TagFileMetadata,
    pub tag_config: TagDefinition,
    #[serde(default)]
    pub text_cache: HashMap<String, String>,
    pub bills: HashMap<String, BillTagResult>,
}

/// Metadata about the tag file
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TagFileMetadata {
    pub last_run: String,
    pub model: String,
    pub tag_config_hash: String,
}

/// Result for a single bill
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BillTagResult {
    pub text_hash: String,
    pub score: ScoreBreakdown,
}

/// Hash text for deduplication
pub fn hash_text(text: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(text.as_bytes());
    format!("{:x}", hasher.finalize())
}

/// Tag definition provided by the creator
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
    /// Minimum similarity score (0.0 - 1.0). Default to 0.5 if not provided.
    #[serde(default = "default_threshold")]
    pub threshold: f32,
}

fn default_threshold() -> f32 {
    0.5
}

#[derive(Debug, Deserialize)]
pub struct RawTag {
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
    #[serde(default = "default_threshold")]
    pub threshold: f32,
}

#[derive(Debug, Deserialize)]
pub struct RawTagConfig {
    pub tags: std::collections::HashMap<String, RawTag>,
}

pub fn load_tags_config<P: AsRef<Path>>(path: P) -> anyhow::Result<Vec<TagDefinition>> {
    let contents = std::fs::read_to_string(path)?;
    let raw: RawTagConfig = serde_yaml::from_str(&contents)
        .map_err(|e| anyhow::anyhow!("Failed to parse govbot.yml: {}", e))?;

    let mut tags = Vec::new();
    for (name, raw_tag) in raw.tags {
        tags.push(TagDefinition {
            name,
            description: raw_tag.description,
            examples: raw_tag.examples,
            include_keywords: raw_tag.include_keywords,
            exclude_keywords: raw_tag.exclude_keywords,
            negative_examples: raw_tag.negative_examples,
            threshold: raw_tag.threshold,
        });
    }
    Ok(tags)
}

/// Lightweight embedding service powered by ONNX Runtime
pub struct EmbeddingService {
    session: Session,
    tokenizer: Tokenizer,
}

impl EmbeddingService {
    pub fn new<P: AsRef<Path>>(model_path: P, tokenizer_path: P) -> anyhow::Result<Self> {
        let tokenizer = Tokenizer::from_file(tokenizer_path.as_ref())
            .map_err(|e| anyhow::anyhow!("Failed to load tokenizer: {}", e))?;

        let session = Session::builder()?.commit_from_file(model_path)?;

        Ok(Self { session, tokenizer })
    }

    /// Embed text using the configured model with mean pooling over last hidden state
    pub fn embed(&mut self, text: &str) -> anyhow::Result<Array1<f32>> {
        // Tokenize
        let encoding = self
            .tokenizer
            .encode(text, true)
            .map_err(|e| anyhow::anyhow!("Tokenizer encode failed: {}", e))?;

        let ids = encoding.get_ids();
        let mask = encoding.get_attention_mask();
        let type_ids = encoding.get_type_ids();

        let input_ids: Vec<i64> = ids.iter().map(|&x| x as i64).collect();
        let attention_mask_vec: Vec<i64> = mask.iter().map(|&x| x as i64).collect();
        let token_type_vec: Vec<i64> = type_ids.iter().map(|&x| x as i64).collect();

        let outputs = self.session.run(inputs![
            "input_ids" => Value::from_array((vec![1_i64, ids.len() as i64], input_ids))?,
            "attention_mask" => Value::from_array((vec![1_i64, mask.len() as i64], attention_mask_vec))?,
            "token_type_ids" => Value::from_array((vec![1_i64, type_ids.len() as i64], token_type_vec))?,
        ])?;

        // Use last_hidden_state and mean-pool
        let hidden = outputs["last_hidden_state"].try_extract_array::<f32>()?;

        // hidden shape: [batch, seq_len, hidden_dim]
        let shape = hidden.shape();
        if shape.len() != 3 {
            return Err(anyhow::anyhow!("Unexpected embedding shape {:?}", shape));
        }
        let seq_len = shape[1];
        let hidden_dim = shape[2];

        let mut pooled = vec![0f32; hidden_dim];
        for i in 0..seq_len {
            for h in 0..hidden_dim {
                pooled[h] += hidden[[0, i, h]];
            }
        }
        for h in 0..hidden_dim {
            pooled[h] /= seq_len as f32;
        }
        let pooled = Array1::from(pooled);

        Ok(pooled)
    }

    pub fn cosine_similarity(&self, a: &Array1<f32>, b: &Array1<f32>) -> f32 {
        let dot = a.dot(b);
        let norm_a = a.dot(a).sqrt();
        let norm_b = b.dot(b).sqrt();
        dot / (norm_a * norm_b).max(1e-9)
    }
}

/// Return all keywords from the list that appear in the text
/// (case-insensitive, word-boundary aware).
fn find_matching_keywords(text: &str, keywords: &[String]) -> Vec<String> {
    let text_lower = text.to_lowercase();
    let mut matches = Vec::new();

    for keyword in keywords {
        let keyword_lower = keyword.to_lowercase();
        // Check for exact word match or phrase match
        // For multi-word keywords, use contains
        // For single-word keywords, check word boundaries
        let is_match = if keyword_lower.contains(' ') {
            // Multi-word phrase: use contains
            text_lower.contains(&keyword_lower)
        } else {
            // Single word: check word boundaries to avoid partial matches
            // e.g., "trans" should not match "transport" or "transfer"
            // But "lgbtq" should match "lgbtq+" (with punctuation)
            let escaped = regex::escape(&keyword_lower);
            let pattern = format!(r"\b{}(?:\+|\b)", escaped);
            Regex::new(&pattern)
                .map(|re| re.is_match(&text_lower))
                .unwrap_or_else(|_| text_lower.contains(&keyword_lower))
        };

        if is_match {
            matches.push(keyword.clone());
        }
    }

    matches
}

/// Matcher that precomputes tag embeddings and scores logs against them
pub struct TagMatcher {
    embeddings: std::sync::Mutex<EmbeddingService>,
    tag_embeddings: HashMap<String, Array1<f32>>,
    example_embeddings: HashMap<String, Vec<Array1<f32>>>,
    negative_example_embeddings: HashMap<String, Vec<Array1<f32>>>,
    tags: HashMap<String, TagDefinition>,
}

impl TagMatcher {
    pub fn from_files<P: AsRef<Path>>(
        model_path: P,
        tokenizer_path: P,
        tags_path: P,
    ) -> anyhow::Result<Self> {
        let mut embeddings = EmbeddingService::new(&model_path, &tokenizer_path)?;

        // Load tags YAML
        let tag_defs = load_tags_config(tags_path)?;

        // Precompute tag embeddings
        let mut tag_embeddings = HashMap::new();
        let mut example_embeddings = HashMap::new();
        let mut negative_example_embeddings = HashMap::new();
        let mut tags_map = HashMap::new();

        for tag in tag_defs {
            // Combine description + examples for richer embedding
            let mut text = tag.description.clone();
            if !tag.examples.is_empty() {
                text.push_str(" Examples: ");
                text.push_str(&tag.examples.join(" | "));
            }
            let emb = embeddings.embed(&text)?;
            tag_embeddings.insert(tag.name.clone(), emb);

            // Precompute embeddings for individual examples
            let mut example_embs = Vec::new();
            for example in &tag.examples {
                let example_emb = embeddings.embed(example)?;
                example_embs.push(example_emb);
            }
            example_embeddings.insert(tag.name.clone(), example_embs);

            // Precompute embeddings for negative examples
            let mut neg_example_embs = Vec::new();
            for neg_example in &tag.negative_examples {
                let neg_emb = embeddings.embed(neg_example)?;
                neg_example_embs.push(neg_emb);
            }
            negative_example_embeddings.insert(tag.name.clone(), neg_example_embs);

            tags_map.insert(tag.name.clone(), tag);
        }

        Ok(Self {
            embeddings: std::sync::Mutex::new(embeddings),
            tag_embeddings,
            example_embeddings,
            negative_example_embeddings,
            tags: tags_map,
        })
    }

    /// Calculate composite score using multiple signals
    fn calculate_composite_score(
        &self,
        log_embedding: &Array1<f32>,
        log_text: &str,
        tag_name: &str,
        tag_def: &TagDefinition,
        embeddings: &mut EmbeddingService,
    ) -> ScoreBreakdown {
        // 4. Exclude keywords: zero out if exclude keywords match (check first).
        // We don't currently expose which exclude keyword matched; we just block the tag.
        if !tag_def.exclude_keywords.is_empty() {
            let exclude_matches = find_matching_keywords(log_text, &tag_def.exclude_keywords);
            if !exclude_matches.is_empty() {
                return ScoreBreakdown {
                    final_score: 0.0,
                    base_embedding: None,
                    example_similarity: None,
                    keyword_match: Vec::new(),
                    negative_penalty: 0.0,
                };
            }
        }

        // 3. Include keywords: if keywords match, they have the heaviest impact
        let include_matches = if tag_def.include_keywords.is_empty() {
            Vec::new()
        } else {
            find_matching_keywords(log_text, &tag_def.include_keywords)
        };
        let has_keyword_match = !include_matches.is_empty();

        let mut score = 0.0;
        let mut weight_sum = 0.0;
        let mut base_embedding_score: Option<f32> = None;
        let mut example_similarity_score: Option<f32> = None;

        // 1. Base score: embedding similarity to description + examples
        // Industry standard: embeddings are the primary signal
        if let Some(tag_emb) = self.tag_embeddings.get(tag_name) {
            let base_score = embeddings.cosine_similarity(log_embedding, tag_emb);
            base_embedding_score = Some(base_score);
            // Weight embeddings less when keywords match (keywords will add boost)
            let weight = if has_keyword_match { 0.35 } else { 0.5 };
            score += base_score * weight;
            weight_sum += weight;
        }

        // 2. Example similarity: max similarity to individual examples
        if let Some(example_embs) = self.example_embeddings.get(tag_name) {
            if !example_embs.is_empty() {
                let max_example_score = example_embs
                    .iter()
                    .map(|example_emb| embeddings.cosine_similarity(log_embedding, example_emb))
                    .fold(0.0f32, f32::max);
                example_similarity_score = Some(max_example_score);
                let weight = if has_keyword_match { 0.25 } else { 0.35 };
                score += max_example_score * weight;
                weight_sum += weight;
            }
        }

        // 3. Keyword boost: additive boost when keywords match
        // Keywords are explicit signals and should have strong weight
        // This ensures keyword matches are strong but still respect embedding quality
        if has_keyword_match {
            // Strong boost for keywords - they are explicit signals from the tag definition
            // Higher than typical industry systems because keywords are curated and highly reliable
            let keyword_boost = 0.4;
            score += keyword_boost;
            weight_sum += keyword_boost;
        }

        // Normalize the weighted combination
        if weight_sum > 0.0 {
            score = score / weight_sum;
        }

        // If keywords matched, ensure minimum score meets threshold (before negative penalty)
        // Keywords are explicit signals, so they should guarantee threshold unless negated
        if has_keyword_match {
            score = score.max(tag_def.threshold);
        }

        // 5. Negative examples: penalty if too similar to negative examples
        let mut negative_penalty = 0.0f32;
        if let Some(neg_example_embs) = self.negative_example_embeddings.get(tag_name) {
            if !neg_example_embs.is_empty() {
                let max_neg_score = neg_example_embs
                    .iter()
                    .map(|neg_emb| embeddings.cosine_similarity(log_embedding, neg_emb))
                    .fold(0.0f32, f32::max);
                // Apply penalty: subtract up to 0.25 based on negative similarity
                // Higher negative similarity = stronger penalty
                negative_penalty = max_neg_score * 0.25;
                score = (score - negative_penalty).max(0.0);
            }
        }

        // Clamp to [0, 1]
        let final_score = score.min(1.0).max(0.0);

        ScoreBreakdown {
            final_score: final_score as f64,
            base_embedding: base_embedding_score.map(|s| s as f64),
            example_similarity: example_similarity_score.map(|s| s as f64),
            keyword_match: include_matches,
            negative_penalty: negative_penalty as f64,
        }
    }

    /// Match a serde_json::Value log entry against tags, returning (tag, score_breakdown)
    pub fn match_json_value(
        &self,
        value: &serde_json::Value,
    ) -> anyhow::Result<Vec<(String, ScoreBreakdown)>> {
        let text = ocd_files_select_default(value);
        let mut embeddings = self.embeddings.lock().unwrap();
        let log_embedding = embeddings.embed(&text)?;

        let mut results = Vec::new();
        for (name, tag_def) in &self.tags {
            let score_breakdown = self.calculate_composite_score(
                &log_embedding,
                &text,
                name,
                tag_def,
                &mut *embeddings,
            );
            if score_breakdown.final_score >= tag_def.threshold as f64 {
                results.push((name.clone(), score_breakdown));
            }
        }

        // Sort descending by final score
        results.sort_by(|a, b| {
            b.1.final_score
                .partial_cmp(&a.1.final_score)
                .unwrap_or(std::cmp::Ordering::Equal)
        });
        Ok(results)
    }

    /// Access tag definitions (name -> definition)
    pub fn tag_definitions(&self) -> &HashMap<String, TagDefinition> {
        &self.tags
    }
}

/// Keyword-based fallback matcher when embedding mode is unavailable
/// Matches tags based on include_keywords and exclude_keywords from tag definitions
pub fn match_tags_keywords(
    tag_defs: &[TagDefinition],
    json_entry: &serde_json::Value,
) -> Vec<(String, ScoreBreakdown)> {
    let text = ocd_files_select_default(json_entry);
    let text_lower = text.to_lowercase();

    let mut results = Vec::new();

    for tag_def in tag_defs {
        // Check exclude_keywords first - if any match, skip this tag
        if !tag_def.exclude_keywords.is_empty() {
            let exclude_matches = find_matching_keywords(&text_lower, &tag_def.exclude_keywords);
            if !exclude_matches.is_empty() {
                continue;
            }
        }

        // Check include_keywords - if any match, create a match
        let include_matches = if tag_def.include_keywords.is_empty() {
            Vec::new()
        } else {
            find_matching_keywords(&text_lower, &tag_def.include_keywords)
        };

        if !include_matches.is_empty() {
            // If keywords match, assign a score based on threshold
            // Use threshold as the base score, or 0.6 if threshold is lower
            let score = tag_def.threshold.max(0.6) as f64;

            // Only include if score meets threshold
            if score >= tag_def.threshold as f64 {
                results.push((
                    tag_def.name.clone(),
                    ScoreBreakdown {
                        final_score: score,
                        base_embedding: None,
                        example_similarity: None,
                        keyword_match: include_matches,
                        negative_penalty: 0.0,
                    },
                ));
            }
        }
    }

    // Sort by score descending
    results.sort_by(|a, b| {
        b.1.final_score
            .partial_cmp(&a.1.final_score)
            .unwrap_or(std::cmp::Ordering::Equal)
    });

    results
}
