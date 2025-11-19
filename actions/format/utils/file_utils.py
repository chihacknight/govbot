import re
from datetime import datetime
import json
from pathlib import Path
from urllib import request
from typing import Any, TypedDict


class SessionInfo(TypedDict):
    name: str
    date_folder: str


TRACKER_CLASSIFICATIONS = {
    "introduction",
    "passage",
    "executive-receipt",
    "became-law",
}


def verify_folder_exists(folder_path):
    """Raise an error if the specified folder does not exist."""
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        raise FileNotFoundError(f"Required folder does not exist: {folder_path}")


def format_timestamp(date_str: str) -> str | None:
    try:
        dt = datetime.fromisoformat(date_str)
        return dt.strftime("%Y%m%dT%H%M%SZ")
    except Exception:
        return None


def extract_session_mapping(jurisdiction_data: dict) -> dict[str, SessionInfo]:
    session_mapping = {}
    for session in jurisdiction_data.get("legislative_sessions", []):
        identifier = session.get("identifier")
        name = session.get("name")
        start = session.get("start_date", "")[:4]
        end = session.get("end_date", "")[:4]
        if identifier and name and start and end:
            session_mapping[identifier] = {
                "name": name,
                "date_folder": f"{start}-{end}",
            }
    return session_mapping


def ensure_session_mapping(
    state_abbr: str, windycivi_folder: Path, input_folder: str | Path
) -> dict[str, SessionInfo]:
    """
    Ensures .windycivi/sessions.json exists.
    - If jurisdiction_*.json is found, extract and overwrite session cache.
    - If not found, fallback to OpenStates API only if cache doesn't already exist.
    Returns a dictionary like:
    {
        "119": {"name": "119th Congress", "date_folder": "2023-2024"},
        ...
    }
    """
    # Flattened path: no {state}.json subfolder since each repo is state-specific
    session_cache_path = windycivi_folder / "sessions.json"
    windycivi_folder.mkdir(parents=True, exist_ok=True)

    # 1. Look for jurisdiction file
    jurisdiction_files = list(Path(input_folder).glob("jurisdiction_*.json"))
    if jurisdiction_files:
        print(f"🔍 Found jurisdiction file — updating .windycivi/sessions.json")
        with open(jurisdiction_files[0], "r", encoding="utf-8") as f:
            jurisdiction_data = json.load(f)
        session_mapping = extract_session_mapping(jurisdiction_data)
        if session_mapping:
            with open(session_cache_path, "w", encoding="utf-8") as f:
                json.dump(session_mapping, f, indent=2)
            print(f"📅 Wrote extracted session mapping to .windycivi/sessions.json")
            return session_mapping

    # 2. If no jurisdiction file, use existing session cache if it exists
    if session_cache_path.exists():
        print(f"✔️ Using existing .windycivi/sessions.json")
        with open(session_cache_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # 3. Fallback: fetch from OpenStates API
    print(f"🌐 Fetching session list from OpenStates API")
    url = f"https://v3.openstates.org/jurisdictions/{state_abbr}/sessions"
    try:
        response = request.get(url, timeout=10)
        if response.status_code == 200:
            sessions = response.json()
            session_mapping = {}
            for s in sessions:
                identifier = s.get("identifier")
                name = s.get("name")
                start = s.get("start_date", "")[:4]
                end = s.get("end_date", "")[:4]
                if identifier and name and start and end:
                    session_mapping[identifier] = {
                        "name": name,
                        "date_folder": f"{start}-{end}",
                    }
            with open(session_cache_path, "w", encoding="utf-8") as f:
                json.dump(session_mapping, f, indent=2)
            print(f"✅ Wrote session mapping to .windycivi/sessions.json")
            return session_mapping
        else:
            print(f"⚠️ Failed to fetch sessions (status {response.status_code})")
    except Exception as e:
        print(f"❌ Error fetching sessions: {e}")

    return {}


def validate_required_field(
    data: dict[str, Any],
    field_name: str,
    filename: str,
    error_folder: str | Path,
    error_category: str,
    custom_message: str | None = None,
) -> Any:
    """
    Validate that a required field exists in data.

    If the field is missing, logs an error and returns None.
    If the field exists, returns its value.

    Args:
        data: Dictionary containing the data
        field_name: Name of the required field
        filename: Original filename being processed
        error_folder: Folder where error files should be saved
        error_category: Category/subfolder for the error
        custom_message: Optional custom warning message

    Returns:
        Field value if present, None if missing

    Example:
        bill_id = validate_required_field(
            data, "identifier", filename,
            DATA_NOT_PROCESSED_FOLDER,
            "from_handle_bill_missing_identifier"
        )
        if not bill_id:
            return False
    """
    value = data.get(field_name)
    if not value:
        message = custom_message or f"Missing required field: {field_name}"
        print(f"⚠️ Warning: {message}")
        record_error_file(
            error_folder,
            error_category,
            filename,
            data,
            original_filename=filename,
        )
        return None
    return value


def record_error_file(
    error_folder: str | Path,
    category: str,
    filename: str,
    data: dict[str, Any],
    original_filename: str | None = None,
) -> None:
    folder = Path(error_folder) / category
    folder.mkdir(parents=True, exist_ok=True)

    # 🔍 Step 1: Get existing names in that folder
    existing_names = set()
    for f in folder.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as existing_file:
                existing_data = json.load(existing_file)
                name = existing_data.get("name")
                if name:
                    existing_names.add(name)
        except Exception:
            continue

    # 🛑 Step 2: Skip if this "name" already exists
    if data.get("name") in existing_names:
        print(f"⚠️ Skipping duplicate org: {data['name']}")
        return

    if original_filename:
        data["_original_filename"] = original_filename

    with open(folder / filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"📄 Saved error file to: {folder / filename}")


def slugify(text: str, max_length=100):
    """
    Converts a string to a safe, lowercase, underscore-separated slug.
    Strips punctuation (including dashes) and truncates long filenames.
    """
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", "_", text)
    text = text.strip("_")
    return text[:max_length]


def write_action_logs(
    actions: list[dict[str, Any]], bill_identifier: str, log_folder: str | Path
) -> None:
    """
    Writes one JSON file per action for a bill.

    If the action has a classification, file is named:
        {timestamp}.classification.{classification}.{org_class}.json
    Otherwise:
        {timestamp}_{slugified_description}.json
    """
    for action in actions:
        date = action.get("date")
        desc = action.get("description", "no_description")
        timestamp = format_timestamp(date) if date else "unknown"

        classifications = action.get("classification", [])
        org_id = action.get("organization_id", "")

        if classifications and classifications[0] in TRACKER_CLASSIFICATIONS:
            classification = classifications[0]
            # Extract org classification like "lower" or "upper" from string: '~{"classification": "lower"}'
            org_class = "unknown"
            if "classification" in org_id:
                try:
                    org_dict = json.loads(org_id.strip("~"))
                    org_class = org_dict.get("classification", "unknown")
                except Exception:
                    pass

            filename = f"{timestamp}.classification.{classification}.{org_class}.json"
        else:
            slug = slugify(desc)
            filename = f"{timestamp}_{slug}.json"

        output_file = Path(log_folder) / filename
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump({"action": action, "bill_id": bill_identifier}, f, indent=2)


def write_vote_event_log(vote_event: dict[str, Any], log_folder: str | Path) -> None:
    """
    Saves a single vote_event file as a timestamped log.

    - If result == "pass":
        YYYYMMDDT000000Z.vote_event.pass.{org_class}.json
    - Else:
        YYYYMMDDT000000Z_vote_event_<result>.json
    """
    date = vote_event.get("start_date")
    timestamp = format_timestamp(date) if date else "unknown"
    result = vote_event.get("result", "unknown")

    if result == "pass":
        org_id = vote_event.get("organization", "")
        org_class = "unknown"
        if "classification" in org_id:
            try:
                org_dict = json.loads(org_id.strip("~"))
                org_class = org_dict.get("classification", "unknown")
            except Exception:
                pass
        filename = f"{timestamp}.vote_event.pass.{org_class}.json"
    else:
        filename = f"{timestamp}_vote_event_{slugify(result)}.json"

    output_file = Path(log_folder) / filename
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(vote_event, f, indent=2)


def list_json_files(folder: Path) -> list[Path]:
    """
    Returns all .json files in the given folder.

    Args:
        folder (Path): Directory to search.

    Returns:
        list[Path]: List of JSON file paths.
    """
    if not folder.exists() or not folder.is_dir():
        return []

    return sorted(folder.glob("*.json"))
