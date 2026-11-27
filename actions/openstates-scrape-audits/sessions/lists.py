#!/usr/bin/env python3
"""Replay 2026 into the three lists Tamara would read: heads-up, needs you, ready to turn off.

    python3 lists.py --db <history.sqlite> --sessions <sessions.csv> --deadlines <intro_deadlines.csv> --out <dir>

Runs twice: mode `specified` (the rules as first given, 2026-11-26) and mode `revised` (with
Tamara's decisions and the reviewer's corrections on the first replay). Needs reaudit.py (days,
status_days), action_dates.py (action_seen), patterns.py (state_patterns) and deadlines.py.
Writes `list_items` (mode, list, rule, who, opened, closed, days, detail) and `list_weeks` (mode,
week, list, open, raised) to the database, <out>/lists.md (the two modes side by side) and CSVs.

The rules, `specified`:
Heads-up
  quiet_7          7 green days in a row with no new bill, action or vote (any session status)
  failed_run       any day with runs and none green
  broken_data      a per-scrape check (replay.py) fires, the day it appears
Needs you
  quiet_14         14 green in-session days (either source) with nothing new; GU/VI 45, MP 21
  special_no_end   a special session with no end date, 14 days after it convened: check the site
  failed_3         failed runs 3 days in a row; when 3+ states reach day 3 on the same day (±1)
                   it is one item for all of them
  empty_scrape, bill_drop, field_loss    still there 3 days later. Day 1 when the formatter would
                   pass the damage on: a field bill_guards.py doesn't guard.
  broken_votes, chamber_swap             2 scrapes in a row
  log only         what log_jsonl.SCRAPER_FAILURES already skips: ND error-page voters, TN emptied
                   roll calls
Ready to turn off (recommends; Tamara turns scrapers off herself)
  ready_off        14 green days with nothing new (GU/VI 45, MP 21), every source out of session,
                   the latest action dated between 7 days before the session's end and the end +
                   the state's tail, and the last 3 runs green

`revised` changes (2026-11-26):
- failed_3: a reopen within 7 days is the same item.
- ready_off: one item per out-of-session period; not when a session or prefiling starts within
  60 days (UT on 01-09); not when the state's quiet began the same day as 3+ other states' (the
  cache bug's signature: IL and NY on 08-04).
- broken data on 3+ states the same day is one fleet item (both lists).
- quiet_7 counts in session only (either source); out-of-session quiet states are one heads-up
  digest line per week (`quiet_out_digest`).
- no_new_bills (heads-up only): 21 green in-session days with new actions but no new bill, for
  states without an early intro deadline (within 31 days of convening); early-deadline states
  skip it after their deadline.
- chamber_swap: needs you on day 1 (the action logs only add lines, so a doubled action stays).
  broken_votes stay at 2 scrapes.
- bill_drop follows the 3-day rule from the night of the drop. Broken-data items stay open
  until the damage clears (bills back, the field back), so their days open mean something.

Later decisions (2026-11-26, all in `revised`):
- heads-up is dropped while the same state and kind is on needs you;
- a needs-you quiet or broken-data item open more than 30 days moves to `known_ongoing` (shown
  weekly with its day count, counted from when the damage began);
- accepted.csv (state, kind, reason, date): from its date, that state + kind goes to the log;
  kind `off` sends the state's off days to the log;
- `turn_on`: off (no runs) 2+ days in a row while a regular, special or prefiling starts within
  30 days (`starts_soon`) or one is running (`running_now`); a day when no repo ran at all is
  neutral for every state and one heads-up line (`no_scraper_ran`);
- heads-up failed runs start on the 2nd failed day in a row;
- with --timing, days are judged by finished runs only (reaudit.run_days_timed).

Counting: "green day" = a day with a green run, or before run history (01-07) a day with a scrape
commit. Off days (Tamara's pauses) and failed days neither count nor reset. An item is one line
from the day it opens until it clears; if the same item opens again within its reopen window
(2 days; failed_3 7 days in `revised`), it is the same item.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "history"))
sys.path.insert(0, str(HERE.parents[1] / "format"))
import daily  # noqa: E402
import known_events  # noqa: E402
import replay  # noqa: E402
import status as S  # noqa: E402
from utils.bill_guards import GUARDED_FIELDS  # noqa: E402

QUIET_HEADS_UP = 7
QUIET_NEEDS = 14
LONG = {"gu": 45, "vi": 45, "mp": 21}
SPECIAL_CHECK_DAYS = 14
FAILED_DAYS = 3
FLEET_STATES, FLEET_WINDOW = 3, 1
PERSIST_DAYS = 3
REOPEN_DAYS = 2
REOPEN_FAILED_REVISED = 7
END_MARGIN = 7            # the latest action must be dated at most this long before the session's end
SESSION_AHEAD_DAYS = 60   # revised: no ready_off when a session or prefiling starts within this
SAME_START_STATES = 4     # revised: no ready_off when the quiet began the same day in this many states
NO_NEW_BILLS_DAYS = 21
DROP_SHARE, DROP_MIN = 0.05, 20
OPEN_CAP_DAYS = 120       # broken-data items: stop marking an unrepaired item after this
GRACE = replay.GRACE
LOG_ONLY = {("nd", "error_voters"), ("tn", "emptied")}  # log_jsonl.SCRAPER_FAILURES
LISTS = ("heads_up", "needs_you", "known_ongoing", "ready_off", "turn_on")
ONGOING_DAYS = 30         # revised: a quiet or broken-data item open longer moves to "known ongoing"
ONGOING_RULES = ("quiet_14", "empty_scrape", "bill_drop", "field_loss", "chamber_swap", "broken_votes",
                 "no_bills_running", "session_left", "missed_session")
OFF_DAYS = 2              # "off" counts from the 2nd day in a row with no run
FAILED_HEADS_UP_DAYS = 2  # heads-up failed runs from the 2nd failed day in a row
TURN_ON_DAYS = 30         # revised: an off scraper with a session, special or prefiling starting within this
# heads-up rule -> the needs-you kind it duplicates (revised: dropped while that is on needs you)
HEADS_KIND = {"failed_run": "failed", "quiet_7": "quiet", "broken_data": "broken"}
NEEDS_KIND = {"failed_3": "failed", "quiet_14": "quiet", "empty_scrape": "broken", "bill_drop": "broken",
              "field_loss": "broken", "chamber_swap": "broken", "broken_votes": "broken",
              "no_bills_running": "quiet", "session_left": "broken", "missed_session": "quiet"}
BROKEN = ("empty_scrape", "bill_drop", "field_loss", "broken_votes", "chamber_swap", "broken_data", "session_left")


def limit(st: str) -> int:
    return LONG.get(st, QUIET_NEEDS)


class Items:
    """Daily on/off conditions -> items, with the reopen rule. A `group` (revised ready_off: the
    out-of-session period) makes every day in it one item, whatever the gaps."""

    def __init__(self, reopen: dict | None = None):
        self.on = defaultdict(set)      # (list, rule, who, group) -> days the condition held
        self.detail = {}
        self.reopen = reopen or {}

    def mark(self, lst, rule, who, d, detail="", group=None):
        k = (lst, rule, who, group)
        self.on[k].add(d)
        self.detail.setdefault((k, d), detail)

    def items(self):
        out = []
        for k, ds in self.on.items():
            ds = sorted(ds)
            gap = 10 ** 6 if k[3] is not None else self.reopen.get(k[1], REOPEN_DAYS)
            start = prev = ds[0]
            for d in ds[1:] + [None]:
                if d is not None and (d - prev).days <= gap + 1:
                    prev = d
                    continue
                out.append((k[0], k[1], k[2], start, prev, len([x for x in ds if start <= x <= prev]),
                            self.detail.get((k, start), "")))
                if d is not None:
                    start = prev = d
        return out


def fleet_broken(items: list) -> list:
    """Broken data on 3+ states the same day -> one fleet item per (list, rule, day)."""
    out, groups = [], defaultdict(list)
    for x in items:
        if x[1] in BROKEN and not x[2].startswith("fleet"):
            groups[(x[0], x[1], x[3])].append(x)
        else:
            out.append(x)
    for (lst, rule, opened), xs in groups.items():
        states = sorted({x[2] for x in xs})
        if len(states) >= FLEET_STATES:
            out.append((lst, rule, "fleet: " + " ".join(states), opened, max(x[4] for x in xs),
                        max(x[5] for x in xs), f"{len(states)} states the same day; e.g. {xs[0][6][:80]}"))
        else:
            out += xs
    return out


def per_scrape(con, st):
    con.row_factory = sqlite3.Row
    ds = daily.days(con, st)
    rows = [(d.d, r) for d in ds for r in d.rows]
    fired = {name: replay.CHECKS[name](st, ds, [], None, None, con)
             for name in ("empty_scrape", "field_loss", "broken_votes", "chamber_swap", "bill_drop")}
    return ds, rows, fired


def last_by(rows, d):
    best = None
    for day, r in rows:
        if day <= d:
            best = r
        else:
            break
    return best


def field_have(con, st, idx, f) -> int:
    """Bills with the field in that scrape (no row: none; the scan only writes fields some bill has)."""
    row = con.execute("SELECT have FROM scrape_fields WHERE state = ? AND idx = ? AND field = ?", (st, idx, f)).fetchone()
    return row[0] if row else 0


def broken(con, st, rows, fired, items: Items, revised: bool):
    by_day = defaultdict(list)
    for day, r in rows:
        by_day[day].append(r)
    seq = [r for _, r in rows]
    days_of = [day for day, _ in rows]
    pos = {r["idx"]: i for i, r in enumerate(seq)}
    last_day = rows[-1][0] if rows else None

    def still(pred, start, name, who_detail, began):
        """revised: mark needs-you from `start` while pred(last scrape by that day) holds."""
        d = start
        while d <= last_day and (d - start).days < OPEN_CAP_DAYS:
            r = last_by(rows, d)
            if r is None or not pred(r):
                break
            items.mark("needs_you", name, st, d, f"{who_detail}; began {began}")
            d += timedelta(days=1)

    for name, days_ in fired.items():
        for d, why in sorted(days_.items()):
            if name == "broken_votes":
                kinds = set()
                for r in by_day[d]:
                    if r["votes_error_voters"] >= replay.ERROR_VOTERS_MIN:
                        kinds.add("error_voters")
                    if r["votes_emptied"] >= replay.EMPTIED_VOTES_MIN:
                        kinds.add("emptied")
                if kinds and all((st, k) in LOG_ONLY for k in kinds):
                    items.mark("log", name, st, d, why)
                    continue
            if not (revised and name == "bill_drop"):  # revised: the drop's own night, below
                items.mark("heads_up", "broken_data", st, d, f"{name}: {why}")
            d3 = d + timedelta(days=PERSIST_DAYS - 1)
            later = last_by(rows, d3)
            if name == "empty_scrape":
                if later is not None and later["bills"] == 0 and d3 <= last_day:
                    if revised:
                        still(lambda r: r["bills"] == 0, d3, name, why, d)
                    else:
                        items.mark("needs_you", name, st, d3, why)
            elif name == "bill_drop" and not revised:
                first = by_day[d][0]
                i = pos[first["idx"]]
                before = seq[max(0, i - 2)]
                if later is not None and later["bills"] < 0.95 * before["bills"]:
                    items.mark("needs_you", name, st, d3, why)
            elif name == "field_loss":
                lost = {}
                for r in by_day[d]:
                    for f, had in con.execute("SELECT field, had FROM scrape_fields WHERE state = ? AND idx = ? "
                                              "AND had >= 20 AND lost * 2 >= had AND field NOT LIKE '%.%' "
                                              "AND field NOT LIKE '%[%'", (st, r["idx"])):
                        lost.setdefault(f, (had, r["idx"]))
                for f, (had, idx) in lost.items():
                    gone = (lambda r, f=f, had=had: field_have(con, st, r["idx"], f) * 2 < had)
                    if f not in GUARDED_FIELDS:  # passed on to metadata.json the first night
                        det = f"{f} (not guarded, in the data repo on day 1)"
                        if revised:
                            still(gone, d, name, det, d)
                        else:
                            items.mark("needs_you", name, st, d, det)
                        continue
                    if later is not None and gone(later):
                        if revised:
                            still(gone, d3, name, f"{f} still lost", d)
                        else:
                            items.mark("needs_you", name, st, d3, f"{f} still lost")
            elif name == "chamber_swap" and revised:
                items.mark("needs_you", name, st, d, why + " (in the action logs for good)")
            elif name in ("broken_votes", "chamber_swap"):
                rs = by_day[d]
                i = pos[rs[-1]["idx"]]
                if i + 1 < len(seq):
                    nxt = seq[i + 1]
                    if name == "chamber_swap":
                        ok = nxt["actions_chamber_swapped"] >= 50
                    else:
                        ok = ((nxt["votes_error_voters"] >= replay.ERROR_VOTERS_MIN and (st, "error_voters") not in LOG_ONLY)
                              or (nxt["votes_emptied"] >= replay.EMPTIED_VOTES_MIN and (st, "emptied") not in LOG_ONLY))
                    if ok:
                        items.mark("needs_you", name, st, date.fromisoformat(nxt["committed_at"][:10]), why)
    if revised:
        # bill_drop, 3-day rule from the drop's own night: 5%+ (20+) of the bills gone, less a
        # whole session leaving while another is scraped (replay._drop), and still gone 3 days on.
        for i in range(1, len(seq)):
            prev, r = seq[i - 1], seq[i]
            if not r["bills"] or not prev["bills"]:
                continue
            gone = replay._drop(r, prev)
            if gone < max(DROP_MIN, DROP_SHARE * prev["bills"]) or days_of[i] >= daily.PAUSE:
                continue
            d0 = days_of[i]
            floor = prev["bills"] - 0.75 * gone
            why = f"{gone:,} of {prev['bills']:,} bills gone"
            items.mark("heads_up", "broken_data", st, d0, f"bill_drop: {why}")
            d3 = d0 + timedelta(days=PERSIST_DAYS - 1)
            later = last_by(rows, d3)
            if later is not None and later["bills"] <= floor and d3 <= last_day:
                still(lambda x, floor=floor: x["bills"] <= floor, d3, "bill_drop", why + ", still gone 3 days on", d0)


def load_deadlines(path: Path) -> dict:
    """{(state, year): (early, latest deadline)} from deadlines.py's CSV."""
    out = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            dl = [date.fromisoformat(x) for x in (r["house"], r["senate"]) if x]
            out[(r["state"], int(r["year"]))] = (r["early"] == "True", max(dl) if dl else None)
    return out


