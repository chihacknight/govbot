#!/usr/bin/env python3
"""Scrape upcoming committee hearings (and best-effort witness-slip counts) for
the jurisdictions govbot surfaces on the Pages dashboard.

Unlike the bill dataset (OpenStates -> git-repos-as-datasets), committee hearings
are *live* artifacts published by each statehouse on its own machine-readable
endpoint. govbot does not get them from OpenStates, so this action taps the
sources directly:

* Illinois     -> ilga.gov Hearings JSON API (per chamber, date range)
* Washington   -> leg.wa.gov CommitteeMeetingService SOAP/XML
* Massachusetts -> malegislature.gov Hearings JSON API (list + per-hearing detail)

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
import os
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
# Rolling window: from today through ~6 weeks out. Only upcoming hearings are
# shown (past ones are filtered in assemble), and committee calendars rarely
# post further than this.
WINDOW_BACK_DAYS = 0
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
    "ma": {
        "code": "ma", "name": "Massachusetts", "participation": "written_testimony",
        "portal_url": "https://malegislature.gov/",
    },
    "us": {
        "code": "us", "name": "USA (Federal)", "participation": "public_comment",
        "portal_url": "https://www.regulations.gov/",
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


def il_bill_status_url(bill_id):
    """The official Bill Status page for a bill — a reliable, always-200 page
    that carries the working "Witness Slips" button. We link here rather than
    to the WitnessSlips deep link, which returns an error page (HTTP 500) when
    hit directly without a live session."""
    m = re.match(r"([A-Z]+)(\d+)", bill_id)
    if not m:
        return "https://my.ilga.gov/"
    doctype, num = m.group(1), m.group(2)
    return (f"https://ilga.gov/legislation/BillStatus"
            f"?DocTypeID={doctype}&DocNum={num}"
            f"&GAID={IL_GA_ID}&SessionID={IL_SESSION_ID}")


def il_slips_scrape_url(bill_id):
    """The witness-slip totals page (used only for best-effort count scraping,
    an opt-in step). It is not linked to users because it 500s when opened
    directly; see il_bill_status_url for the user-facing link."""
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


def il_committee_url(chamber, committee_id):
    """The official ILGA committee page (members/roster) for a committee id."""
    seg = "House" if chamber == "house" else "Senate"
    return f"https://ilga.gov/{seg}/committees/members/{committee_id}"


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
        bills = [{"id": bid, "slips": None, "url": il_bill_status_url(bid)}
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
            "committee_url": il_committee_url(chamber, committee_id),
            "witness_slip_url": (bills[0]["url"] if bills else "https://my.ilga.gov/"),
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
        html = fetch_text(il_slips_scrape_url(bill["id"]))
        counts = parse_slip_counts(html) if html else None
        if counts:
            bill["slips"] = counts
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(one, targets[:60]))  # cap: be polite to ilga.gov


# Markers of a "soft 404": leg.wa.gov serves an unknown committee slug as
# HTTP 200 with a "Page not found" body, and ilga.gov has its own error page, so
# a status-code check alone is not enough — we inspect the returned page too.
_NOT_FOUND_MARKERS = ("page not found", "general assembly - error")


def committee_url_ok(url):
    html = fetch_text(url)
    if not html:
        return False
    low = html.lower()
    return not any(m in low for m in _NOT_FOUND_MARKERS)


def verify_committee_urls(hearings):
    """Live check: null out any committee_url that doesn't resolve to a real
    committee page (guards against guessed slugs and soft-404s), so a broken
    link never ships. One request per distinct URL, cached, run in parallel."""
    urls = {h["committee_url"] for h in hearings if h.get("committee_url")}
    if not urls:
        return
    status = {}
    def probe(u):
        status[u] = committee_url_ok(u)
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(probe, urls))
    for h in hearings:
        if h.get("committee_url") and not status.get(h["committee_url"]):
            h["committee_url"] = None


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


# leg.wa.gov committee URLs use acronym slugs (scpp, jlarc, tran) that can't be
# derived from the committee name, so we resolve them from leg.wa.gov's own
# committee index instead of guessing. Fetched once per run and cached.
WA_COMMITTEE_INDEX_URL = "https://leg.wa.gov/about-the-legislature/committees/"
_wa_index_cache = {"loaded": False, "entries": []}


def _cmte_tokens(name):
    return set(re.findall(r"[a-z0-9]+", (name or "").lower()))


def wa_committee_index():
    """[(token_set, absolute_url), ...] parsed from leg.wa.gov's committee list."""
    if _wa_index_cache["loaded"]:
        return _wa_index_cache["entries"]
    _wa_index_cache["loaded"] = True
    html = fetch_text(WA_COMMITTEE_INDEX_URL)
    if not html:
        return []
    entries = []
    seen = set()
    pattern = (r'<a[^>]+href="([^"]*committees/(?:joint|senate|house)/[a-z0-9-]+/[^"]*)"'
               r'[^>]*>(.*?)</a>')
    for href, text in re.findall(pattern, html, re.S | re.I):
        name = re.sub(r"<[^>]+>", "", text)
        name = re.sub(r"\s+", " ", name).strip()
        if not name or href in seen:
            continue
        seen.add(href)
        url = href if href.startswith("http") else "https://leg.wa.gov" + href
        entries.append((_cmte_tokens(name), url))
    _wa_index_cache["entries"] = entries
    return entries


