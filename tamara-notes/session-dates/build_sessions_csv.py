#!/usr/bin/env python3
"""Build sessions.csv from LegiScan's yearly session-calendar PDFs plus hand-kept rows.

    python3 build_sessions_csv.py            # writes sessions.csv next to this file

Needs `pdftohtml` (poppler). The PDF's colours carry meaning, so it is read as XML
(text + font colour), not plain text: a red date is one LegiScan marks as estimated.

Rules:
- PDFs are found under sources/<legiscan|multistate>/<year covered>/<updated YYYY-MM-DD>.pdf
  (see README.md). Regular sessions come from the NEWEST PDF for each year.
- LegiScan drops a special-session note once that special is over, so every PDF's notes
  are kept: each note becomes a "special" row (start date only; the PDF gives no end).
- MultiState's yearly PDFs (sources/multistate/) are read too and kept as their own rows: their
  regular-session dates, plus the dated events on their notes page (special, veto,
  organizational and reconvened sessions, recesses, informal sessions). LegiScan and
  MultiState sometimes disagree by a few days; both rows are kept, each with its source.
- Congress comes from congress.gov API responses saved in congress/ (one row per session).
- MANUAL rows (territories, specials with known dates, corrections) are added last and
  replace any PDF row with the same code + year + session. Fix things there, by hand.
- A date not covered by any row is out of session.
"""
import csv
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent

SOURCES = HERE / "sources"


def calendars(kind):
    """[(path, year covered, updated date)] for sources/<kind>/<year>/<YYYY-MM-DD>.pdf, newest first
    within a year. The folder is the year the calendar covers; the file name is the date the
    publisher says it was updated (LegiScan's "Updated ...", MultiState's "last updated ...")."""
    out = []
    for path in sorted((SOURCES / kind).glob("*/*.pdf")):
        year, updated = path.parent.name, path.stem
        if not re.fullmatch(r"\d{4}", year) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", updated):
            raise SystemExit(f"{path}: expected sources/{kind}/<year>/<YYYY-MM-DD>.pdf")
        out.append((path, int(year), updated))
    return sorted(out, key=lambda c: (c[1], c[2]), reverse=True)

CODES = {
    "Alabama": "al", "Alaska": "ak", "Arizona": "az", "Arkansas": "ar", "California": "ca",
    "Colorado": "co", "Connecticut": "ct", "Delaware": "de", "Florida": "fl", "Georgia": "ga",
    "Hawaii": "hi", "Idaho": "id", "Illinois": "il", "Indiana": "in", "Iowa": "ia",
    "Kansas": "ks", "Kentucky": "ky", "Louisiana": "la", "Maine": "me", "Maryland": "md",
    "Massachusetts": "ma", "Michigan": "mi", "Minnesota": "mn", "Mississippi": "ms",
    "Missouri": "mo", "Montana": "mt", "Nebraska": "ne", "Nevada": "nv",
    "New Hampshire": "nh", "New Jersey": "nj", "New Mexico": "nm", "New York": "ny",
    "North Carolina": "nc", "North Dakota": "nd", "Ohio": "oh", "Oklahoma": "ok",
    "Oregon": "or", "Pennsylvania": "pa", "Rhode Island": "ri", "South Carolina": "sc",
    "South Dakota": "sd", "Tennessee": "tn", "Texas": "tx", "Utah": "ut", "Vermont": "vt",
    "Virginia": "va", "Washington": "wa", "West Virginia": "wv", "Wisconsin": "wi",
    "Wyoming": "wy", "District of Columbia": "dc", "US Congress": "usa",
}
RED = {"#ff0000", "#ed0000"}
MONTHS = {m: i for i, m in enumerate(
    "January February March April May June July August September October November December".split(), 1)}

FIELDS = ["code", "state", "year", "session", "type", "convenes", "adjourns",
          "convenes_estimated", "adjourns_estimated", "source", "source_updated", "notes"]

