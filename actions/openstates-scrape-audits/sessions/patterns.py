#!/usr/bin/env python3
"""Step 6: each state's patterns, from the re-audit tables.

    python3 patterns.py --db <history.sqlite> --csv-dir <dir>

Needs reaudit.py (days, status_days), action_dates.py (action_seen) and rescore.py
(rescore_alarms). Writes `state_patterns` (one row per state) and `session_tails` (one row per
state and session end) to the database, and a CSV of each.

- lag: days from an action's date to the UTC day of the first scrape that had it, over the full
  raw history. `lag_*` counts an action only when every day from its date to the day before it
  was seen had a green run and lay outside every data-delaying event (known, overnight or
  candidate, plus the 3 days after one): the wait was the source's, not ours (catch-ups after our own outages are left
  out; `lag_all_p90` keeps them, for comparison). Actions dated after the day they were seen
  (scheduled hearings) are left out. A state's first scrape is a backlog, never a lag.
- tail: for each in-session block (combined status, any source) of 14+ days that ended before
  the scrapers were paused, the actions dated after it ended and before the next block: how many
  days after the end they are dated (p90, max), and the last day one of them arrived.
- breaks: alarms by check from rescore.py (episodes), plus run failures and scraper-off days.
"""
from __future__ import annotations

import argparse
import csv
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "history"))
import candidates  # noqa: E402
import known_events  # noqa: E402
import status as S  # noqa: E402

PAUSE = date(2026, 9, 30)
MIN_BLOCK = 14
TAIL_HORIZON = 180  # days after a session's end that its tail may run, at most


def pct(xs: Counter, p: float):
    """Percentile of a {value: count} histogram."""
    n = sum(xs.values())
    if not n:
        return None
    k, acc = math.ceil(p * n), 0
    for v in sorted(xs):
        acc += xs[v]
        if acc >= k:
            return v


def event_days(st: str) -> set:
    out = set()
    # Only events that hold back new data: a field loss or broken roll calls doesn't delay actions.
    spans = [(e.start, e.end) for e in known_events.events_for(st)
             if e.check in ("unchanged", "no_new_bills", "empty_scrape", "no_scrape", "")] + \
            [(c.start, c.end) for c in candidates.CANDIDATES if st in c.states]
    for a, b in spans:  # + 3 days after the end: the catch-up scrape is not a normal day
        out |= set(S.days(date.fromisoformat(a), date.fromisoformat(b) + timedelta(days=3)))
    return out


