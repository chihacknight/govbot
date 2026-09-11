#!/usr/bin/env python3
"""Build a legislator-name roster for the Pages dashboard.

Some jurisdictions (Alaska, Wyoming, ...) publish bill sponsors by *surname
only* — the bill metadata carries ``"name": "Hall"`` with no first name, so the
dashboard's detail card can only show "Hall". This script builds a compact
lookup that lets the dashboard fill in the full name ("Carolyn Hall") client
side.

Source of truth is the public-domain (CC0) Open States people repo
(https://github.com/openstates/people), a directory of one YAML file per
current legislator. We read ``data/<state>/legislature/*.yml`` and, per state,
map each legislator's family name to their given + full name.

Output shape (``docs/src/dashboard/people.json``)::

    {
      "ak": { "hall": [["Carolyn", "Carolyn Hall", "Democratic",
                        "House District 19"]], ... },
      "wy": { "campbell": [["Elissa", "Elissa Campbell", "Republican",
                            "House District 58"],
                           ["Kevin", "Kevin Campbell", "Republican",
                            "Senate District 27"]], ... }
    }

Each entry is ``[given, full, party, area]``. ``party`` and ``area`` are the
legislator's **current** party (the party role with no end date) and the seat
they represent (chamber + district, e.g. "Senate District 5"); either is an
empty string when Open States doesn't record it. The first two fields keep the
same positions they always had, so name resolution is unchanged — party/area
are additive.

Chambers are intentionally merged: OpenStates sometimes tags a sponsor's
chamber unreliably (a Wyoming *Senate* file can arrive tagged ``lower``), so
the dashboard resolves a surname against the whole state and only substitutes a
full name when the match is unambiguous. Keeping every same-surname legislator
in the list lets it make that call (and disambiguate "Campbell, K" by initial).

Contact details and anything that drifts week to week (committee assignments,
office, contacts) are still omitted — only the name, current party, and current
seat are emitted, so the file stays small and stable.

Usage:
    # Against a local checkout of openstates/people:
    python3 scripts/build_people_roster.py \
        --people-dir /tmp/openstates-people \
        --output docs/src/dashboard/people.json

The script exits non-zero without writing when it finds no legislators, so a
failed/empty clone in CI leaves the committed roster in place rather than
blanking it. Requires PyYAML (already used across the repo's tooling).
"""

import argparse
import json
import sys
from pathlib import Path

import yaml


# Open States role `type` -> the chamber word a reader recognizes. Types that
# aren't a legislative seat (e.g. "governor", "mayor") map to nothing, so a
# non-legislator role never produces a bogus "District" label.
_CHAMBER = {"upper": "Senate", "lower": "House", "legislature": ""}


def _current(items):
    """Pick the 'current' entry from an Open States list of role/party dicts.

    Open States keeps history: past roles/parties carry an ``end_date``, the
    active one does not. Prefer an entry with no ``end_date``; among several,
    the latest ``start_date`` wins; if every entry has ended, fall back to the
    most recently started so we still show something rather than nothing.
    """
    rows = [r for r in (items or []) if isinstance(r, dict)]
    if not rows:
        return None
    # Dates come back from YAML as date objects or ISO strings; coerce to a
    # string so comparisons never mix types (ISO strings sort chronologically).
    def _s(v):
        return str(v).strip() if v else ""
    active = [r for r in rows if not _s(r.get("end_date"))]
    pool = active or rows
    return max(pool, key=lambda r: _s(r.get("start_date")))


def _area(role):
    """Human seat label from a current legislative role, or "" — e.g.
    "Senate District 5", "House District 19", or "District 3" when the chamber
    is unknown. A named (non-numeric) district is shown as-is beside the chamber
    ("House · 3rd Middlesex") rather than forced into "District <text>"."""
    if not role:
        return ""
    chamber = _CHAMBER.get((role.get("type") or "").strip().lower())
    if chamber is None:  # a non-legislative role — no seat to describe
        return ""
    district = str(role.get("district") or "").strip()
    if not district:
        return chamber  # e.g. an at-large "legislature" seat carries no number
    if district.isdigit() or (len(district) <= 4 and district[:-1].isdigit()):
        return f"{chamber} District {district}".strip()
    return f"{chamber} · {district}".strip(" ·")


def load_person(path):
    """Return (given, family, full, party, area) for one legislator YAML, or
    None to skip.

    Reads the name fields plus the *current* party and seat. A file missing a
    family or full name (mononyms, malformed records) is skipped rather than
    guessed at; missing party/area degrade to "".
    """
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - one bad file must not stop the build
        print(f"warning: could not parse {path}: {exc}", file=sys.stderr)
        return None
    if not isinstance(doc, dict):
        return None
    full = (doc.get("name") or "").strip()
    family = (doc.get("family_name") or "").strip()
    given = (doc.get("given_name") or "").strip()
    if not full or not family:
        return None
    party_row = _current(doc.get("party"))
    party = (party_row.get("name") or "").strip() if party_row else ""
    # Only legislative roles describe a seat; _area() ignores anything else.
    roles = [r for r in (doc.get("roles") or [])
             if isinstance(r, dict) and (r.get("type") or "").strip().lower() in _CHAMBER]
    area = _area(_current(roles))
    return given, family, full, party, area


def build_roster(people_dir):
    """Walk data/<state>/legislature/*.yml into {state: {family_lower: [[given, full]]}}."""
    data_dir = Path(people_dir) / "data"
    roster = {}
    count = 0
    # Federal (data/us) sponsors already arrive with full names, so there is
    # nothing to enrich there; skip it to keep the file lean and collision-free.
    for state_dir in sorted(p for p in data_dir.glob("*") if p.is_dir() and p.name != "us"):
        state = state_dir.name
        leg_dir = state_dir / "legislature"
        if not leg_dir.is_dir():
            continue
        by_family = {}
        for yml in sorted(leg_dir.glob("*.yml")):
            person = load_person(yml)
            if not person:
                continue
            given, family, full, party, area = person
            entries = by_family.setdefault(family.lower(), [])
            entry = [given, full, party, area]
            # Guard against the same legislator appearing twice (compare on the
            # identifying name pair, not party/area, which shouldn't differ).
            if not any(e[0] == given and e[1] == full for e in entries):
                entries.append(entry)
                count += 1
        if by_family:
            roster[state] = by_family
    return roster, count


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--people-dir", required=True,
                    help="Path to a checkout of github.com/openstates/people")
    ap.add_argument("--output", required=True, help="Where to write people.json")
    args = ap.parse_args(argv)

    roster, count = build_roster(args.people_dir)
    if count == 0:
        print("error: no legislators found; refusing to overwrite committed roster",
              file=sys.stderr)
        return 1

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Compact but stable: sorted keys so diffs stay readable across rebuilds.
    out.write_text(json.dumps(roster, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {out} — {count} legislators across {len(roster)} jurisdictions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
