#!/usr/bin/env python3
"""
Human-triggered operation to reset the govbot-data layer for one or more
locales: transfer the current repo to the archive org (preserving full git
history), rename it to avoid colliding with the placeholder repos already
archived there, mark it read-only, and create a fresh repo in its place so
format/extract-text rebuild everything from scratch with no inherited
incremental state (timestamps, partial files) to trust or distrust.

This is NOT close_session.py. It reuses the same transfer/rename/archive
primitives, but deliberately does NOT touch locales.<locale>.session in
chn-openstates-files.yml or its counterpart chn-openstates-scrape.yml --
those fields track real legislative session boundaries, and this operation
has nothing to do with a session closing. Running close_session.py here
would plant a fake "session closed" marker in config that later governs
real close-session decisions.

Prerequisites this script assumes (verify before running at scale):
  - The GitHub App used for scrape -> format repository_dispatch has
    "All repositories" access on govbot-data (confirmed 2026-07-21), so
    freshly created repos are covered automatically -- no per-repo
    re-authorization step needed.

Usage:
    python3 rebuild_data_repos.py --suffix pre-rebuild-2026-07-21 --states il --dry-run
    python3 rebuild_data_repos.py --suffix pre-rebuild-2026-07-21 --states il,ca
    python3 rebuild_data_repos.py --suffix pre-rebuild-2026-07-21 --all-states --dry-run
"""

import argparse
import importlib.util
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
CONFIG_NAME = "chn-openstates-files.yml"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


apply_mod = _load_module("apply", SCRIPT_DIR / "apply.py")
close_session_mod = _load_module("close_session", SCRIPT_DIR / "close_session.py")


def transfer_with_retry(full_repo: str, new_owner: str, dry_run: bool) -> None:
    """
    Like close_session_mod.transfer_repo, but tolerant of GitHub's brief
    "a previous repository operation is still in progress" lock right after
    a rename -- confirmed happening in practice (IL pilot, 2026-07-21) when
    transferring immediately after the pre-transfer rename this script does.
    close_session.py never hit this because it renames AFTER transferring,
    not right before.
    """
    if dry_run:
        close_session_mod.transfer_repo(full_repo, new_owner, dry_run)
        return

    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        try:
            close_session_mod.transfer_repo(full_repo, new_owner, dry_run)
            return
        except subprocess.CalledProcessError as e:
            still_locked = e.stdout and "previous repository operation" in e.stdout
            if not still_locked or attempt == max_attempts:
                raise
            wait_s = 5 * attempt
            print(
                f"     ⏳ Transfer still locked from the rename, retrying in "
                f"{wait_s}s ({attempt}/{max_attempts})..."
            )
            time.sleep(wait_s)


def rebuild_locale(
    config_path: Path,
    locale: str,
    suffix: str,
    archive_org: str,
    skip_sync: bool,
    dry_run: bool,
) -> bool:
    config = close_session_mod.load_config(config_path)
    active_org = config["org"]["username"]
    repo_name = close_session_mod.repo_name_for_locale(config, locale)
    active_full = f"{active_org}/{repo_name}"
    archived_name = f"{repo_name}-{suffix}"
    archive_full = f"{archive_org}/{archived_name}"

    print(f"\n{'='*70}")
    print(f"🔄 Rebuilding {locale} ({repo_name})")
    print(f"   Active:          {active_full}")
    print(f"   Archive target:  {archive_full}")
    print(f"{'='*70}")

    # --- Pre-flight checks -------------------------------------------------
    renamed_full = f"{active_org}/{archived_name}"
    active_info = close_session_mod.get_repo_info(active_full)
    resume_from_transfer = False

    if active_info is None:
        # The original name is gone -- either this locale was never touched
        # (and repo_name itself is wrong/doesn't exist), or a previous run
        # got as far as the pre-transfer rename and then failed before the
        # transfer completed (confirmed happening in practice: GitHub's
        # "previous repository operation in progress" lock, IL pilot
        # 2026-07-21). Detect the latter and resume instead of bailing.
        stranded_info = close_session_mod.get_repo_info(renamed_full)
        if stranded_info is not None and stranded_info.get("owner", {}).get("login") == active_org:
            print(
                f"   ⚠️  Found {renamed_full} -- looks like a previous run "
                f"renamed but didn't finish transferring. Resuming from the "
                f"transfer step."
            )
            resume_from_transfer = True
        else:
            print(f"❌ {active_full} does not exist -- skipping", file=sys.stderr)
            return False
    elif active_info.get("archived"):
        print(f"❌ {active_full} is already archived -- skipping", file=sys.stderr)
        return False

    if not resume_from_transfer and close_session_mod.get_repo_info(archive_full) is not None:
        print(
            f"❌ {archive_full} already exists -- refusing to proceed for "
            f"{locale}. Pick a different --suffix or check whether this "
            f"locale was already rebuilt.",
            file=sys.stderr,
        )
        return False

    if dry_run:
        print("🔍 DRY RUN -- no changes will be made")

    if resume_from_transfer:
        print("\n1-2/5 Skipped (sync + rename already done in a previous attempt)")
        return _finish_rebuild(
            config_path, locale, repo_name, archived_name, active_org, archive_org,
            archive_full, renamed_full, dry_run,
        )

    # --- 1. Final sync of outgoing repo (template files only) -------------
    if skip_sync:
        print("\n1/5 Skipping final sync (--skip-sync)")
    else:
        print("\n1/5 Final sync of outgoing repo...")
        generated_dir = SCRIPT_DIR / "generated"
        expected_repos, _ = apply_mod.get_expected_repos(
            config_path, generated_dir, test_states=locale, all_states=False
        )
        repo_info = expected_repos.get(repo_name)
        if repo_info is None:
            print(
                f"❌ render.py did not produce output for locale '{locale}' -- "
                f"check the locale's template/config",
                file=sys.stderr,
            )
            return False
        apply_mod.update_repo(
            active_org,
            repo_name,
            repo_info["generated_path"],
            dry_run=dry_run,
            fully_override_dirs=repo_info.get("fully_override_dirs"),
        )

    # --- 2. Rename BEFORE transfer -------------------------------------------
    # GitHub's transfer API rejects the transfer outright if a repo with the
    # SOURCE name already exists at the destination -- it has no atomic
    # "transfer with a new name" option, and checks uniqueness before any
    # rename could apply. govbot-archive already has a same-named repo for
    # every locale (this morning's placeholder migration), so renaming after
    # transfer (like close_session.py does, which never hit this because its
    # destination names were always free) doesn't work here. Rename first,
    # while still in the active org, so the transfer itself is collision-free.
    print("\n2/5 Renaming (pre-transfer, to avoid a name collision at the destination)...")
    close_session_mod.rename_repo(active_full, archived_name, dry_run)

    return _finish_rebuild(
        config_path, locale, repo_name, archived_name, active_org, archive_org,
        archive_full, renamed_full, dry_run,
    )