# Hand-kept rows. Each needs a source. These win over the PDFs.
MANUAL = [
    # Territories: not in LegiScan. From old-notes/session-calendar-2026.md (each legislature's own site).
    dict(code="gu", state="Guam", year=2026, session="38th Legislature", type="regular",
         convenes="2025-01-06", adjourns="2026-12-31", source="guamlegislature.gov via old-notes/session-calendar-2026.md",
         source_updated="2026-09-29", notes="Year-round; sessions called as needed"),
    dict(code="mp", state="Northern Mariana Islands", year=2026, session="24th Legislature", type="regular",
         convenes="2025-01-06", adjourns="2026-12-31", source="cnmileg.net via old-notes/session-calendar-2026.md",
         source_updated="2026-09-29", notes="Year-round; regular + special sessions called as needed"),
    dict(code="vi", state="Virgin Islands", year=2026, session="36th Legislature", type="regular",
         convenes="2025-01-06", adjourns="2026-12-31", source="legvi.org via old-notes/session-calendar-2026.md",
         source_updated="2026-09-29", notes="Year-round; regular sessions called as needed"),
    dict(code="pr", state="Puerto Rico", year=2026, session="2026 Regular Session", type="regular",
         convenes="2026-01-12", adjourns="2026-06-30", source="senado.pr.gov via old-notes/session-calendar-2026.md",
         source_updated="2026-09-29", notes="Ends Jun 30 by law; specials not checked"),
    # PR holds a second ordinary session each year, Aug-Nov. senado.pr.gov (read 2026-11-26) says
    # the Senate closed the 4th ordinary session (20th Assembly) on 2026-11-17. The start date is
    # the third Monday of August, from the rule as remembered (Ley 9 of 1954; its text and
    # camara.pr.gov would not load), so it is marked estimated. PR's data picks up in Aug 2026.
    dict(code="pr", state="Puerto Rico", year=2026, session="2026 Second Ordinary Session (4th of the 20th Assembly)",
         type="regular", convenes="2026-08-17", adjourns="2026-11-17", convenes_estimated="yes",
         source="senado.pr.gov (end date); start from the Aug rule, unverified", source_updated="2026-11-26",
         notes="Start = third Monday of August; check Ley 9-1954 or camara.pr.gov"),
    dict(code="pr", state="Puerto Rico", year=2025, session="2025 First Ordinary Session (1st of the 20th Assembly)",
         type="regular", convenes="2025-01-13", adjourns="2025-06-30", convenes_estimated="yes",
         source="the Jan-Jun rule, unverified", source_updated="2026-11-26",
         notes="Second Monday of Jan to Jun 30; not checked on a site"),
    dict(code="pr", state="Puerto Rico", year=2025, session="2025 Second Ordinary Session (2nd of the 20th Assembly)",
         type="regular", convenes="2025-08-18", adjourns="2025-11-18", convenes_estimated="yes",
         adjourns_estimated="yes", source="the Aug-Nov rule, unverified", source_updated="2026-11-26",
         notes="Third Monday of Aug to the Tuesday before the third Thursday of Nov; not checked on a site"),
    # Alaska's specials, with dates (old-notes/session-calendar-2026.md, checked live 2026-09-29).
    dict(code="ak", state="Alaska", year=2026, session="Special Session May 21st", type="special",
         convenes="2026-05-21", adjourns="2026-06-19", source="old-notes/session-calendar-2026.md (legiscan.com/AK, news)",
         source_updated="2026-09-29", notes="2nd special; LNG"),
    dict(code="ak", state="Alaska", year=2026, session="3rd Special Session", type="special",
         convenes="2026-06-20", adjourns="2026-07-16", source="old-notes/session-calendar-2026.md (legiscan.com/AK, news)",
         source_updated="2026-09-29", notes="LNG"),
    dict(code="ak", state="Alaska", year=2026, session="4th Special Session", type="special",
         convenes="2026-07-27", adjourns="2026-08-25", source="old-notes/session-calendar-2026.md (legiscan.com/AK, news)",
         source_updated="2026-09-29", notes="LNG"),
    # Congress was still meeting after LegiScan's 10-30 estimate.
    dict(code="usa", state="US Congress", year=2026, session="119th Congress", type="regular",
         convenes="2026-01-03", adjourns="2026-12-31", adjourns_estimated="yes",
         source="old-notes/session-calendar-2026.md", source_updated="2026-11-24",
         notes="LegiScan says 10-30 (estimated); lame-duck session from the week of Nov 9"),
]


def read_pdf(path):
    """Return the PDF's rows as lists of (left, text, colour), one list per line."""
    xml = subprocess.run(["pdftohtml", "-xml", "-i", "-stdout", str(path)],
                         capture_output=True, text=True, check=True).stdout
    root = ET.fromstring(xml)
    colours = {f.get("id"): f.get("color") for f in root.iter("fontspec")}
    lines = {}
    for t in root.iter("text"):
        text = "".join(t.itertext()).strip()
        if text:
            lines.setdefault(int(t.get("top")), []).append(
                (int(t.get("left")), text, colours.get(t.get("font"))))
    return [sorted(v) for _, v in sorted(lines.items())]


