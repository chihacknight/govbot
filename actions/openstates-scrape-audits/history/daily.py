"""Day-by-day views of the history, shared by profile.py and replay.py.

- `calendar()`: each state's 2026 session window, from tamara-notes/session-dates/old-notes/session-calendar-2026.md
  (LegiScan, one regular session per state; special sessions are not in it, so a special session
  counts as out of session).
- `commit_times()`: every scrape commit time of every raw repo (all 56, not only the scanned
  ones), read with `git log`: what the fleet check needs.
- `is_scrape()`: a data commit made by a scrape, not by hand. The 9 hand commits under `_data/`
  (7 "chore: clear duplicate-accumulated scrape data" on 07-21, "Delete _data/sd directory",
  NH's "fix: restore ... wiped") are left out of every check: they are neither freshness nor
  an empty scrape.
- `days()`: one row per state and UTC day from the database's `scrapes` table.

Days are UTC dates. The history ends at PAUSE: the scrapers were paused on purpose on 2026-09-30.
"""
from __future__ import annotations

import re
import sqlite3
import subprocess
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
CALENDAR = HERE.parents[2] / "tamara-notes" / "session-dates" / "old-notes" / "session-calendar-2026.md"
PAUSE = date(2026, 9, 30)  # PR #180: scrapers paused for the migration; no alarms from here on
# Full-time legislatures (and Congress, and the D.C. Council): in session all year, whatever the
# calendar's convene/adjourn says. Their two-year sessions run the whole time, so news can come
# any day (review of the profiles step, 2026-11-26). The list is NCSL's full-time legislatures
# plus USA and DC; the territories are already all year in the calendar.
FULL_TIME = {"ca", "il", "ma", "mi", "nj", "ny", "oh", "pa", "wi", "usa", "dc"}


# Subjects of the commits a scrape makes (scrape.sh and the auto-save/merge steps); every other
# subject under _data/ is a hand commit. Measured over all 56 raw repos, 2026-11-26.
SCRAPE_SUBJECTS = ("Scrape data", "Auto-save in-progress scrape", "Auto-merge: kept scraped data")


def is_scrape(subject: Optional[str]) -> bool:
    s = subject or ""
    return any(k in s for k in SCRAPE_SUBJECTS) or s.startswith("Merge branch")


def calendar(path: Path = CALENDAR) -> dict[str, Optional[tuple[date, date]]]:
    """{state: (convenes, adjourns)} or None for "No Regular Session"."""
    out: dict[str, Optional[tuple[date, date]]] = {}
    for line in path.read_text().splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) < 6 or not re.fullmatch(r"[a-z]{2,3}", cells[1]):
            continue
        m = [re.fullmatch(r"\d{4}-\d{2}-\d{2}", c) for c in cells[4:6]]
        out[cells[1]] = (date.fromisoformat(cells[4]), date.fromisoformat(cells[5])) if all(m) else None
    return out


def in_session(cal: dict, state: str, d: date) -> bool:
    if state in FULL_TIME:
        return True
    w = cal.get(state)
    return bool(w) and w[0] <= d <= w[1]


def commit_times(raw_root: Path) -> dict[str, list[datetime]]:
    """{state: [commit time, ...]} oldest first, for every <st>-legislation raw repo."""
    out = {}
    for repo in sorted(raw_root.glob("*-legislation")):
        st = repo.name.split("-", 1)[0]
        log = subprocess.run(["git", "-C", str(repo), "log", "--format=%cI%x09%s", "--", f"_data/{st}/"],
                             capture_output=True, text=True).stdout.splitlines()
        out[st] = sorted(datetime.fromisoformat(t).astimezone(timezone.utc)
                         for t, _, subj in (line.partition("\t") for line in log) if is_scrape(subj))
    return out


def day_range(first: date, last: date):
    d = first
    while d <= last:
        yield d
        d += timedelta(days=1)


class Day:
    """One state's day: its scrapes (UTC date), and what they showed."""

    __slots__ = ("d", "scrapes", "bills", "new_bills", "new_actions", "new_votes", "rows")

    def __init__(self, d: date) -> None:
        self.d = d
        self.scrapes = 0
        self.bills = None       # bills in the day's last scrape
        self.new_bills = self.new_actions = self.new_votes = 0
        self.rows: list[sqlite3.Row] = []

    @property
    def new_info(self) -> int:
        return self.new_bills + self.new_actions + self.new_votes


def days(con: sqlite3.Connection, state: str) -> list[Day]:
    """Every UTC day from the state's first scrape to the pause (or its last scrape, if later)."""
    con.row_factory = sqlite3.Row
    rows = [r for r in con.execute("SELECT * FROM scrapes WHERE state = ? ORDER BY idx", (state,))
            if is_scrape(r["subject"])]
    if not rows:
        return []
    by_day = defaultdict(list)
    for r in rows:
        by_day[datetime.fromisoformat(r["committed_at"]).date()].append(r)
    first = min(by_day)
    last = max(max(by_day), PAUSE - timedelta(days=1))
    out = []
    for d in day_range(first, last):
        day = Day(d)
        for r in by_day.get(d, []):
            day.scrapes += 1
            day.bills = r["bills"]
            if r["idx"] > 0:  # the first scrape's bills are all "new"
                day.new_bills += r["bills_new"]
                day.new_actions += r["actions_new"]
                day.new_votes += r["votes_new"]
            day.rows.append(r)
        out.append(day)
    return out