def _finish_rebuild(
    config_path: Path,
    locale: str,
    repo_name: str,
    archived_name: str,
    active_org: str,
    archive_org: str,
    archive_full: str,
    renamed_full: str,
    dry_run: bool,
) -> bool:
    active_full = f"{active_org}/{repo_name}"

    # --- 3. Transfer ---------------------------------------------------------
    print("\n3/5 Transferring to archive org...")
    transfer_with_retry(renamed_full, archive_org, dry_run)

    # --- 4. Archive (read-only) ---------------------------------------------
    print("\n4/5 Marking archived (read-only)...")
    close_session_mod.archive_repo(archive_full, dry_run)

    # --- 5. Recreate active repo, fresh --------------------------------------
    print("\n5/5 Creating fresh repo...")
    generated_dir = SCRIPT_DIR / "generated"
    expected_repos, _ = apply_mod.get_expected_repos(
        config_path, generated_dir, test_states=locale, all_states=False
    )
    repo_info = expected_repos.get(repo_name)
    if repo_info is None:
        print(
            f"❌ render.py did not produce output for locale '{locale}' -- "
            f"cannot recreate. Archive/rename/read-only steps above already "
            f"ran -- this locale now has NO active repo until you fix this "
            f"and create one manually.",
            file=sys.stderr,
        )
        return False
    apply_mod.create_repo(
        active_org, repo_name, locale, repo_info["generated_path"], dry_run=dry_run
    )

    print(f"\n✅ {locale} done." if not dry_run else f"\n✅ {locale} dry run complete.")
    print(f"   Archived: {archive_full}")
    print(f"   Active:   {active_full} (recreated, empty of _data)")
    # Deliberately not touching locales.<locale>.session anywhere -- this
    # operation has nothing to do with a legislative session closing.
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reset govbot-data repos for one or more locales: archive "
        "the current repo (transfer + rename + read-only) and recreate fresh. "
        "Does NOT touch legislative-session config -- see close_session.py "
        "for that. Human-triggered only."
    )
    parser.add_argument(
        "--suffix",
        required=True,
        help="Suffix appended to the archived repo name, e.g. "
        "'pre-rebuild-2026-07-21'. Must be lowercase letters, digits, and "
        "hyphens only.",
    )
    parser.add_argument(
        "--states",
        default=None,
        help="Comma-separated locale codes to rebuild, e.g. 'il,ca'. "
        "Required unless --all-states is given.",
    )
    parser.add_argument(
        "--all-states", action="store_true", help="Rebuild every locale in the config"
    )
    parser.add_argument(
        "--archive-org", default="govbot-archive", help="Destination org (default: govbot-archive)"
    )
    parser.add_argument(
        "--skip-sync",
        action="store_true",
        help="Skip the final template sync before transferring (faster, but "
        "the archived copy won't reflect the latest template changes)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would happen without making changes"
    )
    args = parser.parse_args()

    if not args.all_states and not args.states:
        print("❌ Either --states or --all-states is required", file=sys.stderr)
        sys.exit(1)

    suffix = close_session_mod.slugify_session(args.suffix)

    config_path = SCRIPT_DIR / CONFIG_NAME
    if not config_path.exists():
        print(f"❌ Config file not found at {config_path}", file=sys.stderr)
        sys.exit(1)

    apply_mod.check_requirements()
    apply_mod.setup_git_auth()

    if args.all_states:
        config = close_session_mod.load_config(config_path)
        locales = sorted(config.get("locales", {}).keys())
    else:
        locales = [s.strip() for s in args.states.split(",") if s.strip()]

    print(f"🚀 Rebuilding {len(locales)} locale(s): {', '.join(locales)}")
    print(f"   Suffix: {suffix}")
    print(f"   Archive org: {args.archive_org}")
    print(f"   Dry run: {args.dry_run}")

    results = {}
    for locale in locales:
        try:
            results[locale] = rebuild_locale(
                config_path, locale, suffix, args.archive_org, args.skip_sync, args.dry_run
            )
        except Exception as e:
            print(f"❌ {locale} failed with an exception: {e}", file=sys.stderr)
            results[locale] = False

    print(f"\n{'='*70}")
    print("📊 Summary")
    for locale, ok in results.items():
        print(f"   {'✅' if ok else '❌'} {locale}")
    succeeded = sum(1 for ok in results.values() if ok)
    print(f"\n{succeeded}/{len(locales)} locale(s) completed successfully")
    if succeeded < len(locales):
        sys.exit(1)


if __name__ == "__main__":
    main()