def wa_committee_url(name):
    """Match a committee name to its leg.wa.gov page via the index, tolerating
    reordering and an acronym in parentheses (token-subset match). None if no
    confident match — better no link than a wrong one."""
    want = _cmte_tokens(name)
    if len(want) < 3:
        return None
    best, best_diff = None, 99
    for tokens, url in wa_committee_index():
        if want <= tokens or tokens <= want:
            diff = len(tokens ^ want)
            if diff < best_diff:
                best, best_diff = url, diff
    return best


def resolve_wa_committee_urls(hearings):
    """Fill committee_url for WA hearings from the leg.wa.gov index (live)."""
    for h in hearings:
        if h["jurisdiction"] == "wa" and not h.get("committee_url"):
            h["committee_url"] = wa_committee_url(h.get("committee"))


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
            "committee_url": None,  # filled live from the leg.wa.gov index (pure parse stays offline)
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


def wa_bill_url(bill_id, year):
    """Official Washington bill-summary page for a bill id (e.g. HB1234)."""
    m = re.match(r"([A-Z]+)(\d+)", bill_id)
    if not m:
        return "https://app.leg.wa.gov/csi/"
    return (f"https://app.leg.wa.gov/billsummary?BillNumber={m.group(2)}"
            f"&Year={year}&Initiative=false")


def _wa_year(hearing):
    iso = hearing.get("scheduled_iso") or ""
    return iso[:4] if iso[:4].isdigit() else "2025"


def wa_bills(ids, hearing):
    year = _wa_year(hearing)
    return [{"id": bid, "slips": None, "url": wa_bill_url(bid, year)} for bid in ids]


def fetch_wa(begin, end):
    text = fetch_text(wa_meetings_url(begin, end))
    if not text:
        return []
    meetings = parse_wa_meetings(text)  # keep canceled too; flagged in status
    def items(m):
        xml = fetch_text(wa_items_url(m["_agenda_id"]))
        m["bills"] = wa_bills(parse_wa_items(xml), m) if xml else []
        m.pop("_agenda_id", None)
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(items, meetings))
    return meetings


# --------------------------------------------------------------------------- #
# Massachusetts — malegislature.gov Hearings JSON API
# --------------------------------------------------------------------------- #
# MA publishes a keyless JSON API. GET /api/Hearings lists every hearing of the
# current General Court as {EventId} stubs, ordered newest-scheduled first, so
# upcoming hearings cluster at the front. GET /api/Hearings/<id> returns the full
# record: committee, datetime (naive Eastern), location, and the bills on each
# agenda. We scan a bounded prefix of the list and keep the near-future ones.
MA_LIST_URL = "https://malegislature.gov/api/Hearings"
# Detail requests to pull from the (long, historical) list. Upcoming hearings sit
# at the top; a generous prefix catches them all while bounding the request count.
MA_SCAN_LIMIT = 150