def quiet_starts(con, states) -> dict:
    """{quiet start day: {states}} for every quiet streak (7+ green days) of every state."""
    out = defaultdict(set)
    for st in states:
        last_new, g = None, 0
        for day, run, kind, scrapes in con.execute("SELECT day, run, kind, scrapes FROM days WHERE state = ? ORDER BY day", (st,)):
            d = date.fromisoformat(day)
            if kind == "new":
                last_new, g = d, 0
            elif run == "ok" or (run == "no_record" and scrapes):
                g += 1
                if g == QUIET_HEADS_UP and last_new:
                    out[last_new + timedelta(days=1)].add(st)
    return out


def load_accepted(path: Path) -> dict:
    """{(state, kind): date accepted} from tamara-notes/session-dates/accepted.csv (hand-edited)."""
    out = {}
    if path and path.exists():
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                if r.get("state") and r.get("kind") and r.get("date"):
                    out[(r["state"].strip().lower(), r["kind"].strip())] = date.fromisoformat(r["date"].strip())
    return out


def starts_from(sessions_path: Path) -> dict:
    """{state: [(start day, what, source)]}: every regular and special session's convene date, and
    each prefiling start (a regular row whose notes say "Prefiling": from the source's date)."""
    out = defaultdict(list)
    with open(sessions_path, newline="") as f:
        for r in csv.DictReader(f):
            if r["type"] in ("regular", "special") and r["convenes"]:
                out[r["code"]].append((date.fromisoformat(r["convenes"]), f"{r['type']}: {r['session']}", r["source"]))
            if r["type"] == "regular" and "prefil" in r["notes"].lower() and r["source_updated"]:
                out[r["code"]].append((date.fromisoformat(r["source_updated"]), f"prefiling for {r['session']}",
                                       r["source"]))
    return out


