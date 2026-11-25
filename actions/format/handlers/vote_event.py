import json
from pathlib import Path
from typing import Optional
from utils.file_utils import (
    format_timestamp,
    validate_required_field,
)
from utils.log_jsonl import append_votes, vote_event_line
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
    first_seen: Optional[str] = None,
    pending_votes: Optional[dict[Path, list]] = None,
) -> bool:
    """
    Handles a vote_event JSON file by:

    1. Creating the associated bill folder (and placeholder if missing)
    2. Queuing the vote in `pending_votes` (bill folder -> lines), which
       process_and_save writes with append_votes once per bill, so the log rules
       see every version of a vote in the scrape at once (utils/log_jsonl.py,
       select_new_votes). Without `pending_votes` the vote is appended now.
       Every vote in the scrape is checked, whatever its date: the old "newer
       than the newest vote seen" gate silently dropped votes that arrived late
       (10,476 across 14 states as of 2026-11-24).

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

    (save_path / "files").mkdir(parents=True, exist_ok=True)

    # Add placeholder if bill doesn't exist
    placeholder_file = save_path / "placeholder.json"
    if not placeholder_file.exists():
        placeholder_data = {"identifier": referenced_bill_id, "placeholder": True}
        with open(placeholder_file, "w", encoding="utf-8") as f:
            json.dump(placeholder_data, f, indent=2)

    # Keep the vote watermark current; audits report it. It no longer gates anything.
    date = data.get("start_date")
    timestamp = format_timestamp(date)
    # format_timestamp returns None (not "unknown") for a missing/unparseable
    # date. Such a vote is still logged; it just can't move the watermark.
    if not timestamp:
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

    line = vote_event_line(data, first_seen)
    if pending_votes is None:
        append_votes(save_path, [line], STATE_ABBR)
    else:
        pending_votes.setdefault(save_path, []).append(line)
    return True