def note_date(note, year):
    """'Special Session May 21st' -> '2026-05-21'."""
    m = re.search(r"(" + "|".join(MONTHS) + r")\s+(\d{1,2})", note)
    return f"{year}-{MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}" if m else ""


def parse(path, year, updated):
    regular, specials = [], []
    for line in read_pdf(path):
        state = " ".join(t for left, t, _ in line if left < 200)
        if state not in CODES:
            continue
        cols = {"session": [], "convenes": [], "adjourns": [], "notes": []}
        red = {"convenes": False, "adjourns": False}
        for left, text, colour in line:
            if left < 200:
                continue
            if "No Regular Session" in text:
                cols["session"].append(text)
                continue
            key = ("session" if left < 400 else "convenes" if left < 520
                   else "adjourns" if left < 630 else "notes")
            cols[key].append(text)
            if key in red and re.match(r"\d{4}-\d\d-\d\d", text) and colour in RED:
                red[key] = True
        session = " ".join(cols["session"])
        # The PDF sets "21st" as "21" + a raised "st": join them back.
        note = re.sub(r"(\d)\s+(st|nd|rd|th)\b", r"\1\2", " ".join(cols["notes"]))
        # A note can hold several parts ("Prefiling; Special Session January 27th"): each
        # special part becomes its own row, the rest stays on the regular row. A special with
        # no date ("Special Session TBD") is skipped: a row needs a date.
        parts = [x.strip() for x in note.split(";") if x.strip()]
        special_parts = [x for x in parts if "Special" in x]
        code = CODES[state]
        regular.append(dict(
            code=code, state=state, year=year, session=session,
            type="none" if "No Regular Session" in session else "regular",
            convenes=" ".join(cols["convenes"]), adjourns=" ".join(cols["adjourns"]),
            convenes_estimated="yes" if red["convenes"] else "",
            adjourns_estimated="yes" if red["adjourns"] else "",
            source=str(path.relative_to(HERE)), source_updated=updated,
            notes="; ".join(x for x in parts if x not in special_parts)))
        for sp in special_parts:
            if not note_date(sp, year):
                continue
            specials.append(dict(
                code=code, state=state, year=year, session=sp, type="special",
                convenes=note_date(sp, year), adjourns="", source=str(path.relative_to(HERE)),
                source_updated=updated, notes="end date not in the PDF"))
    return regular, specials


# Words on MultiState's notes page that start a kind of dated event. Dates after a word
# belong to it until the next word. Anything else (deadlines, "TBA", "expected") is ignored.
MS_EVENTS = [
    (r"special session", "special"), (r"veto (?:session|day)", "veto"),
    (r"organi[sz]ation(?:al)? (?:session|days?)", "organizational"),
    (r"reconven\w*|lame duck", "reconvene"), (r"\brecess\b", "recess"),
    (r"informal session", "informal"),
    (r"first adjournment|adjournment deadline|regular session begun|sine die", None),
]
MS_DATE = r"(\d{1,2})/(\d{1,2})/(\d{2})"


def ms_iso(m):
    return f"20{m[2]}-{int(m[0]):02d}-{int(m[1]):02d}"