NO_BILLS_DAYS = 14        # green in-session days into a session with no bill of its own (matches quiet; TN's lag ~10)
CARRY_RULES = ("quiet_14", "empty_scrape", "failed_3")  # a "missed session" carries these on as one line
OS_MATCH_DAYS = 14        # a calendar special is "listed" when an OpenStates session starts this close
SESSION_MATCH_DAYS = 3    # spans from different sources starting this close are one session


def session_spans(cal, st):
    """[(start, end or None, kind)] of the state's regular and special sessions, all sources;
    spans starting within SESSION_MATCH_DAYS of each other are one (earliest start, latest end)."""
    raw = sorted(((sp.start, sp.end, sp.kind) for (f, s_), sps in cal.spans.items() if s_ == st
                  for sp in sps if sp.kind in ("regular", "special")),
                 key=lambda x: (x[0], x[1] or date.max, x[2]))
    out = []
    for start, end, kind in raw:
        if out and out[-1][2] == kind and (start - out[-1][0]).days <= SESSION_MATCH_DAYS:
            s0, e0, k0 = out[-1]
            out[-1] = (s0, None if (e0 is None or end is None) else max(e0, end), k0)
        else:
            out.append((start, end, kind))
    return out


def scrape_index(con, st):
    """[(day, idx, bills, sessions)] of the state's scrapes (hand commits left out), in order."""
    out = []
    for idx, at, subj, bills, bbs in con.execute("SELECT idx, committed_at, subject, bills, bills_by_session "
                                                 "FROM scrapes WHERE state = ? ORDER BY idx", (st,)):
        if daily.is_scrape(subj):
            out.append((date.fromisoformat(at[:10]), idx, bills, set(json.loads(bbs or "{}"))))
    return out


