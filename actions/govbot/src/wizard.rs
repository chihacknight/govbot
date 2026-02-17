use anyhow::Result;
use dialoguer::{Input, Select};
use std::fs;
use std::path::Path;

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

    // Generate files
    let cwd = std::env::current_dir()?;
    let yml_content = generate_govbot_yml(&repos, include_example_tag, &base_url);

    // Write govbot.yml
    let config_path = cwd.join("govbot.yml");
    fs::write(&config_path, &yml_content)?;
    eprintln!("  ✓ Created govbot.yml");

    // Write .gitignore
    write_gitignore(&cwd)?;

    // Write GitHub Actions workflow
    write_github_workflow(&cwd)?;

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
        // Print the AI prompt template
        eprintln!();
        eprintln!("To create a tag, copy this prompt into your preferred AI tool:");
        eprintln!();
        eprintln!("---");
        eprintln!("Create a govbot tag definition in YAML for tracking [YOUR TOPIC] legislation.");
        eprintln!("The tag should have:");
        eprintln!("- A description (multiline, covering subtopics)");
        eprintln!("- 2-3 example bill descriptions that would match");
        eprintln!("- Optional: include_keywords and exclude_keywords lists");
        eprintln!();
        eprintln!("Format:");
        eprintln!("  tag_name:");
        eprintln!("    description: |");
        eprintln!("      ...");
        eprintln!("    examples:");
        eprintln!("      - \"...\"");
        eprintln!("    include_keywords:");
        eprintln!("      - keyword1");
        eprintln!("    exclude_keywords:");
        eprintln!("      - keyword1");
        eprintln!("---");
        eprintln!();
        eprintln!("Paste the result into your govbot.yml under the 'tags:' section.");
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

/// Write GitHub Actions workflow file
pub fn write_github_workflow(cwd: &Path) -> Result<()> {
    let workflows_dir = cwd.join(".github").join("workflows");
    fs::create_dir_all(&workflows_dir)?;

    let workflow_path = workflows_dir.join("build.yml");
    let workflow_content = r#"# Run Govbot
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
"#;

    fs::write(&workflow_path, workflow_content)?;
    eprintln!("  ✓ Created .github/workflows/build.yml");

    Ok(())
}
