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

    # CPS board — check before the generic "president"/"member" words leak.
    if "board of education" in o or "school board" in o or o.startswith("cps") \
            or "board member" in o or "board of ed" in o \
            or ("board" in o and ("subdistrict" in d.lower() or "president" in o)):
        if "president" in o:
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
# assembly
# --------------------------------------------------------------------------- #
def load_seed(seed_path=SEED_PATH):
    try:
        return json.loads(Path(seed_path).read_text())
    except (OSError, json.JSONDecodeError) as err:
        print(f"warning: could not read seed {seed_path}: {err}", file=sys.stderr)
        return {"jurisdictions": [], "races": []}


def assemble(candidates, seed, source, now):
    """Merge scraped candidates into the seed's race structure by race id.

    The seed is the authority on which races exist; candidates only fill them.
    Candidates that don't resolve to a seed race are counted and reported, never
    invented into a new race.
    """
    races = [dict(r) for r in seed.get("races", [])]
    for r in races:
        r.pop("note", None)
        r["candidates"] = []
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
    }, placed


# --------------------------------------------------------------------------- #
# RSS feeds
# --------------------------------------------------------------------------- #
DASHBOARD_URL = "https://chihacknight.github.io/govbot/dashboard/"
FEED_URL = DASHBOARD_URL + "elections.xml"

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


def _race_description(r):
    parts = []
    n = len(r.get("candidates", []))
    if r.get("ballot_date"):
        parts.append(f"On the ballot {r['ballot_date']}.")
    parts.append(f"{n} candidate{'' if n == 1 else 's'} listed."
                 if n else "No candidates confirmed yet.")
    if r.get("candidates"):
        parts.append("Candidates: " + ", ".join(c["name"] for c in r["candidates"]) + ".")
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
    from email.utils import format_datetime
    built = datetime.strptime(doc["generated_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc)
    return format_datetime(built)


def _add_item(ch, r, built_822):
    item = ET.SubElement(ch, "item")
    ET.SubElement(item, "title").text = _race_headline(r)
    ET.SubElement(item, "link").text = r.get("official_list_url") or DASHBOARD_URL + "elections.html"
    ET.SubElement(item, "description").text = _race_description(r)
    ET.SubElement(item, "category").text = OFFICE_GROUP_LABEL.get(
        r.get("office_group"), r.get("office_group", ""))
    ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = r["id"]
    ET.SubElement(item, "pubDate").text = built_822


def _feed_xml(title, description, self_url, races, built_822):
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
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            + ET.tostring(rss, encoding="unicode") + "\n")


def to_rss(doc):
    """The whole ballot as one RSS 2.0 feed (one item per race)."""
    built_822 = _feed_prelude(doc)
    return _feed_xml(
        "govbot — Elections Happening in IL: Chicago & Illinois races",
        "Every office on upcoming Chicago and Illinois ballots (citywide, "
        "aldermanic, CPS board, and Police District Councils), with candidates "
        "as they are confirmed. Refreshed twice daily by govbot.",
        FEED_URL, doc.get("races", []), built_822)


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


def race_feed_name(race_id):
    safe = re.sub(r"[^A-Za-z0-9._-]", "-", race_id or "")
    return f"race-{safe}.xml"


def race_feeds(doc):
    """One RSS feed per individual race, so a reader can follow just their ward,
    their CPS subdistrict, or the mayor's race."""
    built_822 = _feed_prelude(doc)
    feeds = {}
    for r in doc.get("races", []):
        fname = race_feed_name(r["id"])
        feeds[fname] = _feed_xml(
            f"govbot — {_race_headline(r)}",
            f"A single race tracked by govbot; the item updates as candidates "
            f"are confirmed. {r.get('why_note') or ''}".strip(),
            DASHBOARD_URL + "elections/" + fname, [r], built_822)
    return feeds


def all_feeds(doc):
    feeds = {}
    feeds.update(group_feeds(doc))
    feeds.update(race_feeds(doc))
    return feeds


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
                         "one per office group (group-council.xml) and one per "
                         "race (race-chicago-mayor.xml), so readers can follow a "
                         "whole office group or a single race")
    args = ap.parse_args()

    now = (datetime.strptime(args.now, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
           if args.now else datetime.now(timezone.utc))

    seed = load_seed(args.seed)

    if args.from_fixtures:
        candidates = build_from_fixtures(args.from_fixtures)
        source = "fixtures (offline snapshot)"
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

    doc, placed = assemble(candidates, seed, source, now)
    text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    if args.output == "-":
        sys.stdout.write(text)
    else:
        Path(args.output).write_text(text)
        print(f"wrote {len(doc['races'])} races "
              f"({placed} candidate(s) placed) to {args.output}", file=sys.stderr)

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
