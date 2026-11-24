#!/usr/bin/env python3
"""Add Chicago City Council legislation to the dashboard's data.json.

Chicago is Govbot's first city. Its legislation comes from the City Clerk's
keyless, documented eLMS API (api.chicityclerkelms.chicago.gov, see its
/swagger.json), not Open States. We list every NON-routine matter introduced in
the current council term: ordinances, orders, resolutions, appointments and
executive orders (~5,000). Routine matters (parking permits, vehicle-damage
claims, commendations: ~80% of the Clerk's records) and plain communications
or reports are left out, as they aren't legislation people follow.

Each matter becomes a record in the same shape build_dashboard_data.py writes
for state bills, under jurisdiction code "chi" (three letters, so it never
clashes with a state), and is tagged with the same keyword fallback
(scripts/dashboard_tags.json) on its title and the Clerk's own category.

Idempotent: the script replaces any "chi" records already in data.json.
Fail-soft: if the API can't be reached, data.json is left exactly as it was.

usage: build_chicago_matters.py --data docs/src/dashboard/data.json \
           --tags-config scripts/dashboard_tags.json [--fixture FILE]
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_dashboard_data import MAX_ACTION_DESC, MAX_SPONSORS, MAX_TITLE, compile_keyword_tags  # noqa: E402

API = "https://api.chicityclerkelms.chicago.gov/matter"
MATTER_PAGE = "https://chicityclerkelms.chicago.gov/Matter/?matterId="
CODE, NAME = "chi", "Chicago City Council"
# The current council term began with the inauguration on May 15, 2023.
TERM_START, SESSION = "2023-05-15", "2023-2027"
KEEP_TYPES = {"Ordinance", "Order", "Resolution", "Appointment", "Executive Order"}
PAGE = 500                      # the API's maximum page size
MAX_PAGES = 40                  # ~20,000 records: far above a term's non-routine count
UA = "chihacknight-civic-data/1.0"


def matters_url(skip):
    q = {"filter": f"introductionDate gt {TERM_START}T00:00:00Z and routine eq 'NO'",
         "sort": "introductionDate desc", "top": str(PAGE), "skip": str(skip)}
    return API + "?" + urllib.parse.urlencode(q)


def _day(iso):
    """'2026-12-08T16:00:00+00:00' -> '2026-12-08' (Chicago date; every Clerk date is a
    daytime meeting, so the UTC date is the local date)."""
    return (iso or "")[:10] or None


def sponsor_name(m):
    """The filing sponsor as a person's name ("Rodriguez, Michael D." -> "Michael D.
    Rodriguez"), or None for an office ("Dept./Agency", "Misc. Transmittal")."""
    raw = (m.get("filingSponsor") or "").strip()
    if "," not in raw:
        return None
    last, first = (p.strip() for p in raw.split(",", 1))
    return f"{first} {last}".strip() if first and last else None


def latest_action(m, today):
    """(date, description) of the matter's latest step, e.g. ('2026-07-16', 'Passed').
    A matter filed for an upcoming meeting carries that meeting as its introduction date;
    "latest" never means the future, so until then its date is the day it was filed."""
    status = (m.get("status") or "").split("-", 1)[-1].strip()      # "90-Final" -> "Final"
    sub = (m.get("subStatus") or "").strip()
    filed = min(_day(m.get("recordCreateDate")) or today, today)
    intro = _day(m.get("introductionDate"))
    if intro and intro > today:
        intro = filed
    if status == "Final":                     # "Passed", "Adopted", "Placed on File", ...
        final = _day(m.get("finalActionDate")) or intro
        if final and final > today:           # set for an upcoming meeting: not done yet
            return filed, "Filed with the Clerk"
        return final, sub or status
    if sub and sub != status:                 # "In Committee: Referred"
        return intro, f"{status}: {sub}"
    return intro, status or None


def matter_to_bill(m, compiled_tags, today):
    """Pure: one eLMS matter -> one dashboard record, or None when it isn't kept."""
    if not isinstance(m, dict) or m.get("type") not in KEEP_TYPES:
        return None
    if not m.get("recordNumber") or not m.get("matterId"):
        return None
    title = " ".join((m.get("title") or "").split())
    category = (m.get("matterCategory") or "").replace("|", "·")
    hay = f"{title} {category}".lower()
    date, desc = latest_action(m, today)
    person = sponsor_name(m)
    return {
        "state": CODE,
        "session": SESSION,
        "id": m["recordNumber"],
        "title": title[:MAX_TITLE],
        "chamber": "council",
        "latest_action": date,
        "latest_action_desc": desc[:MAX_ACTION_DESC] if desc else None,
        "sponsors": [person][:MAX_SPONSORS] if person else [],
        "url": MATTER_PAGE + urllib.parse.quote(m["matterId"]),
        "tags": sorted(name for name, pats in compiled_tags if any(p.search(hay) for p in pats)),
    }


def parse_matters(json_text, compiled_tags, today):
    """Pure: one API page -> (records kept, rows on the page)."""
    try:
        rows = (json.loads(json_text) or {}).get("data") or []
    except (json.JSONDecodeError, TypeError, AttributeError):
        return [], 0
    out = [b for b in (matter_to_bill(m, compiled_tags, today) for m in rows) if b]
    return out, len(rows)


def fetch_all(compiled_tags, today):
    """Live: page through the term. Returns None on any failure (the caller then
    leaves data.json alone), never a partial list."""
    bills = []
    for page in range(MAX_PAGES):
        req = urllib.request.Request(matters_url(page * PAGE), headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                text = r.read().decode("utf-8")
        except Exception as e:  # noqa: BLE001 - fail-soft on any network/HTTP error
            print(f"chicago: page {page} failed ({e}); leaving data.json unchanged", file=sys.stderr)
            return None
        got, n = parse_matters(text, compiled_tags, today)
        bills.extend(got)
        if n < PAGE:
            return bills
    return bills


def merge(doc, bills):
    """Pure: replace the "chi" records and jurisdiction entry in a data.json doc."""
    doc["bills"] = [b for b in doc.get("bills") or [] if b.get("state") != CODE] + bills
    states = [s for s in doc.get("states") or [] if s.get("code") != CODE]
    doc["states"] = states + ([{"code": CODE, "name": NAME}] if bills else [])
    return doc


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", required=True, help="data.json to add Chicago to (edited in place)")
    ap.add_argument("--tags-config", required=True, help="scripts/dashboard_tags.json")
    ap.add_argument("--fixture", help="read one saved API page instead of the network")
    ap.add_argument("--today", help="YYYY-MM-DD (default: today, UTC); for tests")
    args = ap.parse_args()

    compiled = compile_keyword_tags(args.tags_config)
    today = args.today or f"{datetime.now(timezone.utc):%Y-%m-%d}"
    if args.fixture:
        bills, _ = parse_matters(Path(args.fixture).read_text(), compiled, today)
    else:
        bills = fetch_all(compiled, today)
    if not bills:
        print("chicago: no matters; data.json unchanged", file=sys.stderr)
        return 0
    path = Path(args.data)
    doc = merge(json.loads(path.read_text()), bills)
    path.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"chicago: {len(bills)} City Council matters added to {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
