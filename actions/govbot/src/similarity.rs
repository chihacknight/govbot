use regex::Regex;
/// Lightweight text similarity scorer using TF-IDF and cosine similarity
/// Designed to be fast and work in GitHub Actions without external dependencies
use std::collections::{HashMap, HashSet};
use std::sync::OnceLock;

/// Comprehensive English stop words list combining NLTK and spaCy
/// This is a large list of words that don't add categorical value
const STOP_WORDS_LIST: &[&str] = &[
    "a",
    "about",
    "above",
    "across",
    "after",
    "afterwards",
    "again",
    "against",
    "all",
    "almost",
    "alone",
    "along",
    "already",
    "also",
    "although",
    "always",
    "am",
    "among",
    "amongst",
    "amoungst",
    "amount",
    "an",
    "and",
    "another",
    "any",
    "anyhow",
    "anyone",
    "anything",
    "anyway",
    "anywhere",
    "are",
    "around",
    "as",
    "at",
    "back",
    "be",
    "became",
    "because",
    "become",
    "becomes",
    "becoming",
    "been",
    "before",
    "beforehand",
    "behind",
    "being",
    "below",
    "beside",
    "besides",
    "between",
    "beyond",
    "bill",
    "both",
    "bottom",
    "but",
    "by",
    "call",
    "can",
    "cannot",
    "cant",
    "co",
    "con",
    "could",
    "couldnt",
    "cry",
    "de",
    "describe",
    "detail",
    "do",
    "done",
    "down",
    "due",
    "during",
    "each",
    "eg",
    "eight",
    "either",
    "eleven",
    "else",
    "elsewhere",
    "empty",
    "enough",
    "etc",
    "even",
    "ever",
    "every",
    "everyone",
    "everything",
    "everywhere",
    "except",
    "few",
    "fifteen",
    "fify",
    "fill",
    "find",
    "fire",
    "first",
    "five",
    "for",
    "former",
    "formerly",
    "forty",
    "found",
    "four",
    "from",
    "front",
    "full",
    "further",
    "get",
    "give",
    "go",
    "had",
    "has",
    "hasnt",
    "have",
    "he",
    "hence",
    "her",
    "here",
    "hereafter",
    "hereby",
    "herein",
    "hereupon",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "however",
    "hundred",
    "ie",
    "if",
    "in",
    "inc",
    "indeed",
    "interest",
    "into",
    "is",
    "it",
    "its",
    "itself",
    "keep",
    "last",
    "latter",
    "latterly",
    "least",
    "less",
    "ltd",
    "made",
    "many",
    "may",
    "me",
    "meanwhile",
    "might",
    "mill",
    "mine",
    "more",
    "moreover",
    "most",
    "mostly",
    "move",
    "much",
    "must",
    "my",
    "myself",
    "name",
    "namely",
    "neither",
    "never",
    "nevertheless",
    "next",
    "nine",
    "no",
    "nobody",
    "none",
    "noone",
    "nor",
    "not",
    "nothing",
    "now",
    "nowhere",
    "of",
    "off",
    "often",
    "on",
    "once",
    "one",
    "only",
    "onto",
    "or",
    "other",
    "others",
    "otherwise",
    "our",
    "ours",
    "ourselves",
    "out",
    "over",
    "own",
    "part",
    "per",
    "perhaps",
    "please",
    "put",
    "rather",
    "re",
    "same",
    "see",
    "seem",
    "seemed",
    "seeming",
    "seems",
    "serious",
    "several",
    "she",
    "should",
    "show",
    "side",
    "since",
    "sincere",
    "six",
    "sixty",
    "so",
    "some",
    "somehow",
    "someone",
    "something",
    "sometime",
    "sometimes",
    "somewhere",
    "still",
    "such",
    "system",
    "take",
    "ten",
    "than",
    "that",
    "the",
    "their",
    "them",
    "themselves",
    "then",
    "thence",
    "there",
    "thereafter",
    "thereby",
    "therefore",
    "therein",
    "thereupon",
    "these",
    "they",
    "thick",
    "thin",
    "third",
    "this",
    "those",
    "though",
    "three",
    "through",
    "throughout",
    "thru",
    "thus",
    "to",
    "together",
    "too",
    "top",
    "toward",
    "towards",
    "twelve",
    "twenty",
    "two",
    "un",
    "under",
    "until",
    "up",
    "upon",
    "us",
    "very",
    "via",
    "was",
    "we",
    "well",
    "were",
    "what",
    "whatever",
    "when",
    "whence",
    "whenever",
    "where",
    "whereafter",
    "whereas",
    "whereby",
    "wherein",
    "whereupon",
    "wherever",
    "whether",
    "which",
    "while",
    "whither",
    "who",
    "whoever",
    "whole",
    "whom",
    "whose",
    "why",
    "will",
    "with",
    "within",
    "without",
    "would",
    "yet",
    "you",
    "your",
    "yours",
    "yourself",
    "yourselves",
];

