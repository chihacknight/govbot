#!/usr/bin/env python3
"""
Convert a formatted repo from one-file-per-log to the per-bill .jsonl layout.

    python3 convert_logs.py <path-to-repo> [--dry-run]

For every bill, folds bills/{id}/logs/*.json into bills/{id}/action_logs.jsonl
and bills/{id}/vote_event_logs.jsonl and deletes the old files, then removes the
sessions/{s}/logs/ symlink folders. Idempotent: running it on a converted repo
changes nothing. Files it can't read or recognise are left where they are and
listed, never deleted.

Converted actions get `first_seen` from metadata.json's
actions[]._processing.log_file_created where the pipeline recorded it; converted
votes get null. The backfill from the raw scraper history (see the conversion
plan in tamara-notes/processes/workstreams/jsonl-logs.md) fills those in and
recovers votes the old layout lost.
"""

import argparse
import json
import sys
from pathlib import Path

from utils.log_jsonl import convert_repo, has_legacy_logs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("repo", type=Path, help="Formatted repo root (the folder holding country:us/)")
    parser.add_argument("--dry-run", action="store_true", help="Only report whether the repo needs converting")
    args = parser.parse_args()

    if not (args.repo / "country:us").is_dir():
        print(f"error: {args.repo} has no country:us/ folder", file=sys.stderr)
        return 2
    if args.dry_run:
        print("needs converting" if has_legacy_logs(args.repo) else "already converted")
        return 0

    stats = convert_repo(args.repo).as_dict()
    print(json.dumps(stats, indent=2))
    # Anything left behind needs a person to look at it.
    return 1 if stats["left_in_place"] else 0


if __name__ == "__main__":
    sys.exit(main())