def no_bills_running(con, cal, st, items: Items, os_starts: dict | None = None) -> bool:
    """Needs you: a regular or special session in session NO_BILLS_DAYS+ green days (either source)
    and no bill in the scrape whose first action is on or after its convene date (by dates, not
    session names: GA, VA and AR name sessions their own way). False when the state's bills carry
    no action dates (GU), so the rule can't judge it."""
    bills = [(date.fromisoformat(fa), fi, li) for fa, fi, li in con.execute(
        "SELECT first_action, first_idx, last_idx FROM bill_dates WHERE state = ? AND first_action IS NOT NULL", (st,))]
    if not bills:
        return False
    scr = scrape_index(con, st)
    days = con.execute("SELECT day, run, status FROM days WHERE state = ? ORDER BY day", (st,)).fetchall()
    for start, end, kind in session_spans(cal, st):
        mine = [(fi, li) for fa, fi, li in bills if fa >= start]
        green, si, idx = 0, 0, None
        for day, run, status in days:
            d = date.fromisoformat(day)
            while si < len(scr) and scr[si][0] <= d:
                idx = scr[si][1]
                si += 1
            if d < start or (end and d > end):
                continue
            if run == "ok" and status in S.IN:
                green += 1
            if green < NO_BILLS_DAYS or idx is None:
                continue
            if not any(fi <= idx <= li for fi, li in mine):
                listed = os_lists(os_starts or {}, st, start, kind)
                items.mark("needs_you" if listed else "log", "no_bills_running", st, d,
                           f"{kind} session from {start}: no bill with a first action on or after it"
                           + ("" if listed else "; OpenStates doesn't list this session") + f"; began {start}")
    return True


def session_left(con, cal, st, tail: int, items: Items) -> None:
    """Needs you: a whole session's bills leave the scrape (another session's bills still there)
    while either source has that session in session, or within the state's tail after its end. The
    departing session is placed by dates: the calendar span that holds its bills' latest first
    action (last actions can be effective dates years ahead: GA's run to 2028)."""
    scr = scrape_index(con, st)
    spans = session_spans(cal, st)
    last_day = scr[-1][0] if scr else None
    for (d0, i0, b0, s0), (d1, i1, b1, s1) in zip(scr, scr[1:]):
        if not b0 or not b1:
            continue
        for sess in sorted(s0 - s1):
            fa = con.execute("SELECT MAX(first_action) FROM bill_dates WHERE state = ? AND session = ?",
                             (st, sess)).fetchone()[0]
            if not fa:
                continue
            f = date.fromisoformat(fa)
            held = [sp for sp in spans if sp[0] <= f]
            if not held:
                continue
            start, end, kind = max(held, key=lambda sp: sp[0])
            if end is not None and d1 > end + timedelta(days=tail):
                continue  # a switch after the session and its tail: normal
            newer = [sp for sp in spans if sp[2] == "regular" and start < sp[0] <= d1]
            if any(con.execute("SELECT 1 FROM bill_dates WHERE state = ? AND first_action >= ? AND first_idx <= ? "
                               "AND last_idx >= ? LIMIT 1", (st, str(sp[0]), i1, i1)).fetchone() for sp in newer):
                continue  # a newer regular session has convened and its bills are in the scrape: turnover
            back = next((x[0] for x in scr if x[0] > d1 and sess in x[3]), None)
            stop = min(back - timedelta(days=1) if back else last_day, d1 + timedelta(days=OPEN_CAP_DAYS - 1))
            d = d1
            while d <= stop:  # every calendar day until it comes back: off days don't split the item
                items.mark("needs_you", "session_left", st, d,
                           f"session {sess} left the scrape on {d1} while running ({kind} {start} to {end or 'open'}, "
                           f"tail {tail}); began {d1}")
                d += timedelta(days=1)


def load_os_sessions(path) -> dict:
    """{state: [OpenStates session start dates]} from every version of the raw repos'
    jurisdiction_*.json (os_sessions.py). Classification isn't reliable (MO's specials say
    'primary'), so specials are matched by start date only."""
    if not path or not Path(path).exists():
        return {}
    out = {}
    for st, sessions in json.loads(Path(path).read_text()).items():
        out[st] = [date.fromisoformat(x["start_date"][:10]) for x in sessions if x.get("start_date")]
    return out


def os_lists(os_starts: dict, st: str, start: date, kind: str) -> bool:
    """Regular sessions count as listed (OpenStates lists two-year sessions whose dates go stale:
    AK's '34' ends 2025-05-21 but holds 2026's bills). A special is listed when an OpenStates
    session starts within OS_MATCH_DAYS of it. No data for the state -> assume listed."""
    if kind != "special" or st not in os_starts:
        return True
    return any(abs((s0 - start).days) <= OS_MATCH_DAYS for s0 in os_starts[st])


def carry_cover(items: Items) -> dict:
    """{(state, day): item key} of open quiet, empty-scrape and failed-runs needs-you items (a fleet
    failed-runs item covers each of its states): what a "missed session" carries on."""
    out = {}
    for k, days_ in items.on.items():
        if k[0] == "needs_you" and k[1] in CARRY_RULES:
            for s_ in k[2].replace("fleet: ", "").split():
                for d in days_:
                    out[(s_, d)] = k
    return out


def missed_session(con, cal, st, items: Items, os_starts: dict, through: date, cover: dict | None = None) -> None:
    """Needs you, the day after a regular or special session ends (every source: the merged span's
    end): no bill whose first action is inside its dates ever appeared in the scrape by then.
    Open until one appears. Log only when OpenStates doesn't list the session."""
    bills = [(date.fromisoformat(fa), fi) for fa, fi in con.execute(
        "SELECT first_action, first_idx FROM bill_dates WHERE state = ? AND first_action IS NOT NULL", (st,))]
    if not bills:
        return
    scr = scrape_index(con, st)
    if not scr:
        return
    day_of_idx = {idx: day for day, idx, _, _ in scr}
    for start, end, kind in session_spans(cal, st):
        if end is None or end < scr[0][0] or end + timedelta(days=1) > through:
            continue
        inside = [fi for fa, fi in bills if start <= fa <= end]
        first_seen = min((day_of_idx.get(fi, date.max) for fi in inside), default=date.max)
        d = end + timedelta(days=1)
        if first_seen < d:
            continue
        listed = os_lists(os_starts, st, start, kind)
        lst = "needs_you" if listed else "log"
        why = (f"{kind} session {start} to {end} ended; no bill first acted on inside it ever appeared"
               + ("" if listed else "; OpenStates doesn't list this session") + f"; began {d}")
        stop = min(first_seen - timedelta(days=1), through, d + timedelta(days=OPEN_CAP_DAYS - 1))
        carried = (cover or {}).get((st, end)) if listed else None
        while d <= stop:
            if carried:  # a quiet, empty-scrape or failed-runs item ran up to the end: the same line goes on
                items.mark(carried[0], carried[1], carried[2], d, why, carried[3])
            else:
                items.mark(lst, "missed_session", st, d, why)
            d += timedelta(days=1)


