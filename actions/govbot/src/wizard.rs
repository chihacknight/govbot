use anyhow::Result;
use dialoguer::{Input, Select};
use std::fs;
use std::path::Path;

/// Represents the user's choices during the wizard.
/// Used both by the interactive wizard and by tests to simulate different paths.
pub struct WizardChoices {
    pub repos: Vec<String>,
    pub include_example_tag: bool,
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

        // Step 1: Sources
        display.push_str("? What data sources do you want to track?\n");
        if choices.repos == ["all"] {
            display.push_str("> All states (47 jurisdictions)\n");
            display.push_str("  Select specific states\n");
        } else {
            display.push_str("  All states (47 jurisdictions)\n");
            display.push_str("> Select specific states\n");
            display.push('\n');
            display.push_str("Available states/jurisdictions:\n");
            let all_locales = crate::locale::WorkingLocale::all();
            let locale_strs: Vec<String> = all_locales.iter().map(|l| l.as_str().to_string()).collect();
            for chunk in locale_strs.chunks(10) {
                display.push_str(&format!("  {}\n", chunk.join(", ")));
            }
            display.push('\n');
            display.push_str(&format!("? Enter state codes separated by spaces: {}\n", choices.repos.join(" ")));
        }
        display.push('\n');

        // Step 2: Tags
        display.push_str("Tags let govbot categorize legislation by topics you care about.\n");
        display.push_str("Here's an example tag definition:\n\n");
        display.push_str("  education:\n");
        display.push_str("    description: |\n");
        display.push_str("      Legislation related to schools, education funding,\n");
        display.push_str("      curriculum standards, and educational policy.\n");
        display.push_str("    examples:\n");
        display.push_str("      - \"Increases per-pupil funding for public schools\"\n");
        display.push_str("      - \"Mandates comprehensive sex education curriculum\"\n\n");

        display.push_str("? How would you like to set up tags?\n");
        if choices.include_example_tag {
            display.push_str("> Use the example \"education\" tag to start\n");
            display.push_str("  I'll create my own tags later\n");
        } else {
            display.push_str("  Use the example \"education\" tag to start\n");
            display.push_str("> I'll create my own tags later\n");
            display.push('\n');
            display.push_str(&ai_prompt_template());
        }
        display.push('\n');

        // Step 3: Publishing
        display.push_str("Publishing is configured for RSS feeds by default.\n");
        display.push_str("Your feeds will be generated in the \"docs\" directory.\n\n");
        display.push_str(&format!("? Base URL for your feeds: {}\n\n", choices.base_url));

        // Summary
        display.push_str("  ✓ Created govbot.yml\n");
        display.push_str("  ✓ Created .gitignore with .govbot\n");
        display.push_str("  ✓ Created .github/workflows/build.yml\n\n");
        display.push_str("Setup complete! Run 'govbot' again to start the pipeline.\n");

