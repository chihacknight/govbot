use crate::config::{Manifest, Transform};
use anyhow::{Context, Result};
use std::path::Path;
use std::process::{Command, Stdio};

/// Run a manifest pipeline as a DAG: `source | <transforms…> | apply`, then the
/// publisher stages.
///
/// The runner is **stage-agnostic**: each `transforms` entry is an opaque
/// subprocess that speaks the stream protocol (newline-JSON on stdio), so the
/// built-in `govbot classify` and an external `fastclass classify -` are peers —
/// swapping one for the other is a manifest `command` edit, not a code change.
/// The schema's typed `reads`/`writes` make branch/merge routing possible later;
/// this release walks the pipeline as a linear chain, which covers the one real
/// `source → classify → apply → publish` shape.
pub fn run_manifest_pipeline(
    config_path: &Path,
    pipeline_name: Option<&str>,
    dry_run: bool,
) -> Result<()> {
    let govbot_bin = std::env::current_exe().context("Failed to determine govbot binary path")?;
    let cwd = config_path.parent().unwrap_or_else(|| Path::new("."));
    let manifest = Manifest::load(config_path)?;

    // Resolve the ordered stage list: a named pipeline, else the sole/first
    // pipeline, else a default of every transform followed by every publisher.
    let stages: Vec<String> = if let Some(name) = pipeline_name {
        manifest
            .pipelines
            .get(name)
            .cloned()
            .ok_or_else(|| anyhow::anyhow!("pipeline '{}' not found in govbot.yml", name))?
    } else if let Some((_, first)) = manifest.pipelines.iter().next() {
        first.clone()
    } else {
        let mut s: Vec<String> = manifest.transforms.keys().cloned().collect();
        s.extend(manifest.publish.keys().cloned());
        s
    };

    // Partition into transform stages and publisher stages, preserving order.
    let transform_stages: Vec<(String, Transform)> = stages
        .iter()
        .filter_map(|n| manifest.transforms.get(n).map(|t| (n.clone(), t.clone())))
        .collect();
    let publisher_stages: Vec<String> = stages
        .iter()
        .filter(|n| manifest.publish.contains_key(*n))
        .cloned()
        .collect();

    // Warn on any stage that names neither a transform nor a publisher.
    for stage in &stages {
        if !manifest.transforms.contains_key(stage) && !manifest.publish.contains_key(stage) {
            eprintln!(
                "⚠️  pipeline stage '{}' matches no transform or publisher",
                stage
            );
        }
    }

    // Step 1: source | transforms… | apply
    let chain: Vec<&str> = transform_stages.iter().map(|(n, _)| n.as_str()).collect();
    eprintln!();
    eprintln!("=== Transforms: source | {} | apply ===", chain.join(" | "));
    run_transform_chain(&govbot_bin, cwd, &transform_stages)?;

    // Step 2: publishers. The per-publisher module split lands in a follow-up;
    // for now the publish step is emitted by the existing `govbot build`.
    eprintln!();
    eprintln!("=== Publish ===");
    if publisher_stages.is_empty() {
        eprintln!("(no publisher stages declared)");
    }
    run_publish(&govbot_bin, cwd, dry_run)?;

    eprintln!();
    eprintln!("Pipeline complete!");
    Ok(())
}

/// Spawn `govbot source --select <reads> | <transform…> | govbot apply`,
/// chaining each stage's stdout into the next stage's stdin.
fn run_transform_chain(
    govbot_bin: &Path,
    cwd: &Path,
    transforms: &[(String, Transform)],
) -> Result<()> {
    // The projection `source` emits is the first transform's `reads` kind
    // (`docs` for a classify pipeline). With no transforms there is nothing to
    // classify, so the chain is a no-op.
    if transforms.is_empty() {
        eprintln!("(no transforms declared — skipping classify stage)");
        return Ok(());
    }
    let reads = &transforms[0].1.reads;

    let mut children = Vec::new();

    let mut source = Command::new(govbot_bin)
        .arg("source")
        .arg("--select")
        .arg(reads)
        .current_dir(cwd)
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        .spawn()
        .context("Failed to spawn govbot source")?;
    let mut prev_out = source.stdout.take();
    children.push(source);

    for (name, transform) in transforms {
        let argv = transform.command.argv();
        if argv.is_empty() {
            anyhow::bail!("transform '{}' has an empty command", name);
        }
        // A `govbot …` transform (the built-in classify) resolves to this same
        // executable rather than a `govbot` on PATH; any other program (e.g.
        // `fastclass`) is spawned as named — they are otherwise identical.
        let program = if argv[0] == "govbot" {
            govbot_bin.to_string_lossy().to_string()
        } else {
            argv[0].clone()
        };
        let stdin = prev_out.take().map(Stdio::from).unwrap_or_else(Stdio::null);
        let mut child = Command::new(&program)
            .args(&argv[1..])
            .current_dir(cwd)
            .stdin(stdin)
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .with_context(|| format!("Failed to spawn transform '{}' ({})", name, argv[0]))?;
        prev_out = child.stdout.take();
        children.push(child);
    }

    let apply_stdin = prev_out.take().map(Stdio::from).unwrap_or_else(Stdio::null);
    let mut apply = Command::new(govbot_bin)
        .arg("apply")
        .current_dir(cwd)
        .stdin(apply_stdin)
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .spawn()
        .context("Failed to spawn govbot apply")?;
    let apply_status = apply.wait().context("Failed to wait for govbot apply")?;

    // Reap the upstream stages.
    for mut child in children {
        let _ = child.wait();
    }

    if !apply_status.success() {
        anyhow::bail!(
            "apply stage failed with exit code {}",
            apply_status.code().unwrap_or(-1)
        );
    }
    Ok(())
}

/// Emit the manifest's publishers. For this release publisher stages are emitted
/// by the existing `govbot build` implementation; the per-kind module split (one
/// publisher = one artifact) lands in a follow-up. `--dry-run` is accepted for
/// forward-compatibility and currently just annotates the log line.
fn run_publish(govbot_bin: &Path, cwd: &Path, dry_run: bool) -> Result<()> {
    if dry_run {
        eprintln!("(dry-run) skipping publisher emission");
        return Ok(());
    }
    let status = Command::new(govbot_bin)
        .arg("build")
        .current_dir(cwd)
        .stdin(Stdio::inherit())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .status()
        .context("Failed to run publish (build) stage")?;
    if !status.success() {
        eprintln!("⚠️  publish stage failed (continuing)");
    }
    Ok(())
}
