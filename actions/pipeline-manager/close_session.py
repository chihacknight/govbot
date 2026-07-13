#!/usr/bin/env python3
"""
Human-triggered operation to close out a jurisdiction's current legislative
session.

This is the ONLY place a repo moves from an active org into an archive org.
It is never invoked automatically — a person decides a session has truly
closed (see project notes: OpenStates' session data has been found to miss
things like emergency sessions, so it isn't trusted to gate an irreversible
action) and runs this script, or the close-session.yml workflow that wraps
it, by hand.

check-sessions.py's daily auto-pause/resume is unrelated and untouched by
this script — that only flips a template within the SAME repo and is
reversible; this script permanently relocates the repo.

What it does, for one locale + one config file (chn-openstates-scrape.yml or
chn-openstates-files.yml) at a time:
  1. Final sync of the outgoing repo (push latest template/data state)
  2. Transfer the repo to the archive org (gh api .../transfer — preserves
     full git history, never a copy)
  3. Rename it in the archive org to include the session identifier
  4. Mark it GitHub-Archived (platform-level read-only)
  5. Create a fresh, same-named repo in the active org for the next session
  6. Write the (new) session identifier back into BOTH config files' locale
     entry (chn-openstates-scrape.yml and chn-openstates-files.yml stay
     mirrored) — does NOT commit/push the config change; that's left to the
     human or wrapping workflow, same as check-sessions.py's convention.

Usage:
    gh auth login  # or set GH_TOKEN
    python3 close_session.py --config chn-openstates-scrape.yml --locale ca
    python3 close_session.py --config chn-openstates-scrape.yml --locale ca \\
        --new-session 2027-2028 --archive-org govbot-archive
    python3 close_session.py --config chn-openstates-scrape.yml --locale ca --dry-run

Before running: set locales.<locale>.session in the config to the identifier
of the session that's closing (e.g. "2025-2026", or "2025-2026-ss1" for a
special session) — this script refuses to run without it, since that
identifier is what the archived repo gets renamed to.
"""

import argparse
import importlib.util
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import yaml

SCRIPT_DIR = Path(__file__).parent

COUNTERPART_CONFIG = {
    "chn-openstates-scrape.yml": "chn-openstates-files.yml",
    "chn-openstates-files.yml": "chn-openstates-scrape.yml",
}


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


apply_mod = _load_module("apply", SCRIPT_DIR / "apply.py")
render_mod = _load_module("render", SCRIPT_DIR / "render.py")


def slugify_session(session: str) -> str:
    """Validate a session identifier is safe to use in a repo name."""
    token = session.strip().lower().replace(" ", "-")
    if not re.fullmatch(r"[a-z0-9-]+", token):
        print(
            f"❌ Session identifier '{session}' must be lowercase letters, "
            f"digits, and hyphens only (got: {session!r})",
            file=sys.stderr,
        )
        sys.exit(1)
    return token


def load_config(config_path: Path) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def save_config(config_path: Path, config: dict) -> None:
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def repo_name_for_locale(config: dict, locale: str) -> str:
    locale_cfg = (config.get("locales") or {}).get(locale)
    if not locale_cfg:
        print(f"❌ Locale '{locale}' not found in config", file=sys.stderr)
        sys.exit(1)
    template = locale_cfg.get("template")
    if not template or template not in (config.get("templates") or {}):
        print(
            f"❌ Locale '{locale}' has no valid 'template' set in config", file=sys.stderr
        )
        sys.exit(1)
    markers = config.get("template_markers", {})
    marker_open = markers.get("open", "✏️{")
    marker_close = markers.get("close", "}✏️")
    folder_name_template = config["templates"][template]["folder-name"]
    return render_mod.render_folder_name(folder_name_template, locale, marker_open, marker_close)


def get_repo_info(full_repo: str) -> Optional[dict]:
    """Return repo metadata via `gh api`, or None if it doesn't exist."""
    result = subprocess.run(
        f"gh api 'repos/{full_repo}'", shell=True, capture_output=True, text=True
    )
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def transfer_repo(full_repo: str, new_owner: str, dry_run: bool) -> None:
    print(f"  📦 Transferring {full_repo} -> {new_owner}")
    if dry_run:
        print("     [DRY RUN] Would transfer repo (gh api .../transfer)")
        return
    apply_mod.run_shell(
        f"gh api 'repos/{full_repo}/transfer' -f new_owner='{new_owner}'", check=True
    )
    # Transfer is asynchronous on GitHub's side — poll until the repo shows
    # up under its new owner before continuing.
    owner_only, repo_only = full_repo.split("/", 1)
    new_full = f"{new_owner}/{repo_only}"
    for attempt in range(30):
        if get_repo_info(new_full) is not None:
            print(f"     ✅ Transfer complete: {new_full}")
            return
        time.sleep(2)
    print(f"     ❌ Timed out waiting for transfer to {new_full} to complete", file=sys.stderr)
    sys.exit(1)


def rename_repo(full_repo: str, new_name: str, dry_run: bool) -> None:
    print(f"  ✏️  Renaming {full_repo} -> {new_name}")
    if dry_run:
        print("     [DRY RUN] Would rename repo")
        return
    apply_mod.run_shell(f"gh repo rename '{new_name}' --repo '{full_repo}' --yes", check=True)


def archive_repo(full_repo: str, dry_run: bool) -> None:
    print(f"  🔒 Archiving {full_repo} (read-only)")
    if dry_run:
        print("     [DRY RUN] Would mark repo as archived")
        return
    apply_mod.run_shell(f"gh repo archive '{full_repo}' --yes", check=True)


