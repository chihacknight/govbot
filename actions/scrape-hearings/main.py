#!/usr/bin/env python3
"""Scrape upcoming committee hearings (and best-effort witness-slip counts) for
the jurisdictions govbot surfaces on the Pages dashboard.

Unlike the bill dataset (OpenStates -> git-repos-as-datasets), committee hearings
are *live* artifacts published by each statehouse on its own machine-readable
endpoint. govbot does not get them from OpenStates, so this action taps the
sources directly:

* Illinois  -> ilga.gov Hearings JSON API (per chamber, date range)
* Washington -> leg.wa.gov CommitteeMeetingService SOAP/XML

The output is one document matching schemas/govbot.hearings.schema.json, written
next to the dashboard's data.json. The Pages deploy runs this twice a day, so the
dashboard shows near-future committee activity that the daily bill snapshot cannot.

Design rules (see CLAUDE.md):
* Only the Python standard library — no scraper deps, runs in a bare CI step.
* Fail loudly, recover gracefully: any source that errors degrades to zero
  hearings for that jurisdiction, never a crash. A caller that gets an empty
  document keeps the committed sample instead (see the deploy workflow).
* Pure parsers (parse_*) take raw text and are exercised offline by snapshot
  fixtures under __snapshots__/; only the fetch_* helpers touch the network.
* Witness-slip COUNTS are best-effort. Many capitols only expose counts while a
  slip window is open (a canceled hearing's slip page returns an error page), so
  slips are optional per the schema and their absence is normal. The reliable,
  always-useful signal is the hearing itself plus a deep link to file.

Usage:
    # Live (what the deploy runs):
    python3 actions/scrape-hearings/main.py --jurisdictions il,wa \
        --output docs/src/dashboard/hearings.json

    # Offline, deterministic — rebuild the snapshot from fixtures:
    python3 actions/scrape-hearings/main.py --from-fixtures actions/scrape-hearings/__snapshots__/raw \
        --now 2026-08-28T00:00:00Z --output -
"""

import argparse
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
FETCH_TIMEOUT = 15
# Illinois General Assembly id for the current (104th) GA and its session id,
# as used by ilga.gov's own Hearings API and witness-slip URLs.
IL_GA_ID = 18
IL_SESSION_ID = 114
# Rolling window: a few days back (to keep just-passed items visible) through
# ~6 weeks out. Committee calendars rarely post further than that.
WINDOW_BACK_DAYS = 3
WINDOW_FWD_DAYS = 45

# Jurisdiction participation portals (where a resident actually files/​signs in).
JURISDICTIONS = {
    "il": {
        "code": "il", "name": "Illinois", "participation": "witness_slip",
        "portal_url": "https://my.ilga.gov/",
    },
    "wa": {
        "code": "wa", "name": "Washington", "participation": "committee_sign_in",
        "portal_url": "https://app.leg.wa.gov/csi/",
    },
}

