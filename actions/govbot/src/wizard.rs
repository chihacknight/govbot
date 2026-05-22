use anyhow::Result;
use dialoguer::{Input, Select};
use std::fs;
use std::path::Path;

/// Represents the user's choices during the wizard.
/// Used both by the interactive wizard and by tests to simulate different paths.
pub struct WizardChoices {
    /// The datasets the project consumes (`govbot.yml: datasets:`).
    pub datasets: Vec<String>,
    /// Base URL for the RSS/HTML publisher.
    pub base_url: String,
}

/// Captures the full wizard session output: what the user sees at each step,
/// plus the generated files. This makes the entire wizard experience snapshotable.
pub struct WizardSession {
    /// The text shown during the wizard (prompts, guidance, etc.)
    pub display: String,
    /// The generated govbot.yml content
    pub govbot_yml: String,
    /// The generated GitHub Actions workflow content
    pub workflow_yml: String,
}

impl WizardSession {
    /// Render a complete wizard session from a set of choices.
    /// This is deterministic and requires no interactive input.
    pub fn from_choices(choices: &WizardChoices) -> Self {
        let mut display = String::new();

        // Welcome
        display.push_str("Welcome to govbot! Let's set up your project.\n\n");

        // Step 1: Datasets
        display.push_str("? What datasets do you want to track?\n");
        if choices.datasets == ["all"] {
            display.push_str("> All jurisdictions in the registry\n");
            display.push_str("  Select specific datasets\n");
        } else {
            display.push_str("  All jurisdictions in the registry\n");
            display.push_str("> Select specific datasets\n");
            display.push('\n');
            display.push_str("Browse the registry with `govbot search`.\n");
            display.push('\n');
            display.push_str(&format!(
                "? Enter dataset ids separated by spaces: {}\n",
                choices.datasets.join(" ")
            ));
        }
        display.push('\n');

        // Step 2: Classification (a separate fastclass bundle, not govbot.yml)
        display.push_str("Classification is done by fastclass against a classifier bundle.\n");
        display.push_str("Point the manifest's `transforms.classify.classifier` at your\n");
        display.push_str("bundle directory (containing classifier.yml). See the fastclass\n");
        display.push_str("docs to build one.\n\n");

        // Step 3: Publishing
        display.push_str("Publishing is configured for an RSS feed by default.\n");
        display.push_str("Your feed will be generated in the \"docs\" directory.\n\n");
        display.push_str(&format!(
            "? Base URL for your feed: {}\n\n",
            choices.base_url
        ));

        // Summary
        display.push_str("  ✓ Created govbot.yml\n");
        display.push_str("  ✓ Created .gitignore\n");
        display.push_str("  ✓ Created .github/workflows/build.yml\n\n");
        display.push_str("Setup complete! Run 'govbot' again to start the pipeline.\n");

        let govbot_yml = generate_govbot_yml(&choices.datasets, &choices.base_url);
        let workflow_yml = github_workflow_content().to_string();

        WizardSession {
            display,
            govbot_yml,
            workflow_yml,
        }
    }

    /// Write the generated files (govbot.yml, .gitignore, workflow) to disk.
    pub fn write_files(&self, dir: &std::path::Path) -> Result<()> {
        // Write govbot.yml
        let config_path = dir.join("govbot.yml");
        fs::write(&config_path, &self.govbot_yml)?;
        eprintln!("  ✓ Created govbot.yml");

        // Write .gitignore
        write_gitignore(dir)?;

        // Write GitHub Actions workflow
        write_github_workflow(dir)?;

        Ok(())
    }

    /// Render the full session as a single string for snapshot testing.
    /// Shows exactly what a user would experience for this set of choices.
    pub fn to_snapshot(&self) -> String {
        let mut out = String::new();
        out.push_str("=== Wizard Session ===\n\n");
        out.push_str(&self.display);
        out.push_str("\n=== Generated: govbot.yml ===\n\n");
        out.push_str(&self.govbot_yml);
        out.push_str("\n=== Generated: .github/workflows/build.yml ===\n\n");
        out.push_str(&self.workflow_yml);
        out
    }
}

