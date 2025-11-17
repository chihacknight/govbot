import json
from pathlib import Path


def load_session_mapping(SESSION_MAPPING_FILE: Path) -> dict:
    """
    Loads session metadata mapping from disk.

    Returns a dictionary in the format:
    {
        "113": {"name": "113th Congress", "date_folder": "2013-2015"},
        "114": {"name": "114th Congress", "date_folder": "2015-2017"},
        ...
    }
    """
    if not SESSION_MAPPING_FILE.exists():
        raise FileNotFoundError(
            f"❌ Session mapping file not found: {SESSION_MAPPING_FILE}"
        )

    with open(SESSION_MAPPING_FILE, "r", encoding="utf-8") as f:
        session_mapping = json.load(f)

    if not isinstance(session_mapping, dict):
        raise ValueError("❌ Session mapping must be a dictionary")

    return session_mapping