/// Get the stop words set, initializing it on first use
fn get_stop_words() -> &'static HashSet<String> {
    static STOP_WORDS: OnceLock<HashSet<String>> = OnceLock::new();
    STOP_WORDS.get_or_init(|| STOP_WORDS_LIST.iter().map(|s| s.to_string()).collect())
}

/// Normalize and tokenize text, removing stop words
fn tokenize(text: &str) -> Vec<String> {
    // Convert to lowercase and remove punctuation
    let re = Regex::new(r"[^\w\s]").unwrap();
    let lower_text = text.to_lowercase();
    let cleaned = re.replace_all(&lower_text, " ");

    let stop_words = get_stop_words();

    // Split into words and filter
    cleaned
        .split_whitespace()
        .map(|s| s.to_string())
        .filter(|word| {
            // Filter out short words and stop words
            word.len() > 2 && !stop_words.contains(word)
        })
        .collect()
}

/// Extract text content from a JSON value
pub fn extract_text_from_json(value: &serde_json::Value) -> String {
    match value {
        serde_json::Value::String(s) => s.clone(),
        serde_json::Value::Object(map) => {
            let mut texts = Vec::new();

            // Extract from bill object (if present)
            if let Some(bill) = map.get("bill") {
                if let Some(title) = bill.get("title").and_then(|v| v.as_str()) {
                    texts.push(title.to_string());
                }
                if let Some(subjects) = bill.get("subject") {
                    texts.push(extract_text_from_json(subjects));
                }
                if let Some(abstracts) = bill.get("abstracts") {
                    texts.push(extract_text_from_json(abstracts));
                }
                if let Some(session) = bill.get("legislative_session").and_then(|v| v.as_str()) {
                    texts.push(session.to_string());
                }
                if let Some(org) = bill.get("from_organization").and_then(|v| v.as_str()) {
                    texts.push(org.to_string());
                }
            }

            // Extract from log object (if present)
            if let Some(log) = map.get("log") {
                if let Some(action) = log.get("action") {
                    // Extract description from action object
                    if let Some(desc) = action.get("description").and_then(|v| v.as_str()) {
                        texts.push(desc.to_string());
                    }
                    // Or if action is directly a string
                    if let Some(desc_str) = action.as_str() {
                        texts.push(desc_str.to_string());
                    }
                }
                // Also check for bill_id in log
                if let Some(bill_id) = log
                    .get("bill_id")
                    .or_else(|| log.get("bill_identifier"))
                    .and_then(|v| v.as_str())
                {
                    texts.push(bill_id.to_string());
                }
            }

            // Extract from action object directly (if present at top level, e.g., when processing log object)
            if let Some(action) = map.get("action") {
                // Extract description from action object
                if let Some(desc) = action.get("description").and_then(|v| v.as_str()) {
                    texts.push(desc.to_string());
                }
                // Or if action is directly a string
                if let Some(desc_str) = action.as_str() {
                    texts.push(desc_str.to_string());
                }
            }

            // Fallback: extract from all other text fields (excluding metadata)
            for (key, val) in map {
                if !key.starts_with("_")
                    && key != "id"
                    && key != "sources"
                    && key != "timestamp"
                    && key != "bill"
                    && key != "log"
                    && key != "title"
                    && key != "action"
                    && key != "subjects"
                    && key != "abstracts"
                    && key != "legislative_session"
                    && key != "from_organization"
                {
                    if let Some(text) = val.as_str() {
                        texts.push(text.to_string());
                    } else if val.is_object() || val.is_array() {
                        texts.push(extract_text_from_json(val));
                    }
                }
            }

            texts.join(" ")
        }
        serde_json::Value::Array(arr) => arr
            .iter()
            .map(extract_text_from_json)
            .collect::<Vec<_>>()
            .join(" "),
        _ => String::new(),
    }
}

