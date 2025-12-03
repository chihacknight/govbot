#!/usr/bin/env python3
"""
Config-driven repository management script.

This script reads a config YAML file and ensures that all repositories in the GitHub
organization match the declarative configuration:
- Creates repos that are in config but not in GitHub
- Deletes repos that are in GitHub but not in config
- Updates template files in existing repos to match generated templates
"""

import os
import sys
import subprocess
import argparse
import json
import shutil
from pathlib import Path
from typing import Dict, Set, List, Tuple, Optional


def run_shell(cmd: str, check: bool = True, capture_output: bool = True) -> str:
    """Run a shell command and return the result."""
    result = subprocess.run(
        cmd, shell=True, check=check, capture_output=capture_output, text=True
    )
    if capture_output:
        return result.stdout.strip()
    return ""


def check_requirements():
    """Check if required tools are installed and authenticated."""
    # Check if gh CLI is installed
    if not shutil.which("gh"):
        print("❌ GitHub CLI (gh) is not installed", file=sys.stderr)
        print("Install it: brew install gh", file=sys.stderr)
        sys.exit(1)

    # Check if git is installed
    if not shutil.which("git"):
        print("❌ Git is not installed", file=sys.stderr)
        sys.exit(1)

    # Check if authenticated with GitHub CLI
    print("🔐 Checking GitHub authentication...")
    try:
        result = subprocess.run(
            "gh auth status", shell=True, capture_output=True, text=True, check=True
        )
        print("   ✅ Authenticated")
    except subprocess.CalledProcessError:
        print("   ❌ Not authenticated with GitHub CLI", file=sys.stderr)
        print("", file=sys.stderr)
        print("Run: gh auth login", file=sys.stderr)
        sys.exit(1)


