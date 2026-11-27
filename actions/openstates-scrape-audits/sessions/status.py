#!/usr/bin/env python3
"""Session status for one state on one day, from every source in sessions.csv.

    python3 status.py <sessions.csv> <state> <YYYY-MM-DD> [<YYYY-MM-DD end>]   # prints one line per day

`status(cal, state, day)` returns a Status:
    status     in_session | special | veto_or_lame_duck | prefiling | out_of_session |
               no_regular_session | unknown (no source covers that day)
    sources    {source family: its answer, or None when it doesn't cover the day}
    disagree   True when the covering sources don't agree on in vs out
    estimated  True when an answer rests on an estimated date (red in LegiScan, a default end)

Source families (from the CSV's `source` column): legiscan (the PDFs Tamara downloads),
multistate (MultiState PDFs), congress (congress.gov API), manual (hand rows: territories,
specials with known dates, corrections).

Rules, each for one known case:
- Any source saying in session wins the status (decision 2: either source says in -> alarm);
  `disagree` says when another source said out. Priority when several kinds hit:
  special > veto_or_lame_duck > in_session > prefiling.
- A source only answers "out" for a state and year when it has a regular or "none" row for
  that state and year (a whole calendar). Hand rows that are only specials (Alaska's) say
  "in" on their own dates and nothing on other days.
- Veto sessions, lame ducks and reconvened sessions count as in session (decision 4).
- Organizational days and informal sessions don't count (MA's informal session Aug-Dec).
  A recess takes days out of a regular session (NJ Jul-Nov 2025), not out of a special.
- A row with no end date: congress.gov marks an open session ("open" in notes) -> runs on. Any
  other row with no end takes another source's end when that source has a row of the same kind
  starting within SPECIAL_MATCH_DAYS (LegiScan's MD 08-03 special -> MultiState's 08-05;
  MultiState's AR 2026 regular -> LegiScan's 04-29); without a match (LegiScan's ND 09-02 and
  SC 05-15 specials) it is given MISSING_END_DAYS, estimated.
- Prefiling: a regular row whose notes say "Prefiling" (LegiScan's 2027 PDF) means prefiling
  was open on the PDF's date, so days from `source_updated` to the day before it convenes.
- Within one source, a regular row ends the day before that state's next regular row begins
  (LegiScan's 2025 PDFs give WI, MA, NY, CA... rows running into 2026 or 2027; its 2026 PDF
  says WI met 01-13 to 03-19). "Interim Recess <date>" in a regular row's notes (IL, NY 2025)
  is a recess from that date to the row's end.
- A two-year legislature listed as one row per year (MultiState: WI 2025 to 12-31, then 2026
  from 01-13) stays in session across the New Year gap, within the same source.
"""
import csv
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

MISSING_END_DAYS = 30
SPECIAL_MATCH_DAYS = 3  # a no-end special borrows the end of another source's special starting this close
# How far into January a biennium's second year may start and still bridge the New Year gap.
BIENNIUM_GAP_DAYS = 45
MONTHS = {m: i for i, m in enumerate(
    "January February March April May June July August September October November December".split(), 1)}
IN = ["special", "veto_or_lame_duck", "in_session", "prefiling"]  # priority order
KIND = {"regular": "in_session", "special": "special", "veto": "veto_or_lame_duck",
        "reconvene": "veto_or_lame_duck"}


def family(source: str) -> str:
    if source.startswith("congress.gov"):
        return "congress"
    if source.startswith("sources/multistate/"):
        return "multistate"
    if source.startswith("sources/legiscan/"):
        return "legiscan"
    return "manual"


@dataclass
class Span:
    kind: str            # a CSV type
    start: date
    end: Optional[date]  # None: open
    estimated: bool
    notes: str
    updated: Optional[date]
    start_estimated: bool = False  # the convene date alone (prefiling ends there)
    no_end: bool = False           # the source gave no end date (MISSING_END_DAYS was assumed)


@dataclass
class Calendar:
    spans: dict = field(default_factory=lambda: defaultdict(list))   # (family, state) -> [Span]
    whole: set = field(default_factory=set)                           # (family, state, year)
    none_years: set = field(default_factory=set)                      # (family, state, year)


def _d(s: str) -> Optional[date]:
    return date.fromisoformat(s) if s else None