def parse_multistate(path, year, updated):
    rows = []
    page1 = subprocess.run(["pdftohtml", "-xml", "-i", "-stdout", "-f", "1", "-l", "1", str(path)],
                           capture_output=True, text=True, check=True).stdout
    items = set()  # the PDF draws most text twice
    for t in ET.fromstring(page1).iter("text"):
        text = "".join(t.itertext()).strip()
        if text:
            items.add((int(t.get("top")), int(t.get("left")), text))
    names = {(top, text) for top, left, text in items if left < 100 and text in CODES}
    for top, state in sorted(names):
        near = sorted((left, text) for t, left, text in items if abs(t - top) <= 4 and 100 <= left < 600)
        line = " ".join(text for _, text in near)
        dates = re.findall(MS_DATE, line)
        base = dict(code=CODES[state], state=state, year=year, source=str(path.relative_to(HERE)),
                    source_updated=updated)
        if "No regular session" in line:
            rows.append({**base, "session": "No regular session", "type": "none"})
        elif dates:  # AR 2026 shows only its start date
            rows.append({**base, "session": f"{year} regular session", "type": "regular",
                         "convenes": ms_iso(dates[0]),
                         "adjourns": ms_iso(dates[1]) if len(dates) > 1 else "",
                         "notes": "" if len(dates) > 1 else "end date not shown"})
    page2 = subprocess.run(["pdftotext", "-layout", "-f", "2", "-l", "2", str(path), "-"],
                           capture_output=True, text=True, check=True).stdout
    for raw in page2.splitlines():
        state = next((s for s in CODES if raw.startswith(s + " ")), None)
        if not state:
            continue
        note = raw[len(state):].strip()
        kind = None
        pattern = "|".join(f"(?P<k{i}>{p})" for i, (p, _) in enumerate(MS_EVENTS))
        for m in re.finditer(rf"{pattern}|(?P<range>{MS_DATE}\s*-\s*{MS_DATE})|(?P<one>{MS_DATE})",
                             note, re.I):
            if m.group("range") or m.group("one"):
                if not kind:
                    continue
                ds = re.findall(MS_DATE, m.group(0))
                after = note[m.end():m.end() + 12].lower()
                before = note[max(0, m.start() - 12):m.start()].lower()
                # "canceled", "TBA sometime before 12/31", "reconvening monthly after 7/1"
                if "cancel" in after or "before" in before or "after" in before:
                    continue
                rows.append(dict(
                    code=CODES[state], state=state, year=int("20" + ds[0][2]), session=note,
                    type=kind, convenes=ms_iso(ds[0]), adjourns=ms_iso(ds[-1]),
                    source=str(path.relative_to(HERE)), source_updated=updated,
                    notes="" if len(ds) == 2 else "one date given"))
            else:
                kind = next(t for i, (_, t) in enumerate(MS_EVENTS) if m.group(f"k{i}"))
    return rows


# Date the congress/*.json files were last fetched from the API (update when re-fetched).
CONGRESS_FETCHED = "2026-11-26"


def parse_congress(path):
    """congress.gov API /v3/congress/<n> (saved as congress/congress-<n>.json): one row per
    session. Both chambers share their dates; if they ever differ, each gets its own row.
    An open session has no endDate: adjourns is left empty and the notes say "open"."""
    import json
    d = json.loads(path.read_text())["congress"]
    rows, seen = [], set()
    for s in d["sessions"]:
        key = (s["number"], s["startDate"], s.get("endDate", ""))
        if key in seen:
            continue
        seen.add(key)
        rows.append(dict(code="usa", state="US Congress", year=int(s["startDate"][:4]),
                         session=f"{d['name']}, session {s['number']}", type="regular",
                         convenes=s["startDate"], adjourns=s.get("endDate", ""),
                         source=f"congress.gov API ({path.relative_to(HERE)})",
                         source_updated=CONGRESS_FETCHED, notes="" if s.get("endDate") else "open"))
    return rows


def main():
    rows, seen_years, seen_specials = [], set(), set()
    for path in sorted((HERE / "congress").glob("congress-*.json")):
        rows += parse_congress(path)
    ms_years, ms_events = set(), set()
    for path, year, updated in calendars("multistate"):
        for r in parse_multistate(path, year, updated):
            if r["type"] in ("regular", "none"):
                if year in ms_years:  # newest version for the year wins
                    continue
            else:  # dated events: keep every version's, once
                key = (r["code"], r["type"], r.get("convenes"), r.get("adjourns"))
                if key in ms_events:
                    continue
                ms_events.add(key)
            rows.append(r)
        ms_years.add(year)
    for path, year, updated in calendars("legiscan"):
        regular, specials = parse(path, year, updated)
        if year not in seen_years:  # newest PDF for the year wins
            rows += regular
            seen_years.add(year)
        for s in specials:  # keep every special any version mentioned
            key = (s["code"], s["year"], s["convenes"])
            if key not in seen_specials:
                seen_specials.add(key)
                rows.append(s)
    for m in MANUAL:
        key = lambda r: (r["code"], int(r["year"]), r["session"])
        rows = [r for r in rows if key(r) != key(m)]
        rows.append({**{f: "" for f in FIELDS}, **m})
    rows.sort(key=lambda r: (r["code"], int(r["year"]), r.get("convenes") or "9999", r["type"], r["source"]))
    with open(HERE / "sessions.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to sessions.csv")


if __name__ == "__main__":
    main()
