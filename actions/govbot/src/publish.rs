use crate::config::{Manifest, Publisher, PublisherKind};
use crate::rss;
use anyhow::{Context, Result};
use serde_json::Value;
use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};

/// Load and parse the `govbot.yml` manifest (datasets / transforms / publish /
/// pipelines). A manifest carrying the retired `tags:` block fails to parse.
pub fn load_manifest(config_path: &Path) -> Result<Manifest> {
    Manifest::load(config_path)
}

/// A resolved publishing job: a publisher definition plus the result stream
/// (already filtered, deduplicated, sorted, and limited) it should emit.
pub struct PublishJob<'a> {
    /// The publisher name from `govbot.yml: publish:`.
    pub name: &'a str,
    /// The typed publisher definition.
    pub publisher: &'a Publisher,
    /// The records to publish — the result stream this publisher consumes.
    pub entries: Vec<Value>,
    /// Output directory override (CLI `--output-dir`).
    pub output_dir_override: Option<String>,
    /// Output filename override (CLI `--output-file`).
    pub output_file_override: Option<String>,
    /// The project directory (where `govbot.yml` lives). Stateful publishers
    /// (e.g. `bluesky`'s posted-state ledger) resolve relative paths here.
    pub project_dir: PathBuf,
    /// `--dry-run`: render but do not emit. The `bluesky` publisher honours
    /// this by touching no network and no ledger.
    pub dry_run: bool,
}

/// Run a single publisher against its result stream and emit artifacts.
///
/// govbot's built-in publishers each consume the result stream and emit
/// artifacts: `rss`/`html` write a feed + HTML index, `json` writes a JSON
/// dump, `duckdb` loads the records into a DuckDB database, and `bluesky`
/// posts matched bills to a Bluesky account (see `crate::bluesky`).
pub fn run_publisher(job: &PublishJob) -> Result<()> {
    let p = job.publisher;
    let select = p.select.clone().unwrap_or_default();

    let output_dir = PathBuf::from(
        job.output_dir_override
            .clone()
            .or_else(|| p.output_dir.clone())
            .unwrap_or_else(|| "docs".to_string()),
    );

    match p.kind {
        PublisherKind::Rss | PublisherKind::Html => {
            emit_rss_html(job, &select, &output_dir)
        }
        PublisherKind::Json => emit_json(job, &output_dir),
        PublisherKind::Duckdb => emit_duckdb(job, &output_dir),
        PublisherKind::Bluesky => crate::bluesky::run_bluesky(job, job.dry_run),
    }
}