def load(path) -> Calendar:
    cal = Calendar()
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            fam, st, year = family(r["source"]), r["code"], int(r["year"])
            if r["type"] in ("regular", "none"):
                cal.whole.add((fam, st, year))
            if r["type"] == "none":
                cal.none_years.add((fam, st, year))
                continue
            start = _d(r["convenes"])
            if not start:
                continue
            end, est = _d(r["adjourns"]), bool(r["convenes_estimated"] or r["adjourns_estimated"])
            no_end = end is None and "open" not in r["notes"]
            if no_end:
                end, est = start + timedelta(days=MISSING_END_DAYS - 1), True
            cal.spans[(fam, st)].append(Span(r["type"], start, end, est, r["notes"], _d(r["source_updated"]),
                                                  bool(r["convenes_estimated"]), no_end))
    # A row with no end date takes another source's end when that source has a row of the same
    # kind starting within SPECIAL_MATCH_DAYS of it (LegiScan's MD 08-03 special -> MultiState's
    # 08-03 to 08-05; MultiState's AR 2026 regular, which shows no end -> LegiScan's 04-29).
    for (fam, st), spans in cal.spans.items():
        for sp in spans:
            if not sp.no_end:
                continue
            other = [o for (f2, s2), os_ in cal.spans.items() if s2 == st and f2 != fam for o in os_
                     if o.kind == sp.kind and not o.no_end and o.end and abs((o.start - sp.start).days) <= SPECIAL_MATCH_DAYS]
            if other:
                best = min(other, key=lambda o: abs((o.start - sp.start).days))
                sp.end, sp.estimated, sp.no_end = best.end, best.estimated, False
                sp.notes += f" (end from another source's {sp.kind} row starting {best.start})"
    for spans in cal.spans.values():
        spans.sort(key=lambda s: s.start)
        regs = [s for s in spans if s.kind == "regular"]
        for a, b in zip(regs, regs[1:]):
            # A biennium row from an older calendar (LegiScan 2025: WI to 2026-12-31) ends where
            # the same source's next regular row begins: the newer calendar wins.
            if b.start > a.start and (a.end is None or a.end >= b.start):
                a.end = b.start - timedelta(days=1)
        for r in regs:
            # "Interim Recess May 31" (LegiScan, IL and NY 2025): out from that date to the row's end.
            m = re.search(r"Interim Recess (" + "|".join(MONTHS) + r") (\d{1,2})", r.notes)
            if m and r.end:
                rs = date(r.start.year, MONTHS[m.group(1)], int(m.group(2)))
                if rs < r.start:
                    rs = date(r.start.year + 1, rs.month, rs.day)
                if rs <= r.end:
                    spans.append(Span("recess", rs, r.end, False, "from the regular row's notes", r.updated))
        spans.sort(key=lambda s: s.start)
    return cal


def _covers(s: Span, day: date) -> bool:
    return s.start <= day and (s.end is None or day <= s.end)


def _bridged(spans: list, day: date) -> Optional[Span]:
    """The regular span before `day` if `day` falls in a New Year gap between two regular rows."""
    regs = [s for s in spans if s.kind == "regular" and s.end]
    for a, b in zip(regs, regs[1:]):
        if (a.end.month, a.end.day) == (12, 31) and a.end < day < b.start \
                and (b.start - a.end).days <= BIENNIUM_GAP_DAYS:
            return a
    return None


def answer(cal: Calendar, fam: str, state: str, day: date) -> tuple[Optional[str], bool]:
    """One source's answer for the day, and whether it is estimated."""
    spans = cal.spans.get((fam, state), [])
    hits = [s for s in spans if _covers(s, day)]
    recess = any(s.kind == "recess" for s in hits)
    found = []
    for s in hits:
        k = KIND.get(s.kind)
        if k and not (recess and k == "in_session"):
            found.append((k, s.estimated))
    for s in spans:  # prefiling: from the date the source said it was open, until it convenes
        if s.kind == "regular" and "prefil" in s.notes.lower() and s.updated and s.updated <= day < s.start:
            found.append(("prefiling", s.start_estimated))
    if not found and (b := _bridged(spans, day)):
        found.append(("in_session", b.estimated))
    if found:
        k = min(found, key=lambda x: IN.index(x[0]))[0]
        return k, any(e for kk, e in found if kk == k)
    if (fam, state, day.year) in cal.none_years:
        return "no_regular_session", False
    if (fam, state, day.year) in cal.whole:
        return "out_of_session", False
    return None, False


@dataclass
class Status:
    state: str
    day: date
    status: str
    sources: dict
    disagree: bool
    estimated: bool


FAMILIES = ["legiscan", "multistate", "congress", "manual"]


def status(cal: Calendar, state: str, day: date) -> Status:
    answers, est = {}, False
    for fam in FAMILIES:
        a, e = answer(cal, fam, state, day)
        answers[fam] = a
        est = est or (e and a in IN)
    said = {a for a in answers.values() if a}
    ins = [a for a in said if a in IN]
    if ins:
        st = min(ins, key=IN.index)
    elif said:
        st = "no_regular_session" if said == {"no_regular_session"} else "out_of_session"
    else:
        st = "unknown"
    disagree = len({a in IN for a in said}) > 1
    return Status(state, day, st, answers, disagree, est)


def days(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def main(argv):
    cal = load(argv[1])
    start = date.fromisoformat(argv[3])
    end = date.fromisoformat(argv[4]) if len(argv) > 4 else start
    for d in days(start, end):
        s = status(cal, argv[2], d)
        src = " ".join(f"{k}={v}" for k, v in s.sources.items() if v)
        print(f"{d} {s.status}{' DISAGREE' if s.disagree else ''}{' est' if s.estimated else ''}  {src}")


if __name__ == "__main__":
    main(sys.argv)
