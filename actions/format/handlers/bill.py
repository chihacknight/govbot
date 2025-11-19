from pathlib import Path
import json
from typing import Any
from utils.file_utils import (
    validate_required_field,
    write_action_logs,
)
from utils.timestamp_tracker import (
    LatestTimestamps,
)
from utils.processing_tracker import (
    load_existing_metadata,
    find_new_actions,
    merge_actions,
    add_processing_timestamp,
    get_current_timestamp,
)
from utils.path_utils import build_bill_path


def handle_bill(
    STATE_ABBR: str,
    data: dict[str, Any],
    DATA_PROCESSED_FOLDER: Path,
    DATA_NOT_PROCESSED_FOLDER: Path,
    filename: str,
    latest_timestamps: LatestTimestamps,
) -> bool:
    """
    Handles a bill JSON file by saving:

    1. Bill metadata as metadata.json in the bill folder
    2. One separate JSON file per action in logs/, each timestamped and slugified
    3. A files/ directory, ready for bill text files

    Skips and logs errors if required fields (e.g. identifier) are missing.

    Returns:
        bool: True if saved successfully, False if skipped due to missing identifier.
    """

    bill_identifier = validate_required_field(
        data,
        "identifier",
        filename,
        DATA_NOT_PROCESSED_FOLDER,
        "from_handle_bill_missing_identifier",
        "Bill missing identifier",
    )
    if not bill_identifier:
        return False

    session_id = data.get("legislative_session", "unknown-session")

    # Use centralized path builder
    save_path = build_bill_path(
        DATA_PROCESSED_FOLDER, STATE_ABBR, session_id, bill_identifier
    )

    (save_path / "logs").mkdir(parents=True, exist_ok=True)
    (save_path / "files").mkdir(parents=True, exist_ok=True)

    # Load existing metadata to check for incremental changes
    existing_metadata = load_existing_metadata(DATA_PROCESSED_FOLDER, STATE_ABBR, data)

    actions = data.get("actions", [])

    # Determine which actions are new and need processing
    if existing_metadata:
        existing_actions = existing_metadata.get("actions", [])
        new_actions = find_new_actions(existing_actions, actions)

        # Only write logs for new actions
        if new_actions:
            write_action_logs(new_actions, bill_identifier, save_path / "logs")

            # Add processing timestamps to new actions
            for action in new_actions:
                add_processing_timestamp(action, "log_file_created")

        # Merge actions: preserve existing _processing fields, add new actions
        data["actions"] = merge_actions(existing_actions, actions)

        # Update bill-level _processing timestamp
        if "_processing" not in data:
            data["_processing"] = {}

        # Preserve existing bill-level fields if they exist
        if "_processing" in existing_metadata:
            data["_processing"].update(existing_metadata["_processing"])

        # Update logs timestamp
        data["_processing"]["logs_latest_update"] = get_current_timestamp()
    else:
        # New bill: process all actions
        if actions:
            write_action_logs(actions, bill_identifier, save_path / "logs")

            # Add processing timestamps to all actions
            for action in actions:
                add_processing_timestamp(action, "log_file_created")

        # Set initial bill-level _processing
        data["_processing"] = {"logs_latest_update": get_current_timestamp()}

    # Save bill metadata with _processing fields
    metadata_file = save_path / "metadata.json"
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return True
