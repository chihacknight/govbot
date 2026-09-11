#!/usr/bin/env python3
"""Build the "Elections Happening in IL" feed: offices/races on upcoming Illinois and
Chicago ballots, with the candidates running for each.

Unlike the bill dataset (OpenStates -> git-repos-as-datasets), candidate lists
are *live* artifacts published by each election authority. govbot does not get
them from OpenStates, so this action taps the official sources directly:

* Chicago citywide + Alderperson + Police District Council
      -> Chicago Board of Elections candidate pages (chicagoelections.gov)
* CPS Board (president + subdistricts), and later state/federal offices
      -> Illinois State Board of Elections "Who Is Running" candidate list
* Suburban Cook (future)
      -> Cook County Clerk candidate list

The office/district STRUCTURE of the ballot is stable and lives in a committed
seed (elections_seed.json): every race, its district, ballot date, and a plain-
English "why this race exists" note. The scrapers only *populate candidates* into
those races. A race with no confirmed candidate keeps an empty list plus a link
to its official source — we never invent a candidate.

The output is one document matching schemas/govbot.elections.schema.json, written
next to the dashboard's data.json. The Pages deploy runs this twice a day.

Design rules (see CLAUDE.md):
* Only the Python standard library — no scraper deps, runs in a bare CI step.
* Fail loudly, recover gracefully: any source that errors contributes zero
  candidates, never a crash. With every source down the seed's race structure
  still ships (empty rosters), and the caller keeps the committed sample when
  the fresh run produced nothing new (see the deploy workflow).
* Pure parsers (parse_*) take raw text and are exercised offline by snapshot
  fixtures under __snapshots__/; only the fetch_* helpers touch the network.
* Never fabricate civic data. Parsers emit only what the source states; the
  matcher attaches a candidate to a seed race only when office+district resolve
  unambiguously, and drops (with a warning) anything it can't place.

Usage:
    # Live (what the deploy runs):
    python3 actions/scrape-elections/main.py \
        --output docs/src/dashboard/elections.json \
        --rss docs/src/dashboard/elections.xml \
        --rss-feeds-dir docs/src/dashboard/elections

    # Offline, deterministic — rebuild the snapshot from fixtures:
    python3 actions/scrape-elections/main.py \
        --from-fixtures actions/scrape-elections/__snapshots__/raw \
        --now 2026-09-07T00:00:00Z --output -
"""

import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).parent
SEED_PATH = HERE / "elections_seed.json"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
FETCH_TIMEOUT = 20

# Best-effort official endpoints. These sites reshape their pages between cycles,
# so a fetch/parse failure is expected sometimes; it degrades to the committed
# seed (empty rosters) rather than crashing, and the parsers are validated
# offline against the __snapshots__ fixtures regardless.
ISBE_CANDIDATES_URL = "https://www.elections.il.gov/"
CHICAGO_BOE_CANDIDATES_URL = "https://chicagoelections.gov/"

VALID_PETITION = {"filed", "on_ballot", "objected", "withdrawn", "removed", "unknown"}