/// Generate default govbot.yml and supporting files without interactive prompts.
/// Used when `govbot init` is run in a non-interactive terminal.
pub fn write_default_files(dir: &Path) -> Result<()> {
    let choices = WizardChoices {
        datasets: vec!["all".to_string()],
        base_url: "https://example.com".to_string(),
    };
    let session = WizardSession::from_choices(&choices);
    session.write_files(dir)?;

    eprintln!();
    eprintln!("Setup complete! Edit govbot.yml to customize, then run 'govbot' to start.");
    eprintln!();

    Ok(())
}

/// Run the interactive setup wizard to create govbot.yml and supporting files.
pub fn run_wizard() -> Result<()> {
    // Check if stdin is a terminal - wizard requires interactive input
    if !std::io::IsTerminal::is_terminal(&std::io::stdin()) {
        eprintln!("No govbot.yml found in current directory.");
        eprintln!("Run 'govbot' in an interactive terminal to launch the setup wizard.");
        return Ok(());
    }

    eprintln!();
    eprintln!("Welcome to govbot! Let's set up your project.");
    eprintln!();

    // Step 1: Datasets
    let datasets = prompt_sources()?;

    // Step 2: Classification — handled by a separate fastclass bundle.
    eprintln!();
    eprintln!("Classification is done by fastclass against a classifier bundle.");
    eprintln!("Point the manifest's `transforms.classify.classifier` at your");
    eprintln!("bundle directory (containing classifier.yml).");

    // Step 3: Publishing info
    let base_url = prompt_publishing()?;

    // Generate and write files
    let cwd = std::env::current_dir()?;
    let choices = WizardChoices { datasets, base_url };
    let session = WizardSession::from_choices(&choices);
    session.write_files(&cwd)?;

    eprintln!();
    eprintln!("Setup complete! Run 'govbot' again to start the pipeline.");
    eprintln!();

    Ok(())
}

fn prompt_sources() -> Result<Vec<String>> {
    let options = vec![
        "All jurisdictions in the registry",
        "Select specific datasets",
    ];

    let selection = Select::new()
        .with_prompt("What data sources do you want to track?")
        .items(&options)
        .default(0)
        .interact()?;

    if selection == 0 {
        return Ok(vec!["all".to_string()]);
    }

    // List the registry's datasets so the user can pick from them.
    let cwd = std::env::current_dir().unwrap_or_else(|_| std::path::PathBuf::from("."));
    if let Ok(registry) = crate::registry::Registry::load(&cwd) {
        let ids: Vec<String> = registry
            .all()
            .iter()
            .map(|d| d.short_name().to_string())
            .collect();
        eprintln!();
        eprintln!("Available datasets ({}):", ids.len());
        for chunk in ids.chunks(10) {
            eprintln!("  {}", chunk.join(", "));
        }
        eprintln!();
        eprintln!("Tip: `govbot search <query>` searches the registry.");
        eprintln!();
    }

    let input: String = Input::new()
        .with_prompt("Enter dataset ids separated by spaces (e.g., il ca ny)")
        .interact_text()?;

    let repos: Vec<String> = input
        .split_whitespace()
        .map(|s| s.trim().to_lowercase())
        .filter(|s| !s.is_empty())
        .collect();

    if repos.is_empty() {
        Ok(vec!["all".to_string()])
    } else {
        Ok(repos)
    }
}

fn prompt_publishing() -> Result<String> {
    eprintln!();
    eprintln!("Publishing is configured for RSS feeds by default.");
    eprintln!("Your feeds will be generated in the \"docs\" directory.");
    eprintln!();

    let base_url: String = Input::new()
        .with_prompt("Base URL for your feeds (e.g., https://username.github.io/repo-name)")
        .default("https://example.com".to_string())
        .interact_text()?;

    Ok(base_url)
}

