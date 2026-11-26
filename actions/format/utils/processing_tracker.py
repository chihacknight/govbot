"""
Processing Tracker Utilities

Helpers for updating a bill's metadata.json from tonight's scrape. Every bill is
processed every night; what is new is decided against the bill's action log
(utils/log_jsonl.py), not here.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .log_jsonl import raw_action_key
from .path_utils import build_bill_path


def load_existing_metadata(
    data_processed_folder: Path, state_abbr: str, bill_data: dict
) -> Optional[dict]:
    """
    Load existing metadata.json for a bill if it exists.

    Args:
        data_processed_folder: Path to data_processed folder
        state_abbr: State abbreviation (e.g., 'usa', 'ca')
        bill_data: The incoming bill data with identifier and session

    Returns:
        Existing metadata dict if found, None if bill is new
    """
    bill_identifier = bill_data.get("identifier")
    session_id = bill_data.get("legislative_session", "unknown-session")

    if not bill_identifier:
        return None

    # Use centralized path builder
    bill_folder = build_bill_path(
        data_processed_folder, state_abbr, session_id, bill_identifier
    )
    metadata_path = bill_folder / "metadata.json"

    if not metadata_path.exists():
        return None

    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Error loading existing metadata for {bill_identifier}: {e}")
        return None


def merge_actions(existing_actions: list, incoming_actions: list, rewordings=None) -> list:
    """
    Tonight's actions, in tonight's order, each replaced by the same action from
    existing metadata when there is one, so it keeps its _processing timestamps.

    "The same action" is what the action log means by it (raw_action_key: date,
    description ignoring whitespace, chamber). Ignoring whitespace: KY's scraper
    started putting line breaks inside descriptions, and an exact match would read
    each as a new action and drop its _processing.log_file_created. Chamber: two
    chambers often record identically worded actions on one date ("Read first
    time"); without it both collapsed onto one of the existing actions.

    A rewording (`rewordings`, from find_rewordings) takes tonight's wording and
    keeps the _processing of the action it rewords, as its log line keeps that
    action's id (WY HB0144, 2026-02-23: "H COW:H Motion to move Bill up for
    Consideration Failed…" -> "H Motion to move Bill up in General File Failed…").

    Args:
        existing_actions: List of actions from existing metadata (with _processing fields)
        incoming_actions: List of actions from new scrape (no _processing fields)
        rewordings: log_jsonl.Rewordings for these two lists, or None

    Returns:
        Merged list with all actions, preserving existing _processing timestamps
    """
    existing_map = {raw_action_key(action): action for action in existing_actions}
    pairs = rewordings.pairs if rewordings else {}
    merged = []
    for action in incoming_actions:
        key = raw_action_key(action)
        if key in existing_map:
            merged.append(existing_map[key])
            continue
        reworded = existing_map.get(pairs.get(key))
        if reworded is not None and "_processing" in reworded:
            action = {**action, "_processing": dict(reworded["_processing"])}
        merged.append(action)
    return merged


def add_processing_timestamp(action: dict, field_name: str) -> None:
    """
    Add a timestamp to an action's _processing field.

    Modifies the action dict in place.

    Args:
        action: Action dict to update
        field_name: Name of the timestamp field (e.g., 'log_file_created', 'text_extracted')
    """
    if "_processing" not in action:
        action["_processing"] = {}

    action["_processing"][field_name] = get_current_timestamp()


def get_current_timestamp() -> str:
    """
    Get current UTC timestamp in ISO format.

    Returns:
        ISO formatted timestamp string (e.g., '2025-10-17T19:30:00Z')
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_current_date() -> str:
    """
    Get the current UTC date -- the day this run of actions/format itself
    executed, deliberately unrelated to any bill's own action date. Used to
    key the action_log_files_created activity histogram (see
    timestamp_tracker.py) so a malformed/garbage date inside upstream bill
    data can never corrupt it.

    Returns:
        Date string, e.g. '2026-09-30'
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