        let govbot_yml = generate_govbot_yml(&choices.repos, choices.include_example_tag, &choices.base_url);
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

/// The AI prompt template shown when users choose to create their own tags.
pub fn ai_prompt_template() -> String {
    let mut s = String::new();
    s.push_str("To create a tag, copy this prompt into your preferred AI tool:\n\n");
    s.push_str("---\n");
    s.push_str("Create a govbot tag definition in YAML for tracking [YOUR TOPIC] legislation.\n");
    s.push_str("The tag should have:\n");
    s.push_str("- A description (multiline, covering subtopics)\n");
    s.push_str("- 2-3 example bill descriptions that would match\n");
    s.push_str("- Optional: include_keywords and exclude_keywords lists\n\n");
    s.push_str("Format:\n");
    s.push_str("  tag_name:\n");
    s.push_str("    description: |\n");
    s.push_str("      ...\n");
    s.push_str("    examples:\n");
    s.push_str("      - \"...\"\n");
    s.push_str("    include_keywords:\n");
    s.push_str("      - keyword1\n");
    s.push_str("    exclude_keywords:\n");
    s.push_str("      - keyword1\n");
    s.push_str("---\n\n");
    s.push_str("Paste the result into your govbot.yml under the 'tags:' section.\n");
    s
}

/// Generate default govbot.yml and supporting files without interactive prompts.
/// Used when `govbot init` is run in a non-interactive terminal.
pub fn write_default_files(dir: &Path) -> Result<()> {
    let choices = WizardChoices {
        repos: vec!["all".to_string()],
        include_example_tag: true,
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

    // Step 1: Sources
    let repos = prompt_sources()?;

    // Step 2: Tags
    let include_example_tag = prompt_tags()?;

    // Step 3: Publishing info
    let base_url = prompt_publishing()?;

    // Generate and write files
    let cwd = std::env::current_dir()?;
    let choices = WizardChoices {
        repos,
        include_example_tag,
        base_url,
    };
    let session = WizardSession::from_choices(&choices);
    session.write_files(&cwd)?;

    eprintln!();
    eprintln!("Setup complete! Run 'govbot' again to start the pipeline.");
    eprintln!();

    Ok(())
}

fn prompt_sources() -> Result<Vec<String>> {
    let options = vec![
        "All states (47 jurisdictions)",
        "Select specific states",
    ];

    let selection = Select::new()
        .with_prompt("What data sources do you want to track?")
        .items(&options)
        .default(0)
        .interact()?;

    if selection == 0 {
        return Ok(vec!["all".to_string()]);
    }

    // Show available states and let user type them
    let all_locales = crate::locale::WorkingLocale::all();
    let locale_strs: Vec<String> = all_locales.iter().map(|l| l.as_str().to_string()).collect();

    eprintln!();
    eprintln!("Available states/jurisdictions:");
    for chunk in locale_strs.chunks(10) {
        eprintln!("  {}", chunk.join(", "));
    }
    eprintln!();

    let input: String = Input::new()
        .with_prompt("Enter state codes separated by spaces (e.g., il ca ny)")
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

fn prompt_tags() -> Result<bool> {
    eprintln!();
    eprintln!("Tags let govbot categorize legislation by topics you care about.");
    eprintln!("Here's an example tag definition:");
    eprintln!();
    eprintln!("  education:");
    eprintln!("    description: |");
    eprintln!("      Legislation related to schools, education funding,");
    eprintln!("      curriculum standards, and educational policy.");
    eprintln!("    examples:");
    eprintln!("      - \"Increases per-pupil funding for public schools\"");
    eprintln!("      - \"Mandates comprehensive sex education curriculum\"");
    eprintln!();

    let options = vec![
        "Use the example \"education\" tag to start",
        "I'll create my own tags later",
    ];

    let selection = Select::new()
        .with_prompt("How would you like to set up tags?")
        .items(&options)
        .default(0)
        .interact()?;

    if selection == 1 {
        let template = ai_prompt_template();
        for line in template.lines() {
            eprintln!("{}", line);
        }
        eprintln!();
    }

    Ok(selection == 0)
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

/// Generate govbot.yml content from wizard answers.
/// This is a pure function for easy testing.
pub fn generate_govbot_yml(repos: &[String], include_example_tag: bool, base_url: &str) -> String {
    let mut yml = String::new();

    yml.push_str("# Govbot Configuration\n");
    yml.push_str("# Schema: https://raw.githubusercontent.com/windy-civi/toolkit/main/schemas/govbot.schema.json\n");
    yml.push_str("$schema: https://raw.githubusercontent.com/windy-civi/toolkit/main/schemas/govbot.schema.json\n\n");

    // Repos section
    yml.push_str("repos:\n");
    for repo in repos {
        yml.push_str(&format!("  - {}\n", repo));
    }
    yml.push('\n');

    // Tags section
    yml.push_str("tags:\n");
    if include_example_tag {
        yml.push_str("  education:\n");
        yml.push_str("    description: |\n");
        yml.push_str("      Legislation related to schools, education funding, curriculum standards, and educational policy, including:\n");
        yml.push_str("      - K-12 public school funding, budgets, and resource allocation\n");
        yml.push_str("      - Curriculum standards, content requirements, and academic programs\n");
        yml.push_str("      - Teacher certification, training, professional development, and compensation\n");
        yml.push_str("      - Higher education policy, tuition, financial aid, and student loans\n");
        yml.push_str("      - Charter schools, school choice, vouchers, and alternative education models\n");
        yml.push_str("      - Special education services, accommodations, and individualized education plans\n");
        yml.push_str("      - School safety, security measures, and student discipline policies\n");
        yml.push_str("      - Early childhood education, pre-K programs, and childcare\n");
        yml.push_str("      - Standardized testing, assessments, and accountability measures\n");
        yml.push_str("      - School district governance, administration, and oversight\n");
        yml.push_str("      - Educational technology, digital learning, and online education\n");
        yml.push_str("      - Career and technical education, vocational training, and workforce development\n");
        yml.push_str("    examples:\n");
        yml.push_str("      - \"Increases per-pupil funding for public schools and establishes minimum teacher salary requirements\"\n");
        yml.push_str("      - \"Mandates comprehensive sex education curriculum in all public schools\"\n");
        yml.push_str("      - \"Expands eligibility for state financial aid programs to include part-time students\"\n");
    } else {
        yml.push_str("  # Add your tags here. Example:\n");
        yml.push_str("  # my_topic:\n");
        yml.push_str("  #   description: |\n");
        yml.push_str("  #     Legislation related to ...\n");
        yml.push_str("  #   examples:\n");
        yml.push_str("  #     - \"Example bill description\"\n");
        yml.push_str("  {}\n");
    }
    yml.push('\n');

    // Build section
    yml.push_str("build:\n");
    yml.push_str(&format!("  base_url: \"{}\"\n", base_url));
    yml.push_str("  output_dir: \"docs\"\n");
    yml.push_str("  output_file: \"feed.xml\"\n");

    yml
}

/// Write .gitignore with .govbot entry
pub fn write_gitignore(cwd: &Path) -> Result<()> {
    let gitignore_path = cwd.join(".gitignore");
    let gitignore_entry = ".govbot\n";

    if gitignore_path.exists() {
        let mut content = fs::read_to_string(&gitignore_path)?;
        if content.contains(".govbot") {
            eprintln!("  ✓ .gitignore already contains .govbot");
        } else {
            if !content.ends_with('\n') {
                content.push('\n');
            }
            content.push_str(gitignore_entry);
            fs::write(&gitignore_path, content)?;
            eprintln!("  ✓ Updated .gitignore to include .govbot");
        }
    } else {
        fs::write(&gitignore_path, gitignore_entry)?;
        eprintln!("  ✓ Created .gitignore with .govbot");
    }

    Ok(())
}

fn github_workflow_content() -> &'static str {
    r#"# Run Govbot
# Runs govbot to clone repos, tag bills, and build RSS feeds and HTML index.

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
      tags:
        description: 'Comma-separated list of tags to include (leave empty for all tags)'
        required: false
        type: string
      limit:
        description: 'Limit number of entries per feed (default: 15, use "none" for all)'
        required: false
        type: string

jobs:
  govbot:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Run Govbot
        uses: windy-civi/toolkit/actions/govbot@main
        with:
          tags: ${{ inputs.tags }}
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