def blocks(rows) -> list[tuple[date, date]]:
    out, start, prev = [], None, None
    for day, status in rows:
        d = date.fromisoformat(day)
        if status in S.IN:
            start = start or d
            prev = d
        elif start:
            out.append((start, prev))
            start = None
    if start:
        out.append((start, prev))
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--csv-dir", type=Path, required=True)
    a = p.parse_args()
    con = sqlite3.connect(a.db)
    con.executescript("""
    DROP TABLE IF EXISTS state_patterns;
    CREATE TABLE state_patterns (state TEXT PRIMARY KEY, actions_seen INTEGER, lag_median INTEGER,
      lag_p90 INTEGER, lag_all_p90 INTEGER, clean_actions INTEGER, tail_p90_days INTEGER,
      tail_max_days INTEGER, tail_last_arrival_days INTEGER, quiet_limit INTEGER, green_days INTEGER,
      failed_days INTEGER, failed_episodes INTEGER, longest_failed INTEGER, off_days INTEGER,
      quiet_in_alarms INTEGER, quiet_out_notes INTEGER, alarms_by_check TEXT, scored_events TEXT);
    DROP TABLE IF EXISTS session_tails;
    CREATE TABLE session_tails (state TEXT, block_start TEXT, block_end TEXT, next_start TEXT,
      actions_after INTEGER, dated_p90_days INTEGER, dated_max_days INTEGER, last_arrival TEXT,
      last_arrival_days INTEGER, PRIMARY KEY (state, block_end));
    """)
    states = [r[0] for r in con.execute("SELECT DISTINCT state FROM days ORDER BY state")]
    for st in states:
        days = {d: (run, kind) for d, run, kind in con.execute("SELECT day, run, kind FROM days WHERE state = ?", (st,))}
        bad = event_days(st)
        seen = con.execute("SELECT seen_day, action_day, n FROM action_seen WHERE state = ? AND seen_day IS NOT NULL",
                           (st,)).fetchall()
        lag_all, lag_clean = Counter(), Counter()
        # A lag is clean when every day from the action's date to the day before it was seen had a
        # green run and is outside every data-delaying event (and the 3 days after one): then the
        # wait was the source's, not ours. Catch-ups after a freeze or an outage drop out.
        dlist = sorted(days)
        first = date.fromisoformat(dlist[0]) if dlist else date.max
        unclean = [0]
        for dd in dlist:
            run, _ = days[dd]
            unclean.append(unclean[-1] + (run != "ok" or date.fromisoformat(dd) in bad))
        for sd, ad, n in seen:
            try:
                d, adt = date.fromisoformat(sd), date.fromisoformat(ad)
            except ValueError:
                continue
            lag = (d - adt).days
            if lag < 0:
                continue
            lag_all[lag] += n
            if adt < first:
                continue
            i, j = (adt - first).days, (d - first).days  # days[adt .. d-1]
            if unclean[j] - unclean[i] == 0 and d not in bad:
                lag_clean[lag] += n
        # Tails.
        rows = con.execute("SELECT day, status FROM status_days WHERE state = ? ORDER BY day", (st,)).fetchall()
        bl = [b for b in blocks(rows) if (b[1] - b[0]).days + 1 >= MIN_BLOCK and b[1] < PAUSE - timedelta(days=1)]
        allb = blocks(rows)
        tails = []
        for b0, b1 in bl:
            nxt = next((x[0] for x in allb if x[0] > b1), None)
            until = min(nxt or date.max, b1 + timedelta(days=TAIL_HORIZON))
            after = Counter()
            last = None
            for sd, ad, n in seen:
                try:
                    adt = date.fromisoformat(ad)
                except ValueError:
                    continue
                if b1 < adt < until:
                    after[(adt - b1).days] += n
                    last = max(last or sd, sd)
            tails.append((st, str(b0), str(b1), str(nxt) if nxt else None, sum(after.values()), pct(after, 0.9),
                          max(after) if after else None, last,
                          (date.fromisoformat(last) - b1).days if last else None))
        con.executemany("INSERT INTO session_tails VALUES (?,?,?,?,?,?,?,?,?)", tails)
        # Breaks.
        al = con.execute("SELECT check_name, level, COUNT(*), SUM(days) FROM rescore_alarms WHERE state = ? "
                         "GROUP BY check_name, level", (st,)).fetchall()
        by = {f"{c}" + ("" if lv == "alarm" else " (note)"): n for c, lv, n, _ in al}
        failed = [d for d, (run, _) in sorted(days.items()) if run == "failed"]
        longest, cur, prev = 0, 0, None
        for d in failed:
            dd = date.fromisoformat(d)
            cur = cur + 1 if prev and (dd - prev).days == 1 else 1
            longest, prev = max(longest, cur), dd
        ev = Counter(e.check or "caveat" for e in known_events.events_for(st) if "history scanner" not in e.source)
        lim = con.execute("SELECT quiet_days FROM rescore_settings WHERE state = ?", (st,)).fetchone()
        main_tail = max(tails, key=lambda t: t[4]) if tails else None  # the block with the most tail actions
        con.execute("INSERT INTO state_patterns VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            st, sum(lag_all.values()), pct(lag_clean, 0.5), pct(lag_clean, 0.9), pct(lag_all, 0.9),
            sum(lag_clean.values()),
            main_tail[5] if main_tail else None, main_tail[6] if main_tail else None, main_tail[8] if main_tail else None,
            lim[0] if lim else None, sum(r == "ok" for r, _ in days.values()), len(failed),
            by.get("run_failed", 0), longest, sum(r == "off" for r, _ in days.values()),
            by.get("quiet", 0), by.get("quiet_out (note)", 0),
            "; ".join(f"{k} {v}" for k, v in sorted(by.items())), "; ".join(f"{k} {v}" for k, v in sorted(ev.items()))))
    con.commit()
    a.csv_dir.mkdir(parents=True, exist_ok=True)
    for t in ("state_patterns", "session_tails"):
        cur = con.execute(f"SELECT * FROM {t} ORDER BY 1, 2")
        with open(a.csv_dir / f"{t}.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow([c[0] for c in cur.description])
            w.writerows(cur)


if __name__ == "__main__":
    main()