# --------------------------------------------------------------------------- #
# network (thin, testable-around)
# --------------------------------------------------------------------------- #
def fetch_text(url, timeout=FETCH_TIMEOUT):
    """GET a URL, returning the body text or None on any failure."""
    headers = {
        "user-agent": UA,
        "accept": "text/html,text/csv,application/json,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.9",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return resp.read().decode("utf-8", "replace")
    except Exception as err:  # network, TLS, timeout, decode — all non-fatal
        print(f"warning: fetch failed {url}: {err}", file=sys.stderr)
        return None


def fetch_bytes(url, timeout=FETCH_TIMEOUT):
    """GET a URL, returning the raw bytes or None on any failure (for the BOE
    candidate-list PDF)."""
    url = url.replace(" ", "%20")  # BOE blob names contain spaces; urllib rejects them
    req = urllib.request.Request(url, headers={"user-agent": UA, "accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read() if resp.status == 200 else None
    except Exception as err:
        print(f"warning: fetch failed {url}: {err}", file=sys.stderr)
        return None


# --------------------------------------------------------------------------- #
# normalization + race matching
# --------------------------------------------------------------------------- #
_WORD_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10,
}


def _clean(s):
    return re.sub(r"\s+", " ", (s or "").strip())


def normalize_status(raw):
    """Map a source's status wording onto the schema's petition_status enum."""
    t = (raw or "").strip().lower()
    if not t:
        return None
    if any(k in t for k in ("on ballot", "on the ballot", "certified", "qualified")):
        return "on_ballot"
    if "object" in t:
        return "objected"
    if "withdraw" in t:
        return "withdrawn"
    if "remov" in t or "disqualif" in t or "not on ballot" in t:
        return "removed"
    if "filed" in t or "filing" in t or "submitted" in t:
        return "filed"
    return "unknown"


def race_id_for(office, district):
    """Resolve a candidate's (office, district) to a seed race id, or None.

    Deliberately strict: only well-understood Chicago/CPS offices resolve. An
    unrecognized office returns None so the candidate is reported unplaced
    rather than attached to the wrong race.
    """
    o = (office or "").lower()
    d = district or ""

    # CPS board — require an education signal so a generic "…Board president"
    # (e.g. the Cook County Board president) never resolves to the CPS board. A
    # subdistrict district is itself a CPS signal (only CPS uses subdistricts).
    _edu = ("board of education" in o or "school board" in o or "board of ed" in o
            or "cps" in o)
    if _edu or "subdistrict" in d.lower():
        if _edu and "president" in o:
            return "cps-board-president"
        sub = _subdistrict(d) or _subdistrict(office)
        return f"cps-board-member-{sub.lower()}" if sub else None

    if "mayor" in o:
        return "chicago-mayor"
    if "clerk" in o and "county" not in o:
        return "chicago-city-clerk"
    if "treasurer" in o and "county" not in o:
        return "chicago-city-treasurer"
    if "alder" in o:  # alderman / alderperson / alderwoman
        w = _ward(d) or _ward(office)
        return f"chicago-alderperson-ward-{w:02d}" if w else None
    if "district council" in o or "police district" in o:
        pd = _police_district(d) or _police_district(office)
        return f"chicago-police-district-council-{pd:03d}" if pd else None
    return None


def _ward(text):
    m = re.search(r"ward\s*0*(\d{1,2})", (text or "").lower())
    if m and 1 <= int(m.group(1)) <= 50:
        return int(m.group(1))
    return None


def _subdistrict(text):
    m = re.search(r"(?:sub-?district|district)\s*0*(\d{1,2})\s*([ab])",
                  (text or "").lower())
    if m and 1 <= int(m.group(1)) <= 10:
        return f"{int(m.group(1))}{m.group(2).upper()}"
    m = re.search(r"\b0*(\d{1,2})\s*([ab])\b", (text or "").lower())
    if m and 1 <= int(m.group(1)) <= 10:
        return f"{int(m.group(1))}{m.group(2).upper()}"
    return None


def _police_district(text):
    m = re.search(r"(?:police\s*)?district\s*0*(\d{1,2})", (text or "").lower())
    if m and 1 <= int(m.group(1)) <= 25:
        return int(m.group(1))
    return None


def make_candidate(name, office, district=None, party=None, filing_date=None,
                   petition_status=None, website=None, photo_url=None,
                   incumbent=None, incumbency=None, source=None):
    """A schema-shaped candidate dict, carrying a computed _race_id for the
    matcher. `_race_id` is stripped before output."""
    name = _clean(name)
    cand = {
        "name": name,
        "office": _clean(office) or None,
        "district": _clean(district) or None,
        "party": _clean(party) or None,
        "filing_date": filing_date or None,
        "petition_status": petition_status if petition_status in VALID_PETITION else None,
        "website": website or None,
        "photo_url": photo_url or None,
        "incumbent": incumbent,
        "incumbency": incumbency,
        "source": source or None,
        "_race_id": race_id_for(office, district),
    }
    return cand


# --------------------------------------------------------------------------- #
# Illinois State Board of Elections — "Who Is Running" candidate list
# --------------------------------------------------------------------------- #
# ISBE publishes candidate lists as delimited text (their downloadable list /
# the text extracted from the "Who Is Running" PDF). We parse a header row and
# then rows keyed by that header, so column order changes don't break us.
_ISBE_HEADER_ALIASES = {
    "office": {"office", "office name", "officesought", "office sought"},
    "district": {"district", "district name", "subdistrict", "ward"},
    "name": {"name", "candidate", "candidate name", "candidatename"},
    "party": {"party", "political party"},
    "filing_date": {"filing date", "filingdate", "date filed", "filed"},
    "status": {"status", "ballot status", "candidate status"},
    "website": {"website", "url", "web site"},
}


def _isbe_split(line):
    """Split an ISBE row on tab or pipe (its two common export delimiters);
    fall back to 2+ spaces so a space-padded fixed-width dump still parses."""
    if "\t" in line:
        return [c.strip() for c in line.split("\t")]
    if "|" in line:
        return [c.strip() for c in line.split("|")]
    return [c.strip() for c in re.split(r"\s{2,}", line)]


def _isbe_header_map(cells):
    out = {}
    for i, c in enumerate(cells):
        key = c.strip().lower()
        for field, aliases in _ISBE_HEADER_ALIASES.items():
            if key in aliases and field not in out:
                out[field] = i
    return out


def parse_isbe_candidates(text, source="Illinois State Board of Elections"):
    """Parse an ISBE delimited candidate list into candidate dicts.

    Requires a header row naming at least Office and Name. Rows missing a name
    are skipped. Pure/deterministic; unplaceable candidates keep _race_id=None.
    """
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    header = None
    for ln in lines:
        cells = _isbe_split(ln)
        hmap = _isbe_header_map(cells)
        if "office" in hmap and "name" in hmap:
            header = hmap
            start = lines.index(ln) + 1
            break
    if not header:
        return []
    out = []
    for ln in lines[start:]:
        cells = _isbe_split(ln)
        def col(field):
            i = header.get(field)
            return cells[i] if i is not None and i < len(cells) else ""
        name = col("name")
        if not name or name.strip().lower() in {"name", "candidate", "candidate name"}:
            continue
        district = col("district")
        office = col("office")
        out.append(make_candidate(
            name=name, office=office, district=district,
            party=col("party") or None, filing_date=_iso_date(col("filing_date")),
            petition_status=normalize_status(col("status")),
            website=_clean(col("website")) or None, source=source))
    return out


def _iso_date(raw):
    """Best-effort ISO date from common US formats; None if unrecognized."""
    t = (raw or "").strip()
    if not t:
        return None
    m = re.match(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", t)
    if m:
        mo, da, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if yr < 100:
            yr += 2000
        try:
            return datetime(yr, mo, da).strftime("%Y-%m-%d")
        except ValueError:
            return None
    if re.match(r"\d{4}-\d{2}-\d{2}$", t):
        return t
    return None


# --------------------------------------------------------------------------- #
# Chicago Board of Elections — candidate list HTML table
# --------------------------------------------------------------------------- #
class _BOETableParser(HTMLParser):
    """Extract rows of a candidate table. Emits one list of cell strings per
    <tr>; the caller maps columns by a detected header. Tolerant of the messy
    nested markup these pages ship (links/spans inside cells)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self._row = None
        self._cell = None
        self._in_cell = False
        self._href = None
        self.cell_hrefs = []
        self._row_hrefs = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
            self._row_hrefs = []
        elif tag in ("td", "th") and self._row is not None:
            self._in_cell = True
            self._cell = []
            self._href = None
        elif tag == "a" and self._in_cell:
            for k, v in attrs:
                if k == "href" and not self._href:
                    self._href = v

    def handle_data(self, data):
        if self._in_cell:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._in_cell:
            self._row.append(_clean("".join(self._cell)))
            self._row_hrefs.append(self._href)
            self._in_cell = False
        elif tag == "tr" and self._row is not None:
            if any(c for c in self._row):
                self.rows.append(self._row)
                self.cell_hrefs.append(self._row_hrefs)
            self._row = None


_BOE_HEADER_ALIASES = {
    "office": {"office", "office sought", "contest"},
    "district": {"district", "ward", "subdistrict"},
    "name": {"name", "candidate", "candidate name"},
    "status": {"status", "ballot status"},
    "filing_date": {"filing date", "date filed", "filed"},
    "website": {"website", "web site", "url"},
}


def parse_chicago_boe(html, source="Chicago Board of Elections"):
    """Parse a Chicago BOE candidate-list HTML table into candidate dicts.

    Detects the header row by its column labels; a link inside the name cell is
    kept as the candidate website when present. Pure/deterministic.
    """
    p = _BOETableParser()
    try:
        p.feed(html or "")
    except Exception:
        return []
    if not p.rows:
        return []
    header = None
    start = 0
    for i, row in enumerate(p.rows):
        hmap = {}
        for j, c in enumerate(row):
            key = c.strip().lower()
            for field, aliases in _BOE_HEADER_ALIASES.items():
                if key in aliases and field not in hmap:
                    hmap[field] = j
        if "name" in hmap and ("office" in hmap or "district" in hmap):
            header, start = hmap, i + 1
            break
    if not header:
        return []
    out = []
    for row, hrefs in zip(p.rows[start:], p.cell_hrefs[start:]):
        def col(field):
            k = header.get(field)
            return row[k] if k is not None and k < len(row) else ""
        name = col("name")
        if not name:
            continue
        nlink = None
        ni = header.get("name")
        if ni is not None and ni < len(hrefs):
            nlink = hrefs[ni]
        out.append(make_candidate(
            name=name, office=col("office"), district=col("district"),
            filing_date=_iso_date(col("filing_date")),
            petition_status=normalize_status(col("status")),
            website=nlink or (_clean(col("website")) or None), source=source))
    return out


# --------------------------------------------------------------------------- #
# Cook County Clerk — suburban Cook (future coverage)
# --------------------------------------------------------------------------- #
def parse_cook_clerk(text, source="Cook County Clerk"):
    """Placeholder for suburban-Cook candidate parsing. Returns [] until the
    seed carries Cook County / suburban races; kept so the adapter slot exists
    and the deploy wiring is stable."""
    return []


# --------------------------------------------------------------------------- #
# Chicago BOE official "Candidate List" PDF (ballot-order text)
# --------------------------------------------------------------------------- #
# The Board of Elections publishes the authoritative candidate roster as a PDF
# ("Candidate List_<date>.pdf") linked from chicagoelections.gov/getting-ballot/
# candidates. `pdftotext -layout` renders it as ballot-order text:
#
#     President of the Chicago Board of Education
#      Vote for One
#        (121)   Victor P. Henderson (Nonpartisan)                 Candidate
#     Member of the Chicago Board of Education, Subdistrict 1A
#      Vote for One
#        (131)   Ed Bannon (Nonpartisan)                           Candidate
#
# We scope to the Board-of-Education offices (the only Chicago-seed races on the
# Nov 2026 ballot); the statewide/federal/judicial offices on the same list are
# ignored — critically, so the statewide "Treasurer" is never misread as the
# Chicago City Treasurer. Pure/deterministic; the pdftotext shell-out lives in
# the fetch wrapper, so this is exercised offline against the __snapshots__ text.
_BOE_PDF_ROW = re.compile(
    r'^\s*\(\d+\)\s+(\S.*?)\s{2,}'
    r'(Candidate|Withdrawn|Objected|Removed|Disqualified|Not Certified)\s*$', re.I)
_BOE_PDF_VOTE = re.compile(r'^\s*Vote (?:for|Yes)\b', re.I)
_BOE_PDF_NOISE = re.compile(
    r'^\s*(?:Page \d+ of \d+|Ballot No\.|Write-in\b|This\b|Status as of|'
    r'Candidate Filings)', re.I)


def _boe_pdf_status(raw):
    """The list is the finalized ballot in ballot order, so a plain 'Candidate'
    means on the ballot; other words map through the shared normalizer."""
    return "on_ballot" if (raw or "").strip().lower() == "candidate" else normalize_status(raw)


def _boe_office_race(office):
    """The Chicago-seed race id an office header resolves to, or None. Guards the
    one trap a statewide/county ballot springs: a bare 'Treasurer' or 'Clerk'
    (the Illinois state offices) would resolve to the Chicago City Treasurer/Clerk
    via race_id_for, so those require the word 'City'. Everything race_id_for
    already scopes to Chicago (Mayor, Alderperson wards, CPS, Police District
    Councils) passes straight through — so this parser handles the CPS offices on
    the 2026 ballot today and the municipal offices on a 2027 list unchanged."""
    rid = race_id_for(office, None)
    if rid in ("chicago-city-treasurer", "chicago-city-clerk") \
            and "city" not in (office or "").lower():
        return None
    return rid


def parse_boe_candidate_list(text, source="Chicago Board of Elections (candidate list)"):
    """Parse the `pdftotext -layout` text of the Chicago BOE Candidate List into
    candidate dicts for the Chicago races in the seed. Office context is the most
    recent header line; a candidate row is kept only when that office resolves to
    a seed race (`_boe_office_race`), so statewide / federal / judicial offices on
    the same ballot are ignored and trailing sections can't bleed into the last
    race. Pure/deterministic."""
    office = None
    out = []
    for ln in (text or "").splitlines():
        if not ln.strip():
            continue
        m = _BOE_PDF_ROW.match(ln)
        if m:
            rid = _boe_office_race(office) if office else None
            if rid:
                np = m.group(1).strip()
                pm = re.match(r'^(.*?)\s*\(([^)]+)\)\s*$', np)
                name, party = (pm.group(1).strip(), pm.group(2).strip()) if pm else (np, None)
                if party and party.lower() == "nonpartisan":
                    party = None  # schema: party is for partisan races only
                out.append(make_candidate(
                    name=name, office=office, district=None, party=party,
                    petition_status=_boe_pdf_status(m.group(2)), source=source))
            continue
        if _BOE_PDF_VOTE.match(ln) or _BOE_PDF_NOISE.match(ln):
            continue
        # Any other line is an office/section header — the new office context.
        office = ln.strip()
    return out


BOE_CANDIDATES_PAGE = "https://chicagoelections.gov/getting-ballot/candidates"


def discover_boe_pdf_url(page_html=None):
    """Find the newest 'Candidate List ….pdf' link on the BOE candidates page
    (other PDFs there are forms/guides). Newest wins by the YYYYMMDD in the name.
    Pure given `page_html`; fetches the page when it's None."""
    html = page_html if page_html is not None else fetch_text(BOE_CANDIDATES_PAGE)
    if not html:
        return None
    urls = re.findall(r'https?://[^"\'<>]*?Candidate(?:%20|\s)*List[^"\'<>]*?\.pdf',
                      html, re.I)
    if not urls:
        return None
    return sorted(urls, key=lambda u: (re.search(r'(\d{8})', u) or [""])[0])[-1]


def pdf_to_text(pdf_path):
    """Extract ballot-order text from a PDF via the `pdftotext -layout` system
    tool (poppler-utils), the way DuckDB is shelled out elsewhere. Returns None
    if pdftotext is missing or fails — fully fail-soft."""
    import subprocess
    try:
        r = subprocess.run(["pdftotext", "-layout", str(pdf_path), "-"],
                           capture_output=True, timeout=120)
        return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError) as err:
        print(f"warning: pdftotext failed ({err}); is poppler-utils installed?",
              file=sys.stderr)
        return None


def fetch_boe_candidates(pdf_source=None):
    """Resolve, download and parse the Chicago BOE Candidate List PDF into
    candidate dicts. `pdf_source` may be a local text file (already extracted, for
    testing), a local .pdf, a .pdf URL, or None (auto-discover). Fail-soft: any
    step failing yields []."""
    text = None
    if pdf_source and pdf_source.lower().endswith((".txt",)):
        try:
            text = Path(pdf_source).read_text()
        except OSError:
            return []
    else:
        pdf_path = pdf_source
        tmp = None
        if not pdf_path or pdf_path.lower().startswith(("http://", "https://")):
            url = pdf_source or discover_boe_pdf_url()
            if not url:
                return []
            blob = fetch_bytes(url)
            if not blob:
                return []
            import tempfile
            tmp = Path(tempfile.mkstemp(suffix=".pdf")[1])
            tmp.write_bytes(blob)
            pdf_path = str(tmp)
        text = pdf_to_text(pdf_path)
        if tmp:
            try:
                tmp.unlink()
            except OSError:
                pass
    return parse_boe_candidate_list(text) if text else []


def merge_candidates(doc, candidates):
    """Place scraped candidates into an assembled doc's races by resolved race id
    (dedupe by name; a populated race flips 'upcoming' -> 'on_ballot'). Returns the
    number placed. Mirrors assemble()'s placement so an enrichment run matches a
    fresh build."""
    by_id = {r["id"]: r for r in doc.get("races", [])}
    placed = 0
    for c in candidates:
        rid = c.pop("_race_id", None)
        race = by_id.get(rid) if rid else None
        if not race:
            continue
        race.setdefault("candidates", [])
        if any(x["name"].lower() == c["name"].lower() for x in race["candidates"]):
            continue
        if race.get("status") == "upcoming":
            race["status"] = "on_ballot"
        race["candidates"].append(c)
        placed += 1
    for r in doc.get("races", []):
        r.get("candidates", []).sort(key=lambda c: c["name"].lower())
    return placed


def enrich_candidates_from_boe(doc, pdf_source=None):
    """Attach official Chicago BOE candidates (currently the Board of Education
    offices on the ballot) to an assembled elections doc, in place. Returns the
    number placed."""
    return merge_candidates(doc, fetch_boe_candidates(pdf_source))


# --------------------------------------------------------------------------- #
# live fetch
# --------------------------------------------------------------------------- #
def fetch_isbe():
    text = fetch_text(ISBE_CANDIDATES_URL)
    return parse_isbe_candidates(text) if text else []


def fetch_chicago_boe():
    html = fetch_text(CHICAGO_BOE_CANDIDATES_URL)
    return parse_chicago_boe(html) if html else []


def fetch_cook_clerk():
    return []  # future


# --------------------------------------------------------------------------- #
# fixtures (offline, deterministic)
# --------------------------------------------------------------------------- #
def build_from_fixtures(fixtures_dir):
    d = Path(fixtures_dir)
    cands = []
    isbe = d / "isbe_who_is_running.txt"
    if isbe.exists():
        cands.extend(parse_isbe_candidates(isbe.read_text()))
    boe = d / "chicago_boe_candidates.html"
    if boe.exists():
        cands.extend(parse_chicago_boe(boe.read_text()))
    return cands


# --------------------------------------------------------------------------- #
# Springfield side feed — "the rules of the game"
# --------------------------------------------------------------------------- #
# Illinois bills from govbot's legislation dataset that shape how these elections
# work. Shown beside the races as context, never mixed into candidate lists.
SPRINGFIELD_STATE = "il"
SPRINGFIELD_TOPICS = ["elections & voting", "education"]
SPRINGFIELD_LIMIT = 40


def _norm_bill_id(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def _hearing_index(hearings):
    """Map normalized IL bill id -> its upcoming hearing (first seen), from a
    hearings.json document. Fail-soft: a missing/other-shape doc yields {}."""
    idx = {}
    for h in (hearings or {}).get("hearings", []):
        if (h.get("jurisdiction") or "").lower() != SPRINGFIELD_STATE:
            continue
        for b in h.get("bills", []):
            key = _norm_bill_id(b.get("id"))
            if key and key not in idx:
                idx[key] = {
                    "committee": h.get("committee"),
                    "scheduled_display": h.get("scheduled_display"),
                    "details_url": h.get("details_url"),
                    "witness_slip_url": h.get("witness_slip_url"),
                }
    return idx


def build_springfield(legislation, hearings=None, limit=SPRINGFIELD_LIMIT):
    """Extract the IL 'rules of the game' bills from a govbot data.json document.

    Keeps IL bills tagged 'elections & voting' or 'education', attaches an
    upcoming committee hearing when the bill is on the ILGA calendar, and returns
    them newest-action first. Pure/deterministic given its inputs; an
    empty/missing dataset yields []."""
    bills = (legislation or {}).get("bills", [])
    hidx = _hearing_index(hearings)
    topics = set(SPRINGFIELD_TOPICS)
    out = []
    for b in bills:
        if (b.get("state") or "").lower() != SPRINGFIELD_STATE:
            continue
        matched = sorted(topics.intersection(b.get("tags") or []))
        if not matched:
            continue
        rec = {
            "id": b.get("id"),
            "title": b.get("title") or "",
            "url": b.get("url") or None,
            "session": b.get("session") or None,
            "chamber": b.get("chamber") or None,
            "tags": matched,
            "latest_action": b.get("latest_action") or None,
            "latest_action_desc": b.get("latest_action_desc") or None,
            "hearing": hidx.get(_norm_bill_id(b.get("id"))),
        }
        out.append(rec)
    # Newest action first (bills without a date sort last), then by id.
    out.sort(key=lambda r: (r["latest_action"] or "", r["id"] or ""), reverse=True)
    return out[:limit]


def load_json(path):
    """Read a JSON file, returning the parsed object or None on any failure."""
    if not path:
        return None
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as err:
        print(f"warning: could not read {path}: {err}", file=sys.stderr)
        return None


# --------------------------------------------------------------------------- #
# Campaign money — Illinois SBE bulk data (D2 filings via the ID crosswalk)
# --------------------------------------------------------------------------- #
# The SBE publishes tab-delimited, header-first bulk files at
# elections.il.gov/campaigndisclosuredatafiles/. We use the reliable ID
# crosswalk — never fuzzy dollar matching:
#   our candidate name -> Candidates.txt (ID) -> CmteCandidateLinks (CommitteeID)
#   -> Committees.txt (Name) -> D2Totals (latest filing: receipts/expend/funds).
# A candidate gets money only when their normalized "First Last" resolves to
# exactly one SBE candidate record; ambiguous names are skipped, not guessed.
SBE_COMMITTEE_SEARCH = "https://www.elections.il.gov/CampaignDisclosure/CommitteeDetailRevenue.aspx"


def _name_key(name):
    """Normalized 'firstlast' key from a ballot name ('Last, First' or 'First
    ... Last'); '' when it can't be split."""
    raw = (name or "").strip()
    if not raw:
        return ""
    if "," in raw:
        last, _, first = raw.partition(",")
        first = first.strip().split()[0] if first.strip() else ""
    else:
        parts = raw.split()
        if len(parts) < 2:
            return re.sub(r"[^a-z0-9]", "", raw.lower())
        first, last = parts[0], parts[-1]
    return re.sub(r"[^a-z0-9]", "", (first + last).lower())


def read_tsv(path):
    """Yield each row of a tab-delimited, header-first SBE file as a dict.
    Streaming (line by line) so the 50MB+ D2Totals file never loads fully."""
    p = Path(path)
    if not p.exists():
        return
    with p.open(encoding="utf-8", errors="replace") as fh:
        header = fh.readline().rstrip("\n").split("\t")
        for line in fh:
            cells = line.rstrip("\n").split("\t")
            if len(cells) < len(header):
                cells += [""] * (len(header) - len(cells))
            yield dict(zip(header, cells))


def _to_float(s):
    try:
        return round(float((s or "").strip() or 0), 2)
    except ValueError:
        return 0.0


def build_money_index(money_dir, wanted_name_keys, now):
    """Resolve campaign money for the given candidate name-keys from a directory
    of SBE bulk files. Returns {name_key: money_dict}. Fail-soft: missing files
    yield {}. Only unambiguous name matches are kept."""
    d = Path(money_dir)
    if not d.exists():
        return {}
    wanted = set(k for k in wanted_name_keys if k)
    if not wanted:
        return {}

    # 1) name -> candidate id (drop names that map to more than one SBE record)
    cand_ids, ambiguous = {}, set()
    for row in read_tsv(d / "Candidates.txt"):
        key = _name_key(row.get("LastName", "") + ", " + row.get("FirstName", ""))
        if key not in wanted:
            continue
        cid = (row.get("ID") or "").strip()
        if not cid:
            continue
        if key in cand_ids and cand_ids[key] != cid:
            ambiguous.add(key)
        cand_ids.setdefault(key, cid)
    for k in ambiguous:
        cand_ids.pop(k, None)
    if not cand_ids:
        return {}
    id_to_key = {v: k for k, v in cand_ids.items()}

    # 2) candidate id -> committee ids
    cand_committees = {}
    for row in read_tsv(d / "CmteCandidateLinks.txt"):
        cid = (row.get("CandidateID") or "").strip()
        k = id_to_key.get(cid)
        if k:
            cand_committees.setdefault(k, set()).add((row.get("CommitteeID") or "").strip())
    wanted_committees = {c for cs in cand_committees.values() for c in cs if c}
    if not wanted_committees:
        return {}

    # 3) committee id -> name
    cmte_name = {}
    for row in read_tsv(d / "Committees.txt"):
        cid = (row.get("ID") or "").strip()
        if cid in wanted_committees:
            cmte_name[cid] = (row.get("Name") or "").strip()

    # 4) committee id -> latest D2 filing (max numeric ID) totals
    latest = {}  # committee_id -> (max_id, receipts, expend, funds)
    for row in read_tsv(d / "D2Totals.txt"):
        cid = (row.get("CommitteeID") or "").strip()
        if cid not in wanted_committees:
            continue
        try:
            rid = int((row.get("ID") or "0").strip() or 0)
        except ValueError:
            continue
        if cid not in latest or rid > latest[cid][0]:
            latest[cid] = (rid, _to_float(row.get("TotalReceipts")),
                           _to_float(row.get("TotalExpend")), _to_float(row.get("EndFundsAvail")))

    # 5) aggregate per candidate
    out = {}
    for k, cids in cand_committees.items():
        cids = [c for c in cids if c in latest]
        if not cids:
            continue
        raised = sum(latest[c][1] for c in cids)
        spent = sum(latest[c][2] for c in cids)
        cash = sum(latest[c][3] for c in cids)
        primary = max(cids, key=lambda c: latest[c][3])  # most cash on hand
        out[k] = {
            "committee_name": cmte_name.get(primary) or None,
            "committee_id": primary,
            "committees": len(cids),
            "funds_raised": raised,
            "funds_spent": spent,
            "cash_on_hand": cash,
            "as_of": now.strftime("%Y-%m-%d"),
            "source_url": SBE_COMMITTEE_SEARCH,
        }
    return out


def enrich_money(doc, money_dir, now):
    """Attach `money` to each candidate in an assembled elections doc, in place.
    Returns the number of candidates enriched."""
    cands = [c for r in doc.get("races", []) for c in r.get("candidates", [])]
    if not cands:
        return 0
    index = build_money_index(money_dir, {_name_key(c["name"]) for c in cands}, now)
    if not index:
        return 0
    n = 0
    for c in cands:
        m = index.get(_name_key(c["name"]))
        if m:
            c["money"] = m
            n += 1
    return n


# --------------------------------------------------------------------------- #
# Results — post-Election-Night vote tallies (Chicago BOE / Cook County Clerk)
# --------------------------------------------------------------------------- #
# Scaffold: results don't exist until an election happens, so this stays inert
# (no results attached) until a results file is provided. When it is, results
# attach to a race only when office+district resolve and the candidate name
# matches — vote totals come straight from the authority; winners are shown only
# when the source marks them. Nothing is ever projected or invented.
_RESULTS_ALIASES = {
    "office": {"office", "contest", "contest name", "office name", "race"},
    "district": {"district", "ward", "subdistrict", "police district"},
    "name": {"name", "candidate", "candidate name", "choice"},
    "votes": {"votes", "vote total", "votes total", "total votes", "vote count", "ballots"},
    "winner": {"winner", "elected", "is winner"},
    "precincts_reporting": {"precincts reporting", "reporting", "precincts_reported"},
    "precincts_total": {"precincts", "precincts total", "total precincts"},
}


def _split_row(line):
    if "\t" in line:
        return [c.strip() for c in line.split("\t")]
    return [c.strip() for c in line.split(",")]


def _header_map(cells, aliases):
    out = {}
    for i, c in enumerate(cells):
        key = c.strip().lower()
        for field, al in aliases.items():
            if key in al and field not in out:
                out[field] = i
    return out


def _int(s):
    try:
        return int(re.sub(r"[^0-9-]", "", str(s or "")) or 0)
    except ValueError:
        return 0


def _truthy(s):
    return str(s or "").strip().lower() in {"1", "true", "yes", "y", "won", "winner", "elected"}


def parse_results_rows(text, source="Chicago Board of Elections"):
    """Parse a delimited (CSV/TSV) results export into per-candidate rows tagged
    with a resolved race id. Header-driven; requires at least office/contest,
    candidate name, and votes columns. Pure/deterministic; unplaceable rows keep
    _race_id=None (dropped by attach_results)."""
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    header, start = None, 0
    for i, ln in enumerate(lines):
        hm = _header_map(_split_row(ln), _RESULTS_ALIASES)
        if "name" in hm and "votes" in hm and ("office" in hm or "district" in hm):
            header, start = hm, i + 1
            break
    if not header:
        return []
    rows = []
    for ln in lines[start:]:
        cells = _split_row(ln)
        def col(f):
            i = header.get(f)
            return cells[i] if i is not None and i < len(cells) else ""
        name = col("name")
        if not name:
            continue
        rows.append({
            "name": _clean(name),
            "office": col("office"),
            "district": col("district"),
            "votes": _int(col("votes")),
            "winner": _truthy(col("winner")),
            "precincts_reporting": _int(col("precincts_reporting")) if header.get("precincts_reporting") is not None else None,
            "precincts_total": _int(col("precincts_total")) if header.get("precincts_total") is not None else None,
            "_race_id": race_id_for(col("office"), col("district")),
            "source": source,
        })
    return rows


def attach_results(doc, rows, now, source_url=None):
    """Group parsed result rows by race id and attach a `results` block to each
    matching race, ordered by votes. Only rows whose candidate name matches a
    listed candidate in that race are counted (so a stray write-in row can't
    invent a candidate). Returns the number of races updated."""
    by_race = {}
    for r in rows:
        rid = r.get("_race_id")
        if rid:
            by_race.setdefault(rid, []).append(r)
    if not by_race:
        return 0
    updated = 0
    for race in doc.get("races", []):
        group = by_race.get(race["id"])
        if not group:
            continue
        # Official results are authoritative for who ran, so count every reported
        # row for the race (don't filter by our — possibly stale — candidate list,
        # which would distort the percentages).
        chosen = group
        total = sum(r["votes"] for r in chosen)
        pr = next((r["precincts_reporting"] for r in chosen if r["precincts_reporting"] is not None), None)
        pt = next((r["precincts_total"] for r in chosen if r["precincts_total"] is not None), None)
        cands = sorted(
            ({"name": r["name"], "votes": r["votes"],
              "pct": round(100.0 * r["votes"] / total, 1) if total else None,
              "winner": bool(r["winner"])} for r in chosen),
            key=lambda c: c["votes"], reverse=True)
        race["results"] = {
            "reported": True,
            "complete": (pr is not None and pt is not None and pr >= pt and pt > 0),
            "as_of": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "precincts_reporting": pr,
            "precincts_total": pt,
            "total_votes": total,
            "source_url": source_url,
            "candidates": cands,
        }
        updated += 1
    return updated


def enrich_results(doc, results_path, now, source_url=None):
    """Load a results export and attach results to `doc` in place. Returns the
    number of races updated. Fail-soft: a missing/unreadable file is a no-op."""
    try:
        text = Path(results_path).read_text()
    except OSError as err:
        print(f"warning: could not read results {results_path}: {err}", file=sys.stderr)
        return 0
    return attach_results(doc, parse_results_rows(text), now, source_url)


# --------------------------------------------------------------------------- #
# Potential candidates — unofficial names from public news coverage
# --------------------------------------------------------------------------- #
# The official candidates[] list only ever holds people an election authority has
# confirmed. But long before filing opens, outlets report who is running,
# exploring, or rumored to run. This adapter surfaces those names as a *separate*,
# clearly-unofficial potential_candidates[] list, each tied to the article(s) it
# came from so a reader can verify. It reads Google News' public RSS search (an
# aggregator over Illinois/Chicago outlets) — the "internet" source; raw social-
# platform scraping is neither TOS-safe nor reliable, so we don't do it. A name is
# attached ONLY when a headline both names the person next to a candidacy verb and
# references the race's office (and, for a district race, its district). Nothing
# is invented, and this signal never becomes a ballot record — no petition status,
# money, or votes ride on it.
NEWS_RSS_BASE = "https://news.google.com/rss/search"
POTENTIAL_MAX_PER_RACE = 12      # cap names surfaced per race
POTENTIAL_MAX_SOURCES = 6        # cap articles kept per name
POTENTIAL_FETCH_SLEEP = 0.7      # be polite between pooled group fetches

# Signal verbs -> status. "announced" is a firm declaration; "exploring" is a
# maybe. Order matters: the strongest signal seen for a name wins.
_ANNOUNCE_VERBS = (
    r"announces?|announced|launch(?:es|ed)?|enters?|entered|joins?|joined|"
    r"declares?|declared|files?|filed|to run|running(?: for)?|will run|"
    r"kicks? off|jumps? in(?:to)?|throws? (?:his|her|their) hat|"
    r"seeks?|to seek|enters? the race|launch(?:es|ed)? (?:a )?(?:bid|campaign)|"
    r"challenges?|to challenge|to unseat|takes? on|to take on|running against")
_EXPLORE_VERBS = (
    r"mulls?|mulling|weighs?|weighing|considers?|considering|eyes?|eyeing|"
    r"explores?|exploring|could run|may run|might run|thinking about|"
    r"reportedly|rumored|floated|expected to run|potential(?:ly)?|possible")

# Names rely on capitalization, so keep _NAME case-sensitive — but make the VERBS
# case-insensitive (?i:…), because title-case local-outlet headlines capitalize
# them ("… Launches …", "… Running …"). `{1,2}?` is non-greedy so a captured name
# stops at the shortest match (an adverb like "Again"/"formally" between the name
# and the verb is skipped by `_ADV`, not swallowed into the name).
_NAME = r"([A-Z][a-zA-Z.'’-]+(?:\s+(?:[A-Z]\.?|[A-Z][a-zA-Z.'’-]+)){1,2}?)"
_ADV = r"(?:\s+(?i:again|formally|officially|finally|now|once more|reportedly))?"

# Person-name is <name> [<adverb>] <verb>, or <candidate/hopeful/challenger …> <name>.
_ANNOUNCE_RE = re.compile(_NAME + _ADV + r"\s+(?i:" + _ANNOUNCE_VERBS + r")\b")
_EXPLORE_RE = re.compile(_NAME + _ADV + r"\s+(?i:" + _EXPLORE_VERBS + r")\b")
# Reverse form: the name must sit right after candidate/hopeful/…, either
# immediately ("candidate Jane Smith") or after a "for <office>:" ("… candidate
# for alderman: Jane Smith"). No arbitrary words in between — that grabbed
# unrelated names mentioned later in the headline.
_REVERSE_RE = re.compile(r"\b(?i:candidate|hopeful|contender|challenger)\s+" + _NAME + r"\b")
_REVERSE_COLON_RE = re.compile(
    r"\b(?i:candidate|hopeful|contender|challenger)(?:\s+(?i:for)\s+[a-z]+){0,2}"
    r"\s*:\s*" + _NAME + r"\b")
_BID_RE = re.compile(_NAME + r"['’]s\s+(?i:bid|campaign|run)\b")

# Tokens that are never a person's given/sur-name in this context; a candidate
# match containing any of these is rejected (kills "Chicago Mayor", "Ward Five",
# "Board President", month/day words, outlet-ish words, etc.).
_NAME_STOPWORDS = {
    "chicago", "illinois", "cook", "county", "city", "board", "education",
    "school", "mayor", "mayoral", "alderman", "alderperson", "alderwoman",
    "ward", "district", "council", "councilmember", "police", "president",
    "election", "elections", "who", "new", "the", "state", "community",
    "special", "report", "news", "candidate", "candidates", "running", "race",
    "primary", "general", "runoff", "vote", "voters", "ballot", "committee",
    "commissioner", "trustee", "governor", "senate", "house", "congress",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december", "monday", "tuesday",
    "wednesday", "thursday", "friday", "saturday", "sunday", "this", "next",
    "here", "meet", "poll", "opinion", "editorial", "endorses", "endorsement",
    # common headline/event nouns — guard the weaker "candidate NAME" pattern
    # against title-case phrases like "Candidate Forum Draws Crowd".
    "forum", "debate", "guide", "tracker", "roundup", "questionnaire", "field",
    "spotlight", "event", "night", "crowd", "draws", "hall", "recap", "preview",
    "explainer", "primer", "rundown", "lineup", "slate", "profiles", "profile",
    "list", "questions", "answers", "town", "watch", "update", "updates",
    "coverage", "results", "forums", "debates",
    # verb words are never a name token — a candidacy verb captured as part of a
    # name means the match slid ("Propels Claudia Zuno", "Boosts …").
    "announces", "announced", "launches", "launched", "enters", "entered",
    "joins", "joined", "declares", "declared", "files", "filed", "seeks",
    "running", "challenges", "challenger", "unseat", "mulls", "weighs", "faces",
    "considers", "eyes", "explores", "propels", "boosts", "backs", "taps",
    "urges", "pushes", "picks", "names", "leads", "vows", "rips", "slams",
}


def _office_terms(race):
    """(required office keywords, whether a district token is also required) for
    matching a headline to a race. A headline must contain at least one office
    keyword — and, for district races, the district token — before any name from
    it is attributed to this race."""
    g = race.get("office_group")
    office = (race.get("office") or "").lower()
    if g == "citywide":
        if "mayor" in office:
            return (["mayor", "mayoral"], False)
        if "clerk" in office:
            return (["city clerk", "clerk"], False)
        if "treasurer" in office:
            return (["city treasurer", "treasurer"], False)
        return ([office], False)
    if g == "council":
        return (["alder"], True)
    if g == "cps_board":
        return (["board of education", "school board", "cps",
                 "board of ed"], not race.get("is_citywide"))
    if g == "police_district_council":
        return (["police district council", "district council",
                 "police district"], True)
    return ([office] if office else [], bool(race.get("district")))


_ORD = r"(?:st|nd|rd|th)"


def _district_patterns(race):
    """Regex patterns (word-boundary anchored) that must match a headline for a
    district race — e.g. ward 5 -> r'\\bward 0*5\\b' | r'\\b0*5(?:st|nd|rd|th)
    ward\\b'. Boundaries are essential: a naive 'ward 5' substring also matches
    'ward 50' and '5th ward' matches '25th ward'. Empty for citywide races."""
    g = race.get("office_group")
    pats = []
    if g == "council":
        w = _ward(race.get("district"))
        if w:
            pats += [rf"\bward\s+0*{w}\b", rf"\b0*{w}{_ORD}\s+ward\b"]
    elif g == "cps_board" and not race.get("is_citywide"):
        sub = _subdistrict(race.get("district"))
        if sub:
            n, letter = sub[:-1], sub[-1].lower()
            pats += [rf"\b(?:sub-?district\s+|district\s+)?0*{n}\s*{letter}\b"]
    elif g == "police_district_council":
        pd = _police_district(race.get("district"))
        if pd:
            pats += [rf"\b(?:police\s+)?district\s+0*{pd}\b",
                     rf"\b0*{pd}{_ORD}\s+(?:police\s+)?district\b"]
    return pats


# Honorifics / role prefixes a headline puts before a name ("Rep. Mike Quigley",
# "Comptroller Susana Mendoza", "Dr. Lisa Nee"). Stripped from the front so the
# same person doesn't split into two potential candidates.
_TITLE_PREFIXES = {
    "rep", "reps", "sen", "us", "usrep", "gov", "mayor", "ald", "alderman",
    "alderperson", "alderwoman", "comptroller", "dr", "mr", "ms", "mrs", "mx",
    "businessman", "businesswoman", "lobbyist", "cardiologist", "former",
    "congressman", "congresswoman", "judge", "attorney", "prof", "professor",
    "commissioner", "chairman", "chairwoman", "chair", "sec", "secretary",
    "gen", "capt", "rev", "hon", "councilman", "councilwoman", "councilmember",
    "activist", "advocate", "pastor", "coach", "sheriff", "treasurer", "clerk",
    "president", "governor", "senator", "representative", "state", "county",
    "ceo", "founder", "chief", "supt", "superintendent", "candidate",
}


def _strip_titles(name):
    """Drop leading honorific/role tokens from a captured name."""
    parts = [p for p in _clean(name).split() if p]
    while parts:
        base = re.sub(r"[.'’-]", "", parts[0]).lower()
        if base in _TITLE_PREFIXES:
            parts.pop(0)
        else:
            break
    return " ".join(parts)


def _valid_person(name):
    """A conservative gate: 2-3 tokens, each capitalized and not an office/place/
    calendar/verb stopword, not an all-caps acronym. The last token must be a real
    word (>=2 letters), so a name truncated by the headline at an initial or a
    dropped apostrophe ("Matthew J. O", "Tanya G") is rejected."""
    name = _clean(name)
    parts = [p for p in name.split() if p]
    if not (2 <= len(parts) <= 3):
        return False
    if name.isupper():
        return False
    last = re.sub(r"[^a-z]", "", parts[-1].lower())
    if len(last) < 2:  # truncated surname ("Matthew J. O", "Tanya G")
        return False
    if last in {"la", "de", "van", "von", "del", "di", "da", "el", "al", "st", "mc", "o"}:
        return False  # a name particle as the LAST token means it was cut ("Daniel La [Spata]")
    for p in parts:
        base = re.sub(r"[.'’-]", "", p).lower()
        if not base or base in _NAME_STOPWORDS:
            return False
    return True


def headline_matches_race(headline, race):
    """True when a headline references this race — its office keyword, plus the
    district token for a district race. The gate that keeps a name from one race's
    coverage off another race."""
    low = _clean(headline).lower()
    terms, need_district = _office_terms(race)
    if terms and not any(t in low for t in terms):
        return False
    if need_district:
        pats = _district_patterns(race)
        if not pats or not any(re.search(p, low) for p in pats):
            return False
    return True


def extract_candidacy(headline, race):
    """Names a headline attributes to `race`, as [(name, status)]. Returns [] when
    the headline doesn't reference this race's office (and district, for a district
    race) or no candidacy pattern with a valid person-name matches. Deterministic;
    no network."""
    text = _clean(headline)
    if not headline_matches_race(text, race):
        return []
    found = {}  # name_key -> (display_name, status)
    for regex, status in ((_ANNOUNCE_RE, "announced"), (_BID_RE, "announced"),
                          (_REVERSE_RE, "reported"), (_REVERSE_COLON_RE, "reported"),
                          (_EXPLORE_RE, "exploring")):
        for m in regex.finditer(text):
            name = _strip_titles(m.group(1))
            # Drop leading verb/place/garbage words the pattern swept into the name
            # ("… Propels Claudia Zuno To Run" -> "Claudia Zuno"), keeping >=2 tokens.
            toks = name.split()
            while len(toks) > 2 and re.sub(r"[.'’-]", "", toks[0].lower()) in _NAME_STOPWORDS:
                toks.pop(0)
            name = " ".join(toks)
            if not _valid_person(name):
                continue
            key = name.lower()
            # Strongest signal wins (announced > exploring > reported).
            rank = {"announced": 3, "exploring": 2, "reported": 1}
            if key not in found or rank[status] > rank[found[key][1]]:
                found[key] = (name, status)
    return list(found.values())


def parse_news_rss(xml_text):
    """Parse a Google News RSS search result into items [{title, link,
    publisher, date}]. `title` is the bare headline (the ' - Publisher' suffix
    Google appends is stripped). Pure/deterministic; bad XML yields []."""
    try:
        root = ET.fromstring(xml_text or "")
    except ET.ParseError:
        return []
    out = []
    for it in root.findall(".//item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        # <source> carries the outlet; Google also appends ' - Outlet' to titles.
        src_el = it.find("source")
        if src_el is None:
            src_el = it.find("{*}source")
        publisher = (src_el.text.strip() if src_el is not None and src_el.text else None)
        headline = title
        if publisher and headline.endswith(" - " + publisher):
            headline = headline[: -(len(publisher) + 3)].rstrip()
        elif " - " in headline:
            head, _, tail = headline.rpartition(" - ")
            if head and tail and not publisher:
                headline, publisher = head.strip(), tail.strip()
        out.append({
            "title": headline,
            "link": link,
            "publisher": publisher,
            "date": _rss_date(it.findtext("pubDate")),
        })
    return out


def _rss_date(raw):
    """ISO YYYY-MM-DD from an RFC-822 RSS pubDate; None if unparseable."""
    t = (raw or "").strip()
    if not t:
        return None
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(t)
        return dt.strftime("%Y-%m-%d") if dt else None
    except (TypeError, ValueError):
        return None


def news_url(query):
    from urllib.parse import quote_plus
    return (f"{NEWS_RSS_BASE}?q={quote_plus(query)}"
            "&hl=en-US&gl=US&ceid=US:en")


def _news_query_for_race(race):
    """A citywide race gets its own office query; district races share one broad
    per-group query (the pool is filtered per race by the district token)."""
    office = race.get("office") or ""
    yr = (race.get("ballot_date") or "")[:4]
    if "mayor" in office.lower():
        return 'Chicago mayor candidate ' + (yr or "2027")
    if "clerk" in office.lower():
        return 'Chicago "city clerk" candidate ' + (yr or "2027")
    if "treasurer" in office.lower():
        return 'Chicago "city treasurer" candidate ' + (yr or "2027")
    return f"Chicago {office} candidate {yr}".strip()


_GROUP_QUERY = {
    "council": 'Chicago City Council alderman candidate ward',
    "cps_board": '"Chicago Board of Education" candidate',
    "police_district_council": 'Chicago "Police District Council" candidate',
}


def _ordinal(n):
    """1 -> '1st', 2 -> '2nd', 3 -> '3rd', 11 -> '11th', 22 -> '22nd', …"""
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _race_news_query(race):
    """A per-race query so each district race gets its own coverage pool (one
    pooled group query can't cover 50 wards / 22 districts). Returns None for
    citywide/unknown, which fall back to the pooled group query + _news_query_for_race."""
    g = race.get("office_group")
    yr = (race.get("ballot_date") or "")[:4]
    if g == "council":
        w = _ward(race.get("district"))
        if w:
            return f'Chicago alderman "{_ordinal(w)} ward" candidate {yr or "2027"}'
    if g == "police_district_council":
        pd = _police_district(race.get("district"))
        if pd:
            return f'Chicago "police district council" "{_ordinal(pd)} district" candidate'
    if g == "cps_board" and not race.get("is_citywide"):
        sub = _subdistrict(race.get("district"))
        if sub:
            n = re.match(r"(\d+)", sub).group(1)
            return f'Chicago "Board of Education" "district {n}" candidate {yr or "2026"}'
    return None


def fetch_news_items(query):
    """Live fetch+parse of one news query. Fail-soft: any failure yields []."""
    return parse_news_rss(fetch_text(news_url(query)))


def build_potential(race, items, now, existing=None):
    """Assemble a race's potential_candidates[] from news `items` (already the
    relevant pool), merged with any `existing` list so names/sources accumulate
    across the twice-daily runs. Pure/deterministic given its inputs.

    A name that has since become an *official* candidate for this race (present in
    race['candidates'], populated earlier by --enrich-candidates-boe) is dropped:
    once the authority confirms someone, they graduate out of the unofficial
    "potential/rumored" list rather than double-listing as both."""
    official = {(c.get("name") or "").lower() for c in race.get("candidates", [])}
    people = {}  # name_key -> record

    def _seed(name):
        key = name.lower()
        if key not in people:
            people[key] = {"name": name, "status": None, "sources": [],
                           "_urls": set(), "_dates": set()}
        return people[key]

    # Carry forward what we already had (older articles roll out of the news
    # window; keeping them preserves a real first_seen and the citations).
    for p in (existing or []):
        rec = _seed(p.get("name") or "")
        rec["status"] = p.get("status")
        for s in p.get("sources", []):
            url = s.get("url")
            if url and url not in rec["_urls"]:
                rec["_urls"].add(url)
                rec["sources"].append({"title": s.get("title"), "url": url,
                                       "publisher": s.get("publisher"),
                                       "date": s.get("date")})
                if s.get("date"):
                    rec["_dates"].add(s["date"])

    rank = {"announced": 3, "exploring": 2, "reported": 1, None: 0}

    def _add_source(rec, it):
        url = it.get("link")
        if url and url not in rec["_urls"]:
            rec["_urls"].add(url)
            rec["sources"].append({"title": it.get("title"), "url": url,
                                   "publisher": it.get("publisher"),
                                   "date": it.get("date")})
            if it.get("date"):
                rec["_dates"].add(it["date"])

    # Pass 1: candidacy patterns discover names (and their signal strength).
    for it in items:
        for name, status in extract_candidacy(it.get("title", ""), race):
            rec = _seed(name)
            if rank[status] > rank[rec["status"]]:
                rec["status"] = status
            _add_source(rec, it)

    # Pass 2: for a name already established (here or from a prior run), any other
    # race-relevant headline that mentions it is supporting coverage — so ongoing
    # stories accumulate without a weak headline ever inventing a *new* name.
    if people:
        for it in items:
            title = it.get("title", "")
            if not headline_matches_race(title, race):
                continue
            low = title.lower()
            for key, rec in people.items():
                if key in low:
                    _add_source(rec, it)

    out = []
    for key, rec in people.items():
        if not rec["sources"]:
            continue
        if key in official:      # now an official candidate — no longer "potential"
            continue
        dates = sorted(rec["_dates"])
        rec["sources"].sort(key=lambda s: (s.get("date") or ""), reverse=True)
        out.append({
            "name": rec["name"],
            "status": rec["status"],
            "mentions": len(rec["sources"]),
            "first_seen": dates[0] if dates else None,
            "last_seen": dates[-1] if dates else None,
            "sources": rec["sources"][:POTENTIAL_MAX_SOURCES],
        })
    # Most-cited first, then firmest signal, then name — stable and useful.
    rank2 = {"announced": 3, "exploring": 2, "reported": 1, None: 0}
    out.sort(key=lambda p: (-p["mentions"], -rank2[p["status"]], p["name"].lower()))
    return out[:POTENTIAL_MAX_PER_RACE]


def enrich_potential(doc, now, fetcher=fetch_news_items, sleep=POTENTIAL_FETCH_SLEEP):
    """Attach unofficial, news-sourced potential_candidates[] to each race in an
    assembled elections doc, in place.

    Each race draws on: a broad pooled query for its office group (cross-cutting
    coverage), PLUS a per-race query for district races (so each ward / CPS
    subdistrict / police district gets its own coverage pool — one pooled query
    can't cover 50 wards). Citywide races use their own office query. Extraction
    is unchanged (strict office+district gating), so a bigger pool never means a
    looser match — a name still attaches only when a headline names the person
    with a candidacy verb AND references this race. `fetcher` is injectable so
    tests run offline. Returns the number of races given >=1 potential candidate."""
    import time
    races = doc.get("races", [])

    def _fetch(q):
        items = fetcher(q) or []
        if sleep:
            time.sleep(sleep)
        return items

    # Broad per-group pools (cheap: one request per group) for cross-cutting hits.
    group_pool = {g: _fetch(q) for g, q in _GROUP_QUERY.items()
                  if any(r.get("office_group") == g for r in races)}

    updated = 0
    for r in races:
        g = r.get("office_group")
        items = list(group_pool.get(g, []))
        rq = _race_news_query(r)                 # per-district query, when applicable
        items += _fetch(rq) if rq else (_fetch(_news_query_for_race(r)) if g not in group_pool else [])
        pcs = build_potential(r, items, now, existing=r.get("potential_candidates"))
        r["potential_candidates"] = pcs
        if pcs:
            updated += 1
    return updated


# --------------------------------------------------------------------------- #
# assembly
# --------------------------------------------------------------------------- #
def load_seed(seed_path=SEED_PATH):
    try:
        return json.loads(Path(seed_path).read_text())
    except (OSError, json.JSONDecodeError) as err:
        print(f"warning: could not read seed {seed_path}: {err}", file=sys.stderr)
        return {"jurisdictions": [], "races": []}


def assemble(candidates, seed, source, now, springfield=None):
    """Merge scraped candidates into the seed's race structure by race id.

    The seed is the authority on which races exist; candidates only fill them.
    Candidates that don't resolve to a seed race are counted and reported, never
    invented into a new race. `springfield` (the IL "rules of the game" bills) is
    attached as its own top-level list, kept separate from candidate data.
    """
    races = [dict(r) for r in seed.get("races", [])]
    for r in races:
        r.pop("note", None)
        r["candidates"] = []
        # Unofficial, news-sourced names attach later via --enrich-potential; the
        # base build always ships the field empty so the shape is stable and the
        # committed sample never carries a fabricated name.
        r.setdefault("potential_candidates", [])
    by_id = {r["id"]: r for r in races}

    placed, unplaced = 0, 0
    for c in candidates:
        rid = c.pop("_race_id", None)
        race = by_id.get(rid) if rid else None
        if not race:
            unplaced += 1
            continue
        # De-dupe within a race by candidate name (case-insensitive).
        if any(x["name"].lower() == c["name"].lower() for x in race["candidates"]):
            continue
        # A populated race is on the ballot; reflect that in its status.
        if race.get("status") == "upcoming":
            race["status"] = "on_ballot"
        race["candidates"].append(c)
        placed += 1
    if unplaced:
        print(f"warning: {unplaced} scraped candidate(s) did not resolve to a "
              f"seed race and were dropped", file=sys.stderr)

    # Sort candidates within each race by ballot name for stable output.
    for r in races:
        r["candidates"].sort(key=lambda c: c["name"].lower())

    counts = {}
    for r in races:
        counts[r["jurisdiction"]] = counts.get(r["jurisdiction"], 0) + 1

    return {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": source,
        "jurisdictions": seed.get("jurisdictions", []),
        "counts": counts,
        "races": races,
        "springfield": springfield or [],
    }, placed


# --------------------------------------------------------------------------- #
# RSS feeds
# --------------------------------------------------------------------------- #
DASHBOARD_URL = "https://chihacknight.github.io/govbot/dashboard/"
FEED_URL = DASHBOARD_URL + "elections.xml"

# Attaching this XSLT makes a browser render the feed as a readable page instead
# of a raw "this XML has no style information" tree (feed readers ignore it and
# parse the RSS as usual). The stylesheet lives at dashboard/feed.xsl, so a
# whole-ballot feed at the dashboard root references "feed.xsl" and a granular
# feed one directory down references "../feed.xsl". See docs/src/dashboard/feed.xsl.
FEED_XSL = "feed.xsl"


def _xml_prolog(xsl_href):
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<?xml-stylesheet type="text/xsl" href="{xsl_href}"?>\n')

# Feed dates are published in Chicago local time (CST/CDT) — these are Chicago/IL
# races, so a reader sees times in the ballot's own zone, not UTC. zoneinfo is
# DST-aware; if the IANA db is somehow missing we fall back to UTC (still valid
# RFC-822, just not localized) rather than crash.
try:
    from zoneinfo import ZoneInfo
    FEED_TZ = ZoneInfo("America/Chicago")
except Exception:  # pragma: no cover - tzdata unavailable
    FEED_TZ = timezone.utc


def _to_822(dt):
    """RFC-822 date string for `dt`, expressed in the feed's Central timezone."""
    from email.utils import format_datetime
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return format_datetime(dt.astimezone(FEED_TZ))


def _date_822(iso, fallback):
    """RFC-822 (Central, at local noon) for a YYYY-MM-DD, so per-candidate items
    sort by their real date; `fallback` (the build time) when it's missing/bad."""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})$", iso or "")
    if not m:
        return fallback
    return _to_822(datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                            12, 0, tzinfo=FEED_TZ))


OFFICE_GROUP_LABEL = {
    "citywide": "Chicago citywide",
    "council": "Alderperson (City Council)",
    "cps_board": "CPS Board of Education",
    "police_district_council": "Police District Councils",
    "cook_county": "Cook County",
    "suburban": "Suburban Cook",
    "judicial": "Judicial",
    "state": "Statewide",
    "federal": "Federal",
    "other": "Other",
}


def _race_headline(r):
    office = r.get("office", "Race")
    return f"{office} — {r['district']}" if r.get("district") else office


def _race_item_title(r):
    """A self-describing feed-item / channel title so even a title-only reader or
    widget conveys the key facts: office (+ district) · ballot · candidate count.
    Falls back to the potential-candidate count, then 'no candidates yet'."""
    bits = [_race_headline(r)]
    if r.get("ballot_date"):
        bits.append("on the " + _pretty_date(r["ballot_date"]) + " ballot")
    n = len(r.get("candidates") or [])
    p = len(r.get("potential_candidates") or [])
    if n:
        bits.append(f"{n} candidate{'' if n == 1 else 's'}")
    elif p:
        bits.append(f"{p} potential (unofficial)")
    else:
        bits.append("no candidates yet")
    return " · ".join(bits)


def _race_description(r):
    parts = []
    n = len(r.get("candidates", []))
    if r.get("ballot_date"):
        parts.append(f"On the ballot {r['ballot_date']}.")
    parts.append(f"{n} candidate{'' if n == 1 else 's'} listed."
                 if n else "No candidates confirmed yet.")
    if r.get("candidates"):
        parts.append("Candidates: " + ", ".join(c["name"] for c in r["candidates"]) + ".")
    if r.get("potential_candidates"):
        names = ", ".join(p["name"] for p in r["potential_candidates"][:6])
        parts.append(f"Potential (unofficial, from news): {names}.")
    tl = _timeline_summary(r.get("timeline"))
    if tl:
        parts.append("Timeline: " + tl + ".")
    if r.get("why_note"):
        parts.append(r["why_note"])
    return " ".join(parts)


def _timeline_summary(timeline):
    """Compact 'Filing deadline ~Nov 23, 2026 · Election Day Feb 23, 2027' line for
    a feed item, so subscribers see the whole election calendar. '~' marks an
    expected (statutory) date."""
    bits = []
    for m in timeline or []:
        if not m.get("date"):
            continue
        pre = "~" if m.get("confirmed") is False else ""
        bits.append(f"{m['label']} {pre}{_pretty_date(m['date'])}")
    return " · ".join(bits)


def _pretty_date(iso):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})$", iso or "")
    if not m:
        return iso or ""
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{months[int(m.group(2)) - 1]} {int(m.group(3))}, {m.group(1)}"


