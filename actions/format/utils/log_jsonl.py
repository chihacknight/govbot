"""
Per-bill JSON Lines logs: bills/{bill_id}/action_logs.jsonl and vote_event_logs.jsonl.

Purpose: every night's scrape is the whole dataset, so these files mark what is
NEW. They are append-only. A night's new actions and votes are added to the end
of each bill's files, in the order we first saw them, and existing lines are
never edited, reordered or removed. So `git diff` of a night's commit lists
exactly the bills with new activity, and the added lines are exactly the new
entries.

Before this, every action and vote was its own file under bills/{id}/logs/,
plus a symlink to it under sessions/{session}/logs/. `convert_repo()` folds that
old layout into this one.

One line, action_logs.jsonl:

    {"id": "20250114T210515Z.classification.introduction.upper",
     "first_seen": "2026-09-29T10:33:32+00:00",
     "chamber": "upper",
     "action": {...exactly the object the old per-action file held, including
                occurred_at (the government's date) and the bill's sources...},
     "bill_id": "SF0015"}

One line, vote_event_logs.jsonl:

    {"id": "20250205T173055Z_vote_event_fail",
     "first_seen": "2026-09-29T10:33:32+00:00",
     "chamber": "upper",
     "vote_event": {...the OpenStates vote event as published...},
     "bill_id": "SF0001"}

- `id` is the old filename without ".json", so converted entries keep the names
  readers already know. When two different entries in one file would get the same
  id (the old layout silently overwrote one of them), the second gets a short hash
  suffix.
- `first_seen` is when the scrape that first contained the entry was committed to
  the raw scraper repo, not the formatter's run time, so a backfill from the raw
  history gets the right date. null when unknown (converted entries we have no
  record for).
- `chamber` is the plain value from the "~{"classification": "lower"}" string
  beside it, for readers that can't decode that.

Duplicates: an action is the same action when its date, description (ignoring
whitespace, since some scrapers start emitting line breaks inside descriptions)
and chamber match. A vote is the same vote when its roll-call identifier, date and
motion match (scrapers reuse identifiers across votes; see vote_keys),
or, failing that, its date, motion, chamber and counts match. A vote seen again
with different substance (result, counts, member votes, motion) is a correction:
it is appended as a new line with the same id, and readers take the last line
for each id.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional, Union

ACTION_LOG_FILE = "action_logs.jsonl"
VOTE_EVENT_LOG_FILE = "vote_event_logs.jsonl"
LEGACY_LOG_DIR = "logs"

# Same set the old per-file writer used to choose the dotted filename form.
TRACKER_CLASSIFICATIONS = {
    "introduction",
    "passage",
    "executive-receipt",
    "became-law",
}

# The fields that make a vote what it is. A change in anything else (source URL
# format, roll-call number filled in later, the scraper's internal bill UUID,
# bill_action wording) is not a correction worth a new line.
_VOTE_SUBSTANCE = ("start_date", "motion_text", "motion_classification", "organization", "result", "counts", "votes")

_TS_PREFIX = re.compile(r"^(\d{8}T\d{6}Z)")


# --------------------------------------------------------------------------
# Small helpers. Kept local so this module stands alone and the conversion
# script can use it without the rest of actions/format.
# --------------------------------------------------------------------------


def format_timestamp(date_str: Optional[str]) -> Optional[str]:
    """ISO 8601 -> YYYYMMDDTHHMMSSZ, or None if it can't be parsed."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str).strftime("%Y%m%dT%H%M%SZ")
    except Exception:
        return None


def _slugify(text: str, max_length: int = 100) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", "_", text)
    return text.strip("_")[:max_length]


def chamber_of(org_id: Any) -> Optional[str]:
    """'~{"classification": "lower"}' -> 'lower'; None when there isn't one."""
    if isinstance(org_id, str) and "classification" in org_id:
        try:
            return json.loads(org_id.lstrip("~")).get("classification")
        except Exception:
            pass
    return None