def ma_detail_url(event_id):
    return f"https://malegislature.gov/api/Hearings/{event_id}"


def ma_hearing_page_url(event_id):
    return f"https://malegislature.gov/Events/Hearings/Detail/{event_id}"


def ma_bill_url(bill_number, general_court):
    return f"https://malegislature.gov/Bills/{general_court}/{bill_number}"


def ma_committee_page_url(code, general_court):
    return f"https://malegislature.gov/Committees/Detail/{code}/{general_court}"


def _ma_chamber(name, code):
    """House / Senate / Joint from the committee name, falling back to the
    committee-code prefix (H/S/J), else 'other'."""
    text = (name or "").lower()
    if "joint" in text:
        return "joint"
    if "house" in text:
        return "house"
    if "senate" in text:
        return "senate"
    return {"J": "joint", "H": "house", "S": "senate"}.get((code or "")[:1].upper(), "other")


def _ma_real_committee_code(code):
    """MA tags conference/special hearings with a placeholder code (Hxx/Sxx/Jxx)
    that has no committee page. Return the code only when it is a real one
    (letter + digits, e.g. J17), else None so no bogus committee link is built."""
    return code if re.match(r"^[HSJ]\d+$", code or "") else None


def parse_ma_hearing_list(json_text):
    """Pure: ordered event ids from the /api/Hearings stub list."""
    try:
        rows = json.loads(json_text)
    except (json.JSONDecodeError, TypeError):
        return []
    ids = []
    for r in rows if isinstance(rows, list) else []:
        eid = r.get("EventId") if isinstance(r, dict) else None
        if eid is not None:
            ids.append(eid)
    return ids


