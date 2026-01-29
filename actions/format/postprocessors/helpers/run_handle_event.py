from handlers.event import handle_event
from pathlib import Path


def run_handle_event(
    state_abbr: str,
    event_data: dict,
    session_id: str,
    date_folder: str,
    data_processed_folder: Path,
    data_not_processed_folder: Path,
    bill_id: str,
    filename: str,
):
    """
    Wrapper for handle_event that sets up paths and handles logging or errors.

    Args:
        state_abbr (str): State abbreviation (e.g., 'il', 'ca').
        event_data (dict): The parsed event JSON.
        session_id (str): The session ID for folder structure (e.g., "119").
        date_folder (str): The date folder for the session (unused but kept for compatibility).
        data_processed_folder (Path): Base path for processed output.
        data_not_processed_folder (Path): Base path for skipped/error output.
        bill_id (str): The bill ID this event references.
        filename (str): Original event file name.
    """
    try:
        # Create a minimal LatestTimestamps dict for events
        # Since events are post-processed, we don't update repository-level timestamps
        from utils.timestamp_tracker import get_default_timestamps
        latest_timestamps = get_default_timestamps()
        
        handle_event(
            STATE_ABBR=state_abbr,
            data=event_data,
            DATA_PROCESSED_FOLDER=data_processed_folder,
            DATA_NOT_PROCESSED_FOLDER=data_not_processed_folder,
            filename=filename,
            latest_timestamps=latest_timestamps,
            session_id=session_id,
            referenced_bill_id=bill_id,
        )
    except Exception as e:
        print(f"❌ Failed to handle event {filename}: {e}")