def get_expected_repos(
    config_file: Path,
    generated_dir: Path,
    test_states: Optional[str] = None,
    all_states: bool = False,
) -> Tuple[Dict[str, Dict], str]:
    """
    Get expected repos from config YAML file and generated directory.
    Returns tuple of (dict mapping repo_name -> {locale, generated_path, config}, org_username)
    """
    # First, run render.py to generate files
    script_dir = config_file.parent
    render_script = script_dir / "render.py"

    print("📝 Generating template files...")
    try:
        cmd = f"cd '{script_dir}' && python3 '{render_script}' -c '{config_file.name}' -o generated"
        if all_states:
            cmd += " --all-states"
        elif test_states:
            cmd += f" --test-states '{test_states}'"
        run_shell(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to generate templates: {e}", file=sys.stderr)
        sys.exit(1)

    # Parse config to get locale info
    # Import render module from the same directory
    import importlib.util

    render_path = script_dir / "render.py"
    spec = importlib.util.spec_from_file_location("render", render_path)
    render = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(render)

    all_locales, all_configs, marker_open, marker_close, templates, org_username = (
        render.parse_config(config_file)
    )

    # Filter locales based on test_states/all_states flags (same logic as render.py)
    if not all_states:
        # Default: only process test states
        if test_states is None:
            test_states_list = ["al", "ak", "de", "wy", "sd"]  # Default test states
        else:
            # Parse comma-separated string
            test_states_list = [s.strip() for s in test_states.split(",") if s.strip()]

        # Filter to only test states
        filtered_locales = []
        filtered_configs = []
        for locale, config_str in zip(all_locales, all_configs):
            if str(locale) in test_states_list:
                filtered_locales.append(locale)
                filtered_configs.append(config_str)

        all_locales = filtered_locales
        all_configs = filtered_configs

        print(
            f"  🧪 Test mode: Processing {len(all_locales)} test states: {', '.join(test_states_list)}"
        )
    else:
        print(f"  🌍 Processing all {len(all_locales)} states from config")

    expected_repos = {}

    for locale, config_str in zip(all_locales, all_configs):
        # Extract template
        template = render.get_config_value(config_str, "template", "")
        if not template:
            continue

        # Extract managed status
        managed = render.get_config_value(config_str, "managed", "true")
        if managed == "false":
            continue

        # Get folder name (repo name)
        folder_name = locale  # default
        if template in templates and "folder-name" in templates[template]:
            folder_name_template = templates[template]["folder-name"]
            folder_name = render.render_folder_name(
                folder_name_template, locale, marker_open, marker_close
            )

        generated_path = generated_dir / config_file.stem / folder_name

        if generated_path.exists():
            # Get fully_override_dirs from template config
            fully_override_dirs = None
            if template in templates and "fully_override_dirs" in templates[template]:
                fully_override_dirs = templates[template]["fully_override_dirs"]

            expected_repos[folder_name] = {
                "locale": locale,
                "generated_path": generated_path,
                "config": config_str,
                "template": template,
                "fully_override_dirs": fully_override_dirs,
            }

    return expected_repos, org_username


def get_actual_repos(org: str) -> Set[str]:
    """Get list of actual repos in the GitHub organization."""
    print(f"📋 Fetching existing repos in {org}...")
    try:
        repos_json = run_shell(
            f"gh repo list '{org}' --limit 1000 --json name", check=True
        )
        repos_data = json.loads(repos_json)
        return {repo["name"] for repo in repos_data}
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to list repos in {org}", file=sys.stderr)
        print(f"   Error: {e}", file=sys.stderr)
        print("", file=sys.stderr)
        print("   Possible causes:", file=sys.stderr)
        print(
            "   - Not authenticated with GitHub CLI (run: gh auth login)",
            file=sys.stderr,
        )
        print(f"   - No access to organization '{org}'", file=sys.stderr)
        print(f"   - Organization '{org}' does not exist", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Failed to parse repo list: {e}", file=sys.stderr)
        sys.exit(1)


def create_repo(
    org: str, repo_name: str, locale: str, generated_path: Path, dry_run: bool = False
) -> bool:
    """Create a new repository and push template files."""
    full_repo = f"{org}/{repo_name}"

    print(f"  🔨 Creating repository: {full_repo}")

    if dry_run:
        print(f"     [DRY RUN] Would create repo and push files")
        return True

    try:
        # Create repo (public by default)
        run_shell(
            f"gh repo create '{full_repo}' --public "
            f"--description '🏛️ {locale.upper()} legislative data pipeline' "
            f"--clone=false",
            check=True,
        )

        # Wait for repo to be ready
        import time

        time.sleep(2)

        # Clone repo
        temp_dir = Path(subprocess.check_output(["mktemp", "-d"], text=True).strip())
        repo_dir = temp_dir / repo_name

        try:
            run_shell(
                f"gh repo clone '{full_repo}' '{repo_dir}' -- --depth 1 --quiet",
                check=True,
            )

            # Copy all files from generated_path to repo_dir
            for item in generated_path.rglob("*"):
                if item.is_file():
                    rel_path = item.relative_to(generated_path)
                    dest_path = repo_dir / rel_path
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dest_path)

            # Commit and push
            run_shell(
                f"cd '{repo_dir}' && git config user.name 'github-actions[bot]'",
                check=True,
            )
            run_shell(
                f"cd '{repo_dir}' && git config user.email 'github-actions[bot]@users.noreply.github.com'",
                check=True,
            )
            run_shell(f"cd '{repo_dir}' && git add .", check=True)

            # Check if there are any changes to commit
            result = subprocess.run(
                f"cd '{repo_dir}' && git diff --staged --quiet",
                shell=True,
                capture_output=True,
            )
            if result.returncode == 0:
                # No changes
                print(f"     ℹ️  No files to commit (repo may be empty)")
            else:
                # There are changes, commit them
                run_shell(
                    f"cd '{repo_dir}' && git commit -m 'Initial commit: Generated from template'",
                    check=True,
                )

            # Try to push to main, fallback to master if needed
            try:
                run_shell(f"cd '{repo_dir}' && git push origin main", check=True)
            except subprocess.CalledProcessError:
                # Try master branch
                try:
                    run_shell(f"cd '{repo_dir}' && git push origin master", check=True)
                except subprocess.CalledProcessError:
                    # Create and push to main
                    run_shell(f"cd '{repo_dir}' && git branch -M main", check=True)
                    run_shell(f"cd '{repo_dir}' && git push -u origin main", check=True)

            print(f"     ✅ Created and initialized repository")
            return True

        finally:
            # Cleanup
            if repo_dir.exists():
                shutil.rmtree(repo_dir, ignore_errors=True)
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    except subprocess.CalledProcessError as e:
        print(f"     ❌ Failed to create repository: {e}", file=sys.stderr)
        return False


def delete_repo(org: str, repo_name: str, dry_run: bool = False) -> bool:
    """Delete a repository."""
    full_repo = f"{org}/{repo_name}"

    print(f"  🗑️  Deleting repository: {full_repo}")

    if dry_run:
        print(f"     [DRY RUN] Would delete repo")
        return True

    try:
        run_shell(f"gh repo delete '{full_repo}' --yes", check=True)
        print(f"     ✅ Deleted repository")
        return True
    except subprocess.CalledProcessError as e:
        print(f"     ❌ Failed to delete repository: {e}", file=sys.stderr)
        return False


def update_repo(
    org: str,
    repo_name: str,
    generated_path: Path,
    dry_run: bool = False,
    fully_override_dirs: Optional[List[str]] = None,
) -> bool:
    """Update template files in an existing repository.

    Args:
        org: GitHub organization name
        repo_name: Repository name
        generated_path: Path to generated template files
        dry_run: If True, don't make changes
        fully_override_dirs: List of directory names (like '.github') that should be fully overridden.
                             Files in these directories that don't exist in generated will be deleted.
    """
    if fully_override_dirs is None:
        fully_override_dirs = [".github"]  # Default: fully override .github directory

    full_repo = f"{org}/{repo_name}"

    print(f"  ✏️  Updating repository: {full_repo}")

    if dry_run:
        print(f"     [DRY RUN] Would update template files")
        if fully_override_dirs:
            print(
                f"     [DRY RUN] Fully override directories: {', '.join(fully_override_dirs)}"
            )
        return True

    temp_dir = Path(subprocess.check_output(["mktemp", "-d"], text=True).strip())
    repo_dir = temp_dir / repo_name

    try:
        # Clone repo
        run_shell(
            f"gh repo clone '{full_repo}' '{repo_dir}' -- --depth 1 --quiet", check=True
        )

        changes_made = False

        # Get all files from generated_path
        generated_files = {}
        generated_dirs = set()  # Track which directories have files in generated
        for item in generated_path.rglob("*"):
            if item.is_file():
                rel_path = item.relative_to(generated_path)
                generated_files[rel_path] = item
                # Track parent directories
                for parent in rel_path.parents:
                    if str(parent) != ".":
                        generated_dirs.add(parent)

        # Update or create files
        for rel_path, source_file in generated_files.items():
            dest_path = repo_dir / rel_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            # Check if file exists and is different
            if dest_path.exists():
                if source_file.read_bytes() != dest_path.read_bytes():
                    shutil.copy2(source_file, dest_path)
                    changes_made = True
            else:
                shutil.copy2(source_file, dest_path)
                changes_made = True

        # Get all files in repo (excluding .git and data directories)
        repo_files = {}
        data_dirs = (".git", "country:us", ".windycivi", "_data")
        for item in repo_dir.rglob("*"):
            if item.is_file():
                rel_path = item.relative_to(repo_dir)
                # Skip data directories and .git
                if not any(part in data_dirs for part in rel_path.parts):
                    repo_files[rel_path] = item

        # For fully override directories, delete files that don't exist in generated
        deleted_files = []
        for repo_file_path, repo_file in repo_files.items():
            # Check if this file is in a fully override directory
            is_in_override_dir = any(
                repo_file_path.parts[0] == override_dir
                for override_dir in fully_override_dirs
            )

            if is_in_override_dir:
                # In a fully override directory - delete if not in generated
                if repo_file_path not in generated_files:
                    print(f"     🗑️  Deleting {repo_file_path} (not in template)")
                    repo_file.unlink()
                    deleted_files.append(repo_file_path)
                    changes_made = True
            else:
                # Not in a fully override directory - only remove root-level template files
                # (preserve data files and other user-created files)
                if repo_file_path not in generated_files:
                    # Only remove if it's a root-level file (not in any subdirectory)
                    if len(repo_file_path.parts) == 1:
                        # Check if it's a common template file (README.md, etc.)
                        if repo_file_path.name in ("README.md",):
                            print(
                                f"     🗑️  Deleting {repo_file_path} (not in template)"
                            )
                            repo_file.unlink()
                            deleted_files.append(repo_file_path)
                            changes_made = True

        # Clean up empty directories in fully override directories
        for override_dir in fully_override_dirs:
            override_path = repo_dir / override_dir
            if override_path.exists() and override_path.is_dir():
                # Remove empty subdirectories
                for root, dirs, files in os.walk(override_path, topdown=False):
                    root_path = Path(root)
                    # Skip if directory is not empty or is the override_dir itself
                    if root_path == override_path:
                        continue
                    try:
                        if not any(root_path.iterdir()):
                            print(
                                f"     🗑️  Removing empty directory {root_path.relative_to(repo_dir)}"
                            )
                            root_path.rmdir()
                            changes_made = True
                    except OSError:
                        pass  # Directory not empty or doesn't exist

        if not changes_made:
            print(f"     ℹ️  No changes needed")
            return True

        # Commit and push
        run_shell(
            f"cd '{repo_dir}' && git config user.name 'github-actions[bot]'", check=True
        )
        run_shell(
            f"cd '{repo_dir}' && git config user.email 'github-actions[bot]@users.noreply.github.com'",
            check=True,
        )
        run_shell(f"cd '{repo_dir}' && git add .", check=True)

        # Check if there are changes
        result = subprocess.run(
            f"cd '{repo_dir}' && git diff --staged --quiet",
            shell=True,
            capture_output=True,
        )
        if result.returncode == 0:
            # No changes
            print(f"     ℹ️  No changes detected")
            return True

        run_shell(
            f"cd '{repo_dir}' && git commit -m 'chore: update template files from config'",
            check=True,
        )

        # Try main branch first, fallback to master
        try:
            run_shell(f"cd '{repo_dir}' && git push origin main", check=True)
        except subprocess.CalledProcessError:
            run_shell(f"cd '{repo_dir}' && git push origin master", check=True)

        print(f"     ✅ Updated repository")
        return True

    except subprocess.CalledProcessError as e:
        print(f"     ❌ Failed to update repository: {e}", file=sys.stderr)
        return False
    finally:
        # Cleanup
        if repo_dir.exists():
            shutil.rmtree(repo_dir, ignore_errors=True)
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Apply config YAML file to manage repositories declaratively"
    )
    parser.add_argument(
        "--org",
        type=str,
        default=None,
        help="GitHub organization name (overrides config file, default: read from config file)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--no-delete", action="store_true", help="Skip deletion of repos not in config"
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        required=True,
        help="Config YAML file (relative to script directory)",
    )
    parser.add_argument(
        "--all-states",
        action="store_true",
        help="Process all states from config (default: only test states: al,ak,de,wy,sd)",
    )
    parser.add_argument(
        "--test-states",
        type=str,
        default=None,
        help="Comma-separated list of test states to process (default: al,ak,de,wy,sd). Ignored if --all-states is used.",
    )
    args = parser.parse_args()

    # Check requirements
    check_requirements()

    # Get script directory
    script_dir = Path(__file__).parent
    config_file = script_dir / args.config
    generated_dir = script_dir / "generated"

    if not config_file.exists():
        print(f"❌ Config file not found at {config_file}", file=sys.stderr)
        sys.exit(1)

    # Get expected and actual repos (this also parses config to get org)
    expected_repos, org_from_config = get_expected_repos(
        config_file, generated_dir, args.test_states, args.all_states
    )

    # Get org from args or config
    org = args.org if args.org else org_from_config
    if not org:
        print(
            f"❌ org.username not found in {args.config} and --org not provided",
            file=sys.stderr,
        )
        sys.exit(1)

    print("🚀 Config-driven repository management")
    print(f"   Organization: {org}")
    print(f"   Dry run: {args.dry_run}")
    print(f"   Skip deletions: {args.no_delete}")
    print()

    actual_repos = get_actual_repos(org)

    expected_names = set(expected_repos.keys())

    # Calculate differences
    to_create = expected_names - actual_repos
    to_delete = actual_repos - expected_names
    to_update = expected_names & actual_repos

    print()
    print("📊 Summary:")
    print(f"   Expected repos: {len(expected_names)}")
    print(f"   Actual repos: {len(actual_repos)}")
    print(f"   To create: {len(to_create)}")
    print(f"   To update: {len(to_update)}")
    print(f"   To delete: {len(to_delete)}")
    print()

    if args.dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")
        print()

    # Create missing repos
    if to_create:
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("📦 Creating missing repositories:")
        print()
        success_count = 0
        for repo_name in sorted(to_create):
            repo_info = expected_repos[repo_name]
            if create_repo(
                org,
                repo_name,
                repo_info["locale"],
                repo_info["generated_path"],
                args.dry_run,
            ):
                success_count += 1
        print()
        print(f"✅ Created {success_count}/{len(to_create)} repositories")
        print()

    # Update existing repos
    if to_update:
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("✏️  Updating existing repositories:")
        print()
        success_count = 0
        for repo_name in sorted(to_update):
            repo_info = expected_repos[repo_name]
            # Get fully_override_dirs from template config, default to ['.github'] if not specified
            fully_override_dirs = repo_info.get("fully_override_dirs", [".github"])
            if update_repo(
                org,
                repo_name,
                repo_info["generated_path"],
                args.dry_run,
                fully_override_dirs=fully_override_dirs,
            ):
                success_count += 1
        print()
        print(f"✅ Updated {success_count}/{len(to_update)} repositories")
        print()

    # Delete repos not in config
    if to_delete and not args.no_delete:
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("🗑️  Deleting repositories not in config:")
        print()
        if not args.dry_run:
            print("⚠️  WARNING: This will permanently delete repositories!")
            response = input("Continue? (yes/no): ")
            if response.lower() != "yes":
                print("❌ Deletion cancelled")
                return

        success_count = 0
        for repo_name in sorted(to_delete):
            if delete_repo(org, repo_name, args.dry_run):
                success_count += 1
        print()
        print(f"✅ Deleted {success_count}/{len(to_delete)} repositories")
        print()
    elif to_delete:
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(
            f"⚠️  {len(to_delete)} repositories would be deleted (use --no-delete to skip)"
        )
        print()

    print("✅ Done!")


if __name__ == "__main__":
    main()