def parse_ma_hearing(json_text):
    """Pure: normalize one /api/Hearings/<id> detail into a hearing record, or
    None when the body isn't a usable hearing object. Tolerates the null-heavy
    records the API returns for stub/placeholder events."""
    try:
        d = json.loads(json_text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(d, dict) or d.get("EventId") is None:
        return None
    host = d.get("HearingHost") or {}
    code = host.get("CommitteeCode")
    general_court = host.get("GeneralCourtNumber")
    name = d.get("Name") or ""
    chamber = _ma_chamber(name, code)
    real_code = _ma_real_committee_code(code)
    when = d.get("StartTime") or d.get("EventDate") or ""
    when = when.strip() if isinstance(when, str) else ""
    loc = d.get("Location") or {}
    location = join_location(loc.get("LocationName") or "", loc.get("City") or "")
    canceled = str(d.get("Status") or "").lower() == "canceled"
    # Bills: every document on every agenda, de-duplicated, normalized (H5516).
    bill_urls = {}
    for agenda in d.get("HearingAgendas") or []:
        for doc in (agenda or {}).get("DocumentsInAgenda") or []:
            num = str((doc or {}).get("BillNumber") or "").replace(" ", "").upper()
            if not num:
                continue
            gc = (doc or {}).get("GeneralCourtNumber") or general_court or 194
            bill_urls.setdefault(num, ma_bill_url(num, gc))
    bills = [{"id": bid, "slips": None, "url": url} for bid, url in bill_urls.items()]
    return {
        "id": f"ma-{chamber}-{d['EventId']}",
        "jurisdiction": "ma",
        "chamber": chamber,
        "committee": name or "Committee",
        "title": (d.get("Description") or name or "").strip(),
        "scheduled_iso": when or None,
        "scheduled_display": when,
        "timezone": "America/New_York",
        "location": location,
        "status": "canceled" if canceled else "scheduled",
        "bills": bills,
        "details_url": ma_hearing_page_url(d["EventId"]),
        "committee_url": ma_committee_page_url(real_code, general_court) if real_code and general_court else None,
        "witness_slip_url": "https://malegislature.gov/",
        "source": "malegislature.gov",
    }


def fetch_ma(begin, end):
    """Live: pull the hearing list, fetch a bounded prefix of details in parallel,
    and keep those in the [begin, end] window. The MA API has no date filter, so
    we bound client-side; fail-soft — a missed detail drops only that hearing."""
    listing = fetch_text(MA_LIST_URL)
    if not listing:
        return []
    ids = parse_ma_hearing_list(listing)[:MA_SCAN_LIMIT]
    if not ids:
        return []
    lo, hi = begin.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    def one(eid):
        text = fetch_text(ma_detail_url(eid))
        return parse_ma_hearing(text) if text else None

    out = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for rec in pool.map(one, ids):
            if not rec:
                continue
            day = (rec.get("scheduled_iso") or "")[:10]
            # Keep undated (can't prove past) and anything inside the window;
            # assemble() also drops past hearings, but bounding the far side here
            # keeps months-out hearings out of the near-future feed.
            if not day or lo <= day <= hi:
                out.append(rec)
    return out


# --------------------------------------------------------------------------- #
# USA (Federal) — open comment periods from Regulations.gov
# --------------------------------------------------------------------------- #
# Federal "hearings" are open public-comment periods (agencies also post public
# hearings on the same dockets). The Regulations.gov API needs a key; supply one
# via REGULATIONS_GOV_API_KEY (free from api.data.gov). Without a key it uses the
# shared DEMO_KEY, which is heavily rate-limited, so any failure falls back to a
# small committed seed (federal_seed.json) — federal is thus never empty.
REGS_API = "https://api.regulations.gov/v4/documents"
REGS_DOC_URL = "https://www.regulations.gov/document/"
REGS_COMMENT_URL = "https://www.regulations.gov/commenton/"
FEDERAL_SEED = Path(__file__).with_name("federal_seed.json")

# A handful of agency codes → readable names; unknown codes fall back to the code.
AGENCY_NAMES = {
    "CMS": "Centers for Medicare & Medicaid Services",
    "USCIS": "U.S. Citizenship and Immigration Services",
    "BLM": "Bureau of Land Management",
    "HHS": "Department of Health and Human Services",
    "FAA": "Federal Aviation Administration",
    "EPA": "Environmental Protection Agency",
    "FDA": "Food and Drug Administration",
    "DOL": "Department of Labor",
    "ED": "Department of Education",
    "IRS": "Internal Revenue Service",
    "DHS": "Department of Homeland Security",
    "DOE": "Department of Energy",
    "FWS": "U.S. Fish and Wildlife Service",
    "OSHA": "Occupational Safety and Health Administration",
}


def _fed_pretty_date(iso):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", iso or "")
    if not m:
        return ""
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
              "Oct", "Nov", "Dec"]
    return f"{months[int(m.group(2)) - 1]} {int(m.group(3))}, {m.group(1)}"


def _fed_record(doc_id, agency_id, title, comment_end, url=None, comment_url=None):
    """Map one open federal comment period into a hearing record."""
    agency = AGENCY_NAMES.get((agency_id or "").upper(), agency_id or "Federal agency")
    disp = _fed_pretty_date(comment_end)
    details = url or (REGS_DOC_URL + doc_id)
    return {
        "id": f"us-{doc_id}",
        "jurisdiction": "us",
        "chamber": "federal",
        "committee": agency,
        "title": title,
        "scheduled_iso": comment_end or None,
        "scheduled_display": ("Comments due " + disp) if disp else "Open for comment",
        "timezone": None,
        "location": "Online · Regulations.gov",
        "status": "open",
        "bills": [{"id": doc_id, "title": title, "url": details, "slips": None}],
        "details_url": details,
        "committee_url": None,
        "witness_slip_url": comment_url or url or (REGS_COMMENT_URL + doc_id),
        "source": "regulations.gov",
    }


