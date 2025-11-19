"""
Path Utilities

This module provides utilities for building consistent file paths across
the data processing pipeline. Uses unified path structure for federal and
state data (both use state:{code} pattern).
"""

from pathlib import Path


def build_data_path(
    repo_root: Path,
    state_abbr: str,
    data_type: str,
    session_id: str,
    identifier: str,
) -> Path:
    """
    Build a standardized path for processed data.

    Args:
        repo_root: Root of the git repository (caller repo)
        state_abbr: State abbreviation ('usa', 'ca', 'tx', etc.)
        data_type: Type of data ('bills', 'events', 'vote_events')
        session_id: Legislative session ID
        identifier: Unique identifier for the item (bill_id, event_id, etc.)

    Returns:
        Complete Path object for the item's folder

    Examples:
        >>> build_data_path(base, 'usa', 'bills', '119', 'HR1')
        Path('country:us/state:usa/sessions/119/bills/HR1')

        >>> build_data_path(base, 'ca', 'bills', '2023', 'AB123')
        Path('country:us/state:ca/sessions/2023/bills/AB123')
    """
    return (
        repo_root
        / "country:us"
        / f"state:{state_abbr.lower()}"
        / "sessions"
        / session_id
        / data_type
        / identifier
    )


def build_bill_path(
    repo_root: Path,
    state_abbr: str,
    session_id: str,
    bill_identifier: str,
) -> Path:
    """
    Build path for a bill folder.

    Args:
        repo_root: Root of the git repository (caller repo)
        state_abbr: State abbreviation
        session_id: Legislative session ID
        bill_identifier: Bill identifier (e.g., 'HR 1')

    Returns:
        Path to bill folder
    """
    bill_id = bill_identifier.replace(" ", "")
    return build_data_path(repo_root, state_abbr, "bills", session_id, bill_id)


def build_event_path(
    repo_root: Path,
    state_abbr: str,
    session_id: str,
    event_identifier: str,
) -> Path:
    """
    Build path for an event folder.

    Args:
        repo_root: Root of the git repository (caller repo)
        state_abbr: State abbreviation
        session_id: Legislative session ID
        event_identifier: Event identifier

    Returns:
        Path to event folder
    """
    return build_data_path(
        repo_root, state_abbr, "events", session_id, event_identifier
    )


def build_vote_event_path(
    repo_root: Path,
    state_abbr: str,
    session_id: str,
    vote_identifier: str,
) -> Path:
    """
    Build path for a vote event folder.

    Args:
        repo_root: Root of the git repository (caller repo)
        state_abbr: State abbreviation
        session_id: Legislative session ID
        vote_identifier: Vote event identifier

    Returns:
        Path to vote event folder
    """
    return build_data_path(
        repo_root, state_abbr, "vote_events", session_id, vote_identifier
    )
