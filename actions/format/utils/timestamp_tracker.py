import json
from pathlib import Path
from datetime import datetime
from typing import Any, Optional, TypedDict, Union
from .file_utils import format_timestamp, record_error_file


class LatestTimestamps(TypedDict):
    """Type definition for the latest timestamps dictionary."""

    vote_events: datetime
    events: datetime
    # Most recent government-recorded date among genuinely new bill actions
    # this run (handlers/bill.py, gated on find_new_actions() finding
    # something new -- unlike events/vote_events, which are separate
    # top-level OCD record types many states never populate at all, this
    # covers ordinary bill activity and is the one most states will actually
    # move. See tamara-notes/processes/dream-list.md item 2 for why this was
    # added: vote_events/events alone made states with no published votes or
    # calendar events (e.g. MA) look permanently stuck at the sentinel below,
    # indistinguishable from a broken pipeline.
    actions: datetime
    # Deliberately independent cross-check for `actions`: a months-deep daily
    # histogram {"YYYY-MM-DD": count}, keyed by the date *this run itself*
    # executed (get_current_date(), processing_tracker.py) -- never by a
    # bill's own action date, so a garbage upstream date (e.g. the real 2035
    # value found for MP this session) can't corrupt it. Count = how many new
    # action-log files were written that day, across all bills. If `actions`
    # ever looks wrong, this gives an independent "did we actually get real
    # activity around then" signal to check it against.
    action_log_files_created: dict[str, int]


def get_latest_timestamp_path(output_folder: Path) -> Path:
    """Get the path to the latest timestamp file based on the output folder."""
    return output_folder / ".windycivi" / "latest_timestamp_seen.txt"


def get_default_timestamps() -> LatestTimestamps:
    """Get default timestamps dictionary."""
    return {
        "vote_events": datetime(1900, 1, 1),
        "events": datetime(1900, 1, 1),
        "actions": datetime(1900, 1, 1),
        "action_log_files_created": {},
    }


# Keys in LatestTimestamps whose value is a plain dict (not a datetime) --
# read/write need to treat these differently from the timestamp categories.
_DICT_VALUED_KEYS = {"action_log_files_created"}


def read_latest_timestamps(output_folder: Path) -> LatestTimestamps:
    """Read latest timestamps from file, returning defaults if file doesn't exist."""
    timestamp_path = get_latest_timestamp_path(output_folder)
    try:
        with open(timestamp_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
            print(f"📂 Raw timestamp file contents: {json.dumps(raw, indent=2)}")
            # Merge onto defaults, not just whatever's in the file -- a file
            # committed before a given category existed won't have that key
            # at all, and callers index latest_timestamps[...] unconditionally
            # (see handlers/bill.py).
            timestamps = get_default_timestamps()
            for k, v in raw.items():
                if not v:
                    continue
                if k in _DICT_VALUED_KEYS:
                    timestamps[k] = v
                else:
                    timestamps[k] = to_dt_obj(v)
            return timestamps
    except Exception:
        print("⚠️ No timestamp file found or invalid JSON. Using defaults.")
        return get_default_timestamps()


def to_dt_obj(ts_str: Union[str, datetime]) -> Optional[datetime]:
    if isinstance(ts_str, datetime):
        return ts_str
    try:
        ts_str = ts_str.rstrip("Z")
        if "-" in ts_str:
            return datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S")
        else:
            return datetime.strptime(ts_str, "%Y%m%dT%H%M%S")
    except Exception as e:
        print(f"❌ Failed to parse timestamp: {ts_str} ({e})")
        return None


def update_latest_timestamp(
    category: str,
    current_dt: Optional[datetime],
    existing_dt: Optional[datetime],
    latest_timestamps: LatestTimestamps,
) -> Optional[datetime]:
    if not current_dt:
        return existing_dt

    if not existing_dt or current_dt > existing_dt:
        latest_timestamps[category] = current_dt
        print(f"🕓 Updating {category} latest timestamp to {current_dt}")
        print(f"📄 File contents: {latest_timestamps}")
        return current_dt

    return existing_dt


def extract_timestamp(data: dict[str, Any], category: str) -> Optional[str]:
    """
    Extract timestamp from data for events and vote_events.
    Note: Bills no longer use this - they use incremental processing with _processing metadata.
    """
    try:
        if category == "events":
            date = data.get("start_date")
            if date:
                return format_timestamp(date)
            return "MISSING_EVENT_DATE"

        elif category == "vote_events":
            date = data.get("start_date")
            if date:
                return format_timestamp(date)
            return "MISSING_VOTE_DATE"

        return "UNKNOWN_CATEGORY"

    except Exception as e:
        return f"ERROR_{category.upper()}_{str(e)}"


def is_newer_than_latest(
    data: dict[str, Any],
    latest_timestamp_dt: datetime,
    category: str,
    DATA_NOT_PROCESSED_FOLDER: Path,
) -> bool:
    raw_ts = extract_timestamp(data, category)

    if isinstance(raw_ts, str) and raw_ts in {
        "MISSING_EVENT_DATE",
        "MISSING_VOTE_DATE",
        "UNKNOWN_CATEGORY",
    }:
        print(f"⚠️ Skipping item in {category} — invalid timestamp: {raw_ts}")
        record_error_file(
            DATA_NOT_PROCESSED_FOLDER,
            f"from_is_newer_than_latest_{raw_ts.lower()}",
            filename="unknown.json",
            data=data,
        )
        return False

    try:
        current_dt = to_dt_obj(raw_ts)
        return current_dt > latest_timestamp_dt if current_dt else False
    except Exception as e:
        print(f"❌ Failed to parse timestamp '{raw_ts}' in {category}: {e}")
        record_error_file(
            DATA_NOT_PROCESSED_FOLDER,
            f"from_is_newer_than_latest_parse_error",
            filename="unknown.json",
            data=data,
            original_filename=raw_ts,
        )
        return False


def write_latest_timestamp_file(
    output_folder: Path, latest_timestamps: LatestTimestamps
):
    try:
        output = {}
        for k, dt in latest_timestamps.items():
            if isinstance(dt, datetime):
                output[k] = dt.strftime("%Y-%m-%dT%H:%M:%S")
            elif k in _DICT_VALUED_KEYS and dt:
                output[k] = dt

        if not output:
            print("⚠️ No timestamps to write.")
            return

        timestamp_path = get_latest_timestamp_path(output_folder)
        timestamp_path.parent.mkdir(parents=True, exist_ok=True)
        with open(timestamp_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)

        print(f"📝 Updated latest timestamp path: {timestamp_path}")
        print("📄 File contents:")
        print(json.dumps(output, indent=2))

    except Exception as e:
        print(f"❌ Failed to write latest timestamp: {e}")
