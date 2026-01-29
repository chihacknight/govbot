from typing import Optional


def find_session_from_bill_id(bill_id: str, bill_to_session: dict) -> Optional[str]:
    """
    Given a bill ID, return the session name if found.

    Args:
        bill_id (str): The bill identifier.
        bill_to_session (dict): Mapping from bill ID to session name.

    Returns:
        Optional[str]: The session name if found, otherwise None.
    """
    return bill_to_session.get(bill_id)
