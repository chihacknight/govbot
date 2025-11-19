import json
from pathlib import Path
from postprocessors.helpers import (
    load_bill_to_session_mapping,
    extract_bill_ids_from_event,
    run_handle_event,
)
from utils.file_utils import list_json_files
from utils.session_utils import load_session_mapping


def link_events_to_bills_pipeline(
    state_abbr: str,
    event_archive_folder: Path,
    repo_root: Path,
    errors_folder: Path,
    bill_session_mapping_file: Path,
    sessions_file: Path,
) -> None:
    """
    Main pipeline for linking events to bills and saving them in the correct folder.
    """
    print("\n📦 Starting event-to-bill linking pipeline")

    session_mapping = load_session_mapping(sessions_file)
    bill_to_session = load_bill_to_session_mapping(
        bill_session_mapping_file,
        repo_root,
        session_mapping=session_mapping,
        force_rebuild=True,
    )

    print(f"📂 Loaded {len(bill_to_session)} bill-session mappings")

    skipped = []
    for event_file in list_json_files(event_archive_folder):
        with open(event_file) as f:
            data = json.load(f)

        bill_ids = extract_bill_ids_from_event(data)
        if not bill_ids:
            continue

        for bill_id in bill_ids:
            session_meta = bill_to_session.get(bill_id)
            if session_meta:
                run_handle_event(
                    state_abbr,
                    data,
                    session_meta[
                        "session_id"
                    ],  # Pass session ID (e.g., "119") not name
                    session_meta["date_folder"],
                    repo_root,
                    errors_folder,
                    bill_id,
                    filename=event_file.name,
                )
                event_file.unlink()
                missing_path = errors_folder / "missing_session" / event_file.name
                if missing_path.exists():
                    missing_path.unlink()
                break
        else:
            skipped.append((event_file, bill_ids))

    if skipped:
        bill_to_session = load_bill_to_session_mapping(
            bill_session_mapping_file,
            repo_root,
            session_mapping=session_mapping,
            force_rebuild=True,
        )

        for event_file, bill_ids in skipped:
            for bill_id in bill_ids:
                session_meta = bill_to_session.get(bill_id)
                if session_meta:
                    with open(event_file) as f:
                        data = json.load(f)
                    run_handle_event(
                        state_abbr,
                        data,
                        session_meta[
                            "session_id"
                        ],  # Pass session ID (e.g., "119") not name
                        session_meta["date_folder"],
                        repo_root,
                        errors_folder,
                        bill_id,
                        filename=event_file.name,
                    )
                    event_file.unlink()
                    missing_path = errors_folder / "missing_session" / event_file.name
                    if missing_path.exists():
                        missing_path.unlink()
                    break

    print("\n✅ Event-to-bill linking complete")