def fleet_skip_days(con) -> set:
    """Days when no repo ran at all (GitHub skipped the schedule: 2026-05-26, 07-05)."""
    return {date.fromisoformat(d) for (d,) in con.execute(
        "SELECT day FROM days WHERE day >= '2026-01-07' GROUP BY day HAVING SUM(run != 'off') = 0")}


def turn_on(con, cal, states, starts, items: Items, skip: set, accepted: dict) -> None:
    """A scraper off (no runs) for 2+ days in a row while a regular session, special or prefiling
    starts within TURN_ON_DAYS (any source), or while one is already running (`running_now`: a
    scraper switched off mid-session would otherwise show nowhere). A day when no repo ran at all
    is neutral (one fleet heads-up line instead). An accepted.csv line with kind `off` sends the
    state's off days to the log from its date."""
    for st in states:
        streak = 0
        for day, run in con.execute("SELECT day, run FROM days WHERE state = ? ORDER BY day", (st,)):
            d = date.fromisoformat(day)
            if d in skip:
                continue
            streak = streak + 1 if run == "off" else 0
            if streak < OFF_DAYS:
                continue
            soon = sorted(x for x in starts.get(st, []) if d < x[0] <= d + timedelta(days=TURN_ON_DAYS))
            now = S.status(cal, st, d).status
            lst = "log" if accepted.get((st, "off")) and d >= accepted[(st, "off")] else "turn_on"
            if soon:
                items.mark(lst, "starts_soon", st, d, f"{soon[0][1]} starts {soon[0][0]} ({soon[0][2]})")
            elif now in ("in_session", "special", "prefiling"):
                items.mark(lst, "running_now", st, d, f"{now} now, scraper off")