def federal_from_seed():
    """Committed placeholder comment periods, used offline and whenever the live
    Regulations.gov fetch is unavailable. Each seed row carries its own links so
    it never points at a fabricated document id."""
    try:
        rows = json.loads(FEDERAL_SEED.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    return [_fed_record(r["doc_id"], r.get("agency_id"), r.get("title", ""),
                        r.get("comment_end"), url=r.get("url"),
                        comment_url=r.get("comment_url")) for r in rows]


def fetch_us(use_api=True, limit=12):
    """Open federal comment periods, soonest-closing first. Live from the
    Regulations.gov API when reachable, else the committed seed."""
    if use_api:
        key = os.environ.get("REGULATIONS_GOV_API_KEY") or "DEMO_KEY"
        url = (f"{REGS_API}?filter[openForComment]=true&sort=commentEndDate"
               f"&page[size]={limit}&api_key={key}")
        text = fetch_text(url)
        if text:
            try:
                data = json.loads(text)
                recs = []
                for it in data.get("data", []):
                    a = it.get("attributes", {})
                    doc_id = it.get("id", "")
                    if not doc_id:
                        continue
                    recs.append(_fed_record(doc_id, a.get("agencyId"),
                                            a.get("title", ""), a.get("commentEndDate")))
                if recs:
                    return recs
            except (json.JSONDecodeError, TypeError):
                pass
    return federal_from_seed()


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
                m["bills"] = wa_bills(parse_wa_items(items_file.read_text()), m)
            m.pop("_agenda_id", None)
            hearings.append(m)
    # Massachusetts: a list stub file names the detail fixtures to parse.
    ma_list = d / "ma_hearings.json"
    if ma_list.exists():
        for eid in parse_ma_hearing_list(ma_list.read_text()):
            detail = d / f"ma_hearing_{eid}.json"
            if detail.exists():
                rec = parse_ma_hearing(detail.read_text())
                if rec:
                    hearings.append(rec)
    # Federal comment periods come from the committed seed offline (deterministic).
    hearings.extend(federal_from_seed())
    return hearings


# --------------------------------------------------------------------------- #
# assembly
# --------------------------------------------------------------------------- #
def assemble(hearings, jurisdictions, source, now):
    # Only upcoming hearings: drop anything whose date is before today. A hearing
    # with an unparseable time (scheduled_iso None) is kept — we can't prove it's
    # past. "Today" uses the build date so a hearing earlier today still shows.
    today = now.strftime("%Y-%m-%d")
    hearings = [h for h in hearings
                if not h.get("scheduled_iso") or h["scheduled_iso"][:10] >= today]
    # USA (Federal) leads, then the rest alphabetically — the dashboard shows the
    # federal comment periods above the state hearings.
    rank = lambda code: (0 if code == "us" else 1, code)
    used = [j for j in jurisdictions if any(h["jurisdiction"] == j for h in hearings)] \
        or list(jurisdictions)
    used = sorted(used, key=rank)
    hearings = sorted(hearings, key=lambda h: (
        rank(h["jurisdiction"]), h["scheduled_iso"] or "9999", h["id"]))
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


# --------------------------------------------------------------------------- #
# RSS feed
# --------------------------------------------------------------------------- #
# Public URL where the dashboard (and this feed) live, so readers resolve links.
DASHBOARD_URL = "https://chihacknight.github.io/govbot/dashboard/"
FEED_URL = DASHBOARD_URL + "hearings.xml"


def _pretty_when(h):
    """Human 'Aug 4, 2026, 10:00 AM' from scheduled_iso, else the raw display."""
    s = h.get("scheduled_iso") or ""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})", s)
    if not m:
        return h.get("scheduled_display") or "Time TBA"
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
              "Oct", "Nov", "Dec"]
    hh = int(m.group(4))
    ampm = "PM" if hh >= 12 else "AM"
    hh = (hh + 11) % 12 + 1
    return (f"{months[int(m.group(2)) - 1]} {int(m.group(3))}, {m.group(1)}, "
            f"{hh}:{m.group(5)} {ampm}")