/// Generate a `govbot.yml` manifest from wizard answers.
///
/// The manifest declares `datasets` + `transforms` + `publish` + `pipelines` —
/// it is NOT a classifier. The tag taxonomy lives in a separate fastclass
/// classifier bundle that `transforms.classify.classifier` references by path.
/// This is a pure function for easy testing.
pub fn generate_govbot_yml(datasets: &[String], base_url: &str) -> String {
    let mut yml = String::new();

    yml.push_str("# Govbot Manifest\n");
    yml.push_str("# Schema: https://raw.githubusercontent.com/chihacknight/govbot/main/schemas/govbot.schema.json\n");
    yml.push_str("$schema: https://raw.githubusercontent.com/chihacknight/govbot/main/schemas/govbot.schema.json\n\n");

    // datasets — the government-data sources this project consumes.
    yml.push_str("datasets:\n");
    for dataset in datasets {
        yml.push_str(&format!("  - {}\n", dataset));
    }
    yml.push('\n');

    // transforms — external processes speaking the govbot stream protocol.
    // The classify transform shells out to fastclass; point `classifier:` at
    // your fastclass classifier bundle directory (containing classifier.yml).
    yml.push_str("transforms:\n");
    yml.push_str("  classify:\n");
    yml.push_str("    command: [fastclass, classify, \"-\"]\n");
    yml.push_str("    reads: docs\n");
    yml.push_str("    writes: classification\n");
    yml.push_str("    # Path to your fastclass classifier bundle (containing classifier.yml).\n");
    yml.push_str("    classifier: ./classifier\n");
    yml.push('\n');

    // publish — a publisher consumes the result stream and emits artifacts.
    yml.push_str("publish:\n");
    yml.push_str("  feed:\n");
    yml.push_str("    type: rss\n");
    yml.push_str(&format!("    base_url: \"{}\"\n", base_url));
    yml.push_str("    output_dir: \"docs\"\n");
    yml.push_str("    output_file: \"feed.xml\"\n");
    yml.push('\n');

    // pipelines — named `govbot run` targets, npm-script style.
    yml.push_str("pipelines:\n");
    yml.push_str("  default:\n");
    yml.push_str("    - classify\n");
    yml.push_str("    - feed\n");

    yml
}

/// Write .gitignore with govbot's generated dirs and secret-bearing files.
///
/// Everything under `.govbot/` (cloned datasets, ledgers, lockfile state),
/// every publisher output dir (`dist/`, `docs/`), and any local `.env` is
/// untracked. The userland repo is a few dozen text files plus tool artifacts;
/// the artifacts never belong in git.
pub fn write_gitignore(cwd: &Path) -> Result<()> {
    let gitignore_path = cwd.join(".gitignore");
    // Single canonical block — easy to grep, easy to update.
    let block = "\
# govbot — generated, reconstructed on every run
.govbot/
dist/
docs/

# Secrets — never commit
.env
";

    // Idempotency: only append entries that are not already present.
    let existing = if gitignore_path.exists() {
        fs::read_to_string(&gitignore_path)?
    } else {
        String::new()
    };

    let mut updated = existing.clone();
    let mut added = Vec::new();
    for line in block.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        if !existing.lines().any(|l| l.trim() == trimmed) {
            if !updated.is_empty() && !updated.ends_with('\n') {
                updated.push('\n');
            }
            updated.push_str(line);
            updated.push('\n');
            added.push(trimmed.to_string());
        }
    }

    if existing.is_empty() {
        fs::write(&gitignore_path, block)?;
        eprintln!("  ✓ Created .gitignore");
    } else if !added.is_empty() {
        fs::write(&gitignore_path, &updated)?;
        eprintln!("  ✓ Updated .gitignore ({} entries added)", added.len());
    } else {
        eprintln!("  ✓ .gitignore already covers govbot's generated dirs");
    }

    Ok(())
}

fn github_workflow_content() -> &'static str {
    r#"# Run Govbot
# Runs govbot to pull datasets, apply classifications, and publish feeds.

name: Build Govbot

on:
  push:
    branches:
      - main
      - master
  schedule:
    - cron: '0 0 * * *'
  workflow_dispatch:
    inputs:
      limit:
        description: 'Limit number of entries per artifact (default: 100, use "none" for all)'
        required: false
        type: string

jobs:
  govbot:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Run Govbot
        uses: chihacknight/govbot/actions/govbot@main
        with:
          limit: ${{ inputs.limit }}
"#
}

/// Write GitHub Actions workflow file
pub fn write_github_workflow(cwd: &Path) -> Result<()> {
    let workflows_dir = cwd.join(".github").join("workflows");
    fs::create_dir_all(&workflows_dir)?;

    let workflow_path = workflows_dir.join("build.yml");
    fs::write(&workflow_path, github_workflow_content())?;
    eprintln!("  ✓ Created .github/workflows/build.yml");

    Ok(())
}
