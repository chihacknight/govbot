from pathlib import Path
import json
from typing import Any
from utils.file_utils import (
    format_timestamp,
    validate_required_field,
    write_action_logs,
)
from utils.timestamp_tracker import (
    LatestTimestamps,
    to_dt_obj,
    update_latest_timestamp,
)
from utils.processing_tracker import (
    load_existing_metadata,
    find_new_actions,
    merge_actions,
    add_processing_timestamp,
    get_current_timestamp,
    get_current_date,
)
from utils.path_utils import build_bill_path


def _update_actions_watermark(
    actions: list[dict[str, Any]], latest_timestamps: LatestTimestamps
) -> None:
    """Bump latest_timestamps["actions"] to the newest date among `actions`.

    Mirrors handlers/event.py's pattern for its own "events" category, but
    keyed on each action's own "date" field (the government's recorded date,
    same field write_action_logs() uses for log filenames) rather than
    "start_date" -- bill actions and top-level Event/VoteEvent records use
    different field names for the same concept.

    Implausible (source-data-error) dates are guarded centrally inside
    update_latest_timestamp() itself, not here -- see that function's
    docstring in timestamp_tracker.py. write_action_logs() already wrote
    every action to logs/ untouched before this runs regardless, preserving
    a faithful record of exactly what the government published.
    """
    for action in actions:
        timestamp = format_timestamp(action.get("date", ""))
        if timestamp and timestamp != "unknown":
            current_dt = to_dt_obj(timestamp)
            latest_timestamps["actions"] = update_latest_timestamp(
                "actions", current_dt, latest_timestamps["actions"], latest_timestamps
            )


def _record_action_log_files_created(
    count: int, latest_timestamps: LatestTimestamps
) -> None:
    """Bump today's bucket in the action_log_files_created activity histogram.

    Deliberately independent of _update_actions_watermark above: keyed by the
    date this run of actions/format itself executed (get_current_date()), not
    by anything in the bill data, so a garbage/malformed action date upstream
    (e.g. the real 2035 value found for MP this session) can't corrupt it.
    Additive, not overwrite -- a same-day re-run (manual re-dispatch same day
    as the scheduled run) should add to the day's real total, not replace it.
    """
    if count <= 0:
        return
    today = get_current_date()
    bucket = latest_timestamps["action_log_files_created"]
    bucket[today] = bucket.get(today, 0) + count


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
    sources = data.get("sources", [])

    # Determine which actions are new and need processing
    if existing_metadata:
        existing_actions = existing_metadata.get("actions", [])
        new_actions = find_new_actions(existing_actions, actions)

        # Only write logs for new actions
        if new_actions:
            write_action_logs(
                new_actions, bill_identifier, sources, session_id, save_path / "logs"
            )

            # Add processing timestamps to new actions
            for action in new_actions:
                add_processing_timestamp(action, "log_file_created")

            _update_actions_watermark(new_actions, latest_timestamps)
            _record_action_log_files_created(len(new_actions), latest_timestamps)

        # Merge actions: preserve existing _processing fields, add new actions
        data["actions"] = merge_actions(existing_actions, actions)

        # Update bill-level _processing timestamp
        if "_processing" not in data:
            data["_processing"] = {}

        # Preserve existing bill-level fields if they exist
        if "_processing" in existing_metadata:
            data["_processing"].update(existing_metadata["_processing"])

        # Update logs timestamp -- gated on new_actions, not unconditional:
        # this field is meant to mean "the last time this bill's logs/
        # actually changed," and previously got bumped to the current run
        # time on every single call regardless of whether anything new was
        # found, which made it useless as a staleness signal (see
        # tamara-notes/processes/dream-list.md item 2).
        if new_actions:
            data["_processing"]["logs_latest_update"] = get_current_timestamp()
    else:
        # New bill: process all actions
        if actions:
            write_action_logs(
                actions, bill_identifier, sources, session_id, save_path / "logs"
            )

            # Add processing timestamps to all actions
            for action in actions:
                add_processing_timestamp(action, "log_file_created")

            _update_actions_watermark(actions, latest_timestamps)
            _record_action_log_files_created(len(actions), latest_timestamps)

        # Set initial bill-level _processing. A brand-new bill with zero
        # actions genuinely has no logs/ entry to date, so logs_latest_update
        # is only set when there was something to log -- same gating as the
        # existing-bill branch above, kept consistent rather than always
        # stamping the current run time regardless of content.
        data["_processing"] = (
            {"logs_latest_update": get_current_timestamp()} if actions else {}
        )

    # Save bill metadata with _processing fields
    metadata_file = save_path / "metadata.json"
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return True