def build(con, cal, states, tails, fleet_tail, deadlines, sessions_path, revised: bool, accepted=None,
          os_starts=None):
    items = Items({"failed_3": REOPEN_FAILED_REVISED} if revised else {})
    failed_day3 = defaultdict(list)
    streaks = {}
    starts = quiet_starts(con, states) if revised else {}
    digest = defaultdict(set)  # revised: week -> out-of-session quiet states
    for st in states:
        rows = con.execute("SELECT day, run, status, disagree, kind, scrapes, new_bills, new_actions FROM days "
                           "WHERE state = ? ORDER BY day", (st,)).fetchall()
        seen = con.execute("SELECT COALESCE(seen_day, '0000'), MAX(action_day) FROM action_seen WHERE state = ? "
                           "GROUP BY 1 ORDER BY 1", (st,)).fetchall()
        tail = tails.get(st) or fleet_tail
        g_all = g_in = 0
        last_end = None
        last_new = None
        recent_runs: list = []
        fail_run: list = []
        nb_window: list = []
        si = 0
        latest_action = None
        for day, run, status, dis, kind, scrapes, nbills, nacts in rows:
            d = date.fromisoformat(day)
            while si < len(seen) and seen[si][0] <= day:
                latest_action = max(latest_action or seen[si][1], seen[si][1])
                si += 1
            inside = status in S.IN
            if inside:
                last_end = d
            green = run == "ok" or (run == "no_record" and scrapes)
            if kind == "new":
                g_all = g_in = 0
                last_new = d
            elif green:
                g_all += 1
                g_in += inside
            if run in ("ok", "failed"):
                recent_runs = (recent_runs + [run])[-3:]
            if run == "failed":
                fail_run.append(d)
                if not revised or len(fail_run) >= FAILED_HEADS_UP_DAYS:
                    items.mark("heads_up", "failed_run", st, d, f"failed {len(fail_run)} days in a row")
                if len(fail_run) == FAILED_DAYS:
                    failed_day3[d].append(st)
                if len(fail_run) >= FAILED_DAYS:
                    streaks.setdefault((st, fail_run[0]), []).append(d)
            elif run == "ok":
                fail_run = []
            quiet = green and kind != "new"
            # heads-up quiet
            if quiet and g_all >= QUIET_HEADS_UP:
                if not revised:
                    items.mark("heads_up", "quiet_7", st, d, f"{g_all} green days, nothing new")
                elif inside:
                    items.mark("heads_up", "quiet_7", st, d, f"{g_all} green days, nothing new, in session")
                else:
                    digest[d - timedelta(days=d.weekday())].add(st)
            # revised: no new bills while actions came (heads-up), not for early-deadline states after the deadline
            if revised and green and inside:
                nb_window = (nb_window + [(nbills, nacts)])[-NO_NEW_BILLS_DAYS:]
                early, dl = deadlines.get((st, d.year), (False, None))
                skip = early and dl is not None and d > dl
                if (not skip and len(nb_window) == NO_NEW_BILLS_DAYS and sum(a for _, a in nb_window)
                        and not sum(b for b, _ in nb_window)):
                    items.mark("heads_up", "no_new_bills", st, d,
                               f"{NO_NEW_BILLS_DAYS} green in-session days with new actions, no new bill")
            # needs you: quiet in session
            if quiet and inside and g_in >= limit(st):
                items.mark("needs_you", "quiet_14", st, d,
                           f"{g_in} green in-session days, nothing new" + (" (sources disagree)" if dis else "")
                           + (f"; began {last_new + timedelta(days=1)}" if last_new else ""))
            # ready to turn off
            if (quiet and g_all >= limit(st) and not inside and status != "unknown" and not dis
                    and last_end and latest_action
                    and str(last_end - timedelta(days=END_MARGIN)) <= latest_action <= str(last_end + timedelta(days=tail))
                    and recent_runs == ["ok"] * 3):
                if revised:
                    ahead = next((d + timedelta(days=k) for k in range(1, SESSION_AHEAD_DAYS + 1)
                                  if S.status(cal, st, d + timedelta(days=k)).status in S.IN), None)
                    qstart = last_new + timedelta(days=1) if last_new else None
                    crowd = len(starts.get(qstart, ())) if qstart else 0
                    if ahead or crowd >= SAME_START_STATES:
                        continue
                    items.mark("ready_off", "ready_off", st, d,
                               f"out of session since {last_end + timedelta(days=1)}; latest action {latest_action}; "
                               f"tail {tail}", group=str(last_end))
                else:
                    items.mark("ready_off", "ready_off", st, d,
                               f"out of session since {last_end + timedelta(days=1)}; latest action {latest_action}; "
                               f"tail {tail}")
        ds, srows, fired = per_scrape(con, st)
        con.row_factory = None
        broken(con, st, srows, fired, items, revised)
    used = set()
    for d in sorted(failed_day3):
        group = sorted({s for k in range(-FLEET_WINDOW, FLEET_WINDOW + 1) for s in failed_day3.get(d + timedelta(days=k), [])
                        if (s, d + timedelta(days=k)) not in used})
        if len(group) >= FLEET_STATES:
            who = "fleet: " + " ".join(group)
            for (s, start), ds_ in streaks.items():
                if s in group and abs(((start + timedelta(days=FAILED_DAYS - 1)) - d).days) <= FLEET_WINDOW:
                    for x in ds_:
                        items.mark("needs_you", "failed_3", who, x, f"{len(group)} states failing together")
                    used.add((s, start + timedelta(days=FAILED_DAYS - 1)))
    for (s, start), ds_ in streaks.items():
        if (s, start + timedelta(days=FAILED_DAYS - 1)) in used:
            continue
        for x in ds_:
            items.mark("needs_you", "failed_3", s, x, "failed 3+ days in a row")
    with open(sessions_path, newline="") as f:
        for r in csv.DictReader(f):
            if r["type"] == "special" and r["convenes"] and not r["adjourns"]:
                c = date.fromisoformat(r["convenes"])
                for k in range(SPECIAL_CHECK_DAYS, S.MISSING_END_DAYS):
                    items.mark("needs_you", "special_no_end", r["code"], c + timedelta(days=k),
                               f"{r['session']} ({r['source']}): no end date, check the state's site")
    if revised:
        skip = fleet_skip_days(con)
        turn_on(con, cal, states, starts_from(sessions_path), items, skip, accepted or {})
        for d in sorted(skip):
            items.mark("heads_up", "no_scraper_ran", "fleet", d, f"no scraper ran on {d}")
        through = max(date.fromisoformat(r[0]) for r in con.execute("SELECT MAX(day) FROM days"))
        cover = carry_cover(items)
        for st in states:
            if not no_bills_running(con, cal, st, items, os_starts):
                items.mark("log", "no_bills_running_unjudged", st, date(2026, 1, 7), "bills carry no action dates")
            session_left(con, cal, st, tails.get(st) or fleet_tail, items)
            missed_session(con, cal, st, items, os_starts or {}, through, cover)
        # fold "no bills" into an open quiet or empty-scrape item for the same state (one cause, one line)
        fold = set()
        for x in items.items():
            if x[0] == "needs_you" and x[1] in ("quiet_14", "empty_scrape"):
                d = x[3]
                while d <= x[4]:
                    fold.add((x[2], d))
                    d += timedelta(days=1)
        for k in list(items.on):
            if k[0] == "needs_you" and k[1] == "no_bills_running":
                kept = {d for d in items.on[k] if (k[2], d) not in fold}
                if kept:
                    items.on[k] = kept
                else:
                    del items.on[k]
        # drop a heads-up day while the same state and kind is on needs you
        cover = set()
        for x in items.items():
            if x[0] == "needs_you" and x[1] in NEEDS_KIND:
                for s_ in x[2].replace("fleet: ", "").split():
                    d = x[3]
                    while d <= x[4]:
                        cover.add((s_, NEEDS_KIND[x[1]], d))
                        d += timedelta(days=1)
        for k in list(items.on):
            if k[0] == "heads_up" and k[1] in HEADS_KIND:
                kept = {d for d in items.on[k] if (k[2], HEADS_KIND[k[1]], d) not in cover}
                if kept:
                    items.on[k] = kept
                else:
                    del items.on[k]
    out = items.items()
    if revised:
        out = fleet_broken(out)
        # accepted (accepted.csv): from its date, that state's items of that kind go to the log
        acc = accepted or {}
        moved = []
        for x in out:
            when = acc.get((x[2], x[1]))
            if x[0] == "needs_you" and when and x[4] >= when:
                moved.append(("log", x[1], x[2], max(x[3], when), x[4], x[5], "accepted: " + x[6]))
                if x[3] < when:
                    moved.append((x[0], x[1], x[2], x[3], when - timedelta(days=1), (when - x[3]).days, x[6]))
            else:
                moved.append(x)
        out = moved
        # open more than ONGOING_DAYS: the rest of the item is one weekly "known ongoing" line
        split = []
        for x in out:
            if x[0] == "needs_you" and x[1] in ONGOING_RULES and (x[4] - x[3]).days + 1 > ONGOING_DAYS:
                cut = x[3] + timedelta(days=ONGOING_DAYS)
                split.append((x[0], x[1], x[2], x[3], cut - timedelta(days=1), ONGOING_DAYS, x[6]))
                split.append(("known_ongoing", x[1], x[2], cut, x[4], (x[4] - cut).days + 1,
                              f"open since {x[3]} (day {ONGOING_DAYS + 1}+); {x[6]}"))
            else:
                split.append(x)
        out = split
        for wk, sts in digest.items():
            out.append(("heads_up", "quiet_out_digest", "digest", wk, wk + timedelta(days=6), 7,
                        f"{len(sts)} states quiet 7+ days, out of session: {' '.join(sorted(sts))}"))
    return out


def weeks_of(all_items):
    first_week = date(2025, 11, 24)
    last = max(x[4] for x in all_items)
    weeks, w = [], first_week
    while w <= last:
        we = w + timedelta(days=6)
        for lst in LISTS:
            its = [x for x in all_items if x[0] == lst]
            weeks.append((str(w), lst, sum(1 for x in its if x[3] <= we and x[4] >= w),
                          sum(1 for x in its if w <= x[3] <= we)))
        w += timedelta(days=7)
    return weeks