BILL_RE = re.compile(r"\b(HJR|SJR|HB|SB|HR|SR)\s*-?\s*(\d{1,5})\b", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# network (thin, testable-around)
# --------------------------------------------------------------------------- #
def fetch_text(url, timeout=FETCH_TIMEOUT):
    """GET a URL, returning the body text or None on any failure."""
    req = urllib.request.Request(url, headers={
        "user-agent": UA,
        "accept": "application/json,text/xml,application/xml,text/html;q=0.9,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return resp.read().decode("utf-8", "replace")
    except Exception as err:  # network, TLS, timeout, decode — all non-fatal
        print(f"warning: fetch failed {url}: {err}", file=sys.stderr)
        return None


# --------------------------------------------------------------------------- #
# shared helpers
# --------------------------------------------------------------------------- #
def extract_bill_ids(text):
    """Compact bill ids referenced in a subject/agenda line, de-duplicated."""
    seen = {}
    for m in BILL_RE.finditer(text or ""):
        seen[f"{m.group(1).upper()}{int(m.group(2))}"] = None
    return list(seen)


def join_location(*parts):
    return " · ".join(p.strip() for p in parts if p and p.strip())


# --------------------------------------------------------------------------- #
# Illinois — ilga.gov Hearings JSON API
# --------------------------------------------------------------------------- #
def il_hearings_url(chamber, begin, end):
    cid = "h" if chamber == "house" else "s"
    return (f"https://ilga.gov/API/Hearings/GetHearingsListByRange"
            f"?ChamberId={cid}&GaId={IL_GA_ID}"
            f"&BeginDate={begin:%-m/%-d/%Y}&EndDate={end:%-m/%-d/%Y}")


def il_witness_slip_url(bill_id):
    """The official witness-slip page for a bill. LegId=0 is ilga.gov's own
    placeholder on bill-status pages; the resident resolves the live bill there."""
    m = re.match(r"([A-Z]+)(\d+)", bill_id)
    if not m:
        return "https://my.ilga.gov/"
    doctype, num = m.group(1), m.group(2)
    return (f"https://ilga.gov/Legislation/BillStatus/WitnessSlips"
            f"?GAID={IL_GA_ID}&DocNum={num}&DocTypeID={doctype}"
            f"&LegId=0&SessionID={IL_SESSION_ID}")


def il_details_url(chamber, committee_id, hearing_id):
    seg = "House" if chamber == "house" else "Senate"
    return f"https://ilga.gov/{seg}/hearings/details/{committee_id}/{hearing_id}"


def _il_time_to_iso(raw):
    """'8/31/2026 10:00 AM' -> '2026-08-31T10:00:00' (naive local), else None."""
    for fmt in ("%m/%d/%Y %I:%M %p", "%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%dT%H:%M:%S")
        except (ValueError, AttributeError):
            continue
    return None


def parse_il_hearings(json_text, chamber):
    """Pure: normalize ilga.gov hearings JSON for one chamber into records."""
    try:
        rows = json.loads(json_text)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(rows, list):
        return []
    out = []
    for r in rows:
        hearing_id = str(r.get("hearingID") or r.get("HearingID") or "")
        committee_id = str(r.get("committeeID") or r.get("CommitteeID") or "")
        if not hearing_id or not committee_id:
            continue
        subject = str(r.get("subjectMatter") or r.get("SubjectMatter") or "")
        committee = str(r.get("longDescription") or r.get("LongDescription")
                        or "Committee")
        text_line = str(r.get("textLine") or r.get("TextLine") or "")
        canceled = "cancel" in text_line.lower() or "cancel" in subject.lower()
        raw_when = str(r.get("scheduledDateTime") or r.get("ScheduledDateTime") or "")
        location = join_location(r.get("room") or r.get("Room") or "",
                                 r.get("building") or r.get("Building") or "",
                                 r.get("city") or r.get("City") or "")
        bills = [{"id": bid, "slips": None}
                 for bid in extract_bill_ids(subject + " " + committee)]
        out.append({
            "id": f"il-{chamber}-{committee_id}-{hearing_id}",
            "jurisdiction": "il",
            "chamber": chamber,
            "committee": committee,
            "title": subject,
            "scheduled_iso": _il_time_to_iso(raw_when),
            "scheduled_display": raw_when,
            "timezone": "America/Chicago",
            "location": location,
            "status": "canceled" if canceled else "scheduled",
            "bills": bills,
            "details_url": il_details_url(chamber, committee_id, hearing_id),
            "witness_slip_url": (il_witness_slip_url(bills[0]["id"]) if bills
                                 else "https://my.ilga.gov/"),
            "source": "ilga.gov",
        })
    return out


def parse_slip_counts(html):
    """Pure, best-effort: aggregate proponent/opponent/no-position counts from a
    witness-slip page, or None when the page is an error / has no counts."""
    if not html or "General Assembly - Error" in html:
        return None
    def n(label):
        m = re.search(label + r"\s*:?\s*([\d,]+)", html, re.IGNORECASE)
        return int(m.group(1).replace(",", "")) if m else None
    prop, opp, none = n("Proponents?"), n("Opponents?"), n("No Position")
    if prop is None and opp is None and none is None:
        return None
    return {"proponents": prop or 0, "opponents": opp or 0, "no_position": none or 0}


def fetch_il(begin, end, with_slips):
    hearings = []
    for chamber in ("house", "senate"):
        text = fetch_text(il_hearings_url(chamber, begin, end))
        if text:
            hearings.extend(parse_il_hearings(text, chamber))
    if with_slips:
        enrich_il_slips(hearings)
    return hearings


def enrich_il_slips(hearings):
    """Best-effort: fill slip counts for bills of non-canceled hearings only,
    bounded and parallel. Failures leave slips as None (the schema allows it)."""
    targets = []
    for h in hearings:
        if h["status"] == "canceled":
            continue
        for b in h["bills"]:
            targets.append(b)
    if not targets:
        return
    def one(bill):
        html = fetch_text(il_witness_slip_url(bill["id"]))
        counts = parse_slip_counts(html) if html else None
        if counts:
            bill["slips"] = counts
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(one, targets[:60]))  # cap: be polite to ilga.gov


# --------------------------------------------------------------------------- #
# Washington — leg.wa.gov CommitteeMeetingService (SOAP/XML)
# --------------------------------------------------------------------------- #
WA_NS = "{http://WSLWebServices.leg.wa.gov/}"


def _wa_text(el, tag):
    child = el.find(WA_NS + tag)
    return (child.text or "").strip() if child is not None and child.text else ""


def wa_meetings_url(begin, end):
    return ("https://wslwebservices.leg.wa.gov/CommitteeMeetingService.asmx/"
            f"GetCommitteeMeetings?beginDate={begin:%Y-%m-%d}&endDate={end:%Y-%m-%d}")


def wa_items_url(agenda_id):
    return ("https://wslwebservices.leg.wa.gov/CommitteeMeetingService.asmx/"
            f"GetCommitteeMeetingItems?agendaId={agenda_id}")


def wa_chamber(agency):
    a = (agency or "").lower()
    if "senate" in a:
        return "senate"
    if "house" in a:
        return "house"
    return "other"


def parse_wa_meetings(xml_text):
    """Pure: normalize a GetCommitteeMeetings XML body into records (no bills)."""
    try:
        root = ET.fromstring(xml_text)
    except (ET.ParseError, TypeError):
        return []
    out = []
    for m in root.findall(WA_NS + "CommitteeMeeting"):
        agenda_id = _wa_text(m, "AgendaId")
        if not agenda_id:
            continue
        agency = _wa_text(m, "Agency")
        committee = "Committee"
        committees = m.find(WA_NS + "Committees")
        if committees is not None:
            first = committees.find(WA_NS + "Committee")
            if first is not None:
                committee = _wa_text(first, "Name") or committee
        when = _wa_text(m, "Date")  # already ISO-naive local
        canceled = _wa_text(m, "Cancelled").lower() == "true"
        location = join_location(_wa_text(m, "Room"), _wa_text(m, "Building"),
                                 _wa_text(m, "City"))
        notes = _wa_text(m, "Notes")
        chamber = wa_chamber(agency)
        out.append({
            "id": f"wa-{chamber}-{agenda_id}",
            "jurisdiction": "wa",
            "chamber": chamber,
            "committee": committee,
            "title": notes or f"{agency} · {committee}",
            "scheduled_iso": when or None,
            "scheduled_display": when,
            "timezone": "America/Los_Angeles",
            "location": location,
            "status": "canceled" if canceled else "scheduled",
            "bills": [],
            "details_url": f"https://app.leg.wa.gov/committeeschedules/Home/Agenda/{agenda_id}",
            "witness_slip_url": "https://app.leg.wa.gov/csi/",
            "source": "leg.wa.gov",
            "_agenda_id": agenda_id,
        })
    return out


def parse_wa_items(xml_text):
    """Pure: bill ids on a committee-meeting agenda."""
    try:
        root = ET.fromstring(xml_text)
    except (ET.ParseError, TypeError):
        return []
    ids = {}
    for item in root.findall(WA_NS + "CommitteeMeetingItem"):
        htype = (_wa_text(item, "HearingTypeDescription")
                 or _wa_text(item, "HearingType"))
        # Skip pure work sessions (not a public-testimony hearing).
        if htype and "work session" in htype.lower() and "public" not in htype.lower():
            continue
        bill = _wa_text(item, "BillId").replace(" ", "").upper()
        if bill:
            ids[bill] = None
    return list(ids)


def fetch_wa(begin, end):
    text = fetch_text(wa_meetings_url(begin, end))
    if not text:
        return []
    meetings = [m for m in parse_wa_meetings(text) if m["status"] != "canceled"
                or True]  # keep canceled too; flagged
    def items(m):
        xml = fetch_text(wa_items_url(m["_agenda_id"]))
        m["bills"] = [{"id": bid, "slips": None} for bid in parse_wa_items(xml)] if xml else []
        m.pop("_agenda_id", None)
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(items, meetings))
    return meetings


# --------------------------------------------------------------------------- #
# offline (snapshot) build — no network
# --------------------------------------------------------------------------- #
def build_from_fixtures(fixtures_dir):
    """Deterministic build straight from raw __snapshots__ fixtures."""
    d = Path(fixtures_dir)
    hearings = []
    il_files = [("il_house.json", "house"), ("il_active.json", "house"),
                ("il_senate.json", "senate")]
    for fname, chamber in il_files:
        p = d / fname
        if p.exists():
            hearings.extend(parse_il_hearings(p.read_text(), chamber))
    wa_path = d / "wa_meetings.xml"
    if wa_path.exists():
        for m in parse_wa_meetings(wa_path.read_text()):
            items_file = d / f"wa_items_{m['_agenda_id']}.xml"
            if items_file.exists():
                m["bills"] = [{"id": b, "slips": None}
                              for b in parse_wa_items(items_file.read_text())]
            m.pop("_agenda_id", None)
            hearings.append(m)
    return hearings


# --------------------------------------------------------------------------- #
# assembly
# --------------------------------------------------------------------------- #
def assemble(hearings, jurisdictions, source, now):
    used = [j for j in jurisdictions if any(h["jurisdiction"] == j for h in hearings)] \
        or jurisdictions
    hearings = sorted(hearings, key=lambda h: (
        h["jurisdiction"], h["scheduled_iso"] or "9999", h["id"]))
    counts = {}
    for h in hearings:
        counts[h["jurisdiction"]] = counts.get(h["jurisdiction"], 0) + 1
    return {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": source,
        "jurisdictions": [
            {k: JURISDICTIONS[j][k] for k in ("code", "name", "participation", "portal_url")}
            for j in used if j in JURISDICTIONS
        ],
        "counts": counts,
        "hearings": hearings,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--jurisdictions", default="il,wa",
                    help="Comma-separated codes to scrape live (default: il,wa)")
    ap.add_argument("--from-fixtures", default=None,
                    help="Build offline from a raw fixtures dir (no network)")
    ap.add_argument("--no-slips", action="store_true",
                    help="Skip best-effort witness-slip count enrichment")
    ap.add_argument("--now", default=None,
                    help="Override generated_at (ISO, e.g. 2026-08-28T00:00:00Z) "
                         "— used for deterministic snapshots")
    ap.add_argument("--output", "-o", default="-", help="Output path (default: stdout)")
    args = ap.parse_args()

    now = (datetime.strptime(args.now, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
           if args.now else datetime.now(timezone.utc))

    if args.from_fixtures:
        hearings = build_from_fixtures(args.from_fixtures)
        source = "fixtures (offline snapshot)"
        codes = ["il", "wa"]
    else:
        codes = [c.strip().lower() for c in args.jurisdictions.split(",") if c.strip()]
        begin = now - timedelta(days=WINDOW_BACK_DAYS)
        end = now + timedelta(days=WINDOW_FWD_DAYS)
        hearings = []
        if "il" in codes:
            hearings.extend(fetch_il(begin, end, with_slips=not args.no_slips))
        if "wa" in codes:
            hearings.extend(fetch_wa(begin, end))
        source = "ilga.gov + leg.wa.gov (govbot scrape-hearings)"

    doc = assemble(hearings, codes, source, now)
    text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    if args.output == "-":
        sys.stdout.write(text)
    else:
        Path(args.output).write_text(text)
        print(f"wrote {len(doc['hearings'])} hearings "
              f"({', '.join(f'{k}:{v}' for k, v in doc['counts'].items()) or 'none'}) "
              f"to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