def close_session(
    config_path: Path,
    locale: str,
    archive_org: str,
    new_session: Optional[str],
    dry_run: bool,
) -> None:
    config = load_config(config_path)
    active_org = config["org"]["username"]
    repo_name = repo_name_for_locale(config, locale)
    active_full = f"{active_org}/{repo_name}"

    locale_cfg = config["locales"][locale]
    session_id = locale_cfg.get("session")
    if not session_id:
        print(
            f"❌ locales.{locale}.session is not set in {config_path.name}.\n"
            f"   Set it to the identifier of the session that's closing "
            f'(e.g. "2025-2026") before running close_session.py.',
            file=sys.stderr,
        )
        sys.exit(1)

    session_slug = slugify_session(session_id)
    archived_name = f"{repo_name}-{session_slug}"
    archive_full = f"{archive_org}/{archived_name}"

    print(f"🔒 Closing session '{session_id}' for {locale}")
    print(f"   Active:          {active_full}")
    print(f"   Archive target:  {archive_full}")
    print()

    # --- Pre-flight checks -------------------------------------------------
    active_info = get_repo_info(active_full)
    if active_info is None:
        print(f"❌ {active_full} does not exist", file=sys.stderr)
        sys.exit(1)
    if active_info.get("archived"):
        print(f"❌ {active_full} is already archived — nothing to close", file=sys.stderr)
        sys.exit(1)
    if get_repo_info(archive_full) is not None:
        print(
            f"❌ {archive_full} already exists — refusing to proceed.\n"
            f"   This usually means the session identifier '{session_id}' was already used, "
            f"or a previous close_session.py run for this locale didn't finish cleanly.",
            file=sys.stderr,
        )
        sys.exit(1)

    if dry_run:
        print("🔍 DRY RUN — no changes will be made\n")

    apply_mod.check_requirements()
    apply_mod.setup_git_auth()

    # --- 1. Final sync -------------------------------------------------
    print("1/6 Final sync of outgoing repo...")
    generated_dir = SCRIPT_DIR / "generated"
    expected_repos, _ = apply_mod.get_expected_repos(
        config_path, generated_dir, test_states=locale, all_states=False
    )
    repo_info = expected_repos.get(repo_name)
    if repo_info is None:
        print(
            f"❌ render.py did not produce output for locale '{locale}' — "
            f"check the locale's template/config",
            file=sys.stderr,
        )
        sys.exit(1)
    apply_mod.update_repo(
        active_org,
        repo_name,
        repo_info["generated_path"],
        dry_run=dry_run,
        fully_override_dirs=repo_info.get("fully_override_dirs"),
    )

    # --- 2. Transfer -----------------------------------------------------
    print("\n2/6 Transferring to archive org...")
    transfer_repo(active_full, archive_org, dry_run)

    # --- 3. Rename ---------------------------------------------------------
    print("\n3/6 Renaming in archive org...")
    transferred_full = f"{archive_org}/{repo_name}"
    rename_repo(transferred_full, archived_name, dry_run)

    # --- 4. Archive (read-only) --------------------------------------------
    print("\n4/6 Marking archived (read-only)...")
    archive_repo(archive_full, dry_run)

    # --- 5. Recreate active repo for the next session -----------------------
    print("\n5/6 Creating fresh repo for the next session...")
    apply_mod.create_repo(
        active_org, repo_name, locale, repo_info["generated_path"], dry_run=dry_run
    )

    # --- 6. Update config (session field, mirrored in both files) ----------
    print("\n6/6 Updating config...")
    for fname in {config_path.name, COUNTERPART_CONFIG.get(config_path.name, "")}:
        if not fname:
            continue
        target = SCRIPT_DIR / fname
        if not target.exists():
            print(f"   ⚠️  {fname} not found, skipping session-field update")
            continue
        target_config = load_config(target)
        if locale not in (target_config.get("locales") or {}):
            print(f"   ⚠️  Locale '{locale}' not present in {fname}, skipping")
            continue
        if dry_run:
            print(
                f"   [DRY RUN] Would set locales.{locale}.session = "
                f"{new_session!r} in {fname}"
            )
            continue
        if new_session:
            target_config["locales"][locale]["session"] = new_session
        else:
            target_config["locales"][locale].pop("session", None)
        save_config(target, target_config)
        print(f"   ✅ Updated locales.{locale}.session in {fname}")

    print("\n✅ Session close complete." if not dry_run else "\n✅ Dry run complete.")
    print(f"   Archived: {archive_full}")
    print(f"   Active:   {active_full} (recreated for next session)")
    if not new_session:
        print(
            f"   ⚠️  No --new-session given — locales.{locale}.session is now unset. "
            f"Fill it in once the next session's identifier is known."
        )
    print(
        "\nRemember: this script does not commit/push config changes — "
        "review and commit them yourself (same as check-sessions.py)."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Close out a jurisdiction's current legislative session: "
        "transfer its repo to the archive org, rename, archive (read-only), "
        "and recreate for the next session. Human-triggered only."
    )
    parser.add_argument(
        "-c",
        "--config",
        required=True,
        help="Config YAML file (relative to script directory), e.g. chn-openstates-scrape.yml",
    )
    parser.add_argument("--locale", required=True, help="Locale code to close, e.g. ca")
    parser.add_argument(
        "--archive-org", default="govbot-archive", help="Destination org (default: govbot-archive)"
    )
    parser.add_argument(
        "--new-session",
        default=None,
        help="Session identifier for the NEXT session (optional — leave unset if not yet known)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would happen without making changes"
    )
    args = parser.parse_args()

    config_path = SCRIPT_DIR / args.config
    if not config_path.exists():
        print(f"❌ Config file not found at {config_path}", file=sys.stderr)
        sys.exit(1)

    close_session(
        config_path=config_path,
        locale=args.locale,
        archive_org=args.archive_org,
        new_session=args.new_session,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
