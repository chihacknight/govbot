import os
import json
from pathlib import Path
from utils.file_utils import record_error_file
from utils.timestamp_tracker import (
    is_newer_than_latest,
    LatestTimestamps,
)
from utils.processing_tracker import (
    load_existing_metadata,
    compare_action_counts,
)


def load_json_files(
    input_folder: str | Path,
    EVENT_ARCHIVE_FOLDER: str | Path,
    DATA_NOT_PROCESSED_FOLDER: str | Path,
    latest_timestamps: LatestTimestamps,
    state_abbr: str,
    data_processed_folder: Path,
):
    vote_events_ts = latest_timestamps["vote_events"]
    events_ts = latest_timestamps["events"]

    all_data = []
    for filename in os.listdir(input_folder):
        if not filename.endswith(".json"):
            continue

        filepath = os.path.join(input_folder, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

                # Determine type for timestamp comparison
                if filename.startswith("bill"):
                    # Use smart filtering: compare action counts
                    existing_metadata = load_existing_metadata(
                        data_processed_folder, state_abbr, data
                    )
                    should_process, existing_count, incoming_count = (
                        compare_action_counts(existing_metadata, data)
                    )

                    if not should_process:
                        # Same action count - likely no changes, skip
                        continue

                    # Different count or new bill - pass to processing
                    # (Will be handled in handle_bill with granular action comparison)
                elif filename.startswith("vote_event"):
                    if not is_newer_than_latest(
                        data, vote_events_ts, "vote_events", DATA_NOT_PROCESSED_FOLDER
                    ):
                        continue
                elif filename.startswith("event"):
                    if not is_newer_than_latest(
                        data, events_ts, "events", DATA_NOT_PROCESSED_FOLDER
                    ):
                        continue

                all_data.append((filename, data))

                # Archive event_*.json files
                if filename.startswith("event_"):
                    EVENT_ARCHIVE_FOLDER.mkdir(parents=True, exist_ok=True)
                    missing_event_file = (
                        DATA_NOT_PROCESSED_FOLDER / "missing_session" / filename
                    )
                    if missing_event_file.exists():
                        missing_event_file.unlink()

                    archive_path = EVENT_ARCHIVE_FOLDER / filename
                    with open(archive_path, "w", encoding="utf-8") as archive_f:
                        json.dump(data, archive_f, indent=2)

        except json.JSONDecodeError:
            print(f"❌ Skipping {filename}: could not parse JSON")
            with open(filepath, "r", encoding="utf-8") as f:
                raw_text = f.read()
            record_error_file(
                DATA_NOT_PROCESSED_FOLDER,
                "invalid_json",
                filename,
                {"error": "Could not parse JSON", "raw": raw_text},
                original_filename=filename,
            )

    return all_data
