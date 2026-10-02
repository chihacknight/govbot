import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, TypedDict, Union
from .file_utils import format_timestamp, record_error_file
from .processing_tracker import get_current_date


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
    # {category: {"YYYY-MM-DD": count}} -- how many times update_latest_timestamp()
    # (below) rejected a category's own date as implausible and fell back to
    # today's date instead. Covers all three timestamp categories (actions,
    # events, vote_events), not just actions -- events/vote_events matter
    # *more* here, since their watermark also gates whether a file gets
    # processed at all (see is_newer_than_latest() + io_utils.py): a poisoned
    # events/vote_events watermark wouldn't just look wrong, it would
    # silently make every future real event/vote_event fail that gate and
    # get dropped forever, never processed, no trace. Normally tiny (real
    # source-data typos are rare -- found exactly 2 across ~2,000 real log
    # files for MP this session, both in `actions`). If this ever spikes on
    # the same day as a big action_log_files_created count, that's a
    # systemic date-parsing bug, not isolated upstream typos.
    implausible_date_fallbacks: dict[str, dict[str, int]]
    # Months-deep daily histogram {"YYYY-MM-DD": count} of genuinely NEW bills
    # seen for the first time ever (handlers/bill.py's "New bill" branch --
    # existing_metadata is falsy), keyed by the date this run executed, same
    # pattern as action_log_files_created. Deliberately a DIFFERENT question
    # from that field: action_log_files_created answers "did the pipeline
    # find anything new today" (a new action on an already-known bill counts),
    # this answers "did we discover a brand-new bill today" specifically --
    # the two can diverge (a state could have ongoing activity on existing
    # bills while bill *discovery* has silently stalled, which is exactly
    # the UT case found 2026-10-02: a scraper stuck at the same bill count
    # for weeks while still reporting GitHub Actions "success"). Built
    # specifically to feed a weekly flatline audit
    # (tamara-notes/processes/audit_new_bill_flatline.py) that flags any
    # in-session state with zero new bills for 7+ consecutive days.
    # Deliberately NOT derived from action-log dates -- GU has 277 real bills
    # and zero action logs ever (confirmed empirically), so a signal based on
    # logs would be permanently blind for GU; hooking the actual "new bill"
    # branch in handle_bill() works regardless of whether a bill has any
    # actions at all.
    new_bills_seen: dict[str, int]


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
        "implausible_date_fallbacks": {},
        "new_bills_seen": {},
    }


# Keys in LatestTimestamps whose value is a plain dict (not a datetime) --
# read/write need to treat these differently from the timestamp categories.
_DICT_VALUED_KEYS = {"action_log_files_created", "implausible_date_fallbacks", "new_bills_seen"}

# How far into the future a category's own date can plausibly be before
# it's treated as a source-data error rather than real data, for ratchet
# purposes. Real example that motivated this: CNMI's own official site
# (cnmileg.net) shows a literal clerical typo, "05/09/35" instead of
# "05/09/25", for a real bill action -- confirmed directly against the
# source, not a scraping bug. See
# tamara-notes/processes/presentation-talking-points.md item 1 and
# tamara-notes/processes/dream-list.md item 1.
_MAX_FUTURE_SLACK = timedelta(days=2)


def _is_plausible_date(dt: datetime) -> bool:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return dt <= now + _MAX_FUTURE_SLACK


def _record_implausible_date_fallback(
    category: str, latest_timestamps: LatestTimestamps
) -> None:
    today = get_current_date()
    by_category = latest_timestamps["implausible_date_fallbacks"]
    bucket = by_category.setdefault(category, {})
    bucket[today] = bucket.get(today, 0) + 1


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
    """Bump latest_timestamps[category] to current_dt if it's newer.

    Guards against implausible (source-data-error) dates before they can
    ever reach the watermark: since this ratchet never regresses, one bad
    future date would otherwise poison it permanently. Matters most for
    "events"/"vote_events" -- their watermark doesn't just get reported, it
    actively gates whether future files get processed at all
    (is_newer_than_latest(), called from io_utils.py before this function
    ever runs) -- so an unguarded poison here would silently and
    permanently drop real data, not just look wrong. An implausible date
    falls back to today's own date instead of being skipped outright, so a
    systemic failure (e.g. every date suddenly looking implausible) still
    advances the watermark rather than freezing it with no trace -- see
    _record_implausible_date_fallback for the visible counter that makes
    that distinguishable from a normal, rare, isolated source typo.
    """
    if not current_dt:
        return existing_dt

    if not _is_plausible_date(current_dt):
        print(
            f"⚠️ Implausible {category} date {current_dt} (more than "
            f"{_MAX_FUTURE_SLACK} in the future) -- falling back to today "
            "rather than trusting it"
        )
        current_dt = datetime.now(timezone.utc).replace(tzinfo=None)
        _record_implausible_date_fallback(category, latest_timestamps)

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
