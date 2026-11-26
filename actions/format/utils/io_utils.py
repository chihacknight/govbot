import os
import json
from pathlib import Path
from typing import Union
from utils.file_utils import record_error_file
from utils.timestamp_tracker import (
    is_newer_than_latest,
    LatestTimestamps,
)


def load_json_files(
    input_folder: Union[str, Path],
    EVENT_ARCHIVE_FOLDER: Union[str, Path],
    DATA_NOT_PROCESSED_FOLDER: Union[str, Path],
    latest_timestamps: LatestTimestamps,
):
    events_ts = latest_timestamps["events"]

    all_data = []
    for filename in os.listdir(input_folder):
        if not filename.endswith(".json"):
            continue

        filepath = os.path.join(input_folder, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

                # bill_*.json files are not gated here: every bill in the scrape
                # goes to handle_bill every night, which decides what's new
                # against the bill's action_logs.jsonl. The old "same number of
                # actions as metadata.json -> skip the bill" shortcut lost real
                # updates (GA HB69's new cosponsor, SR3's new version, HR13's
                # title fix) and rewordings, and let metadata.json fall behind.
                # Nor are vote_event files: every vote in the scrape goes to
                # handle_vote_event, which skips ones already in the bill's
                # vote_event_logs.jsonl. The old "newer than the newest vote
                # seen" check dropped every vote that arrived late.
                if filename.startswith("event"):
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
