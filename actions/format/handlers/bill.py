from pathlib import Path
import json
from typing import Any, Optional
from utils.file_utils import (
    format_timestamp,
    validate_required_field,
)
from utils.bill_guards import BillGuards
from utils.log_jsonl import action_key, action_line, append_actions, find_rewordings, raw_action_key
from utils.timestamp_tracker import (
    LatestTimestamps,
    to_dt_obj,
    update_latest_timestamp,
)
from utils.processing_tracker import (
    load_existing_metadata,
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
    same field the action log line's `occurred_at` comes from) rather than
    "start_date" -- bill actions and top-level Event/VoteEvent records use
    different field names for the same concept.

    Implausible (source-data-error) dates are guarded centrally inside
    update_latest_timestamp() itself, not here -- see that function's
    docstring in timestamp_tracker.py. append_actions() already wrote
    every action to action_logs.jsonl untouched before this runs regardless, preserving
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


def _record_new_bill_seen(latest_timestamps: LatestTimestamps) -> None:
    """Bump today's bucket in the new_bills_seen activity histogram.

    Called once per bill in the "New bill" branch below (existing_metadata
    was falsy) -- deliberately unconditional on whether the bill has any
    actions at all, unlike _record_action_log_files_created above. GU has
    277 real bills and zero action logs ever (confirmed 2026-10-02): a
    "new bill" signal gated on actions would be permanently blind for GU,
    exactly the gap this exists to avoid. Answers a different question than
    action_log_files_created -- "did we discover a brand-new bill today,"
    not "did anything new happen on any bill today" -- see
    tamara-notes/processes/audit_new_bill_flatline.py, which uses this to
    catch a scraper that's stuck at the same bill count while still
    reporting GitHub Actions "success" (the real UT case, found 2026-10-02).
    """
    today = get_current_date()
    bucket = latest_timestamps["new_bills_seen"]
    bucket[today] = bucket.get(today, 0) + 1


def handle_bill(
    STATE_ABBR: str,
    data: dict[str, Any],
    DATA_PROCESSED_FOLDER: Path,
    DATA_NOT_PROCESSED_FOLDER: Path,
    filename: str,
    latest_timestamps: LatestTimestamps,
    first_seen: Optional[str] = None,
    guards: Optional[BillGuards] = None,
) -> bool:
    """
    Handles a bill JSON file by saving:

    1. Bill metadata as metadata.json in the bill folder
    2. Each action not yet logged, appended to action_logs.jsonl in the bill
       folder (see utils/log_jsonl.py), stamped with `first_seen`: when the raw
       scrape holding it was committed

    Every bill is processed every night. For a bill we already have, a field
    tonight's scrape has empty keeps last night's value (`guards`, see
    utils/bill_guards.py).
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

    (save_path / "files").mkdir(parents=True, exist_ok=True)

    # Load existing metadata to check for incremental changes
    existing_metadata = load_existing_metadata(DATA_PROCESSED_FOLDER, STATE_ABBR, data)

    if existing_metadata:
        existing_actions = existing_metadata.get("actions", [])
        if guards is not None:
            guards.keep_nonempty(f"{session_id}/{bill_identifier}", existing_metadata, data)
        actions = data.get("actions", [])
        sources = data.get("sources", [])

        # Every scraped action goes to the log, which keeps only the ones it
        # doesn't have (date + description ignoring whitespace + chamber). A new
        # wording of an action the previous scrape had (metadata.json keeps that
        # scrape's list, in order) is logged as a correction of it, not as a new
        # action.
        rewordings = find_rewordings(existing_actions, actions)
        added: list[dict[str, Any]] = []
        logged = append_actions(
            save_path,
            [action_line(a, bill_identifier, sources, session_id, first_seen) for a in actions],
            rewordings=rewordings,
            added=added,
        )

        # Merge actions: preserve existing _processing fields, add new actions
        data["actions"] = merge_actions(existing_actions, actions, rewordings)

        # Stamp the actions logged tonight (an action already in the log but
        # missing from metadata.json, which the old action-count skip could
        # leave behind, was logged by someone else and gets no stamp).
        added_keys = {action_key(line["action"]) for line in added}
        newly_logged = [a for a in data["actions"] if raw_action_key(a) in added_keys]
        for action in newly_logged:
            if not (action.get("_processing") or {}).get("log_file_created"):
                add_processing_timestamp(action, "log_file_created")
        _update_actions_watermark(newly_logged, latest_timestamps)
        _record_action_log_files_created(logged, latest_timestamps)

        # Update bill-level _processing timestamp
        if "_processing" not in data:
            data["_processing"] = {}

        # Preserve existing bill-level fields if they exist
        if "_processing" in existing_metadata:
            data["_processing"].update(existing_metadata["_processing"])

        # Update logs timestamp -- gated on lines actually being logged, not
        # unconditional: this field is meant to mean "the last time this bill's
        # action log actually changed," and previously got bumped to the current
        # run time on every single call regardless of whether anything new was
        # found, which made it useless as a staleness signal (see
        # tamara-notes/processes/dream-list.md item 2).
        if logged:
            data["_processing"]["logs_latest_update"] = get_current_timestamp()
    else:
        # New bill: process all actions
        _record_new_bill_seen(latest_timestamps)
        actions = data.get("actions", [])
        sources = data.get("sources", [])
        if actions:
            logged = append_actions(
                save_path,
                [action_line(a, bill_identifier, sources, session_id, first_seen) for a in actions],
            )

            # Add processing timestamps to all actions
            for action in actions:
                add_processing_timestamp(action, "log_file_created")

            _update_actions_watermark(actions, latest_timestamps)
            _record_action_log_files_created(logged, latest_timestamps)

        # Set initial bill-level _processing. A brand-new bill with zero
        # actions genuinely has no action log entry to date, so logs_latest_update
        # is only set when there was something to log -- same gating as the
        # existing-bill branch above, kept consistent rather than always
        # stamping the current run time regardless of content.
        data["_processing"] = (
            {"logs_latest_update": get_current_timestamp()} if actions else {}
        )

    # Save bill metadata with _processing fields. Every bill is rewritten every
    # night, so only write when something changed: an unchanged night leaves
    # the file untouched.
    metadata_file = save_path / "metadata.json"
    text = json.dumps(data, indent=2)
    if not metadata_file.exists() or metadata_file.read_text(encoding="utf-8") != text:
        metadata_file.write_text(text, encoding="utf-8")

    return True