/// Title-case a tag name (`clean_energy` -> `Clean Energy`).
fn titlecase_tag(tag: &str) -> String {
    tag.replace('_', " ")
        .split_whitespace()
        .map(|w| {
            let mut chars = w.chars();
            match chars.next() {
                None => String::new(),
                Some(f) => f.to_uppercase().collect::<String>() + chars.as_str(),
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}

/// The `rss`/`html` publisher: a combined RSS feed + HTML index.
fn emit_rss_html(job: &PublishJob, select: &[String], output_dir: &Path) -> Result<()> {
    let p = job.publisher;

    let output_file = job
        .output_file_override
        .clone()
        .or_else(|| p.output_file.clone())
        .unwrap_or_else(|| "feed.xml".to_string());

    let feed_link = p.base_url.as_deref().unwrap_or("https://example.com");

    // Auto-derive a title from the selected tags when none is configured.
    let feed_title = p.title.clone().unwrap_or_else(|| {
        if select.is_empty() {
            "Legislation".to_string()
        } else {
            format!(
                "{} Legislation",
                select.iter().map(|t| titlecase_tag(t)).collect::<Vec<_>>().join(" & ")
            )
        }
    });

    // The auto-description previously read each tag's `description` from
    // `govbot.yml`; that taxonomy data now lives in the fastclass bundle, not
    // here. Fall back to a simple tag-name-derived description.
    let feed_description = p.description.clone().unwrap_or_else(|| {
        if select.is_empty() {
            "Legislative updates".to_string()
        } else {
            format!(
                "Legislative updates tagged {}",
                select.iter().map(|t| titlecase_tag(t)).collect::<Vec<_>>().join(", ")
            )
        }
    });

    fs::create_dir_all(output_dir)
        .with_context(|| format!("Failed to create output dir: {}", output_dir.display()))?;

    eprintln!("Generating RSS feed with {} entries...", job.entries.len());
    let rss_xml = rss::json_to_rss(
        job.entries.clone(),
        &feed_title,
        &feed_description,
        feed_link,
        Some(feed_link),
        "en-us",
    );
    let rss_path = output_dir.join(&output_file);
    fs::write(&rss_path, rss_xml)?;
    eprintln!("✓ Generated RSS feed: {}", rss_path.display());

    eprintln!("Generating HTML index with {} entries...", job.entries.len());
    // Only pass an explicit (configured) title to the HTML header.
    let html_title = p.title.as_deref().filter(|s| !s.trim().is_empty());
    let html = rss::json_to_html(job.entries.clone(), html_title, feed_link, Some(feed_link));
    let html_path = output_dir.join("index.html");
    fs::write(&html_path, html)?;
    eprintln!("✓ Generated HTML index: {}", html_path.display());
    Ok(())
}

/// The `json` publisher: a JSON dump of the result stream.
fn emit_json(job: &PublishJob, output_dir: &Path) -> Result<()> {
    let output_file = job
        .output_file_override
        .clone()
        .or_else(|| job.publisher.output_file.clone())
        .unwrap_or_else(|| "feed.json".to_string());

    fs::create_dir_all(output_dir)
        .with_context(|| format!("Failed to create output dir: {}", output_dir.display()))?;
    let path = output_dir.join(&output_file);
    fs::write(&path, serde_json::to_string_pretty(&job.entries)?)?;
    eprintln!(
        "✓ Generated JSON dump ({} entries): {}",
        job.entries.len(),
        path.display()
    );
    Ok(())
}

/// The `duckdb` publisher: load the result stream into a DuckDB database by
/// writing the records to a JSON file and `read_json_auto`-ing them.
fn emit_duckdb(job: &PublishJob, output_dir: &Path) -> Result<()> {
    use std::process::Command;

    let db_file = job
        .output_file_override
        .clone()
        .or_else(|| job.publisher.output_file.clone())
        .unwrap_or_else(|| "feed.duckdb".to_string());

    fs::create_dir_all(output_dir)
        .with_context(|| format!("Failed to create output dir: {}", output_dir.display()))?;
    let db_path = output_dir.join(&db_file);
    let json_path = output_dir.join(format!("{}.records.json", job.name));
    fs::write(&json_path, serde_json::to_string(&job.entries)?)?;

    let sql = format!(
        "CREATE OR REPLACE TABLE records AS SELECT * FROM read_json_auto('{}');",
        json_path.display()
    );
    let status = Command::new("duckdb")
        .arg(db_path.to_string_lossy().as_ref())
        .arg("-c")
        .arg(&sql)
        .status()
        .context("Failed to run `duckdb` — is the DuckDB CLI installed?")?;
    if !status.success() {
        anyhow::bail!("duckdb publisher '{}' failed", job.name);
    }
    eprintln!(
        "✓ Loaded {} entries into DuckDB: {}",
        job.entries.len(),
        db_path.display()
    );
    Ok(())
}

/// Filter entries by tags
/// Only includes entries that have tags (excludes untagged entries)
/// If tag_names is empty, includes any entry that has tags
/// If tag_names are specified, only includes entries that have at least one matching tag
pub fn filter_by_tags(entry: &Value, tag_names: &[String]) -> bool {
    // Get tags from entry - if no tags field exists, exclude it
    let tags = match entry.get("tags").and_then(|t| t.as_object()) {
        Some(tags) => tags,
        None => {
            // Entry has no tags field - exclude it (only include tagged entries)
            return false;
        }
    };

    // If tags object is empty, exclude it (only include entries with actual tags)
    if tags.is_empty() {
        return false;
    }

    // If no specific tags requested, include any entry that has tags
    if tag_names.is_empty() {
        return true;
    }

    // Check if any specified tag matches
    for tag_name in tag_names {
        if tags.contains_key(tag_name) {
            return true;
        }
    }

    // Entry has tags but none match the specified tags - exclude it
    false
}

/// Deduplicate entries by GUID
pub fn deduplicate_entries(entries: Vec<Value>) -> Vec<Value> {
    let mut seen = HashSet::new();
    let mut result = Vec::new();

    for entry in entries {
        let guid = rss::extract_guid(&entry);
        if !seen.contains(&guid) {
            seen.insert(guid);
            result.push(entry);
        }
    }

    result
}

/// Sort entries by timestamp (newest first)
pub fn sort_by_timestamp(mut entries: Vec<Value>) -> Vec<Value> {
    entries.sort_by(|a, b| {
        let ts_a = a.get("timestamp").and_then(|t| t.as_str()).unwrap_or("");
        let ts_b = b.get("timestamp").and_then(|t| t.as_str()).unwrap_or("");
        ts_b.cmp(ts_a) // Reverse order (newest first)
    });
    entries
}
