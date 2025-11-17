from pathlib import Path
import json
import re
from typing import Any
from utils.file_utils import format_timestamp, validate_required_field
from utils.timestamp_tracker import (
    update_latest_timestamp,
    to_dt_obj,
    LatestTimestamps,
)


def clean_event_name(name: str) -> str:
    return re.sub(r"[^\w]+", "_", name.lower()).strip("_")[:40]


def handle_event(
    state_abbr: str,
    data: dict[str, any],
    repo_root: Path,
    errors_folder: Path,
    filename: str,
    latest_timestamps: LatestTimestamps,
    session_id: str = None,
    referenced_bill_id: str = None,
) -> bool:
    """
    Saves event JSON to the correct session folder under events,
    using a consistent timestamped format to match bill action logs.
    """
    event_id = data.get("_id") or filename.replace(".json", "")

    start_date = validate_required_field(
        data,
        "start_date",
        filename,
        errors_folder,
        "from_handle_event_missing_start_date",
        f"Event {event_id} missing start_date",
    )
    if not start_date:
        return False

    # Use provided referenced_bill_id if available (from event linking)
    # Otherwise, validate that bill_identifier exists in the data
    if referenced_bill_id is None:
        referenced_bill_id = validate_required_field(
            data,
            "bill_identifier",
            filename,
            errors_folder,
            "from_handle_event_missing_bill_identifier",
            "Event missing bill_identifier",
        )
        if not referenced_bill_id:
            return False

    timestamp = format_timestamp(start_date)
    if timestamp == "unknown":
        print(f"⚠️ Event {event_id} has unrecognized timestamp format: {start_date}")
    else:
        current_dt = to_dt_obj(timestamp)
        latest_timestamps["events"] = update_latest_timestamp(
            "events", current_dt, latest_timestamps["events"], latest_timestamps
        )

    event_name = data.get("name", "event")
    short_name = clean_event_name(event_name)

    # Use provided session_id if available (from event linking), otherwise get from data
    if session_id is None:
        session_id = data.get("legislative_session", "unknown-session")

    # Build path to events folder
    # Events are saved as individual files directly in the events/ folder (not subdirectories)
    events_folder = (
        repo_root
        / "country:us"
        / f"state:{state_abbr.lower()}"
        / "sessions"
        / session_id
        / "events"
    )

    events_folder.mkdir(parents=True, exist_ok=True)

    output_file = events_folder / f"{timestamp}_{short_name}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return True
