//! Generate the locale enum and each locale's data repos from pipeline-manager's
//! jurisdictions.yml (the single source of truth since the 2026-11 repo reorg).
//! Run with: cargo run --bin generate-locale-enum   (or: just generate)

use serde::Deserialize;
use std::collections::BTreeMap;
use std::fs;
use std::path::PathBuf;

#[derive(Debug, Deserialize)]
struct Jurisdictions {
    orgs: Orgs,
    states: BTreeMap<String, State>,
}

#[derive(Debug, Deserialize)]
struct Orgs {
    data: String,
}

#[derive(Debug, Deserialize)]
struct State {
    #[serde(default)]
    labels: Vec<String>,
    #[serde(default)]
    sessions: Vec<Session>,
    old_repos: OldRepos,
}

#[derive(Debug, Deserialize)]
struct Session {
    id: serde_yaml::Value,
}

#[derive(Debug, Deserialize)]
struct OldRepos {
    data: String,
}

/// <state>-<id> lower-cased; characters outside [a-z0-9._-] become '-'
/// (the same rule as pipeline-manager's jurisdictions.py `pair_key`).
fn pair_key(state: &str, id: &str) -> String {
    format!("{}-{}", state, id)
        .to_lowercase()
        .chars()
        .map(|c| if c.is_ascii_lowercase() || c.is_ascii_digit() || "._-".contains(c) { c } else { '-' })
        .collect()
}

fn session_id(value: &serde_yaml::Value) -> String {
    match value {
        serde_yaml::Value::String(s) => s.clone(),
        other => serde_yaml::to_string(other).unwrap_or_default().trim().to_string(),
    }
}

/// (owner/name, local folder) of every data repo of a state: the old one-repo-per-state
/// repo first (folder `<st>-legislation`, as before), then each session pair (folder =
/// the repo's own name).
fn data_repos(orgs: &Orgs, code: &str, state: &State) -> Vec<(String, String)> {
    let mut repos = vec![(state.old_repos.data.clone(), format!("{}-legislation", code))];
    for session in &state.sessions {
        let key = pair_key(code, &session_id(&session.id));
        repos.push((format!("{}/{}", orgs.data, key), key));
    }
    repos
}

fn locale_to_variant(locale: &str) -> String {
    // Two-letter codes should be uppercase (e.g., 'ar' -> 'AR', 'pr' -> 'PR')
    // Longer codes should be capitalized (e.g., 'usa' -> 'Usa')
    if locale.len() <= 2 {
        locale.to_uppercase()
    } else {
        let mut chars = locale.chars();
        match chars.next() {
            None => String::new(),
            Some(first) => first.to_uppercase().collect::<String>() + chars.as_str(),
        }
    }
}

fn get_working_locales(config: &Jurisdictions) -> Vec<String> {
    // BTreeMap: already sorted
    config
        .states
        .iter()
        .filter(|(_, state)| state.labels.contains(&"working".to_string()))
        .map(|(code, _)| code.clone())
        .collect()
}