/// Compute term frequency for a document
fn compute_tf(tokens: &[String]) -> HashMap<String, f64> {
    let mut tf = HashMap::new();
    let total = tokens.len() as f64;

    for token in tokens {
        *tf.entry(token.clone()).or_insert(0.0) += 1.0;
    }

    // Normalize by document length
    for count in tf.values_mut() {
        *count /= total;
    }

    tf
}

/// Compute cosine similarity between two TF vectors
fn cosine_similarity(tf1: &HashMap<String, f64>, tf2: &HashMap<String, f64>) -> f64 {
    let mut dot_product = 0.0;
    let mut norm1 = 0.0;
    let mut norm2 = 0.0;

    // Compute dot product and norms
    let all_keys: HashSet<_> = tf1.keys().chain(tf2.keys()).cloned().collect();

    for key in all_keys {
        let v1 = tf1.get(&key).copied().unwrap_or(0.0);
        let v2 = tf2.get(&key).copied().unwrap_or(0.0);

        dot_product += v1 * v2;
        norm1 += v1 * v1;
        norm2 += v2 * v2;
    }

    if norm1 == 0.0 || norm2 == 0.0 {
        return 0.0;
    }

    dot_product / (norm1.sqrt() * norm2.sqrt())
}

/// Calculate similarity score between a tag string and a JSON log entry
/// Returns a score between 0.0 and 1.0
fn calculate_similarity(tag: &str, json_entry: &serde_json::Value) -> f64 {
    // Extract text from JSON entry (focus on log content)
    let entry_text = if let Some(log) = json_entry.get("log") {
        extract_text_from_json(log)
    } else {
        extract_text_from_json(json_entry)
    };

    // Tokenize both tag and entry text
    let tag_tokens = tokenize(tag);
    let entry_tokens = tokenize(&entry_text);

    if tag_tokens.is_empty() || entry_tokens.is_empty() {
        return 0.0;
    }

    // Compute TF vectors
    let tag_tf = compute_tf(&tag_tokens);
    let entry_tf = compute_tf(&entry_tokens);

    // Calculate cosine similarity
    cosine_similarity(&tag_tf, &entry_tf)
}

/// Generate tag matches for a JSON entry given a list of tag strings
/// Returns a vector of (tag_key, similarity_score) tuples sorted by score (descending)
pub fn match_tags(tags: &[String], json_entry: &serde_json::Value) -> Vec<(String, f64)> {
    let mut results: Vec<(String, f64)> = tags
        .iter()
        .map(|tag| {
            let score = calculate_similarity(tag, json_entry);
            (tag.clone(), score)
        })
        .collect();

    // Sort by score descending
    results.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));

    // Filter out very low scores (below 0.1)
    results.retain(|(_, score)| *score >= 0.1);

    results
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tokenize() {
        let text = "This is a sample tokenization function demonstration.";
        let tokens = tokenize(text);
        // Verify meaningful words are kept
        assert!(tokens.contains(&"sample".to_string()));
        assert!(tokens.contains(&"tokenization".to_string()));
        assert!(tokens.contains(&"function".to_string()));
        assert!(tokens.contains(&"demonstration".to_string()));
        // Verify stop words are filtered out
        assert!(!tokens.contains(&"this".to_string())); // stop word
        assert!(!tokens.contains(&"is".to_string())); // stop word
        assert!(!tokens.contains(&"a".to_string())); // stop word
        assert!(!tokens.contains(&"of".to_string())); // stop word
        assert!(!tokens.contains(&"the".to_string())); // stop word
    }

    #[test]
    fn test_similarity() {
        let tag = "education funding";
        let json = serde_json::json!({
            "log": {
                "action": {
                    "description": "Education funding bill passed"
                }
            }
        });

        let score = calculate_similarity(tag, &json);
        assert!(score > 0.0);
        assert!(score <= 1.0);
    }

    #[test]
    fn test_match_tags() {
        let tags = vec![
            "education".to_string(),
            "budget".to_string(),
            "healthcare".to_string(),
        ];

        let json = serde_json::json!({
            "log": {
                "action": {
                    "description": "Education funding bill for schools"
                }
            }
        });

        let matches = match_tags(&tags, &json);
        assert!(!matches.is_empty());
        // Education should have the highest score
        assert_eq!(matches[0].0, "education");
    }
}
