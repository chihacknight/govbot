"""
Processing Tracker Utilities

This module provides utilities for tracking what data has been processed
and what is new. Used for incremental processing to avoid reprocessing
existing data while ensuring no new data is missed.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Tuple

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


def create_action_identifier(action: dict) -> str:
    """
    Create a unique identifier for an action using description + date.

    Args:
        action: Action dict with 'description' and 'date' keys

    Returns:
        Unique identifier string
    """
    description = action.get("description", "")
    date = action.get("date", "")
    return f"{description}|{date}"


def find_new_actions(existing_actions: list, incoming_actions: list) -> list:
    """
    Find actions in incoming list that don't exist in existing list.

    Uses description + date to identify unique actions.

    Args:
        existing_actions: List of actions from existing metadata
        incoming_actions: List of actions from new scrape

    Returns:
        List of new actions that need to be processed
    """
    existing_ids = {create_action_identifier(action) for action in existing_actions}

    new_actions = []
    for action in incoming_actions:
        action_id = create_action_identifier(action)
        if action_id not in existing_ids:
            new_actions.append(action)

    return new_actions


def merge_actions(existing_actions: list, incoming_actions: list) -> list:
    """
    Merge existing and incoming actions, preserving _processing timestamps.

    For actions that exist in both lists, keeps the existing action with its
    _processing timestamps. For new actions, includes them from incoming list.

    Args:
        existing_actions: List of actions from existing metadata (with _processing fields)
        incoming_actions: List of actions from new scrape (no _processing fields)

    Returns:
        Merged list with all actions, preserving existing _processing timestamps
    """
    # Create a map of existing actions by identifier
    existing_map = {}
    for action in existing_actions:
        action_id = create_action_identifier(action)
        existing_map[action_id] = action

    # Build merged list
    merged = []
    for action in incoming_actions:
        action_id = create_action_identifier(action)
        if action_id in existing_map:
            # Use existing action (has _processing timestamps)
            merged.append(existing_map[action_id])
        else:
            # New action - use incoming data
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


def compare_action_counts(
    existing_metadata: Optional[dict], incoming_data: dict
) -> Tuple[bool, int, int]:
    """
    Compare action counts between existing and incoming data.

    Args:
        existing_metadata: Existing metadata dict (or None if new bill)
        incoming_data: Incoming scraped data

    Returns:
        Tuple of (should_process, existing_count, incoming_count)
        - should_process: True if counts differ or bill is new
        - existing_count: Number of actions in existing metadata
        - incoming_count: Number of actions in incoming data
    """
    incoming_count = len(incoming_data.get("actions", []))

    if existing_metadata is None:
        # New bill - always process
        return (True, 0, incoming_count)

    existing_count = len(existing_metadata.get("actions", []))

    # Process if counts are different
    should_process = existing_count != incoming_count

    return (should_process, existing_count, incoming_count)
