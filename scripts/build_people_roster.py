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
      "ak": { "hall": [["Carolyn", "Carolyn Hall"]], ... },
      "wy": { "campbell": [["Elissa", "Elissa Campbell"],
                           ["Kevin", "Kevin Campbell"]], ... }
    }

Chambers are intentionally merged: OpenStates sometimes tags a sponsor's
chamber unreliably (a Wyoming *Senate* file can arrive tagged ``lower``), so
the dashboard resolves a surname against the whole state and only substitutes a
full name when the match is unambiguous. Keeping every same-surname legislator
in the list lets it make that call (and disambiguate "Campbell, K" by initial).

Only the given/family/full name is emitted — no contact details, party, or
district — keeping the file small and free of data that drifts.

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


def load_person(path):
    """Return (given, family, full) for one legislator YAML, or None to skip.

    Reads only the three name fields; a file missing a family or full name
    (mononyms, malformed records) is skipped rather than guessed at.
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
    return given, family, full


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
            given, family, full = person
            entries = by_family.setdefault(family.lower(), [])
            pair = [given, full]
            # Guard against the same legislator appearing twice.
            if pair not in entries:
                entries.append(pair)
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
