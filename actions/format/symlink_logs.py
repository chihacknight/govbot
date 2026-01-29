#!/usr/bin/env python3

"""
Symlink all log files from bill directories to a central logs folder.

This allows downstream workflows to stream the contents of the logs folder
to get a timeseries of log files.
"""

import argparse
import os
import sys
from pathlib import Path
from collections import defaultdict


def find_log_files(bills_path: Path):
    """Find all JSON log files in bills/{bill_id}/logs/ directories."""
    log_files = []
    bills_dir = bills_path

    if not bills_dir.exists():
        print(f"Error: Bills path does not exist: {bills_dir}", file=sys.stderr)
        return log_files

    # Walk through bills directories
    for bill_dir in bills_dir.iterdir():
        if not bill_dir.is_dir():
            continue

        logs_dir = bill_dir / "logs"
        if not logs_dir.exists() or not logs_dir.is_dir():
            continue

        # Find all JSON files in this logs directory
        for log_file in logs_dir.glob("*.json"):
            if log_file.is_file():
                log_files.append((bill_dir.name, log_file))

    return log_files


def create_symlink(source: Path, target: Path, target_dir: Path):
    """Create a relative symlink from source to target."""
    # Remove existing symlink if it exists
    if target.exists():
        target.unlink()

    # Calculate relative path from target_dir to source
    try:
        relative_path = os.path.relpath(source, target_dir)
    except ValueError:
        # If paths are on different drives (Windows), use absolute path
        relative_path = str(source)

    # Create symlink
    target.symlink_to(relative_path)


def main():
    parser = argparse.ArgumentParser(
        description="Symlink all log files from bill directories to a central logs folder"
    )
    parser.add_argument(
        "--root",
        required=True,
        type=Path,
        help="Root directory containing sessions (e.g., country:us/state:il)",
    )
    parser.add_argument(
        "--session",
        required=True,
        help="Session ID (e.g., 104th)",
    )
    parser.add_argument(
        "--target",
        required=True,
        type=Path,
        help="Target logs directory (e.g., state:il/sessions/104th/logs)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't create symlinks, just print what would be done",
    )

    args = parser.parse_args()

    # Build the search path: root/sessions/{session}/bills
    bills_path = args.root / "sessions" / args.session / "bills"

    if not bills_path.exists():
        print(f"Error: Bills path does not exist: {bills_path}", file=sys.stderr)
        sys.exit(1)

    # Create target directory if it doesn't exist
    if not args.dry_run:
        args.target.mkdir(parents=True, exist_ok=True)
    else:
        print(f"[DRY RUN] Would create target directory: {args.target}")

    # Find all log files
    print(f"Finding log files in {bills_path}...", file=sys.stderr)
    log_files = find_log_files(bills_path)
    print(f"Found {len(log_files)} log files", file=sys.stderr)

    linked_count = 0
    error_count = 0
    collision_count = 0
    seen_filenames = set()

    # Process each log file
    for bill_id, log_file in log_files:
        # Skip if source file doesn't exist
        if not log_file.exists():
            error_count += 1
            print(f"Warning: Source file does not exist: {log_file}", file=sys.stderr)
            continue

        filename = log_file.name
        symlink_path = args.target / filename

        # Handle collisions: track seen filenames and append bill_id if needed
        if filename in seen_filenames or symlink_path.exists():
            # Check if existing symlink points to the same file
            if symlink_path.exists() and symlink_path.is_symlink():
                try:
                    existing_target = symlink_path.readlink()
                    # Resolve to absolute paths for comparison
                    existing_abs = (args.target / existing_target).resolve()
                    current_abs = log_file.resolve()
                    if existing_abs == current_abs:
                        # Already linked to the same file, skip
                        continue
                except (OSError, ValueError):
                    pass

            # Collision detected - append bill_id to filename
            stem = log_file.stem
            ext = log_file.suffix
            new_filename = f"{stem}_{bill_id}{ext}"
            collision_count += 1
            symlink_path = args.target / new_filename
        else:
            seen_filenames.add(filename)

        # Create the symlink
        if args.dry_run:
            print(f"Would symlink: {symlink_path} -> {log_file}")
            linked_count += 1
        else:
            try:
                create_symlink(log_file, symlink_path, args.target)
                linked_count += 1

                # Print progress every 1000 files
                if linked_count % 1000 == 0:
                    print(
                        f"Progress: {linked_count} files linked, {error_count} errors, {collision_count} collisions",
                        file=sys.stderr,
                    )
            except Exception as e:
                error_count += 1
                print(f"Error linking {log_file}: {e}", file=sys.stderr)
                # Continue processing other files

    print(
        f"Completed: {linked_count} files linked, {error_count} errors, {collision_count} collisions"
    )

    if error_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

