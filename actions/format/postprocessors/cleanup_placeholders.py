"""
Post-processor to clean up placeholder.json files after processing.

When a vote_event or event comes through before its bill, we create a placeholder.json
to hold the folder structure. Once the bill is processed (metadata.json exists), we can
safely delete the placeholder.

This module also reports "orphaned" placeholders - bills that never got real data,
with persistent tracking to show how long they've been orphaned.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List


def load_orphan_tracking(repo_root: Path) -> Dict:
    """
    Load existing orphan tracking data.

    Returns a dict mapping bill_id to tracking info:
    {
      "HR999": {
        "first_seen": "2025-10-21T12:00:00Z",
        "last_seen": "2025-10-23T12:00:00Z",
        "occurrence_count": 3,
        "session": "119",
        "vote_count": 2,
        "event_count": 0
      }
    }
    """
    tracking_file = (
        repo_root / ".windycivi" / "errors" / "orphaned_placeholders_tracking.json"
    )

    if tracking_file.exists():
        with open(tracking_file, "r", encoding="utf-8") as f:
            return json.load(f)

    return {}


def save_orphan_tracking(repo_root: Path, tracking_data: Dict) -> None:
    """Save orphan tracking data to persistent file."""
    tracking_file = (
        repo_root / ".windycivi" / "errors" / "orphaned_placeholders_tracking.json"
    )
    tracking_file.parent.mkdir(parents=True, exist_ok=True)

    with open(tracking_file, "w", encoding="utf-8") as f:
        json.dump(tracking_data, f, indent=2, sort_keys=True)


def cleanup_placeholders(repo_root: Path) -> Dict[str, int]:
    """
    Clean up placeholder.json files after all processing is complete.

    Process:
    1. Load existing orphan tracking data
    2. Find all placeholder.json files in bill folders
    3. Check if the bill has metadata.json (real bill data)
    4. If yes: delete the placeholder and remove from tracking
    5. If no: keep it and update tracking (first_seen, last_seen, occurrence_count)

    Args:
        repo_root: Path to the git repository root

    Returns:
        Dict with stats:
        - placeholders_found: Total placeholders discovered
        - placeholders_deleted: Placeholders removed (bill exists)
        - orphans_found: Placeholders kept (bill missing)
        - new_orphans: Orphans found for the first time
        - resolved_orphans: Orphans that now have bills
    """
    print("\n🧹 Cleaning up placeholder files...")

    current_timestamp = datetime.now().isoformat()

    # Load existing tracking
    orphan_tracking = load_orphan_tracking(repo_root)

    placeholders_found = 0
    placeholders_deleted = 0
    orphans_current_run = set()  # Bill IDs found as orphans this run
    new_orphans = 0
    resolved_orphans = 0

    # Find all placeholder.json files in bill folders
    # Pattern: country:us/state:*/sessions/*/bills/*/placeholder.json
    for placeholder_file in repo_root.rglob("**/bills/*/placeholder.json"):
        placeholders_found += 1
        bill_folder = placeholder_file.parent
        metadata_file = bill_folder / "metadata.json"

        # Extract bill info for reporting
        bill_id = bill_folder.name
        session_folder = bill_folder.parent.parent
        session_id = session_folder.name

        if metadata_file.exists():
            # Bill exists! Placeholder is redundant - delete it
            placeholder_file.unlink()
            placeholders_deleted += 1
            print(f"   ✓ Deleted placeholder for {bill_id} (bill exists)")

            # If this bill was tracked as orphan, it's now resolved!
            if bill_id in orphan_tracking:
                resolved_orphans += 1
                print(
                    f"   🎉 Resolved orphan: {bill_id} (was orphaned for {orphan_tracking[bill_id]['occurrence_count']} runs)"
                )
                del orphan_tracking[bill_id]
        else:
            # Orphan! Bill never came through, but we have votes/events for it
            orphans_current_run.add(bill_id)

            # Check what data we do have
            logs_folder = bill_folder / "logs"
            has_logs = logs_folder.exists()

            vote_count = 0
            event_count = 0

            if has_logs:
                for log_file in logs_folder.glob("*.json"):
                    if "vote" in log_file.name:
                        vote_count += 1
                    elif "event" in log_file.name:
                        event_count += 1

            # Update tracking
            if bill_id in orphan_tracking:
                # Existing orphan - update last_seen and increment count
                orphan_tracking[bill_id]["last_seen"] = current_timestamp
                orphan_tracking[bill_id]["occurrence_count"] += 1
                orphan_tracking[bill_id]["vote_count"] = vote_count
                orphan_tracking[bill_id]["event_count"] = event_count
                print(
                    f"   ⚠️  Orphan: {bill_id} (session {session_id}) - "
                    f"seen {orphan_tracking[bill_id]['occurrence_count']} times, "
                    f"{vote_count} votes, {event_count} events"
                )
            else:
                # New orphan - initialize tracking
                orphan_tracking[bill_id] = {
                    "first_seen": current_timestamp,
                    "last_seen": current_timestamp,
                    "occurrence_count": 1,
                    "session": session_id,
                    "vote_count": vote_count,
                    "event_count": event_count,
                    "path": str(bill_folder.relative_to(repo_root)),
                }
                new_orphans += 1
                print(
                    f"   🆕 New orphan: {bill_id} (session {session_id}) - "
                    f"{vote_count} votes, {event_count} events"
                )

    # Save updated tracking
    if orphan_tracking:
        save_orphan_tracking(repo_root, orphan_tracking)
        print(
            f"\n📋 Orphan tracking updated: .windycivi/errors/orphaned_placeholders_tracking.json"
        )
        print(f"   Total orphans being tracked: {len(orphan_tracking)}")

        # Show chronic orphans (seen 3+ times)
        chronic_orphans = {
            bid: data
            for bid, data in orphan_tracking.items()
            if data["occurrence_count"] >= 3
        }
        if chronic_orphans:
            print(f"   ⚠️  Chronic orphans (3+ occurrences): {len(chronic_orphans)}")
            for bill_id, data in list(chronic_orphans.items())[:5]:  # Show first 5
                print(f"      - {bill_id}: {data['occurrence_count']} times")

        print(f"\n   Review for:")
        print(f"   - Typos in vote/event bill identifiers")
        print(f"   - Bills that exist but weren't scraped")
        print(f"   - Data quality issues from the source")

    # Summary
    print(f"\n✨ Placeholder cleanup complete:")
    print(f"   Found: {placeholders_found}")
    print(f"   Deleted: {placeholders_deleted} (bills exist)")
    print(f"   Orphaned: {len(orphan_tracking)} (bills missing)")
    if new_orphans > 0:
        print(f"   New orphans: {new_orphans}")
    if resolved_orphans > 0:
        print(f"   Resolved: {resolved_orphans} 🎉")

    return {
        "placeholders_found": placeholders_found,
        "placeholders_deleted": placeholders_deleted,
        "orphans_found": len(orphan_tracking),
        "new_orphans": new_orphans,
        "resolved_orphans": resolved_orphans,
    }