def _feed_prelude(doc):
    """Shared (built_822, names) derived from a hearings doc for feed rendering."""
    from email.utils import format_datetime
    built = datetime.strptime(doc["generated_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc)
    names = {j["code"]: j["name"] for j in doc.get("jurisdictions", [])}
    return format_datetime(built), names


def _add_item(ch, h, state, built_822):
    """Append one <item> for hearing `h` to channel `ch`."""
    bills = ", ".join(b["id"] for b in h.get("bills", []))
    status = " [CANCELED]" if h.get("status") == "canceled" else ""
    title = f"{state} · {h.get('committee', 'Committee')} — {_pretty_when(h)}{status}"

    parts = []
    if bills:
        parts.append(f"Bills: {bills}.")
    if h.get("location"):
        parts.append(h["location"] + ".")
    if h.get("status") != "canceled" and h.get("witness_slip_url"):
        parts.append(f"Participate: {h['witness_slip_url']}")

    item = ET.SubElement(ch, "item")
    ET.SubElement(item, "title").text = title
    ET.SubElement(item, "link").text = h.get("details_url") or DASHBOARD_URL
    ET.SubElement(item, "description").text = " ".join(parts) or title
    ET.SubElement(item, "category").text = state
    ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = h["id"]
    ET.SubElement(item, "pubDate").text = built_822


def _feed_xml(title, description, self_url, hearings, names, built_822):
    """Render an RSS 2.0 channel (one <item> per hearing) as a string."""
    rss = ET.Element("rss", {"version": "2.0",
                             "xmlns:atom": "http://www.w3.org/2005/Atom"})
    ch = ET.SubElement(rss, "channel")
    ET.SubElement(ch, "title").text = title
    ET.SubElement(ch, "link").text = DASHBOARD_URL
    ET.SubElement(ch, "description").text = description
    ET.SubElement(ch, "language").text = "en-us"
    ET.SubElement(ch, "lastBuildDate").text = built_822
    ET.SubElement(ch, "atom:link", {"href": self_url, "rel": "self",
                                    "type": "application/rss+xml"})
    for h in hearings:
        state = names.get(h["jurisdiction"], h["jurisdiction"].upper())
        _add_item(ch, h, state, built_822)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            + ET.tostring(rss, encoding="unicode") + "\n")


def to_rss(doc):
    """Render the whole hearings document as an RSS 2.0 feed (one item per
    hearing). Pure/deterministic given `doc`. Feed readers subscribe to this to
    get every upcoming committee hearing without visiting the dashboard.
    """
    built_822, names = _feed_prelude(doc)
    return _feed_xml(
        "govbot — Upcoming committee hearings & witness slips",
        "Upcoming legislative committee hearings where the public can weigh in "
        "(Illinois & Washington), refreshed twice daily by govbot.",
        FEED_URL, doc.get("hearings", []), names, built_822)


def bill_feed_name(jurisdiction, bill_id):
    """Deterministic per-bill feed filename, e.g. ('il', 'HB 1643') -> 'il-HB1643.xml'.
    The hearings page recomputes this exact name to link each bill to its feed,
    so both sides must normalize identically (see _norm_bill_id)."""
    return f"{jurisdiction}-{_norm_bill_id(bill_id)}.xml"


def bill_feeds(doc):
    """One RSS feed per distinct bill that appears in any hearing.

    Returns {filename: xml_string}. Each feed lists just the hearings that
    reference that bill, so a reader can follow a single bill instead of the
    whole calendar. Pure/deterministic given `doc`.
    """
    built_822, names = _feed_prelude(doc)
    # Group hearings by (jurisdiction, normalized id); keep the first display id
    # seen so the human-facing title reads naturally.
    groups = {}
    for h in doc.get("hearings", []):
        for b in h.get("bills", []):
            key = (h["jurisdiction"], _norm_bill_id(b["id"]))
            g = groups.get(key)
            if g is None:
                g = groups[key] = {"jur": h["jurisdiction"], "id": b["id"], "hearings": []}
            g["hearings"].append(h)

    feeds = {}
    for g in groups.values():
        state = names.get(g["jur"], g["jur"].upper())
        disp = g["id"]
        fname = bill_feed_name(g["jur"], disp)
        self_url = DASHBOARD_URL + "hearings/" + fname
        feeds[fname] = _feed_xml(
            f"govbot — {state} {disp}: upcoming committee hearings",
            f"Upcoming committee hearings featuring {state} {disp}, "
            f"refreshed twice daily by govbot.",
            self_url, g["hearings"], names, built_822)
    return feeds


def jurisdiction_feed_name(code):
    """Per-state feed filename, e.g. 'wa' -> 'wa.xml'. No hyphen, so it never
    collides with a per-bill '<jur>-<ID>.xml' or a per-hearing 'hearing-*.xml'."""
    return f"{code}.xml"


def jurisdiction_feeds(doc):
    """One RSS feed per jurisdiction (all of that state's upcoming hearings), so
    a state whose hearings list no individual bills (e.g. WA committee meetings)
    is still followable. Returns {filename: xml_string}."""
    built_822, names = _feed_prelude(doc)
    by_code = {}
    for h in doc.get("hearings", []):
        by_code.setdefault(h["jurisdiction"], []).append(h)
    feeds = {}
    for code, hearings in by_code.items():
        state = names.get(code, code.upper())
        fname = jurisdiction_feed_name(code)
        feeds[fname] = _feed_xml(
            f"govbot — {state}: upcoming committee hearings",
            f"All upcoming {state} legislative committee hearings, "
            f"refreshed twice daily by govbot.",
            DASHBOARD_URL + "hearings/" + fname, hearings, names, built_822)
    return feeds


def hearing_feed_name(hearing_id):
    """Per-hearing feed filename, e.g. 'wa-other-33551' -> 'hearing-wa-other-33551.xml'.
    The 'hearing-' prefix keeps it distinct from per-bill/per-state names; other
    characters are sanitized to stay filesystem/URL safe."""
    safe = re.sub(r"[^A-Za-z0-9._-]", "-", hearing_id or "")
    return f"hearing-{safe}.xml"


def hearing_feeds(doc):
    """One RSS feed per individual hearing (a single item that updates if the
    hearing is rescheduled or canceled), so any committee meeting is followable
    on its own. Returns {filename: xml_string}."""
    built_822, names = _feed_prelude(doc)
    feeds = {}
    for h in doc.get("hearings", []):
        state = names.get(h["jurisdiction"], h["jurisdiction"].upper())
        fname = hearing_feed_name(h["id"])
        feeds[fname] = _feed_xml(
            f"govbot — {state} {h.get('committee', 'committee')}: {_pretty_when(h)}",
            f"A single {state} committee hearing tracked by govbot; the item "
            f"updates if it is rescheduled or canceled.",
            DASHBOARD_URL + "hearings/" + fname, [h], names, built_822)
    return feeds


def all_feeds(doc):
    """Every per-entity feed to publish alongside the whole-calendar hearings.xml:
    one per bill, one per jurisdiction, and one per hearing."""
    feeds = {}
    feeds.update(bill_feeds(doc))
    feeds.update(jurisdiction_feeds(doc))
    feeds.update(hearing_feeds(doc))
    return feeds


# --------------------------------------------------------------------------- #
# govbot bill enrichment
# --------------------------------------------------------------------------- #
def _norm_bill_id(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def enrich_from_govbot(hearings, data_path):
    """Cross-reference each hearing's bills against govbot's own bill dataset
    (docs/src/dashboard/data.json) and attach the govbot title + topic tags where
    the bill is tracked. IL and WA are both scraped by govbot, so their hearing
    bills resolve to real govbot records. Fail-soft: a missing/partial data.json
    (e.g. the offline sample) simply means no enrichment."""
    try:
        data = json.loads(Path(data_path).read_text())
    except (OSError, json.JSONDecodeError):
        return 0
    index = {}
    for b in data.get("bills", []):
        st = (b.get("state") or "").lower()
        index[(st, _norm_bill_id(b.get("id")))] = b
    matched = 0
    for h in hearings:
        for bill in h.get("bills", []):
            rec = index.get((h["jurisdiction"], _norm_bill_id(bill["id"])))
            if not rec:
                continue
            title = (rec.get("title") or "").strip()
            if title:
                bill["govbot_title"] = title
            tags = [t for t in (rec.get("tags") or []) if t]
            if tags:
                bill["govbot_tags"] = tags
            if title or tags:
                matched += 1
    return matched


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--jurisdictions", default="il,wa,ma,us",
                    help="Comma-separated codes to scrape live (default: il,wa,ma,us; "
                         "'us' = federal comment periods from Regulations.gov)")
    ap.add_argument("--from-fixtures", default=None,
                    help="Build offline from a raw fixtures dir (no network)")
    ap.add_argument("--slips", action="store_true",
                    help="Attempt best-effort witness-slip count enrichment "
                         "(opt-in; the IL totals endpoint is currently unreliable)")
    ap.add_argument("--now", default=None,
                    help="Override generated_at (ISO, e.g. 2026-08-28T00:00:00Z) "
                         "— used for deterministic snapshots")
    ap.add_argument("--output", "-o", default="-", help="Output path (default: stdout)")
    ap.add_argument("--rss", default=None,
                    help="Also write an RSS 2.0 feed of the hearings to this path")
    ap.add_argument("--rss-feeds-dir", default=None,
                    help="Also write granular RSS 2.0 feeds into this directory: one "
                         "per bill (il-HB1643.xml), one per jurisdiction (wa.xml), and "
                         "one per hearing (hearing-<id>.xml), so readers can follow a "
                         "single bill, a whole state, or one hearing instead of the "
                         "entire calendar")
    ap.add_argument("--dashboard-data", default="docs/src/dashboard/data.json",
                    help="govbot bill dataset (data.json) used to enrich hearing "
                         "bills with their govbot title + topic tags")
    args = ap.parse_args()

    now = (datetime.strptime(args.now, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
           if args.now else datetime.now(timezone.utc))

    if args.from_fixtures:
        hearings = build_from_fixtures(args.from_fixtures)
        source = "fixtures (offline snapshot)"
        codes = ["us", "il", "wa", "ma"]
    else:
        codes = [c.strip().lower() for c in args.jurisdictions.split(",") if c.strip()]
        begin = now - timedelta(days=WINDOW_BACK_DAYS)
        end = now + timedelta(days=WINDOW_FWD_DAYS)
        hearings = []
        if "il" in codes:
            hearings.extend(fetch_il(begin, end, with_slips=args.slips))
        if "wa" in codes:
            hearings.extend(fetch_wa(begin, end))
        if "ma" in codes:
            hearings.extend(fetch_ma(begin, end))
        resolve_wa_committee_urls(hearings)  # WA committee pages from the index
        verify_committee_urls(hearings)      # drop any link that 404s / soft-404s
        if "us" in codes:                    # federal comment periods (Regulations.gov)
            hearings.extend(fetch_us())
        source = "ilga.gov + leg.wa.gov + malegislature.gov + regulations.gov (govbot scrape-hearings)"

    if args.dashboard_data:
        n = enrich_from_govbot(hearings, args.dashboard_data)
        if n:
            print(f"enriched {n} hearing bills from govbot data", file=sys.stderr)

    doc = assemble(hearings, codes, source, now)
    text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    if args.output == "-":
        sys.stdout.write(text)
    else:
        Path(args.output).write_text(text)
        print(f"wrote {len(doc['hearings'])} hearings "
              f"({', '.join(f'{k}:{v}' for k, v in doc['counts'].items()) or 'none'}) "
              f"to {args.output}", file=sys.stderr)

    if args.rss:
        Path(args.rss).write_text(to_rss(doc))
        print(f"wrote RSS feed to {args.rss}", file=sys.stderr)

    if args.rss_feeds_dir:
        outdir = Path(args.rss_feeds_dir)
        outdir.mkdir(parents=True, exist_ok=True)
        feeds = all_feeds(doc)
        for fname, xml in feeds.items():
            (outdir / fname).write_text(xml)
        print(f"wrote {len(feeds)} granular RSS feeds to {outdir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