def score_known(all_items, con):
    """For each scored event (the 51 minus the 11 no check is meant to catch): the needs-you item
    that catches it and how late; else the heads-up item, or why not."""
    want = {"unchanged": {"quiet_14"}, "empty_scrape": {"empty_scrape"}, "field_loss": {"field_loss"},
            "broken_votes": {"broken_votes"}, "chamber_swap": {"chamber_swap"}, "no_new_bills": set()}
    out = []
    needs = [x for x in all_items if x[0] == "needs_you"]
    for e in known_events.EVENTS:
        if not e.check or "history scanner" in e.source:
            continue
        s, end = date.fromisoformat(e.start), date.fromisoformat(e.end) + timedelta(days=GRACE)

        def mine(x):
            return (x[2] == e.state or e.state in x[2].replace("fleet: ", "").split()) and x[3] <= end and x[4] >= s
        hits = [x for x in needs if x[1] in want.get(e.check, set()) and mine(x)
                and (e.check != "field_loss" or x[6].split()[0] in e.what or x[2].startswith("fleet"))]
        logged = [x for x in all_items if x[0] == "log" and x[1] == e.check and mine(x)]
        heads = [x for x in all_items if x[0] == "heads_up" and mine(x)
                 and (x[1] == "no_new_bills" if e.check == "no_new_bills" else
                      x[1] == "quiet_7" if e.check == "unchanged" else x[1] == "broken_data")]
        if hits:
            h = min(hits, key=lambda x: x[3])
            fi = con.execute("SELECT MIN(day) FROM days WHERE state = ? AND day >= ? AND status IN "
                             "('in_session','special','veto_or_lame_duck','prefiling') AND (run = 'ok' OR "
                             "(run = 'no_record' AND scrapes > 0))", (e.state, e.start)).fetchone()[0]
            from_in = (h[3] - max(s, date.fromisoformat(fi))).days if (fi and e.check == "unchanged") else None
            out.append((e, "caught", h, (h[3] - s).days, from_in))
        else:
            hh = min(heads, key=lambda x: x[3]) if heads else None
            why = ("log only (SCRAPER_FAILURES)" if logged else
                   "heads-up only" if not want.get(e.check) and hh else
                   "no rule" if not want.get(e.check) else "missed (needs you)")
            if hh:
                why += f"; heads-up {hh[1]} on day {max(0, (hh[3] - s).days)}"
            out.append((e, why, None, None, None))
    return out


