#!/usr/bin/env python3
"""Replay the year through each candidate auditor check (Q16), state by state.

Each check is run as the auditor would have run it: on each UTC day, using only what was
committed by the end of that day. Alarm days are merged into alarms (an alarm ends when the
check stops firing). Then each alarm is matched to the known failures (known_events.py, plus
every gap of more than 14 days with no scrape, which is a fact in the git history):

- for each known failure: caught or missed, and how many days after it started;
- for each alarm that matches no known failure: listed for review. It is either a false alarm
  (the check fired on normal behaviour: a lesson for its threshold) or a failure nobody had
  noticed. The replay can't tell which.

Thresholds come from each state's profile (<out>/profiles/<st>.json, from profiles.py), or with
--uniform from one setting for every state, to compare the two.

The checks (CHECKS below):
  no_scrape        no scrape committed for N days (N in session, a longer N out of session)
  fleet_no_scrape  K or more states (of all 56 raw repos) stopped committing within 2 days of each other
  unchanged        in session, scrapes committed but nothing new (bill, action, vote) for N days
  no_new_bills     in session, new actions but no new bill for N days (MA's stuck bill count)
  empty_scrape     a committed scrape with no readable bill
  field_loss       a top-level field emptied on at least half of the 20+ bills that had it (option C guard (c))
  broken_votes     in one scrape, 1+ roll call with an error page as a voter (ND), or 20+ emptied (TN)
  chamber_swap     50+ actions in one scrape back under another chamber, same date and words (TN 07-02)
  bill_drop        5%+ of the bills (at least 20) gone in one scrape and still gone in the next, not
                   explained by a whole session leaving while a newer one is scraped (a session switch)

Hand commits under _data/ (daily.is_scrape) are not scrapes for any check. A state's no_scrape
waits while its silence began in a fleet alarm naming it, until the silence passes 14 days: the
fleet alarm already said it (review of step 5).

Output: <out>/replay.md, and a `replay_alarms` table in the history database.

usage: python3 replay.py [--uniform] [--db ...] [--out ...] [states...]   (default: every state in the database)
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import daily  # noqa: E402
import known_events  # noqa: E402
import profiles as profiles_mod  # noqa: E402

DEFAULT_OUT = Path("/Volumes/govbot-data/scratch/history-analysis")
FLEET_K = 3          # states going quiet together (4 missed TN + NJ + a third on 02-19; 3 raised no unexplained alarm)
FLEET_N = 2          # days without a commit that counts as "quiet" for the fleet check
FLEET_WINDOW = 2     # days within which they went quiet
LONG_GAP = 14        # days: a no-scrape gap this long is a known failure
GRACE = 3            # days after a failure ends during which an alarm still counts as catching it

ALARMS_SCHEMA = """
CREATE TABLE IF NOT EXISTS replay_alarms (    -- one row per alarm from a check replay (replay.py)
  mode TEXT NOT NULL,                         -- 'profile', 'uniform', 'heldout' or a --mode name
  state TEXT NOT NULL,                        -- jurisdiction, or 'fleet'
  check_name TEXT NOT NULL,                   -- replay.CHECKS
  start TEXT NOT NULL, end TEXT NOT NULL,     -- first and last UTC day it fired
  days INTEGER,                               -- days it fired
  detail TEXT,                                -- what it saw on the first day
  matched TEXT                                -- the known failure it caught, or NULL (for review)
);
"""


def end_of(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc)


def last_commit_before(commits: list[datetime], t: datetime):
    lo, hi = 0, len(commits)
    while lo < hi:
        mid = (lo + hi) // 2
        if commits[mid] <= t:
            lo = mid + 1
        else:
            hi = mid
    return commits[lo - 1] if lo else None


# Each check: (state, days, commits, calendar, thresholds, con) -> {day: detail}


def check_no_scrape(st, ds, commits, cal, th, con, fleet_days=None):
    """fleet_days: {day: (detail, states)} from fleet(). While a state's silence began inside a
    fleet alarm that names it, the fleet alarm has said it, so this one waits until the silence
    passes LONG_GAP days and becomes the state's own outage (review of step 5: the July fleet
    outage gave 14 held-out and most in-sample unmatched alarms)."""
    out = {}
    if not commits:
        return out
    named = sorted(d for d, (_, sts) in (fleet_days or {}).items() if st in sts)
    for d in daily.day_range(commits[0].date() + timedelta(days=1), daily.PAUSE - timedelta(days=1)):
        last = last_commit_before(commits, end_of(d))
        age = (end_of(d) - last).total_seconds() / 86400
        inside = daily.in_session(cal, st, d)
        n = th["no_scrape_in_session_days" if inside else "no_scrape_out_of_session_days"]["value"]
        in_fleet = any(last.date() <= f <= d for f in named)
        if age > n and not (in_fleet and age <= LONG_GAP):
            out[d] = f"no scrape for {age:.0f} days ({'in' if inside else 'out of'} session, limit {n})"
    return out


def check_unchanged(st, ds, commits, cal, th, con):
    n = th["unchanged_in_session_days"]["value"]
    out = {}
    for i, d in enumerate(ds):
        if i + 1 < n or not daily.in_session(cal, st, d.d) or d.d >= daily.PAUSE:
            continue
        window = ds[i + 1 - n:i + 1]
        if not all(daily.in_session(cal, st, x.d) for x in window):
            continue  # the whole window must be in session, or the run-up to it counts
        if any(x.scrapes for x in window) and all(x.new_info == 0 for x in window) \
                and any((x.bills or 0) > 0 for x in window):
            out[d.d] = f"{n} days of scrapes in session with no new bill, action or vote"
    return out


def check_no_new_bills(st, ds, commits, cal, th, con):
    n = th["no_new_bills_in_session_days"]["value"]
    out = {}
    for i, d in enumerate(ds):
        if i + 1 < n or not daily.in_session(cal, st, d.d) or d.d >= daily.PAUSE:
            continue
        window = ds[i + 1 - n:i + 1]
        if not all(daily.in_session(cal, st, x.d) for x in window):
            continue
        if sum(x.new_actions for x in window) > 0 and sum(x.new_bills for x in window) == 0:
            out[d.d] = f"{n} days in session with new actions but no new bill"
    return out


def per_scrape(pred):
    def check(st, ds, commits, cal, th, con):
        out = {}
        had_bills = False
        prev = None
        for d in ds:
            for r in d.rows:
                why = pred(r, prev, had_bills, con)
                if why and d.d < daily.PAUSE:
                    out.setdefault(d.d, why)
                had_bills = had_bills or r["bills"] > 0
                prev = r
        return out
    return check


def _empty(r, prev, had_bills, con):
    return "a scrape with 0 readable bills" if had_bills and r["bills"] == 0 else None


def _field_loss(r, prev, had_bills, con):
    rows = con.execute("SELECT field, lost, had FROM scrape_fields WHERE state = ? AND idx = ? AND had >= 20 "
                       "AND lost * 2 >= had AND field NOT LIKE '%.%' AND field NOT LIKE '%[%'",
                       (r["state"], r["idx"])).fetchall()
    return "; ".join(f"{f} lost on {l:,} of {h:,}" for f, l, h in rows) or None


ERROR_VOTERS_MIN = 1    # an error page as a voter is never legitimate (review, 2026-11-26)
EMPTIED_VOTES_MIN = 20  # emptied roll calls can be a scraper fixing its parsing (OK, HI), so a margin


def _broken_votes(r, prev, had_bills, con):
    why = []
    if r["votes_error_voters"] >= ERROR_VOTERS_MIN:
        why.append(f"{r['votes_error_voters']:,} with an error page as a voter")
    if r["votes_emptied"] >= EMPTIED_VOTES_MIN:
        why.append(f"{r['votes_emptied']:,} roll calls emptied")
    return "; ".join(why) or None


def _chamber_swap(r, prev, had_bills, con):
    n = r["actions_chamber_swapped"]
    if n < 50:
        return None
    top = json.loads(r["examples"] or "{}").get("chamber_swap_top") or []
    return f"{n:,} actions back under another chamber ({', '.join(top[:2])})"


def _drop(r, prev):
    """Bills gone in scrape r since prev, less a whole session leaving while another is still
    scraped: that is a session switch (KY 2025RS -> 2026RS; FL and GA following a newer special
    session), a profile item, not a drop."""
    before, after = json.loads(prev["bills_by_session"]), json.loads(r["bills_by_session"])
    return r["bills_gone"] - sum(n for s, n in before.items() if s not in after)


def check_bill_drop(st, ds, commits, cal, th, con):
    """5%+ of the bills (20+) gone in one scrape and still gone in the next one. A drop that the
    very next scrape undoes is a partial run (ME 04-04, MO 04-11 / 06-17 / 07-21, all came back):
    the review of step 5 asked for two scrapes. Fires on the day of the second scrape."""
    rows = [(d.d, r) for d in ds for r in d.rows]
    out = {}
    for i in range(1, len(rows) - 1):
        (_, prev), (_, r), (d2, nxt) = rows[i - 1], rows[i], rows[i + 1]
        if not r["bills"] or not prev["bills"] or d2 >= daily.PAUSE:
            continue
        gone = _drop(r, prev)
        # Still gone: the next scrape has no more than a quarter of them back.
        if gone >= max(20, 0.05 * prev["bills"]) and nxt["bills"] <= prev["bills"] - 0.75 * gone:
            out.setdefault(d2, f"{gone:,} of {prev['bills']:,} bills gone and still gone in the next scrape "
                               f"({r['bills_gone_back']:,} of all gone came back later)")
    return out


IN_SESSION_CHECKS = {"unchanged", "no_new_bills"}

CHECKS = {
    "no_scrape": check_no_scrape,
    "unchanged": check_unchanged,
    "no_new_bills": check_no_new_bills,
    "empty_scrape": per_scrape(_empty),
    "field_loss": per_scrape(_field_loss),
    "broken_votes": per_scrape(_broken_votes),
    "chamber_swap": per_scrape(_chamber_swap),
    "bill_drop": check_bill_drop,
}


def episodes(fired: dict[date, str]) -> list[tuple[date, date, int, str]]:
    """Merge alarm days into alarms: a gap of a day or more ends one."""
    out = []
    for d in sorted(fired):
        if out and (d - out[-1][1]).days <= 1:
            s, _, n, why = out[-1]
            out[-1] = (s, d, n + 1, why)
        else:
            out.append((d, d, 1, fired[d]))
    return out


def gap_events(st: str, commits: list[datetime]) -> list[known_events.Event]:
    """Every stretch of more than 14 days with no commit, before the pause."""
    out = []
    for a, b in zip(commits, commits[1:]):
        if (b - a).total_seconds() > LONG_GAP * 86400 and a.date() < daily.PAUSE:
            out.append(known_events.Event(st, "no_scrape", str(a.date() + timedelta(days=1)), str(min(b.date(), daily.PAUSE)),
                                          f"no scrape for {(b - a).total_seconds() / 86400:.0f} days", "git log"))
    last = commits[-1] if commits else None
    if last and (datetime(2026, 9, 30, tzinfo=timezone.utc) - last).days > LONG_GAP:
        out.append(known_events.Event(st, "no_scrape", str(last.date() + timedelta(days=1)), str(daily.PAUSE),
                                      f"no scrape from {last.date()} to the pause", "git log"))
    return out


def fleet(commits: dict[str, list[datetime]]) -> dict[date, tuple[str, set]]:
    """Days when FLEET_K+ states each passed FLEET_N days without a commit within FLEET_WINDOW
    days: {day: (detail, those states)}."""
    crossed = defaultdict(list)  # day a state's silence reached FLEET_N days -> states
    for st, cs in commits.items():
        for a, b in zip(cs, cs[1:] + [datetime(2026, 9, 30, tzinfo=timezone.utc)]):
            if (b - a).total_seconds() > FLEET_N * 86400:
                d = (a + timedelta(days=FLEET_N)).date()
                if d < daily.PAUSE:
                    crossed[d].append(st)
    out = {}
    for d in sorted(crossed):
        window = sorted({s for k in range(FLEET_WINDOW) for s in crossed.get(d - timedelta(days=k), [])})
        if len(window) >= FLEET_K:
            out[d] = (f"{len(window)} states quiet for {FLEET_N}+ days: {', '.join(window)}", set(window))
    return out


def matches(ep, ev) -> bool:
    s, e = date.fromisoformat(ev.start), date.fromisoformat(ev.end) + timedelta(days=GRACE)
    return ep[0] <= e and ep[1] >= s


def replay(con, states, mode: str, profs: dict, cal, commits) -> dict:
    con.row_factory = sqlite3.Row
    results = {"caught": [], "missed": [], "unmatched": [], "alarms": []}
    fired = fleet(commits)
    for st in states:
        ds = daily.days(con, st)
        th = profs[st]["thresholds"]
        known = [e for e in known_events.events_for(st) if e.check] + gap_events(st, commits.get(st, []))
        explained = known + [e for e in known_events.events_for(st) if not e.check]  # e.g. FL's caveat windows
        for name, fn in CHECKS.items():
            extra = {"fleet_days": fired} if name == "no_scrape" else {}
            eps = episodes(fn(st, ds, commits.get(st, []), cal, th, con, **extra))
            evs = [e for e in known if e.check == name]
            for ep in eps:
                hit = next((e for e in evs if matches(ep, e)), None)
                other = hit or next((e for e in explained if matches(ep, e)), None)
                results["alarms"].append((mode, st, name, str(ep[0]), str(ep[1]), ep[2], ep[3],
                                          f"{other.check}: {other.what} ({other.start})" if other else None))
                if other is None:
                    results["unmatched"].append((st, name, ep))
            for e in evs:
                eps_hit = [ep for ep in eps if matches(ep, e)]
                if eps_hit:
                    start = date.fromisoformat(e.start)
                    if name in IN_SESSION_CHECKS and cal.get(st) and st not in daily.FULL_TIME:
                        # it can only fire once the session starts
                        start = max(start, cal[st][0])
                    lag = max(0, (eps_hit[0][0] - start).days)
                    results["caught"].append((st, name, e, lag, eps_hit[0]))
                else:
                    results["missed"].append((st, name, e))
    # The fleet check: one alarm stream for all 56 repos, scored against every state's long gaps.
    feps = episodes({d: v[0] for d, v in fired.items()})
    allgaps = [g for st, cs in commits.items() for g in gap_events(st, cs)]
    for ep in feps:
        hits = [g for g in allgaps if date.fromisoformat(g.start) - timedelta(days=FLEET_N + FLEET_WINDOW) <= ep[0]
                <= date.fromisoformat(g.end)]
        results["alarms"].append((mode, "fleet", "fleet_no_scrape", str(ep[0]), str(ep[1]), ep[2], ep[3],
                                  f"{len(hits)} long gaps" if hits else None))
        if not hits:
            results["unmatched"].append(("fleet", "fleet_no_scrape", ep))
    for g in allgaps:
        s, e = date.fromisoformat(g.start), date.fromisoformat(g.end)
        day = next((d for d in sorted(fired) if s - timedelta(days=1) <= d <= e and g.state in fired[d][1]), None)
        if day:
            ep = next(ep for ep in feps if ep[0] <= day <= ep[1])
            results["caught"].append((g.state, "fleet_no_scrape", g, max(0, (day - s).days), ep))
        else:
            results["missed"].append((g.state, "fleet_no_scrape", g))
    return results


def write_md(path: Path, res: dict, mode: str, states: list[str], profs: dict) -> None:
    L = [f"# Check replays ({mode} thresholds)\n",
         f"States: {', '.join(states)}. Replayed day by day from each state's first scrape to the pause "
         f"(2026-09-30). The fleet check reads all 56 raw repos. Generated by `replay.py`; thresholds "
         f"{'the same for every state' if mode == 'uniform' else 'from each state profile'}.\n",
         "## Summary by check\n",
         "| Check | Known failures | Caught | Median days to catch | Worst | Alarms | Matching no known failure |",
         "|---|---|---|---|---|---|---|"]
    for name in list(CHECKS) + ["fleet_no_scrape"]:
        c = [x for x in res["caught"] if x[1] == name]
        m = [x for x in res["missed"] if x[1] == name]
        lags = sorted(x[3] for x in c)
        alarms = [a for a in res["alarms"] if a[2] == name]
        un = [u for u in res["unmatched"] if u[1] == name]
        L.append(f"| `{name}` | {len(c) + len(m)} | {len(c)} | {lags[len(lags) // 2] if lags else '—'} | "
                 f"{lags[-1] if lags else '—'} | {len(alarms)} | {len(un)} |")
    # The two no-scrape checks together, for these states: no_scrape waits while the fleet check
    # has a state's outage, so what matters is when either one first said it.
    first = {}
    for st, name, e, lag, _ in res["caught"]:
        if name in ("no_scrape", "fleet_no_scrape") and st in states and e.check == "no_scrape":
            first[(st, e.start)] = min(lag, first.get((st, e.start), lag))
    gaps = {(st, e.start) for st, name, e in res["missed"] if name == "no_scrape"} | \
           {(st, e.start) for st, name, e, *_ in res["caught"] if name == "no_scrape"}
    lags = sorted(first[g] for g in gaps if g in first)
    L.append(f"| either no-scrape check | {len(gaps)} | {len(lags)} | {lags[len(lags) // 2] if lags else '—'} | "
             f"{lags[-1] if lags else '—'} | | |")
    L.append("\n## Known failures: caught or missed\n")
    L.append("Days to catch count from the failure's start, or for the in-session checks (`unchanged`, "
             "`no_new_bills`) from the session's start if that was later: they can't fire before it.\n")
    L.append("| State | Check | Failure | Started | Caught after (days) | Alarm |")
    L.append("|---|---|---|---|---|---|")
    rows = [(x[0], x[1], x[2], x[3], f"{x[4][0]} → {x[4][1]}") for x in res["caught"]] + \
           [(x[0], x[1], x[2], None, "**missed**") for x in res["missed"]]
    for st, name, e, lag, al in sorted(rows, key=lambda r: (r[1], r[0], r[2].start)):
        L.append(f"| {st} | `{name}` | {e.what} | {e.start} | {'—' if lag is None else lag} | {al} |")
    L.append("\n## Alarms that match no known failure (false alarm, or a failure nobody noticed)\n")
    L.append("| State | Check | From | To | Days | What it saw |")
    L.append("|---|---|---|---|---|---|")
    for st, name, ep in sorted(res["unmatched"], key=lambda u: (u[1], u[0], u[2][0])):
        L.append(f"| {st} | `{name}` | {ep[0]} | {ep[1]} | {ep[2]} | {ep[3][:160]} |")
    L.append("\n## Thresholds used\n")
    L.append("| State | no scrape, in / out of session | unchanged | no new bills |")
    L.append("|---|---|---|---|")
    for st in states:
        th = profs[st]["thresholds"]
        L.append(f"| {st} | {th['no_scrape_in_session_days']['value']} / {th['no_scrape_out_of_session_days']['value']} | "
                 f"{th['unchanged_in_session_days']['value']} | {th['no_new_bills_in_session_days']['value']} |")
    L.append(f"\nFleet: {FLEET_K}+ states each {FLEET_N}+ days without a commit, within {FLEET_WINDOW} days. "
             f"Per-scrape checks use fixed limits (see `replay.py`).")
    path.write_text("\n".join(L) + "\n")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("states", nargs="*")
    p.add_argument("--uniform", action="store_true", help="one threshold for every state instead of its profile")
    p.add_argument("--db", type=Path)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--raw-root", type=Path, default=Path("/Volumes/govbot-data/raw-scrapers"))
    p.add_argument("--mode", help="name for this run (replay-<mode>.md and replay_alarms.mode), e.g. "
                                   "after-tuning-insample; default 'profile' or 'uniform'")
    p.add_argument("--frozen", type=Path, help="frozen-settings.json: refuse to run if this code's settings differ "
                                                "from it; writes replay-heldout.md")
    a = p.parse_args(argv)
    con = sqlite3.connect(str(a.db or a.out / "history.sqlite"))
    con.executescript(ALARMS_SCHEMA)
    states = [s.lower() for s in a.states] or [r[0] for r in con.execute("SELECT state FROM runs ORDER BY state")]
    mode = a.mode or ("uniform" if a.uniform else "profile")
    if a.frozen:
        import freeze
        frozen = json.loads(a.frozen.read_text())
        now = freeze.settings()
        if now["checks"] != frozen["checks"] or now["profile_method"] != frozen["profile_method"]:
            raise SystemExit(f"{a.frozen}: the checks or the profile method changed since the settings were frozen")
        mode = "heldout"
    if a.uniform:
        profs = {s: {"thresholds": {k: {"value": v, "how": "uniform"} for k, v in profiles_mod.DEFAULTS.items()}}
                 for s in states}
    else:
        profs = {s: json.loads((a.out / "profiles" / f"{s}.json").read_text()) for s in states}
    cal = daily.calendar()
    commits = daily.commit_times(a.raw_root)
    res = replay(con, states, mode, profs, cal, commits)
    with con:
        con.execute("DELETE FROM replay_alarms WHERE mode = ?", (mode,))
        con.executemany("INSERT INTO replay_alarms VALUES (?,?,?,?,?,?,?,?)", res["alarms"])
    out = a.out / f"replay-{mode}.md"
    write_md(out, res, mode, states, profs)
    print(f"{out}: {len(res['caught'])} caught, {len(res['missed'])} missed, {len(res['unmatched'])} alarms unmatched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
