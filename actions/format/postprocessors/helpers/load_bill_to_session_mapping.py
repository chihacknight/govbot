import json
from pathlib import Path


def load_bill_to_session_mapping(
    mapping_file: Path,
    data_processed_folder: Path,
    session_mapping: dict = None,
    force_rebuild: bool = False,
) -> dict:
    """
    Loads or rebuilds a mapping from bill IDs to full session metadata.

    Args:
        mapping_file (Path): Path to the bill-session mapping JSON.
        data_processed_folder (Path): Folder where processed bills are stored.
        session_mapping (dict): Optional session metadata with name and date_folder.
        force_rebuild (bool): If True, rebuild mapping from folder structure.

    Returns:
        dict: {
            "HR 1234": {
                "name": "119th Congress",
                "date_folder": "2023-2024"
            }, ...
        }
    """
    if mapping_file.exists() and not force_rebuild:
        with open(mapping_file, "r", encoding="utf-8") as f:
            return json.load(f)

    print("🔄 Rebuilding bill-to-session mapping from saved bill data...")
    bill_to_session = {}

    if session_mapping is None:
        raise ValueError("❌ session_mapping is required when rebuilding.")

    # Sorted, here and in json.dump below, so the same bill folders always give
    # the same file. glob() follows the folder listing, which differs between
    # machines and runs, so the file was rewritten in a new key order every
    # night, an unchanged night's diff included. Sorting here also makes it fixed
    # which session wins if one bill ID is in two sessions (the last one).
    for bill_path in sorted(data_processed_folder.glob("**/bills/*")):
        if not bill_path.is_dir():
            continue
        bill_id = bill_path.name

        try:
            session_id = bill_path.parent.parent.name
        except IndexError:
            continue

        # Match session metadata by session ID (folder name)
        if session_id in session_mapping:
            meta = session_mapping[session_id]
            bill_to_session[bill_id] = {
                "session_id": session_id,  # Add session ID for folder creation
                "name": meta["name"],
                "date_folder": meta["date_folder"],
            }

    with open(mapping_file, "w", encoding="utf-8") as f:
        json.dump(bill_to_session, f, indent=2, sort_keys=True)
    print(f"✅ Saved bill-to-session mapping to {mapping_file}")

    return bill_to_session