fn generate_rust_enum(
    locales: &[String],
    config: &Jurisdictions,
    output_path: &PathBuf,
) -> Result<(), Box<dyn std::error::Error>> {
    // Create mapping of locale -> variant name
    let locale_variants: Vec<(String, String)> = locales
        .iter()
        .map(|loc| (loc.clone(), locale_to_variant(loc)))
        .collect();

    // Generate enum variants
    let enum_variants: Vec<String> = locale_variants
        .iter()
        .map(|(_, variant)| format!("    {},", variant))
        .collect();

    // Generate match arms for as_str
    let as_str_arms: Vec<String> = locale_variants
        .iter()
        .map(|(locale, variant)| {
            format!("            WorkingLocale::{} => \"{}\",", variant, locale)
        })
        .collect();

    // Generate match arms for as_lowercase
    let as_lowercase_arms: Vec<String> = locale_variants
        .iter()
        .map(|(locale, variant)| {
            format!(
                "            WorkingLocale::{} => \"{}\",",
                variant,
                locale.to_lowercase()
            )
        })
        .collect();

    // Generate match arms for From<&str>
    let from_str_arms: Vec<String> = locale_variants
        .iter()
        .map(|(locale, variant)| {
            format!(
                "            \"{}\" => WorkingLocale::{},",
                locale.to_lowercase(),
                variant
            )
        })
        .collect();

    // Generate all() vector items
    let all_items: Vec<String> = locale_variants
        .iter()
        .map(|(_, variant)| format!("            WorkingLocale::{},", variant))
        .collect();

    // data_repos(): one match arm per working locale; locale_for_folder(): the reverse.
    let mut repo_arms = Vec::new();
    let mut folder_arms = Vec::new();
    for locale in locales {
        let repos = data_repos(&config.orgs, locale, &config.states[locale]);
        let items: Vec<String> = repos
            .iter()
            .map(|(full, folder)| format!("(\"{}\", \"{}\")", full, folder))
            .collect();
        repo_arms.push(format!("        \"{}\" => &[{}],", locale, items.join(", ")));
        for (_, folder) in &repos {
            folder_arms.push(format!("        \"{}\" => Some(\"{}\"),", folder, locale));
        }
    }

    let rust_code = format!(
        r#"//! Auto-generated from pipeline-manager jurisdictions.yml: locales and their data repos
//! This file is generated by src/bin/generate-locale-enum.rs
//! Do not edit manually - regenerate using: just generate

/// Locale codes for working pipelines
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum WorkingLocale {{
    All,
{}
}}

impl WorkingLocale {{
    /// Get all working locales as a vector (excludes All variant)
    pub fn all() -> Vec<Self> {{
        vec![
{}
        ]
    }}
    
    /// Get the locale code as a string
    pub fn as_str(&self) -> &'static str {{
        match self {{
            WorkingLocale::All => "all",
{}
        }}
    }}
    
    /// Get the locale code in lowercase
    pub fn as_lowercase(&self) -> &'static str {{
        match self {{
            WorkingLocale::All => "all",
{}
        }}
    }}
}}

impl From<&str> for WorkingLocale {{
    fn from(s: &str) -> Self {{
        match s.to_lowercase().as_str() {{
            "all" => WorkingLocale::All,
{}
            _ => panic!("Invalid working locale: {{}}", s),
        }}
    }}
}}

impl std::fmt::Display for WorkingLocale {{
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {{
        write!(f, "{{}}", self.as_lowercase())
    }}
}}

/// Every data repo of a locale as (owner/name, local folder): the old one-repo-per-state
/// repo first (folder `<locale>-legislation`), then each session pair (folder = repo name).
/// Empty for a locale jurisdictions.yml doesn't list as working.
pub fn data_repos(locale: &str) -> &'static [(&'static str, &'static str)] {{
    match locale {{
{}
        _ => &[],
    }}
}}

/// The locale a local repo folder belongs to (the reverse of data_repos).
pub fn locale_for_folder(folder: &str) -> Option<&'static str> {{
    match folder {{
{}
        _ => None,
    }}
}}
"#,
        enum_variants.join("\n"),
        all_items.join("\n"),
        as_str_arms.join("\n"),
        as_lowercase_arms.join("\n"),
        from_str_arms.join("\n"),
        repo_arms.join("\n"),
        folder_arms.join("\n")
    );

    fs::write(output_path, rust_code)?;
    Ok(())
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // actions/govbot -> actions/pipeline-manager/jurisdictions.yml
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let config_path = manifest_dir
        .parent()
        .unwrap()
        .join("pipeline-manager")
        .join("jurisdictions.yml");
    let output_path = manifest_dir.join("src").join("locale_generated.rs");

    if !config_path.exists() {
        eprintln!("❌ Error: Config file not found at {}", config_path.display());
        std::process::exit(1);
    }

    let config: Jurisdictions = serde_yaml::from_str(&fs::read_to_string(&config_path)?)?;
    let locales = get_working_locales(&config);
    if locales.is_empty() {
        eprintln!("⚠️  Warning: No working locales found in config");
    }

    generate_rust_enum(&locales, &config, &output_path)?;
    println!(
        "✅ Generated {} with {} working locales",
        output_path.display(),
        locales.len()
    );
    println!("📋 Working locales: {}", locales.join(", "));

    Ok(())
}