def summary(weeks, lst, lo, hi, col):
    xs = [x for x in weeks if x[1] == lst and lo <= x[0] <= hi]
    v = sorted(x[col] for x in xs)
    worst = max(xs, key=lambda x: x[col])
    return v[len(v) // 2], worst[col], worst[0]


def evaluate_turn_on(con, items, starts, lo: date, hi: date, skip: set = frozenset()) -> list:
    """For each session, special or prefiling start from lo to hi: was the scraper off in the 30
    days before it, and if so, how many days before the start did "turn back on" first flag it?"""
    ton = [x for x in items if x[0] == "turn_on"]
    seen, out = set(), []
    for st, ss in sorted(starts.items()):
        for start, what, src in sorted(ss):
            if not (lo <= start <= hi) or (st, start, what.split(":")[0]) in seen:
                continue
            seen.add((st, start, what.split(":")[0]))
            w0 = start - timedelta(days=TURN_ON_DAYS)
            runs = dict(con.execute("SELECT day, run FROM days WHERE state = ? AND day BETWEEN ? AND ?",
                                    (st, str(w0), str(start))).fetchall())
            off_all = sorted(d for d, r in runs.items() if r == "off")
            off = [d for d in off_all if date.fromisoformat(d) not in skip]  # fleet-wide skipped days are neutral
            flags = [x for x in ton if x[2] == st and x[3] <= start and x[4] >= w0]
            if not runs:
                res, lead = "outside the replay's days", None
            elif not off:
                res, lead = ("scraper on (nothing to flag)" if not off_all else
                             "scraper on (its only off day was a day no repo ran)"), None
            elif flags:
                first = min(max(x[3], w0) for x in flags)
                lead = (start - first).days
                back_on = next((d for d in sorted(runs) if d >= off[-1] and runs[d] != "off"), None)
                res = (f"flagged {lead} days ahead" if lead > 0 else "flagged on the day") + \
                      (f"; back on {back_on}" if back_on else "; still off at the start")
            elif not any((date.fromisoformat(a) - date.fromisoformat(b)).days == 1 for a, b in zip(off[1:], off)):
                res, lead = "off only single days (below the 2-day rule)", None
            else:
                res, lead = "NOT flagged", None
            out.append((st, str(start), what, src, res, lead))
    return out


def notice_from_pdfs(here: Path) -> list:
    """For each LegiScan special and each next-year regular session: the first PDF version that
    lists it, so how much notice a fetch of that version would have given."""
    sys.path.insert(0, str(here))
    import build_sessions_csv as B
    first = {}
    for path, year, updated in sorted(B.calendars("legiscan"), key=lambda c: c[2]):
        regular, specials = B.parse(path, year, updated)
        for r in specials + [x for x in regular if x["type"] == "regular" and x["convenes"]]:
            key = (r["code"], r["type"], r["convenes"])
            first.setdefault(key, (updated, r["session"]))
    out = []
    for (code, typ, conv), (upd, sess) in sorted(first.items()):
        if typ == "special" or conv[:4] > upd[:4]:
            out.append((code, typ, sess, conv, upd, (date.fromisoformat(conv) - date.fromisoformat(upd)).days))
    return out


def write(out: Path, items, weeks, score, ton_eval, notice) -> None:
    (out / "csv").mkdir(parents=True, exist_ok=True)
    with open(out / "csv" / "list_items.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["list", "rule", "who", "opened", "closed", "days", "detail"])
        w.writerows(sorted(items, key=lambda x: (x[0], x[3], x[2])))
    with open(out / "csv" / "list_weeks.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["week", "list", "open_items", "raised"])
        w.writerows(weeks)
    with open(out / "csv" / "turn_on_starts.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["state", "start", "what", "source", "result", "days_ahead"])
        w.writerows(ton_eval)
    L = ["# Four-list replay of 2026, revised rules (fit to 2026, not a blind test)\n"]
    for lo, hi, label in (("2026-01-05", "2026-09-28", "weeks of 2026-01-05 to 2026-09-28 (scrapers on)"),
                          ("2026-10-05", "2026-11-23", "weeks of 2026-10-05 to 2026-11-23 (paused; 9 states ran)")):
        L += [f"\n## Weekly counts, {label}\n",
              "| List | Open: median | Open: worst (week) | New: median | New: worst (week) | New: total |",
              "|---|---|---|---|---|---|"]
        for lst in LISTS:
            m, wv, ww = summary(weeks, lst, lo, hi, 2)
            m2, wv2, ww2 = summary(weeks, lst, lo, hi, 3)
            tot = sum(x[3] for x in weeks if x[1] == lst and lo <= x[0] <= hi)
            L.append(f"| {lst} | {m} | {wv} ({ww}) | {m2} | {wv2} ({ww2}) | {tot} |")
    L += ["\n## Items opened 2026-01-05 to 2026-09-28, by list and rule\n", "| List | Rule | Items | Median days open |",
          "|---|---|---|---|"]
    by = defaultdict(list)
    for x in items:
        if "2026-01-05" <= str(x[3]) <= "2026-09-28":
            by[(x[0], x[1])].append(x[5])
    for (lst, r), v in sorted(by.items()):
        v = sorted(v)
        L.append(f"| {lst} | {r} | {len(v)} | {v[len(v) // 2]} |")
    L += ["\n## Known failures (revised)\n",
          "| State | Event | Started | Result | Item | Days after start | Days after first green in-session day |",
          "|---|---|---|---|---|---|---|"]
    for e, rr, h, late, late_in in sorted(score, key=lambda s: (s[0].check, s[0].state, s[0].start)):
        L.append(f"| {e.state} | {e.check}: {e.what[:70]} | {e.start} | {rr} | "
                 f"{f'{h[1]} {h[3]}→{h[4]}' if h else '—'} | {'—' if late is None else late} | "
                 f"{'—' if late_in is None else late_in} |")
    L += ["\n## Turn back on: every session, special and prefiling start, 2026-01-07 to 2026-12-25\n",
          "| State | Start | What | Source | Result |", "|---|---|---|---|---|"]
    for st, start, what, src, res, _ in ton_eval:
        L.append(f"| {st} | {start} | {what[:60]} | {src} | {res} |")
    L += ["\n## Notice in the LegiScan PDFs: the first version that lists each special or next-year session\n",
          "| State | Type | Session | Convenes | First listed (PDF updated) | Days of notice |", "|---|---|---|---|---|---|"]
    for row in notice:
        L.append("| " + " | ".join(str(c) for c in row) + " |")
    wk = date(2026, 9, 14)
    L += [f"\n## Known ongoing, as the weekly section would show it (week of {wk})\n"]
    for x in sorted((x for x in items if x[0] == "known_ongoing" and x[3] <= wk + timedelta(days=6) and x[4] >= wk),
                    key=lambda x: x[2]):
        m = re.search(r"began (\d{4}-\d{2}-\d{2})", x[6])  # from when the damage began
        since = date.fromisoformat(m.group(1) if m else x[6].split("open since ", 1)[1][:10])
        day_n = (min(x[4], wk + timedelta(days=6)) - since).days + 1
        what = re.sub(r"; began \d{4}-\d{2}-\d{2}", "", x[6].split("; ", 1)[1] if "; " in x[6] else x[6])
        L.append(f"- {x[2].upper()} {x[1]} ({what[:70]}), day {day_n}")
    for lst in ("needs_you", "known_ongoing", "ready_off", "turn_on"):
        L += [f"\n## Every {lst} item\n", "| Rule | Who | Opened | Closed | Days | Detail |", "|---|---|---|---|---|---|"]
        for x in sorted((x for x in items if x[0] == lst), key=lambda x: (x[3], x[2])):
            L.append(f"| {x[1]} | {x[2]} | {x[3]} | {x[4]} | {x[5]} | {x[6][:120].replace('|', '/')} |")
    (out / "lists.md").write_text("\n".join(L) + "\n")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--sessions", type=Path, required=True)
    p.add_argument("--deadlines", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--accepted", type=Path, help="tamara-notes/session-dates/accepted.csv")
    p.add_argument("--os-sessions", type=Path, help="os_sessions.py's JSON: OpenStates' session list per state")
    p.add_argument("--timing", action="store_true",
                   help="judge days by finished runs only (days.run_timed / kind_timed, see reaudit.py)")
    a = p.parse_args()
    con = sqlite3.connect(a.db)
    if a.timing:
        # a temp view shadows main.days for every query below
        con.execute("CREATE TEMP VIEW days AS SELECT state, day, run_timed AS run, status, disagree, scrapes, "
                    "new_bills, new_actions, new_votes, kind_timed AS kind FROM main.days")
    cal = S.load(a.sessions)
    states = [r[0] for r in con.execute("SELECT DISTINCT state FROM days ORDER BY state")]
    tails = {st: t for st, t in con.execute("SELECT state, tail_p90_days FROM state_patterns")}
    measured = sorted(t for t in tails.values() if t is not None)
    fleet_tail = measured[len(measured) // 2]
    deadlines = load_deadlines(a.deadlines)
    items = build(con, cal, states, tails, fleet_tail, deadlines, a.sessions, True, load_accepted(a.accepted),
                  load_os_sessions(a.os_sessions))
    con.row_factory = None
    weeks = weeks_of(items)
    score = score_known(items, con)
    ton_eval = evaluate_turn_on(con, items, starts_from(a.sessions), date(2026, 1, 7), date(2026, 12, 25),
                                fleet_skip_days(con))
    notice = notice_from_pdfs(a.sessions.parent)
    con.executescript("""
    DROP TABLE IF EXISTS list_items;
    CREATE TABLE list_items (list TEXT, rule TEXT, who TEXT, opened TEXT, closed TEXT, days INTEGER, detail TEXT);
    DROP TABLE IF EXISTS list_weeks;
    CREATE TABLE list_weeks (week TEXT, list TEXT, open_items INTEGER, raised INTEGER, PRIMARY KEY (week, list));
    DROP TABLE IF EXISTS turn_on_starts;
    CREATE TABLE turn_on_starts (state TEXT, start TEXT, what TEXT, source TEXT, result TEXT, days_ahead INTEGER);
    """)
    con.executemany("INSERT INTO list_items VALUES (?,?,?,?,?,?,?)",
                    [(l, r, w, str(o), str(c), n, det) for l, r, w, o, c, n, det in items])
    con.executemany("INSERT INTO list_weeks VALUES (?,?,?,?)", weeks)
    con.executemany("INSERT INTO turn_on_starts VALUES (?,?,?,?,?,?)", ton_eval)
    con.commit()
    write(a.out, items, weeks, score, ton_eval, notice)
    print(len(items), "items")


if __name__ == "__main__":
    main()