def _squash(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _short_hash(value: Any) -> str:
    return hashlib.sha1(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:8]


def dumps(line: dict[str, Any]) -> str:
    return json.dumps(line, ensure_ascii=False)


# --------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------


def action_key(action: dict[str, Any]) -> tuple:
    """What makes two log actions the same action (the `action` object of a line)."""
    return (action.get("occurred_at"), _squash(action.get("description")), action.get("jurisdiction_id"))


def vote_keys(vote: dict[str, Any]) -> tuple[Optional[tuple], tuple]:
    """(identifier key or None, fallback key). Two votes are the same vote when
    both have an identifier key and they match, or when their fallback keys match.

    The identifier key is the roll-call identifier plus the date and motion,
    because scrapers reuse one identifier across different votes: VA puts the
    bill's document number ("26200060D") on every procedural entry ("Presented",
    "Laid on Clerk's Desk", same day), and MT gives a committee vote and the later
    floor vote the same id ("2025-SB 80-562"). With the identifier alone those
    were read as one vote, re-logged as a "correction" every night (51,535 VA
    lines in the backfill). Within one identifier, date and motion, a change in
    counts or member votes is still a correction.

    The fallback includes the counts because date + motion + chamber alone is not
    unique: PA HB 1549 had two committee roll calls on one tabling motion at the
    same time (roll calls 649 and 650).
    """
    identifier = (vote.get("identifier") or "").strip()
    motion = _squash(vote.get("motion_text"))
    id_key = (identifier, vote.get("start_date"), motion) if identifier else None
    counts = sorted((c.get("option"), c.get("value")) for c in vote.get("counts") or [])
    fallback = (vote.get("start_date"), motion, vote.get("organization"), tuple(counts))
    return id_key, fallback


def vote_substance(vote: dict[str, Any]) -> str:
    """The parts of a vote whose change counts as a correction, normalized so a
    reordering of voter rows or counts is not a change."""
    norm = {}
    for field in _VOTE_SUBSTANCE:
        value = vote.get(field)
        if field in ("counts", "votes") and isinstance(value, list):
            value = sorted(value, key=lambda r: json.dumps(r, sort_keys=True))
        if field == "motion_text":
            value = _squash(value)
        norm[field] = value
    return json.dumps(norm, sort_keys=True, ensure_ascii=False)


# --------------------------------------------------------------------------
# Building lines
# --------------------------------------------------------------------------


def legacy_action_id(action: dict[str, Any]) -> str:
    """The filename (minus .json) the old per-action writer used."""
    stamp = format_timestamp(action.get("date")) or "unknown"
    classifications = action.get("classification") or []
    if classifications and classifications[0] in TRACKER_CLASSIFICATIONS:
        return f"{stamp}.classification.{classifications[0]}.{chamber_of(action.get('organization_id')) or 'unknown'}"
    return f"{stamp}_{_slugify(action.get('description', 'no_description'))}"


def legacy_vote_id(vote: dict[str, Any]) -> str:
    """The filename (minus .json) the old per-vote writer used."""
    stamp = format_timestamp(vote.get("start_date")) or "unknown"
    result = vote.get("result", "unknown")
    if result == "pass":
        return f"{stamp}.vote_event.pass.{chamber_of(vote.get('organization')) or 'unknown'}"
    return f"{stamp}_vote_event_{_slugify(str(result))}"


def action_line(
    action: dict[str, Any],
    bill_identifier: str,
    sources: list[dict[str, Any]],
    session_id: str,
    first_seen: Optional[str],
) -> dict[str, Any]:
    """One scraped action -> one line. The `action` object keeps the exact shape
    of the old per-action files, so readers of it don't change."""
    return {
        "id": legacy_action_id(action),
        "first_seen": first_seen,
        "chamber": chamber_of(action.get("organization_id")),
        "action": {
            "description": action.get("description", "no_description"),
            "occurred_at": action.get("date", "no_date"),
            "jurisdiction_id": action.get("organization_id", "no_jurisdiction"),
            "session_id": session_id,
            "entity_type": "bill",
            "classifications": action.get("classification", []),
            "related_entities": action.get("related_entities", []),
            "sources": sources,
        },
        "bill_id": bill_identifier,
    }


def vote_event_line(vote_event: dict[str, Any], first_seen: Optional[str]) -> dict[str, Any]:
    """One scraped vote event -> one line."""
    return {
        "id": legacy_vote_id(vote_event),
        "first_seen": first_seen,
        "chamber": chamber_of(vote_event.get("organization")),
        "vote_event": vote_event,
        "bill_id": vote_event.get("bill_identifier"),
    }


# --------------------------------------------------------------------------
# Reading and appending
# --------------------------------------------------------------------------


def read_lines(path: Union[str, Path]) -> list[dict[str, Any]]:
    """Every line of a .jsonl file ([] if there is no file).

    A line that isn't valid JSON stops the run: appending after a damaged line
    would bury it, and the file is the record of what we saw.
    """
    path = Path(path)
    if not path.exists():
        return []
    lines = []
    with open(path, encoding="utf-8") as f:
        for n, raw in enumerate(f, start=1):
            if raw.strip():
                try:
                    lines.append(json.loads(raw))
                except json.JSONDecodeError as e:
                    raise ValueError(f"{path}:{n}: not valid JSON ({e})") from e
    return lines


def order_batch(lines: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    """One batch (one night's new entries for one bill) in the government's date
    order -- scrapers list actions in no fixed order (WY newest-first) -- so a new
    bill's history reads forwards."""
    return sorted(lines, key=lambda l: _sort_key(l, kind))


def _append(path: Path, lines: list[dict[str, Any]], kind: str, keep_order: bool = False) -> None:
    """Append one batch to the file (ordered by order_batch unless keep_order).
    Lines already in the file are never touched."""
    if not lines:
        return
    if not keep_order:
        lines = order_batch(lines, kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    # A file that doesn't end in a newline (an interrupted write) would glue the
    # next line onto the last one; start on a fresh line instead.
    prefix = ""
    if path.exists() and path.stat().st_size:
        with open(path, "rb") as f:
            f.seek(-1, 2)
            if f.read(1) != b"\n":
                prefix = "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(prefix + "".join(dumps(line) + "\n" for line in lines))


def _unique_id(line: dict[str, Any], taken: set[str], identity: Any) -> None:
    """Give `line` an id no other entry in its file has (in place)."""
    if line["id"] in taken:
        line["id"] = f"{line['id']}~{_short_hash(identity)}"
    taken.add(line["id"])


def append_actions(
    bill_dir: Union[str, Path], new_lines: Iterable[dict[str, Any]], rewordings: Optional["Rewordings"] = None
) -> int:
    """Append the actions not already in the bill's action_logs.jsonl. Returns how
    many. Pass find_rewordings(previous scrape's actions, tonight's) so a reworded
    action is logged as a correction of the one it rewords (see find_rewordings)."""
    return _append_actions_at(Path(bill_dir) / ACTION_LOG_FILE, new_lines, rewordings=rewordings)


def raw_action_key(action: dict[str, Any]) -> tuple:
    """action_key() of a scraped action (OpenStates shape), as action_line() would log it."""
    return action_key({
        "occurred_at": action.get("date", "no_date"),
        "description": action.get("description", "no_description"),
        "jurisdiction_id": action.get("organization_id", "no_jurisdiction"),
    })


class Rewordings:
    """Actions the scraper reworded since the previous scrape: {new key: old key}
    (action_key()s), plus how many changed actions couldn't be paired."""

    def __init__(self) -> None:
        self.pairs: dict[tuple, tuple] = {}
        self.unpaired = 0


def find_rewordings(previous: Optional[list[dict[str, Any]]], current: list[dict[str, Any]]) -> Rewordings:
    """Which of a bill's scraped actions are rewordings of the previous scrape's.

    `previous` is the bill's actions in the previous scrape (the nightly writer
    reads them from metadata.json, which keeps the scrape's list and order;
    the backfill keeps the last version it saw), `current` tonight's. A scraper
    sometimes rewords actions it already published (MT 2026-08-10: "(H) First
    Reading" -> "(H) 1st Reading" on every past bill; KS: "Referred to Committee
    on Judiciary" -> "Referred to Senate Committee on Judiciary"), and without
    this each new wording was logged as a new action, dated that night.

    Per date and chamber, the actions pair up when (agreed 2026-11-25):
    - both scrapes have the same number of actions on that date and chamber, and
    - the actions whose wording didn't change are in the same relative order.
    The changed ones then pair slot by slot: [A, B, C] -> [A, B', C'] pairs B
    with B' and C with C'. Otherwise nothing on that date is paired and each new
    wording is logged as a new action (counted in `unpaired`). No text-similarity
    matching. A new bill (no previous) has nothing to reword.
    """
    out = Rewordings()
    if not previous:
        return out

    def by_slot(actions):
        groups: dict[tuple, list[tuple]] = {}
        for a in actions:
            groups.setdefault((a.get("date"), a.get("organization_id")), []).append(raw_action_key(a))
        return groups

    before, now = by_slot(previous), by_slot(current)
    for slot, new_keys in now.items():
        old_keys = before.get(slot, [])
        old_set, new_set = set(old_keys), set(new_keys)
        changed_new = [k for k in new_keys if k not in old_set]
        if not changed_new:
            continue
        changed_old = [k for k in old_keys if k not in new_set]
        same_order = [k for k in old_keys if k in new_set] == [k for k in new_keys if k in old_set]
        if len(old_keys) == len(new_keys) and same_order and len(changed_old) == len(changed_new):
            out.pairs.update(zip(changed_new, changed_old))
        elif old_keys:
            out.unpaired += len(changed_new)
    return out


def select_new_actions(
    seen: set,
    taken: set,
    new_lines: Iterable[dict[str, Any]],
    rewordings: Optional[Rewordings] = None,
    id_of: Optional[dict[tuple, str]] = None,
) -> list[dict[str, Any]]:
    """The lines of `new_lines` whose action isn't in `seen` (action_key()s already
    in the file), with ids made unique against `taken`. Updates both sets. The
    nightly writer and backfill_logs.py both decide "is this new?" here.

    A line that `rewordings` pairs with an action already in the file is a
    correction: it takes that action's id (`id_of`: action_key -> id of the
    file's lines, updated here), and readers show the last line per id."""
    to_add = []
    pairs = rewordings.pairs if rewordings else {}
    for line in new_lines:
        key = action_key(line["action"])
        if key in seen:
            continue
        seen.add(key)
        old_id = id_of.get(pairs[key]) if id_of is not None and key in pairs else None
        if old_id is not None:
            line["id"] = old_id  # a rewording keeps the id of the action it rewords
        else:
            _unique_id(line, taken, key)
        if id_of is not None:
            id_of[key] = line["id"]
        to_add.append(line)
    return to_add


def _append_actions_at(
    path: Path, new_lines: Iterable[dict[str, Any]], keep_order: bool = False, rewordings: Optional["Rewordings"] = None
) -> int:
    existing = read_lines(path)
    seen = {action_key(line.get("action") or {}) for line in existing}
    taken = {line.get("id") for line in existing}
    id_of = {action_key(line.get("action") or {}): line.get("id") for line in existing}
    to_add = select_new_actions(seen, taken, new_lines, rewordings, id_of)
    _append(path, to_add, "action", keep_order)
    return len(to_add)


def _find_vote(existing: list[dict[str, Any]], vote: dict[str, Any]) -> Optional[dict[str, Any]]:
    """The last line recording the same vote, or None."""
    identifier, fallback = vote_keys(vote)
    for line in reversed(existing):
        other_id, other_fallback = vote_keys(line.get("vote_event") or {})
        if (identifier and other_id and identifier == other_id) or fallback == other_fallback:
            return line
    return None


def append_votes(bill_dir: Union[str, Path], new_lines: Iterable[dict[str, Any]]) -> int:
    """Append new votes and corrections to the bill's vote_event_logs.jsonl.

    A vote already recorded with the same substance is skipped. One recorded with
    different substance is appended again under the same id (a correction).
    Returns how many lines were added.
    """
    return _append_votes_at(Path(bill_dir) / VOTE_EVENT_LOG_FILE, new_lines)


def _append_votes_at(path: Path, new_lines: Iterable[dict[str, Any]], keep_order: bool = False) -> int:
    existing = read_lines(path)
    taken = {line.get("id") for line in existing}
    to_add = select_new_votes(existing, taken, new_lines)
    _append(path, to_add, "vote_event", keep_order)
    return len(to_add)


def select_new_votes(
    existing: list[dict[str, Any]], taken: set, new_lines: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """The lines of `new_lines` that are new votes or corrections of a vote in
    `existing` (the file's lines, in file order). Ids are made unique against
    `taken` (updated); a correction takes the id of the vote it corrects. The
    nightly writer and backfill_logs.py both decide "is this new?" here.

    A version is logged only if it differs from *every* version already logged
    for that vote, not just the last one. Some scrapes hold two versions of one
    vote (OH HB 14: one 6-0 "Reported" vote as both pass and fail; MT: "Sen Elect
    Gregg Hunter" in one copy, "Gregg Hunter" in the other), and comparing with
    the last line only logged A, B, A, B... every night (TN: 13,276 lines). The
    cost, accepted 2026-11-25: a genuine revert (A -> B -> A) isn't logged again."""
    to_add = []
    for line in new_lines:
        vote = line["vote_event"]
        lines = existing + to_add
        match = _find_vote(lines, vote)
        if match is not None:
            substance = vote_substance(vote)
            if any(vote_substance(l["vote_event"]) == substance for l in lines if l.get("id") == match["id"]):
                continue
            line["id"] = match["id"]  # a correction keeps the id of what it corrects
        else:
            _unique_id(line, taken, vote_keys(vote))
        to_add.append(line)
    return to_add


# --------------------------------------------------------------------------
# The old layout
# --------------------------------------------------------------------------


def has_legacy_logs(repo_root: Union[str, Path]) -> bool:
    """Whether any bill or session in the repo still has an old-layout logs/ folder."""
    root = Path(repo_root)
    for pattern in ("country:*/state:*/sessions/*/bills/*/logs", "country:*/state:*/sessions/*/logs"):
        if any(p.is_dir() for p in root.glob(pattern)):
            return True
    return False


class ConvertStats:
    def __init__(self) -> None:
        self.bills_converted = 0
        self.files_folded = 0
        self.duplicates_dropped = 0
        self.symlinks_removed = 0
        # Files left in place because they couldn't be read or recognised. Never
        # deleted: a conversion must not lose data it doesn't understand.
        self.left_in_place: list[str] = []

    def add(self, other: "ConvertStats") -> None:
        self.bills_converted += other.bills_converted
        self.files_folded += other.files_folded
        self.duplicates_dropped += other.duplicates_dropped
        self.symlinks_removed += other.symlinks_removed
        self.left_in_place.extend(other.left_in_place)

    def as_dict(self) -> dict[str, Any]:
        return {
            "bills_converted": self.bills_converted,
            "files_folded": self.files_folded,
            "duplicates_dropped": self.duplicates_dropped,
            "symlinks_removed": self.symlinks_removed,
            "left_in_place": self.left_in_place,
        }


def _bill_metadata(bill_dir: Path) -> dict[str, Any]:
    try:
        return json.loads((bill_dir / "metadata.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _first_logged(meta: dict[str, Any]) -> dict[tuple, str]:
    """When the pipeline first logged each action, from metadata.json's
    actions[]._processing.log_file_created, keyed like action_key()."""
    out = {}
    for a in meta.get("actions") or []:
        stamp = (a.get("_processing") or {}).get("log_file_created")
        if stamp:
            out[(a.get("date"), _squash(a.get("description")), a.get("organization_id"))] = stamp
    return out


def _current_action_shape(action: dict[str, Any], session_id: str, sources: list) -> dict[str, Any]:
    """Old log files hold the action in OpenStates' own shape (date,
    organization_id, classification); the writer has since used occurred_at,
    jurisdiction_id, classifications plus session_id/entity_type/sources. 36 of
    the 56 repos hold both (checked 2026-11-24). Converted lines all get the
    current shape, so readers and the duplicate check see one shape. The missing
    session and sources are filled in the way the writer fills them: the bill's
    session and its metadata.json sources."""
    if "occurred_at" in action or "date" not in action:
        return action
    return {
        "description": action.get("description", "no_description"),
        "occurred_at": action.get("date", "no_date"),
        "jurisdiction_id": action.get("organization_id", "no_jurisdiction"),
        "session_id": session_id,
        "entity_type": "bill",
        "classifications": action.get("classification", []),
        "related_entities": action.get("related_entities", []),
        "sources": sources,
    }


def legacy_file_to_line(
    path: Path, first_logged: dict[tuple, str], session_id: str = "", sources: Optional[list] = None
) -> Optional[tuple[str, dict[str, Any]]]:
    """An old logs/*.json file -> ("action" | "vote_event", line), or None if it
    isn't a log we recognise."""
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(content, dict):
        return None
    stem = path.name[: -len(".json")] if path.name.endswith(".json") else path.name

    if isinstance(content.get("action"), dict):
        action = _current_action_shape(content["action"], session_id, sources or [])
        return "action", {
            "id": stem,
            "first_seen": first_logged.get(action_key(action)),
            "chamber": chamber_of(action.get("jurisdiction_id")),
            "action": action,
            "bill_id": content.get("bill_id"),
        }
    if "vote_event" in path.name or "motion_text" in content or "votes" in content:
        return "vote_event", {
            "id": stem,
            # The old layout kept no record of when a vote was first seen; the
            # backfill from the raw scraper history fills this in.
            "first_seen": None,
            "chamber": chamber_of(content.get("organization")),
            "vote_event": content,
            "bill_id": content.get("bill_identifier"),
        }
    return None


def legacy_jsonl_to_lines(
    path: Path, first_logged: dict[tuple, str], session_id: str = "", sources: Optional[list] = None
) -> Optional[list[tuple[str, dict[str, Any]]]]:
    """An old logs/action_logs.jsonl -> [("action", line), ...], or None if any
    line isn't an action we recognise (then the whole file is left in place).

    The formatter briefly wrote this form (Taha's first JSONL step: one
    {"action", "bill_id"} object per line, inside logs/) to 118 IL bills between
    2026-09-22 and 09-25. Each line is an old action file's content without the
    file, so its id is the filename the old writer would have given it.
    """
    try:
        raw_lines = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    except Exception:
        return None
    out = []
    for content in raw_lines:
        if not isinstance(content, dict) or not isinstance(content.get("action"), dict):
            return None
        action = _current_action_shape(content["action"], session_id, sources or [])
        stem = legacy_action_id({
            "date": action.get("occurred_at"),
            "description": action.get("description", "no_description"),
            "classification": action.get("classifications") or [],
            "organization_id": action.get("jurisdiction_id"),
        })
        out.append(("action", {
            "id": stem,
            "first_seen": first_logged.get(action_key(action)),
            "chamber": chamber_of(action.get("jurisdiction_id")),
            "action": action,
            "bill_id": content.get("bill_id"),
        }))
    return out


def _sort_key(line: dict[str, Any], kind: str) -> tuple:
    # The government's date, then id. Used to order one batch of new entries, and
    # converted entries (which have no record of the order they were first seen in;
    # the old filenames sorted by this date too).
    obj = line.get(kind) or {}
    date = obj.get("occurred_at") if kind == "action" else obj.get("start_date")
    stamp = format_timestamp(date) or (_TS_PREFIX.match(line.get("id") or "") or [None, None])[1]
    return (stamp is None, stamp or "", line.get("id") or "")


def _parse_time(stamp: Optional[str]) -> Optional[datetime]:
    if not stamp:
        return None
    try:
        # Python 3.9 (the action's version) doesn't read a trailing "Z".
        return datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None


def _earlier(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """The earlier of two first_seen stamps; a missing or unreadable one loses."""
    ta, tb = _parse_time(a), _parse_time(b)
    if ta is None:
        return b if tb is not None else a or b
    if tb is None or ta <= tb:
        return a
    return b


def _same_vote(a: dict[str, Any], b: dict[str, Any]) -> bool:
    id_a, fallback_a = vote_keys(a)
    id_b, fallback_b = vote_keys(b)
    return bool(id_a and id_b and id_a == id_b) or fallback_a == fallback_b


def _rename(later: list[dict[str, Any]], old_id: str, new_id: str) -> None:
    """Give every line with id `old_id` the id `new_id`, unless another entry already
    uses `new_id` (then the backfill's id stays, so ids stay unique)."""
    if old_id == new_id or any(line.get("id") == new_id for line in later):
        return
    for line in later:
        if line.get("id") == old_id:
            line["id"] = new_id


def _fold_into_later(kind: str, converted: list[dict[str, Any]], later: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge old-file lines with lines already in the .jsonl file, which on a
    converted repo come from backfill_logs.py (the raw scraper history) or the
    nightly formatter. Returns the old-file lines to keep; edits `later` in place.

    An old file that duplicates a later line is dropped: the later line has the
    scrape's commit time, the old file only the formatter's run time
    (_processing.log_file_created, which a reformat rewrites: 12,240 KY actions say
    July 2026) or nothing (votes). The later line keeps the earlier of the two
    first_seen values, since an entry seen before the raw history began
    (Nov 2025) is better dated by the old file, and takes the old file's id, the
    name people and tools already know.

    A vote also has versions. An old vote file equal to one of the later versions
    is a duplicate as above. One with the same identity but different substance
    from every later version is an older version from before the raw history: it
    is kept, goes first, and shares the vote's id, as the start of its history.
    """
    kept = []
    for old in converted:
        if kind == "action":
            key = action_key(old["action"])
            match = next((l for l in later if action_key(l.get("action") or {}) == key), None)
            if match is None:
                kept.append(old)
                continue
            match["first_seen"] = _earlier(old.get("first_seen"), match.get("first_seen"))
            _rename(later, match["id"], old["id"])
            continue

        vote = old["vote_event"]
        versions = [l for l in later if _same_vote(l.get("vote_event") or {}, vote)]
        if not versions:
            kept.append(old)
            continue
        _rename(later, versions[0]["id"], old["id"])
        same = next((l for l in versions if vote_substance(l["vote_event"]) == vote_substance(vote)), None)
        if same is not None:
            same["first_seen"] = _earlier(old.get("first_seen"), same.get("first_seen"))
            continue
        old["id"] = versions[0]["id"]  # after the rename: one id for the vote's whole history
        kept.append(old)
    return kept


def convert_bill(bill_dir: Union[str, Path]) -> ConvertStats:
    """Fold bills/{id}/logs/*.json into the bill's two .jsonl files, then delete them.

    Converted lines go before anything already in the .jsonl files (they are older),
    so this rewrites the files once, the only time anything but appending happens.
    Where an old file and a line already in the .jsonl file are the same entry,
    the .jsonl line wins (see _fold_into_later).
    """
    bill_dir = Path(bill_dir)
    stats = ConvertStats()
    legacy_dir = bill_dir / LEGACY_LOG_DIR
    if not legacy_dir.is_dir() or legacy_dir.is_symlink():
        return stats

    meta = _bill_metadata(bill_dir)
    first_logged = _first_logged(meta)
    # bills/{id}/ sits in sessions/{session}/bills/
    session_id = meta.get("legislative_session") or bill_dir.parent.parent.name
    sources = meta.get("sources") or []
    folded: list[Path] = []
    converted: dict[str, list[dict[str, Any]]] = {"action": [], "vote_event": []}
    for path in sorted(legacy_dir.iterdir()):
        if path.is_file() and path.name == ACTION_LOG_FILE:
            parsed_many = legacy_jsonl_to_lines(path, first_logged, session_id, sources)
        elif path.is_file() and path.suffix == ".json":
            one = legacy_file_to_line(path, first_logged, session_id, sources)
            parsed_many = [one] if one else None
        else:
            parsed_many = None
        if parsed_many is None:
            stats.left_in_place.append(str(path))
            continue
        for kind, line in parsed_many:
            converted[kind].append(line)
        folded.append(path)

    for kind, filename, append_at in (
        ("action", ACTION_LOG_FILE, _append_actions_at),
        ("vote_event", VOTE_EVENT_LOG_FILE, _append_votes_at),
    ):
        lines = converted[kind]
        if not lines:
            continue
        path = bill_dir / filename
        later = read_lines(path)
        kept = _fold_into_later(kind, lines, later)
        # Write the old-file lines that remain first, then re-add anything already
        # in the new file through the normal duplicate checks.
        tmp = path.with_name(filename + ".tmp")
        if tmp.exists():
            tmp.unlink()
        added = append_at(tmp, kept)
        if kind == "action":
            # _fold_into_later already dropped the old files these lines duplicate,
            # so they go in as they are. Not through the duplicate checks: a
            # rewording repeats its action's id on purpose. Only an id an old file
            # now uses moves aside (the whole group, so its rewordings follow).
            old_ids = {l.get("id") for l in read_lines(tmp)}
            moved: dict[str, str] = {}
            for l in later:
                if l.get("id") in old_ids:
                    moved.setdefault(l["id"], f"{l['id']}~{_short_hash(action_key(l['action']))}")
                    l["id"] = moved[l["id"]]
            _append(tmp, later, "action", keep_order=True)
            added += len(later)
        else:
            # Lines already in the new-layout file keep their first-seen order.
            added += append_at(tmp, later, keep_order=True)
        stats.duplicates_dropped += len(lines) + len(later) - added
        tmp.replace(path)

    # Delete only after the new files are in place: a crash in between leaves both
    # copies, and the next conversion folds them again without duplicating.
    for path in folded:
        path.unlink()
    if folded:
        stats.files_folded = len(folded)
        stats.bills_converted = 1
    try:
        legacy_dir.rmdir()  # only succeeds when empty
    except OSError:
        pass
    return stats


def remove_session_log_symlinks(session_dir: Path) -> ConvertStats:
    """Delete sessions/{s}/logs/, which only ever held symlinks into bills/.
    Only symlinks are removed; a real file there is reported and kept."""
    stats = ConvertStats()
    logs_dir = session_dir / LEGACY_LOG_DIR
    if not logs_dir.is_dir() or logs_dir.is_symlink():
        return stats
    for path in sorted(logs_dir.iterdir()):
        if path.is_symlink():
            path.unlink()
            stats.symlinks_removed += 1
        else:
            stats.left_in_place.append(str(path))
    try:
        logs_dir.rmdir()
    except OSError:
        pass
    return stats


def convert_repo(repo_root: Union[str, Path]) -> ConvertStats:
    """Convert every bill under country:*/state:*/sessions/* to the .jsonl layout.
    Idempotent: on a converted repo it finds nothing and changes nothing."""
    stats = ConvertStats()
    for session_dir in sorted(Path(repo_root).glob("country:*/state:*/sessions/*")):
        if not session_dir.is_dir():
            continue
        stats.add(remove_session_log_symlinks(session_dir))
        bills_dir = session_dir / "bills"
        if bills_dir.is_dir():
            for bill_dir in sorted(bills_dir.iterdir()):
                if bill_dir.is_dir():
                    stats.add(convert_bill(bill_dir))
    return stats
