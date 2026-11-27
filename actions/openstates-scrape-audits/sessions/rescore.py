#!/usr/bin/env python3
"""Step 7: per-state limits and a replay of 2026 with session status and run history.

    python3 rescore.py --db <history.sqlite> --out <dir>

Needs reaudit.py's `days` and `quiet_segments` tables. Writes <out>/profiles/<st>.json,
<out>/rescore.md, and tables `rescore_settings` and `rescore_alarms` in the database.

Scored only against the events in history/known_events.py that come from Tamara's notes, past
fixes and the git log. The overnight scanner's 14 (source "history scanner, unconfirmed") and
candidates.py are reported apart. Every number here is "how the rules fit 2026", not a blind
score: every state's history has been looked at (the real test is 2027).

Checks (decisions of 2026-11-26 in session-status-brief.md):
- quiet: days since the state's last new bill, action or vote. On a day with a green run, once
  the green in-session days since the last new data reach the state's limit: in session ->
  ALARM (marked `disagree` with each source's answer when the sources differ); every source out
  -> NOTE. Out-of-session days never count toward the limit (decision 2), and off or failed
  days don't count either (no evidence either way).
- run_failed: every day with runs and none green -> ALARM, in or out of session (decision 3).
- scraper_off: no run -> NOTE (in 2026 these were Tamara's hand pauses).
- no_new_bills: in session, new actions but no new bill for 21 green in-session days -> ALARM.
- empty_scrape, field_loss, broken_votes, chamber_swap, bill_drop: replay.py's per-scrape
  checks, unchanged (they don't depend on the calendar) -> ALARM.

Limits (`quiet`), learned per state only from quiet_in segments (green runs, in session) that
nothing explains (no notes, overnight or candidate event): the longest of those up to
SUSPECT_DAYS, + MARGIN, at least FLOOR, at most CAP. A state with fewer than MIN_IN_DAYS such
days takes the fleet median. Territories (reaudit.YEAR_ROUND) use their own looser rule.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "history"))
import candidates  # noqa: E402
import daily  # noqa: E402
import known_events  # noqa: E402
import reaudit  # noqa: E402
import replay  # noqa: E402

SUSPECT_DAYS = 21   # a longer unexplained in-session quiet run is a suspect, never learned as normal
MARGIN = 2
FLOOR = 7           # the old uniform default; above the measured lag in most states
CAP = 10            # Tamara's earlier cap (review of the overnight work): WI/MN learned freezes
MIN_IN_DAYS = 30    # green in-session days needed to learn a state's own limit
TERR_FLOOR, TERR_CAP = 14, 45  # territories: meetings are occasional
NO_NEW_BILLS_DAYS = 21
GRACE = replay.GRACE
PER_SCRAPE = {k: replay.CHECKS[k] for k in ("empty_scrape", "field_loss", "broken_votes", "chamber_swap", "bill_drop")}


def scored(st: str) -> list:
    return [e for e in known_events.events_for(st) if e.check and "history scanner" not in e.source]


def overnight(st: str) -> list:
    return [e for e in known_events.events_for(st) if "history scanner" in e.source]


def settings(con: sqlite3.Connection, st: str) -> dict:
    segs = con.execute("SELECT days FROM quiet_segments WHERE state = ? AND kind = ? AND explained_by IS NULL",
                       (st, "quiet_year_round" if st in reaudit.YEAR_ROUND else "quiet_in")).fetchall()
    lens = sorted(n for (n,) in segs)
    green_in = con.execute("SELECT COUNT(*) FROM days WHERE state = ? AND run = 'ok' AND kind IN ('new', 'quiet_in', "
                           "'quiet_year_round') AND status IN ('in_session','special','veto_or_lame_duck','prefiling')",
                           (st,)).fetchone()[0]
    if st in reaudit.YEAR_ROUND:
        p90 = lens[min(len(lens) - 1, math.ceil(0.9 * len(lens)) - 1)] if lens else 0
        v = min(TERR_CAP, max(TERR_FLOOR, p90 + 7))
        return {"quiet": v, "how": f"territory: 90th percentile of its quiet runs ({p90}) + 7, at least {TERR_FLOOR}, "
                                   f"at most {TERR_CAP}", "green_in_session_days": green_in,
                "suspects": [n for n in lens if n > v]}
    normal = [n for n in lens if n <= SUSPECT_DAYS]
    suspects = [n for n in lens if n > SUSPECT_DAYS]
    if green_in < MIN_IN_DAYS or not normal:
        why = (f"too few green in-session days ({green_in})" if green_in < MIN_IN_DAYS
               else f"no unexplained in-session quiet run of {SUSPECT_DAYS} days or less to learn from")
        return {"quiet": None, "how": why, "green_in_session_days": green_in,
                "suspects": suspects}
    v = min(CAP, max(FLOOR, normal[-1] + MARGIN))
    return {"quiet": v, "how": f"longest unexplained in-session quiet run up to {SUSPECT_DAYS} days ({normal[-1]}) "
                              f"+ {MARGIN}, at least {FLOOR}, at most {CAP}", "green_in_session_days": green_in,
            "suspects": suspects}


def quiet_and_runs(con, st: str, limit: int) -> dict[str, dict[date, str]]:
    rows = con.execute("SELECT d.day, d.run, d.status, d.disagree, d.kind, d.new_bills, d.new_actions, "
                       "s.legiscan, s.multistate, s.congress, s.manual FROM days d JOIN status_days s "
                       "USING (state, day) WHERE d.state = ? ORDER BY d.day", (st,)).fetchall()
    out = defaultdict(dict)
    count = 0
    nb_window: list = []
    for day, run, status, dis, kind, nbills, nacts, *src in rows:
        d = date.fromisoformat(day)
        inside = status in reaudit.S.IN
        if kind == "new":
            count = 0
        elif run == "ok" and inside:
            count += 1
        if run == "failed":
            out["run_failed"][d] = "runs, none green"
        elif run == "off":
            out["note:scraper_off"][d] = "no run"
        elif run == "ok" and kind != "new":
            said = dict(zip(reaudit.S.FAMILIES, src))
            who = ", ".join(f"{k}={v}" for k, v in said.items() if v)
            if inside and count >= limit:
                out["quiet"][d] = f"{count} green in-session days with nothing new (limit {limit})" + \
                    (f"; sources disagree: {who}" if dis else "")
            elif not inside and status != "unknown":
                out["note:quiet_out"][d] = f"nothing new, out of session ({who})"
        # no_new_bills: the last 21 green in-session days had new actions but no new bill
        if run == "ok" and inside:
            nb_window = (nb_window + [(nbills, nacts)])[-NO_NEW_BILLS_DAYS:]
            if len(nb_window) == NO_NEW_BILLS_DAYS and sum(a for _, a in nb_window) and not sum(b for b, _ in nb_window):
                out["no_new_bills"][d] = f"{NO_NEW_BILLS_DAYS} green in-session days with new actions, no new bill"
    return out


def matches(ep, ev) -> bool:
    s, e = date.fromisoformat(ev.start), date.fromisoformat(ev.end) + timedelta(days=GRACE)
    return ep[0] <= e and ep[1] >= s


CHECK_FOR = {"unchanged": "quiet"}  # old check name -> the check that should catch it now


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    con = sqlite3.connect(a.db)
    con.row_factory = None
    states = [r[0] for r in con.execute("SELECT DISTINCT state FROM days ORDER BY state")]
    sets = {st: settings(con, st) for st in states}
    measured = sorted(s["quiet"] for st, s in sets.items() if s["quiet"] and st not in reaudit.YEAR_ROUND)
    fleet = measured[len(measured) // 2]
    for st, s in sets.items():
        if s["quiet"] is None:
            s["quiet"], s["how"] = fleet, f"fleet median ({fleet}); {s['how']}"
    con.executescript("""
    DROP TABLE IF EXISTS rescore_settings;
    CREATE TABLE rescore_settings (state TEXT PRIMARY KEY, quiet_days INTEGER, how TEXT,
      green_in_session_days INTEGER, suspect_runs TEXT);
    DROP TABLE IF EXISTS rescore_alarms;
    CREATE TABLE rescore_alarms (state TEXT, check_name TEXT, level TEXT, start TEXT, end TEXT,
      days INTEGER, detail TEXT, matched TEXT, matched_kind TEXT);
    """)
    con2 = sqlite3.connect(a.db)
    con2.row_factory = sqlite3.Row
    caught, missed, alarms = [], [], []
    for st in states:
        s = sets[st]
        con.execute("INSERT INTO rescore_settings VALUES (?,?,?,?,?)",
                    (st, s["quiet"], s["how"], s["green_in_session_days"], json.dumps(s["suspects"])))
        fired = quiet_and_runs(con, st, s["quiet"])
        ds = daily.days(con2, st)
        for name, fn in PER_SCRAPE.items():
            fired[name] = fn(st, ds, [], None, None, con2)
        ev_scored, ev_night = scored(st), overnight(st)
        cands = [c for c in candidates.CANDIDATES if st in c.states]
        for name, days_ in fired.items():
            level = "note" if name.startswith("note:") else "alarm"
            for ep in replay.episodes(days_):
                hit = next((e for e in ev_scored if matches(ep, e)), None)
                kind = "scored" if hit else None
                if not hit:
                    hit = next((e for e in ev_night if matches(ep, e)), None)
                    kind = "overnight" if hit else None
                if not hit:
                    c = next((c for c in cands if ep[0] <= date.fromisoformat(c.end) + timedelta(days=GRACE)
                              and ep[1] >= date.fromisoformat(c.start)), None)
                    if c:
                        hit, kind = c, "candidate"
                what = (f"{hit.check}: {hit.what} ({hit.start})" if kind in ("scored", "overnight")
                        else f"{hit.name}" if kind else None)
                alarms.append((st, name.replace("note:", ""), level, str(ep[0]), str(ep[1]), ep[2], ep[3], what, kind))
        for e in ev_scored:
            want = CHECK_FOR.get(e.check, e.check)
            eps = [ep for ep in replay.episodes(fired.get(want, {})) if matches(ep, e)]
            if eps:
                start = date.fromisoformat(e.start)
                if want == "quiet":  # it can only fire on an in-session green day
                    first_in = con.execute("SELECT MIN(day) FROM days WHERE state = ? AND day >= ? AND run = 'ok' "
                                           "AND status IN ('in_session','special','veto_or_lame_duck','prefiling')",
                                           (st, e.start)).fetchone()[0]
                    start = max(start, date.fromisoformat(first_in)) if first_in else start
                caught.append((st, want, e, max(0, (eps[0][0] - start).days), eps[0]))
            else:
                missed.append((st, want, e))
    con.executemany("INSERT INTO rescore_alarms VALUES (?,?,?,?,?,?,?,?,?)", alarms)
    con.commit()
    (a.out / "profiles").mkdir(parents=True, exist_ok=True)
    for st, s in sets.items():
        (a.out / "profiles" / f"{st}.json").write_text(json.dumps({"state": st, **s}, indent=2) + "\n")
    write_md(a.out / "rescore.md", caught, missed, alarms, sets)
    print(f"{len(caught)} caught, {len(missed)} missed, "
          f"{sum(1 for x in alarms if x[2] == 'alarm' and not x[8])} alarms unexplained")


def write_md(path: Path, caught, missed, alarms, sets) -> None:
    L = ["# Re-audit replay: how the rules fit 2026\n",
         "Not a blind score: every state's 2026 history has been seen. Scored against the events from Tamara's "
         "notes, past fixes and the git log only. Generated by `sessions/rescore.py`.\n",
         "## By check\n", "| Check | Scored events | Caught | Median days to catch | Alarms | Explained by a scored event "
         "| by an overnight event | by a candidate | Unexplained |", "|---|---|---|---|---|---|---|---|---|"]
    names = sorted({x[1] for x in alarms if x[2] == "alarm"} | {x[1] for x in caught} | {x[1] for x in missed})
    for n in names:
        c = [x for x in caught if x[1] == n]
        m = [x for x in missed if x[1] == n]
        lags = sorted(x[3] for x in c)
        al = [x for x in alarms if x[1] == n and x[2] == "alarm"]
        L.append(f"| `{n}` | {len(c) + len(m)} | {len(c)} | {lags[len(lags) // 2] if lags else '—'} | {len(al)} | "
                 f"{sum(x[8] == 'scored' for x in al)} | {sum(x[8] == 'overnight' for x in al)} | "
                 f"{sum(x[8] == 'candidate' for x in al)} | {sum(x[8] is None for x in al)} |")
    notes = [x for x in alarms if x[2] == "note"]
    L.append(f"\nNotes (no alarm): {sum(x[1] == 'quiet_out' for x in notes)} out-of-session quiet stretches, "
             f"{sum(x[1] == 'scraper_off' for x in notes)} scraper-off stretches.\n")
    L += ["## Scored events: caught or missed\n", "| State | Check | Event | Started | Days to catch | Alarm |", "|---|---|---|---|---|---|"]
    rows = [(x[0], x[1], x[2], x[3], f"{x[4][0]} → {x[4][1]}") for x in caught] + \
           [(x[0], x[1], x[2], None, "**missed**") for x in missed]
    for st, n, e, lag, al in sorted(rows, key=lambda r: (r[1], r[0], r[2].start)):
        L.append(f"| {st} | `{n}` | {e.what} | {e.start} | {'—' if lag is None else lag} | {al} |")
    L += ["\n## Alarms nothing explains (a false alarm, or a failure nobody recorded)\n",
          "| State | Check | From | To | Days | What it saw |", "|---|---|---|---|---|---|"]
    for x in sorted((x for x in alarms if x[2] == "alarm" and not x[8]), key=lambda x: (x[1], x[0], x[3])):
        L.append(f"| {x[0]} | `{x[1]}` | {x[3]} | {x[4]} | {x[5]} | {x[6][:150]} |")
    L += ["\n## Limits\n", "| State | quiet (green in-session days) | How |", "|---|---|---|"]
    for st, s in sorted(sets.items()):
        L.append(f"| {st} | {s['quiet']} | {s['how']}{'; longer unexplained runs: ' + str(s['suspects']) if s['suspects'] else ''} |")
    path.write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
