import click
from pathlib import Path
from tempfile import mkdtemp

from utils.timestamp_tracker import (
    read_latest_timestamps,
    LatestTimestamps,
)

from utils.io_utils import load_json_files
from utils.file_utils import ensure_session_mapping
from utils.process_utils import process_and_save
from postprocessors.event_bill_linker import link_events_to_bills_pipeline
from postprocessors.cleanup_placeholders import cleanup_placeholders
from utils.file_utils import verify_folder_exists

session_mapping = {}


@click.command()
@click.option(
    "--state",
    required=True,
    help="Jurisdiction code to process.",
)
@click.option(
    "--openstates-data-folder",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    required=True,
    help="Path to the input folder containing JSON files.",
)
@click.option(
    "--git-repo-folder",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    required=True,
    help="Path to the output folder where processed files will be saved.",
)
def main(
    state: str,
    openstates_data_folder: Path,
    git_repo_folder: Path,
):
    state_abbr = state.lower()

    # New v2.0 structure: .windycivi/ contains all pipeline metadata
    windycivi_folder = git_repo_folder / ".windycivi"
    errors_folder = windycivi_folder / "errors"
    event_archive_folder = errors_folder / "event_archive"

    # Flattened files (no {state}.json subfolder since each repo is state-specific)
    bill_session_mapping_file = windycivi_folder / "bill_session_mapping.json"
    sessions_file = windycivi_folder / "sessions.json"
    session_log_path = windycivi_folder / "new_sessions_added.txt"

    # repo_root is where country:us/ lives (no data_output/data_processed wrapper)
    repo_root = git_repo_folder

    # Ensure output folders exist
    errors_folder.mkdir(parents=True, exist_ok=True)
    event_archive_folder.mkdir(parents=True, exist_ok=True)
    windycivi_folder.mkdir(parents=True, exist_ok=True)

    # Read latest timestamps using the output folder
    latest_timestamps: LatestTimestamps = read_latest_timestamps(git_repo_folder)
    print(f"💬 Latest timestamps: {latest_timestamps}")

    # 1. Verify input_folder exists
    verify_folder_exists(openstates_data_folder)
    # 2. Ensure state specific session mapping is available (from .windycivi/sessions.json)
    session_mapping.update(
        ensure_session_mapping(state_abbr, windycivi_folder, openstates_data_folder)
    )

    # 3. Load and parse all input JSON files
    all_json_files = load_json_files(
        openstates_data_folder,
        event_archive_folder,
        errors_folder,
        latest_timestamps,
        state_abbr,
        repo_root,
    )

    # 4. Route and process by handler (returns counts)
    counts = process_and_save(
        state_abbr,
        all_json_files,
        errors_folder,
        session_mapping,
        session_log_path,
        repo_root,
        latest_timestamps,
        git_repo_folder,
    )

    # 5. Link archived event logs to state sessions and save
    if event_archive_folder.exists():
        print("Linking event references to related bills...")
        link_events_to_bills_pipeline(
            state_abbr,
            event_archive_folder,
            repo_root,
            errors_folder,
            bill_session_mapping_file,
            sessions_file,
        )
    else:
        print(
            f"⚠️ Event archive folder {event_archive_folder} does not exist. Skipping event linking.\n🚀 Processing complete."
        )

    # 6. Cleanup placeholder files (post-processing)
    cleanup_stats = cleanup_placeholders(repo_root)

    print("\n📊 Processing summary:")
    print(f"Bills saved: {counts.get('bills', 0)}")
    print(f"Vote events saved: {counts.get('votes', 0)}")
    print(f"Placeholders cleaned: {cleanup_stats['placeholders_deleted']}")
    if cleanup_stats["orphans_found"] > 0:
        print(f"⚠️  Orphaned bills found: {cleanup_stats['orphans_found']} (see report)")


if __name__ == "__main__":
    main(auto_envvar_prefix="OSDF")