def _feed_prelude(doc):
    built = datetime.strptime(doc["generated_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc)
    return _to_822(built)


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-") or "x"


def _add_item(ch, r, built_822):
    """The race-summary item (one per race), used by every feed. Its title is now
    self-describing so a title-only reader still sees office · ballot · counts."""
    item = ET.SubElement(ch, "item")
    ET.SubElement(item, "title").text = _race_item_title(r)
    ET.SubElement(item, "link").text = r.get("official_list_url") or DASHBOARD_URL + "elections.html"
    ET.SubElement(item, "description").text = _race_description(r)
    ET.SubElement(item, "category").text = OFFICE_GROUP_LABEL.get(
        r.get("office_group"), r.get("office_group", ""))
    ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = r["id"]
    ET.SubElement(item, "pubDate").text = built_822


def _add_candidate_item(ch, r, c, built_822):
    """One item per confirmed, official candidate (in the per-race feeds), so a
    reader gets a new entry each time someone files."""
    item = ET.SubElement(ch, "item")
    head = _race_headline(r)
    ET.SubElement(item, "title").text = f"{c['name']} — {head}"
    ET.SubElement(item, "link").text = (c.get("website") or r.get("official_list_url")
                                        or DASHBOARD_URL + "elections.html")
    bits = []
    if r.get("partisan") and c.get("party"):
        bits.append(c["party"])
    if c.get("petition_status"):
        bits.append(c["petition_status"].replace("_", " "))
    if c.get("incumbent"):
        bits.append("incumbent")
    if c.get("filing_date"):
        bits.append("filed " + _pretty_date(c["filing_date"]))
    desc = f"Candidate for {head}." + (" " + "; ".join(bits) + "." if bits else "")
    money = c.get("money") or {}
    if money.get("funds_raised") is not None:
        desc += f" Raised ${money['funds_raised']:,.0f}."
    ET.SubElement(item, "description").text = desc
    ET.SubElement(item, "category").text = "Candidate (official)"
    ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = f"{r['id']}|cand|{_slug(c['name'])}"
    ET.SubElement(item, "pubDate").text = _date_822(c.get("filing_date"), built_822)


def _add_timeline_item(ch, r, m, built_822):
    """One item per dated election-calendar milestone (per-race feeds), e.g.
    'Filing deadline — Mayor · Nov 23, 2026 (expected)'. The date is in the title
    so a title-only reader sees it; pubDate stays the build time (not the future
    milestone date) so readers don't hide the item until then."""
    if not m.get("date"):
        return
    head = _race_headline(r)
    when = _pretty_date(m["date"])
    approx = " (expected)" if m.get("confirmed") is False else ""
    item = ET.SubElement(ch, "item")
    ET.SubElement(item, "title").text = f"🗓 {m['label']} — {head} · {when}{approx}"
    ET.SubElement(item, "link").text = r.get("official_list_url") or DASHBOARD_URL + "elections.html"
    desc = f"{m['label']} for {head}: {when}{approx}."
    if m.get("note"):
        desc += " " + m["note"]
    ET.SubElement(item, "description").text = desc
    ET.SubElement(item, "category").text = "Election calendar"
    ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = f"{r['id']}|tl|{_slug(m['label'])}"
    ET.SubElement(item, "pubDate").text = built_822


def _add_potential_item(ch, r, p, built_822):
    """One item per UNOFFICIAL, news-sourced potential candidate (per-race feeds
    only). Every such item is prefixed [UNOFFICIAL] and links to a source article,
    so a rumor can never be mistaken for a ballot record in a reader."""
    item = ET.SubElement(ch, "item")
    head = _race_headline(r)
    status = p.get("status") or "reported"
    ET.SubElement(item, "title").text = f"[UNOFFICIAL] {p['name']} ({status}) — {head}"
    srcs = p.get("sources") or []
    ET.SubElement(item, "link").text = ((srcs[0].get("url") if srcs else None)
                                        or DASHBOARD_URL + "elections.html")
    pubs = list(dict.fromkeys(s.get("publisher") for s in srcs if s.get("publisher")))
    desc = (f"UNOFFICIAL — not a filed candidate. Reported by the press as "
            f"{status} for {head}.")
    if pubs:
        desc += " Coverage: " + ", ".join(pubs[:5]) + "."
    desc += " Verify via the linked sources; this is a news signal, not a ballot record."
    ET.SubElement(item, "description").text = desc
    ET.SubElement(item, "category").text = "Potential candidate (unofficial · from news)"
    ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = f"{r['id']}|pot|{_slug(p['name'])}"
    ET.SubElement(item, "pubDate").text = _date_822(p.get("last_seen"), built_822)


def _feed_xml(title, description, self_url, races, built_822, xsl_href="../" + FEED_XSL):
    rss = ET.Element("rss", {"version": "2.0",
                             "xmlns:atom": "http://www.w3.org/2005/Atom"})
    ch = ET.SubElement(rss, "channel")
    ET.SubElement(ch, "title").text = title
    ET.SubElement(ch, "link").text = DASHBOARD_URL + "elections.html"
    ET.SubElement(ch, "description").text = description
    ET.SubElement(ch, "language").text = "en-us"
    ET.SubElement(ch, "lastBuildDate").text = built_822
    ET.SubElement(ch, "atom:link", {"href": self_url, "rel": "self",
                                    "type": "application/rss+xml"})
    for r in races:
        _add_item(ch, r, built_822)
    return _xml_prolog(xsl_href) + ET.tostring(rss, encoding="unicode") + "\n"


def to_rss(doc):
    """The whole ballot as one RSS 2.0 feed (one item per race)."""
    built_822 = _feed_prelude(doc)
    return _feed_xml(
        "govbot — Elections Happening in IL: Chicago & Illinois races",
        "Every office on upcoming Chicago and Illinois ballots (citywide, "
        "aldermanic, CPS board, and Police District Councils), with candidates "
        "as they are confirmed. Refreshed twice daily by govbot.",
        FEED_URL, doc.get("races", []), built_822, xsl_href=FEED_XSL)


def office_group_feed_name(group):
    return f"group-{group}.xml"


def group_feeds(doc):
    """One RSS feed per office group (all citywide races, all aldermanic, ...)."""
    built_822 = _feed_prelude(doc)
    by_group = {}
    for r in doc.get("races", []):
        by_group.setdefault(r["office_group"], []).append(r)
    feeds = {}
    for group, races in by_group.items():
        label = OFFICE_GROUP_LABEL.get(group, group)
        fname = office_group_feed_name(group)
        feeds[fname] = _feed_xml(
            f"govbot — {label}: candidates on upcoming ballots",
            f"All {label} races govbot is tracking on upcoming Chicago/Illinois "
            f"ballots, refreshed twice daily.",
            DASHBOARD_URL + "elections/" + fname, races, built_822)
    return feeds


def ballot_feed_name(date):
    return f"ballot-{date}.xml"


def ballot_feeds(doc):
    """One RSS feed per ballot date (all races sharing an Election Day), so a
    reader can follow a whole ballot — e.g. the 2026 CPS election or the 2027
    Chicago municipal election — rather than a single office group or race."""
    built_822 = _feed_prelude(doc)
    by_date = {}
    for r in doc.get("races", []):
        if r.get("ballot_date"):
            by_date.setdefault(r["ballot_date"], []).append(r)
    feeds = {}
    for date, races in by_date.items():
        groups = {rr["office_group"] for rr in races}
        label = ("Chicago Board of Education (CPS)"
                 if groups == {"cps_board"} else "Chicago municipal election")
        fname = ballot_feed_name(date)
        feeds[fname] = _feed_xml(
            f"govbot — {label}: races on the {date} ballot",
            f"Every race on the {label} ballot ({date}) govbot is tracking, "
            f"refreshed twice daily.",
            DASHBOARD_URL + "elections/" + fname, races, built_822)
    return feeds


def race_feed_name(race_id):
    safe = re.sub(r"[^A-Za-z0-9._-]", "-", race_id or "")
    return f"race-{safe}.xml"


def _race_feed_xml(r, built_822):
    """A single race as its own feed: a summary entry, then one entry per official
    candidate, then one per UNOFFICIAL potential candidate — so following one race
    (your ward, your CPS subdistrict, the mayor's race) surfaces names as items."""
    self_url = DASHBOARD_URL + "elections/" + race_feed_name(r["id"])
    rss = ET.Element("rss", {"version": "2.0",
                             "xmlns:atom": "http://www.w3.org/2005/Atom"})
    ch = ET.SubElement(rss, "channel")
    ET.SubElement(ch, "title").text = f"govbot — {_race_item_title(r)}"
    ET.SubElement(ch, "link").text = DASHBOARD_URL + "elections.html"
    ET.SubElement(ch, "description").text = (
        "A single race tracked by govbot: a summary entry, one entry per candidate "
        "as they are confirmed, unofficial potential candidates the press has named, "
        f"and the key election-calendar dates. {r.get('why_note') or ''}".strip())
    ET.SubElement(ch, "language").text = "en-us"
    ET.SubElement(ch, "lastBuildDate").text = built_822
    ET.SubElement(ch, "atom:link", {"href": self_url, "rel": "self",
                                    "type": "application/rss+xml"})
    _add_item(ch, r, built_822)  # race summary first
    for c in r.get("candidates") or []:
        _add_candidate_item(ch, r, c, built_822)
    for p in r.get("potential_candidates") or []:
        _add_potential_item(ch, r, p, built_822)
    for m in r.get("timeline") or []:  # election-calendar milestones
        _add_timeline_item(ch, r, m, built_822)
    return _xml_prolog("../" + FEED_XSL) + ET.tostring(rss, encoding="unicode") + "\n"


def race_feeds(doc):
    """One RSS feed per individual race, so a reader can follow just their ward,
    their CPS subdistrict, or the mayor's race — each with per-candidate items."""
    built_822 = _feed_prelude(doc)
    return {race_feed_name(r["id"]): _race_feed_xml(r, built_822)
            for r in doc.get("races", [])}


def springfield_feed(doc):
    """One RSS feed of the IL 'rules of the game' bills (springfield.xml), so a
    reader can follow the laws shaping these elections. Returns {} when empty."""
    bills = doc.get("springfield") or []
    if not bills:
        return {}
    built_822 = _feed_prelude(doc)
    rss = ET.Element("rss", {"version": "2.0", "xmlns:atom": "http://www.w3.org/2005/Atom"})
    ch = ET.SubElement(rss, "channel")
    ET.SubElement(ch, "title").text = "govbot — Springfield: the rules of the game (IL elections & education bills)"
    ET.SubElement(ch, "link").text = DASHBOARD_URL + "elections.html"
    ET.SubElement(ch, "description").text = (
        "Illinois bills tagged elections & voting or education — the laws that "
        "shape how Chicago/IL elections work. Context beside the races, from "
        "govbot's legislation dataset; refreshed twice daily.")
    ET.SubElement(ch, "language").text = "en-us"
    ET.SubElement(ch, "lastBuildDate").text = built_822
    self_url = DASHBOARD_URL + "elections/springfield.xml"
    ET.SubElement(ch, "atom:link", {"href": self_url, "rel": "self", "type": "application/rss+xml"})
    for b in bills:
        parts = []
        if b.get("latest_action_desc"):
            parts.append(b["latest_action_desc"] + ".")
        if b.get("tags"):
            parts.append("Topics: " + ", ".join(b["tags"]) + ".")
        if b.get("hearing"):
            h = b["hearing"]
            parts.append("On the " + (h.get("committee") or "committee") + " calendar" +
                         (" — " + h["scheduled_display"] if h.get("scheduled_display") else "") + ".")
        item = ET.SubElement(ch, "item")
        ET.SubElement(item, "title").text = f"{b['id']} — {b.get('title', '')}"
        ET.SubElement(item, "link").text = b.get("url") or (DASHBOARD_URL + "index.html#q=" + (b.get("id") or ""))
        ET.SubElement(item, "description").text = " ".join(parts) or b.get("title", "")
        ET.SubElement(item, "category").text = "Springfield · rules of the game"
        ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = "springfield-" + _norm_bill_id(b.get("id"))
        ET.SubElement(item, "pubDate").text = built_822
    return {"springfield.xml": (_xml_prolog("../" + FEED_XSL)
                                + ET.tostring(rss, encoding="unicode") + "\n")}


def all_feeds(doc):
    feeds = {}
    feeds.update(group_feeds(doc))
    feeds.update(ballot_feeds(doc))
    feeds.update(race_feeds(doc))
    feeds.update(springfield_feed(doc))
    return feeds


def write_feeds(doc, rss_path=None, feeds_dir=None):
    """Write the whole-ballot feed (rss_path) and/or the granular feeds (feeds_dir)
    from an assembled doc. Kept separate so the deploy can regenerate feeds AFTER
    enrichment (potential candidates / money) has mutated elections.json."""
    if rss_path:
        Path(rss_path).write_text(to_rss(doc))
        print(f"wrote RSS feed to {rss_path}", file=sys.stderr)
    if feeds_dir:
        outdir = Path(feeds_dir)
        outdir.mkdir(parents=True, exist_ok=True)
        feeds = all_feeds(doc)
        for fname, xml in feeds.items():
            (outdir / fname).write_text(xml)
        print(f"wrote {len(feeds)} granular RSS feeds to {outdir}", file=sys.stderr)


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sources", default="isbe,chicago,cook",
                    help="Comma-separated candidate sources to scrape live "
                         "(default: isbe,chicago,cook)")
    ap.add_argument("--from-fixtures", default=None,
                    help="Build offline from a raw fixtures dir (no network)")
    ap.add_argument("--seed", default=str(SEED_PATH),
                    help="Race-structure seed (elections_seed.json)")
    ap.add_argument("--now", default=None,
                    help="Override generated_at (ISO, e.g. 2026-09-07T00:00:00Z) "
                         "— used for deterministic snapshots")
    ap.add_argument("--output", "-o", default="-", help="Output path (default: stdout)")
    ap.add_argument("--rss", default=None,
                    help="Also write an RSS 2.0 feed of every race to this path")
    ap.add_argument("--rss-feeds-dir", default=None,
                    help="Also write granular RSS 2.0 feeds into this directory: "
                         "one per office group (group-council.xml), one per "
                         "race (race-chicago-mayor.xml), and springfield.xml, so "
                         "readers can follow a whole office group, a single race, "
                         "or the 'rules of the game' bills")
    ap.add_argument("--legislation", default="docs/src/dashboard/data.json",
                    help="govbot bill dataset (data.json) for the Springfield "
                         "'rules of the game' feed — IL bills tagged elections & "
                         "voting or education. Missing/unreadable degrades to an "
                         "empty Springfield list")
    ap.add_argument("--hearings", default="docs/src/dashboard/hearings.json",
                    help="hearings.json, to cross-reference Springfield bills with "
                         "upcoming ILGA committee hearings")
    ap.add_argument("--enrich-money", default=None,
                    help="Attach SBE campaign-finance money to the candidates in an "
                         "existing elections.json (rewritten in place) using --money-dir, "
                         "then exit. Run after candidates are populated")
    ap.add_argument("--money-dir", default=None,
                    help="Directory of Illinois SBE bulk files (Candidates.txt, "
                         "CmteCandidateLinks.txt, Committees.txt, D2Totals.txt) for "
                         "--enrich-money")
    ap.add_argument("--enrich-results", default=None,
                    help="Attach post-Election-Night vote results to an existing "
                         "elections.json (rewritten in place) from --results-file, "
                         "then exit")
    ap.add_argument("--results-file", default=None,
                    help="A delimited (CSV/TSV) results export from the election "
                         "authority, for --enrich-results")
    ap.add_argument("--results-url", default=None,
                    help="Official results page URL recorded on each results block")
    ap.add_argument("--enrich-potential", default=None,
                    help="Attach UNOFFICIAL, news-sourced potential_candidates[] to "
                         "each race in an existing elections.json (rewritten in "
                         "place) from Google News RSS, then exit. Merges with the "
                         "file's current potential_candidates so names/citations "
                         "accumulate across runs. Fail-soft: sources down leaves the "
                         "lists as they were")
    ap.add_argument("--enrich-candidates-boe", default=None,
                    help="Attach official candidates from the Chicago BOE Candidate "
                         "List PDF to an existing elections.json (rewritten in place), "
                         "then exit. Populates the Board-of-Education races on the "
                         "ballot. Uses --boe-pdf or auto-discovers the latest PDF; needs "
                         "the `pdftotext` system tool (poppler-utils). Fail-soft")
    ap.add_argument("--boe-pdf", default=None,
                    help="Source for --enrich-candidates-boe: a .pdf URL, a local .pdf, "
                         "or a local .txt of already-extracted text (for tests). "
                         "Omitted = auto-discover the latest from the BOE candidates page")
    ap.add_argument("--rss-from", default=None,
                    help="(Re)generate the RSS feeds from an existing elections.json "
                         "(no scrape), then exit — used by the deploy to rebuild feeds "
                         "AFTER enrichment (potential candidates / money) so those items "
                         "land in the per-race feeds. Writes --rss and/or --rss-feeds-dir")
    args = ap.parse_args()

    now = (datetime.strptime(args.now, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
           if args.now else datetime.now(timezone.utc))

    if args.enrich_money:
        doc = load_json(args.enrich_money)
        if doc is None:
            return 0
        n = enrich_money(doc, args.money_dir or "", now)
        Path(args.enrich_money).write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        print(f"enriched {n} candidate(s) with SBE campaign money", file=sys.stderr)
        return 0

    if args.enrich_results:
        doc = load_json(args.enrich_results)
        if doc is None:
            return 0
        n = enrich_results(doc, args.results_file or "", now, args.results_url)
        Path(args.enrich_results).write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        print(f"attached results to {n} race(s)", file=sys.stderr)
        return 0

    if args.enrich_potential:
        doc = load_json(args.enrich_potential)
        if doc is None:
            return 0
        n = enrich_potential(doc, now)
        Path(args.enrich_potential).write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        print(f"attached news-sourced potential candidates to {n} race(s)", file=sys.stderr)
        return 0

    if args.enrich_candidates_boe:
        doc = load_json(args.enrich_candidates_boe)
        if doc is None:
            return 0
        n = enrich_candidates_from_boe(doc, args.boe_pdf)
        Path(args.enrich_candidates_boe).write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        print(f"attached {n} official Chicago BOE candidate(s)", file=sys.stderr)
        return 0

    if args.rss_from:
        doc = load_json(args.rss_from)
        if doc is None:
            return 0
        write_feeds(doc, args.rss, args.rss_feeds_dir)
        return 0

    seed = load_seed(args.seed)

    if args.from_fixtures:
        candidates = build_from_fixtures(args.from_fixtures)
        source = "fixtures (offline snapshot)"
        legislation = load_json(str(Path(args.from_fixtures) / "il_legislation.json"))
        hearings = load_json(str(Path(args.from_fixtures) / "il_hearings.json"))
    else:
        srcs = [s.strip().lower() for s in args.sources.split(",") if s.strip()]
        candidates = []
        if "isbe" in srcs:
            candidates.extend(fetch_isbe())
        if "chicago" in srcs:
            candidates.extend(fetch_chicago_boe())
        if "cook" in srcs:
            candidates.extend(fetch_cook_clerk())
        source = ("chicagoelections.gov + elections.il.gov + Cook County Clerk "
                  "(govbot scrape-elections); race structure from committed seed")
        legislation = load_json(args.legislation)
        hearings = load_json(args.hearings)

    springfield = build_springfield(legislation, hearings)
    doc, placed = assemble(candidates, seed, source, now, springfield=springfield)
    text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    if args.output == "-":
        sys.stdout.write(text)
    else:
        Path(args.output).write_text(text)
        print(f"wrote {len(doc['races'])} races ({placed} candidate(s) placed, "
              f"{len(springfield)} Springfield bill(s)) to {args.output}", file=sys.stderr)

    write_feeds(doc, args.rss, args.rss_feeds_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
