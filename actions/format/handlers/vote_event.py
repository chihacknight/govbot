import json
from pathlib import Path
from utils.file_utils import (
    format_timestamp,
    validate_required_field,
    write_vote_event_log,
)
from utils.timestamp_tracker import (
    update_latest_timestamp,
    to_dt_obj,
    LatestTimestamps,
)
from utils.path_utils import build_bill_path


def handle_vote_event(
    STATE_ABBR: str,
    data: dict[str, any],
    DATA_PROCESSED_FOLDER: Path,
    DATA_NOT_PROCESSED_FOLDER: Path,
    filename: str,
    latest_timestamps: LatestTimestamps,
) -> bool:
    """
    Handles a vote_event JSON file by:

    1. Creating the associated bill folder (and placeholder if missing)
    2. Saving the full vote_event as a timestamped log file using result info
       Format: YYYYMMDDT000000Z_vote_event_<result>.json

    Skips and logs errors if bill_identifier is missing.
    """

    referenced_bill_id = validate_required_field(
        data,
        "bill_identifier",
        filename,
        DATA_NOT_PROCESSED_FOLDER,
        "from_handle_vote_event_missing_bill_identifier",
        "Vote missing bill_identifier",
    )
    if not referenced_bill_id:
        return False

    session_id = data.get("legislative_session", "unknown-session")

    # Use centralized path builder
    save_path = build_bill_path(
        DATA_PROCESSED_FOLDER, STATE_ABBR, session_id, referenced_bill_id
    )

    (save_path / "logs").mkdir(parents=True, exist_ok=True)
    (save_path / "files").mkdir(parents=True, exist_ok=True)

    # Add placeholder if bill doesn't exist
    placeholder_file = save_path / "placeholder.json"
    if not placeholder_file.exists():
        placeholder_data = {"identifier": referenced_bill_id, "placeholder": True}
        with open(placeholder_file, "w", encoding="utf-8") as f:
            json.dump(placeholder_data, f, indent=2)

    # Save timestamped vote log
    date = data.get("start_date")
    timestamp = format_timestamp(date)
    if timestamp == "unknown":
        print(
            f"⚠️ Vote Event {referenced_bill_id} has unrecognized timestamp format: {date}"
        )
    else:
        current_dt = to_dt_obj(timestamp)
        latest_timestamps["vote_events"] = update_latest_timestamp(
            "vote_events",
            current_dt,
            latest_timestamps["vote_events"],
            latest_timestamps,
        )

    write_vote_event_log(data, save_path / "logs")
    return True
