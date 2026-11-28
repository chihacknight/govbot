import click
from typing import Optional
from pathlib import Path
from collections.abc import Callable
from handlers import bill, vote_event, event
from utils.bill_guards import BillGuards
from utils.file_utils import record_error_file
from utils.log_jsonl import append_votes
from utils.timestamp_tracker import write_latest_timestamp_file, LatestTimestamps


def route_handler(
    STATE_ABBR: str,
    filename: str,
    data: dict,
    DATA_NOT_PROCESSED_FOLDER: Path,
    DATA_PROCESSED_FOLDER: Path,
    latest_timestamps: LatestTimestamps,
    output_folder: Path,
    first_seen: Optional[str] = None,
    pending_votes: Optional[dict[Path, list]] = None,
    guards: Optional[BillGuards] = None,
) -> Optional[str]:

    if "bill_" in filename:
        success = bill.handle_bill(
            STATE_ABBR,
            data,
            DATA_PROCESSED_FOLDER,
            DATA_NOT_PROCESSED_FOLDER,
            filename,
            latest_timestamps,
            first_seen=first_seen,
            guards=guards,
        )
        return "bill" if success else None

    elif "vote_event_" in filename:
        success = vote_event.handle_vote_event(
            STATE_ABBR,
            data,
            DATA_PROCESSED_FOLDER,
            DATA_NOT_PROCESSED_FOLDER,
            filename,
            latest_timestamps,
            first_seen=first_seen,
            pending_votes=pending_votes,
        )
        return "vote_event" if success else None

    elif "event_" in filename:
        success = event.handle_event(
            STATE_ABBR,
            data,
            DATA_PROCESSED_FOLDER,
            DATA_NOT_PROCESSED_FOLDER,
            filename,
            latest_timestamps,
        )
        return "event" if success else None

    else:
        print(f"❓ Unrecognized file type: {filename}")
        return None


def process_and_save(
    STATE_ABBR: str,
    data: list[tuple[str, dict]],
    DATA_NOT_PROCESSED_FOLDER: Path,
    SESSION_MAPPING: dict[str, dict[str, str]],
    SESSION_LOG_PATH: Path,
    DATA_PROCESSED_FOLDER: Path,
    latest_timestamps: LatestTimestamps,
    output_folder: Path,
    expected_session: Optional[str] = None,
    first_seen: Optional[str] = None,
) -> dict[str, int]:
    bill_count = 0
    event_count = 0
    vote_event_count = 0
    # Each bill's votes are written once, after the whole scrape is read (see
    # handle_vote_event).
    pending_votes: dict[Path, list] = {}
    # Guards on tonight's bills (empty fields kept, scraper regressions flagged).
    guards = BillGuards(DATA_NOT_PROCESSED_FOLDER, STATE_ABBR, first_seen)

    for filename, data in data:
        session = data.get("legislative_session")
        if not session:
            print(f"⚠️ Skipping {filename}, missing legislative_session")
            record_error_file(
                DATA_NOT_PROCESSED_FOLDER, "missing_session", filename, data
            )
            continue

        session_metadata = SESSION_MAPPING.get(session)

        # If session is unknown, skip and record error
        # Sessions are now fetched automatically via API in ensure_session_mapping()
        if not session_metadata:
            record_error_file(
                DATA_NOT_PROCESSED_FOLDER, "unknown_session", filename, data
            )
            continue

        # This repo is meant to hold exactly one session's data (a session pair
        # from actions/pipeline-manager/jurisdictions.yml). If the scraper repo
        # feeding this run isn't properly session-scoped, don't silently
        # create a second sessions/{id}/ folder here — route it to errors
        # for a human to notice instead.
        if expected_session and session != expected_session:
            print(
                f"⚠️ Skipping {filename}, session '{session}' does not match "
                f"expected session '{expected_session}'"
            )
            record_error_file(
                DATA_NOT_PROCESSED_FOLDER, "wrong_session", filename, data
            )
            continue

        result = route_handler(
            STATE_ABBR,
            filename,
            data,
            DATA_NOT_PROCESSED_FOLDER,
            DATA_PROCESSED_FOLDER,
            latest_timestamps,
            output_folder,
            first_seen=first_seen,
            pending_votes=pending_votes,
            guards=guards,
        )
        if result not in ("bill", "event", "vote_event"):
            print(f"⚠️ Unrecognized result from handler for {filename}: {result}")
            continue

        if result == "bill":
            bill_count += 1
        elif result == "event":
            event_count += 1
        elif result == "vote_event":
            vote_event_count += 1
    for bill_dir, lines in pending_votes.items():
        append_votes(bill_dir, lines, STATE_ABBR)
    guards.finish()
    write_latest_timestamp_file(output_folder, latest_timestamps)
    print("\n✅ File processing complete.")
    return {
        "bills": bill_count,
        "events": event_count,
        "votes": vote_event_count,
    }
