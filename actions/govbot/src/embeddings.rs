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

use crate::similarity::extract_text_from_json;

/// Breakdown of scoring components for a tag match
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScoreBreakdown {
    pub final_score: f64,
    pub base_embedding: Option<f64>,
    pub example_similarity: Option<f64>,
    pub keyword_match: bool,
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

/// Check if any keywords from the list appear in the text (case-insensitive, word-boundary aware)
fn matches_keywords(text: &str, keywords: &[String]) -> bool {
    let text_lower = text.to_lowercase();
    keywords.iter().any(|keyword| {
        let keyword_lower = keyword.to_lowercase();
        // Check for exact word match or phrase match
        // For multi-word keywords, use contains
        // For single-word keywords, check word boundaries
        if keyword_lower.contains(' ') {
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
        }
    })
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
        // 4. Exclude keywords: zero out if exclude keywords match (check first)
        if !tag_def.exclude_keywords.is_empty() {
            if matches_keywords(log_text, &tag_def.exclude_keywords) {
                return ScoreBreakdown {
                    final_score: 0.0,
                    base_embedding: None,
                    example_similarity: None,
                    keyword_match: false,
                    negative_penalty: 0.0,
                };
            }
        }

        // 3. Include keywords: if keywords match, they have the heaviest impact
        let has_keyword_match = !tag_def.include_keywords.is_empty()
            && matches_keywords(log_text, &tag_def.include_keywords);

        let mut score = 0.0;
        let mut weight_sum = 0.0;
        let mut base_embedding_score: Option<f32> = None;
        let mut example_similarity_score: Option<f32> = None;

        // 1. Base score: embedding similarity to description + examples
        if let Some(tag_emb) = self.tag_embeddings.get(tag_name) {
            let base_score = embeddings.cosine_similarity(log_embedding, tag_emb);
            base_embedding_score = Some(base_score);
            let weight = if has_keyword_match { 0.3 } else { 0.4 };
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
                let weight = if has_keyword_match { 0.2 } else { 0.3 };
                score += max_example_score * weight;
                weight_sum += weight;
            }
        }

        // 3. Keyword boost: add significant boost if keywords match
        // Strong LGBTQ keywords get higher boost even with lower embeddings
        let is_strong_keyword = has_keyword_match && {
            let text_lower = log_text.to_lowercase();
            text_lower.contains("lgbtq")
                || text_lower.contains("sexual orientation")
                || text_lower.contains("gender identity")
                || text_lower.contains("gender expression")
                || text_lower.contains("transgender")
                || text_lower.contains("conversion therapy")
                || text_lower.contains("gender affirming")
                || text_lower.contains("gender transition")
        };

        if has_keyword_match {
            let min_embedding = base_embedding_score
                .unwrap_or(0.0)
                .max(example_similarity_score.unwrap_or(0.0));

            if is_strong_keyword {
                // Strong keywords get aggressive boost - these are very specific LGBTQ terms
                if min_embedding > 0.15 {
                    score += 0.4; // 40% boost for strong keywords
                    weight_sum += 0.4;
                } else {
                    score += 0.25; // Still give boost even with low embeddings for strong keywords
                    weight_sum += 0.25;
                }
            } else if min_embedding > 0.2 {
                // Weak keywords need reasonable embeddings
                score += 0.35;
                weight_sum += 0.35;
            } else {
                score += 0.15;
                weight_sum += 0.15;
            }
        }

        // Normalize the score
        if weight_sum > 0.0 {
            score = score / weight_sum;
        }

        // If strong keywords matched, guarantee minimum score
        if has_keyword_match {
            let min_embedding = base_embedding_score
                .unwrap_or(0.0)
                .max(example_similarity_score.unwrap_or(0.0));

            if is_strong_keyword {
                // Strong keywords guarantee at least 0.5 (threshold)
                score = score.max(0.5);
            } else if min_embedding > 0.3 {
                score = score.max(0.6);
            } else if min_embedding > 0.2 {
                score = score.max(0.5);
            }
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
            keyword_match: has_keyword_match,
            negative_penalty: negative_penalty as f64,
        }
    }

    /// Match a serde_json::Value log entry against tags, returning (tag, score_breakdown)
    pub fn match_json_value(
        &self,
        value: &serde_json::Value,
    ) -> anyhow::Result<Vec<(String, ScoreBreakdown)>> {
        let text = extract_text_from_json(value);
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
