#!/usr/bin/env python3
"""Each state's normal (Q15), from the history database: <out>/profiles/<st>.json.

Measured over the state's healthy days only: days outside every known failure
(known_events.py) and outside every stretch with no scrape for over 14 days. The profile says
how much healthy history it rests on; a state with too little (TX) is marked thin, and its
check thresholds fall back to the fleet's typical value.

What's in a profile:
- `source`: what it was built from (the raw history; later possibly a windy-civi repo).
- `session`: the 2026 calendar window, and how many healthy days fell in and out of it.
- `filing`: per session, when its bills first appeared relative to the session's start
  (prefiled / front-loaded / steady), or why that can't be told.
- `activity`: new bills, actions and votes per day, in session and out (median and 90th
  percentile), and the share of days with anything new.
- `quiet`: the longest healthy run of days with scrapes but nothing new, in session and out.
- `scrape_gaps`: the longest healthy gap between scrapes, in session and out (gaps during a
  fleet-wide outage left out).
- `fields`: the share of bills with each top-level field, latest and best.
- `votes`: whether it has roll calls, and the usual share whose counts don't match the voter
  list (WY's joint votes list both chambers: normal for WY).
- `session_switches`: nights a whole session left the scrape while another was scraped.
- `thresholds`: the per-state settings replay.py uses, each with how it was set.
- `caveats`: how this state's raw history misleads (known_events.CAVEATS), when known.

usage: python3 profiles.py [--db ...] [--out ...] wy ky ar ...      (or --all: every state in the database)
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import daily  # noqa: E402
import known_events  # noqa: E402

DEFAULT_OUT = Path("/Volumes/govbot-data/scratch/history-analysis")
LONG_GAP_DAYS = 14          # a gap this long is an outage, not normal (first-wave review)
THIN_DAYS = 60              # fewer healthy days than this: too thin to set its own thresholds
SUSPECT_QUIET_DAYS = 21     # an in-session quiet run longer than this is a suspected freeze, not normal
IN_SESSION_NO_SCRAPE_CAP = 7  # Tamara, 2026-11-26: never more than 7 days blind in session
UNCHANGED_CAP = 10          # review of the overnight work: WI (22) and MN (17) learned theirs from probable freezes
# Uniform defaults, used when a state has too little healthy history of its own.
DEFAULTS = {"no_scrape_in_session_days": 3, "no_scrape_out_of_session_days": 7, "unchanged_in_session_days": 7,
            "no_new_bills_in_session_days": 21}


def pct(xs: list[float], p: float):
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(math.ceil(p * len(xs))) - 1)] if p > 0 else xs[0]


def unhealthy_days(state: str, ds: list, commits: list[datetime]) -> set[date]:
    bad: set[date] = set()
    for e in known_events.events_for(state):
        bad |= set(daily.day_range(date.fromisoformat(e.start), date.fromisoformat(e.end)))
    for a, b in zip(commits, commits[1:]):
        if (b - a).total_seconds() > LONG_GAP_DAYS * 86400:
            bad |= set(daily.day_range(a.date() + timedelta(days=1), b.date()))
    return bad


def filing(con, state: str, cal, first_scrape: str) -> dict:
    w = cal.get(state)
    out = {}
    for sess, n, first in con.execute("SELECT session, COUNT(*), MIN(first_at) FROM bills WHERE state = ? "
                                      "GROUP BY session HAVING COUNT(*) >= 20", (state,)):
        firsts = [datetime.fromisoformat(r[0]).date() for r in con.execute(
            "SELECT first_at FROM bills WHERE state = ? AND session = ? ORDER BY first_at", (state, sess))]
        if first == first_scrape and firsts.count(firsts[0]) > 0.5 * n:
            out[sess] = {"bills": n, "pattern": "unknown: the raw history starts after most of its bills were filed"}
            continue
        if not w or not (firsts[0] <= w[1] and firsts[-1] >= w[0] - timedelta(days=60)):
            out[sess] = {"bills": n, "pattern": "unknown: not the 2026 calendar session",
                         "first_seen": str(firsts[0]), "last_new": str(firsts[-1])}
            continue
        conv = w[0]
        pre = sum(d < conv for d in firsts) / n
        by14 = sum(d <= conv + timedelta(days=14) for d in firsts) / n
        d50 = (firsts[int(0.5 * (n - 1))] - conv).days
        d90 = (firsts[int(0.9 * (n - 1))] - conv).days
        pattern = "prefiled" if pre >= 0.8 else "front-loaded" if by14 >= 0.8 else "steady"
        hit = [e for e in known_events.events_for(state) if e.check in ("unchanged", "empty_scrape", "no_new_bills")
               and date.fromisoformat(e.start) <= firsts[int(0.9 * (n - 1))]
               and date.fromisoformat(e.end) >= conv]
        out[sess] = {"bills": n, "pattern": pattern, "share_before_convene": round(pre, 3),
                     "share_by_convene_plus_14": round(by14, 3), "days_to_50pct": d50, "days_to_90pct": d90}
        if hit:
            out[sess]["caveat"] = "bills arrived late because of a known failure: " + "; ".join(e.what for e in hit)
    return out


def build(con: sqlite3.Connection, state: str, cal: dict, commits: list[datetime], fleet_days: set = frozenset()) -> dict:
    con.row_factory = sqlite3.Row
    ds = daily.days(con, state)
    run = con.execute("SELECT * FROM runs WHERE state = ?", (state,)).fetchone()
    if not ds:
        return {"state": state, "thin": True, "note": "no scrapes"}
    bad = unhealthy_days(state, ds, commits)
    healthy = [d for d in ds if d.d not in bad and d.d < daily.PAUSE]
    ins = [d for d in healthy if daily.in_session(cal, state, d.d)]
    outs = [d for d in healthy if not daily.in_session(cal, state, d.d)]
    w = cal.get(state)

    def act(sel):
        scraped = [d for d in sel if d.scrapes]
        return {"days_scraped": len(scraped),
                "share_with_anything_new": round(sum(d.new_info > 0 for d in scraped) / len(scraped), 3) if scraped else None,
                "new_bills_median": pct([d.new_bills for d in scraped], 0.5),
                "new_bills_p90": pct([d.new_bills for d in scraped], 0.9),
                "new_actions_median": pct([d.new_actions for d in scraped], 0.5),
                "new_actions_p90": pct([d.new_actions for d in scraped], 0.9),
                "new_votes_median": pct([d.new_votes for d in scraped], 0.5),
                "new_votes_p90": pct([d.new_votes for d in scraped], 0.9)}

    def quiet_runs(sel):
        """Runs of calendar days, all in `sel`, with nothing new (a day without a scrape counts as
        quiet too, as replay.py's `unchanged` check counts it): [(first day, days)]."""
        sset = {d.d for d in sel}
        out, start, n = [], None, 0
        for d in ds + [None]:
            if d is not None and d.d in sset and d.new_info == 0:
                start, n = (start or d.d), n + 1
            else:
                if n:
                    out.append((start, n))
                start, n = None, 0
        return out

    def quiet(sel, cap=None):
        lens = [n for _, n in quiet_runs(sel) if cap is None or n <= cap]
        return max(lens, default=0)

    def gaps(in_sess: bool):
        out = []
        for a, b in zip(commits, commits[1:]):
            days_ = (b - a).total_seconds() / 86400
            if days_ > LONG_GAP_DAYS or b.date() >= daily.PAUSE:
                continue
            mid = a + (b - a) / 2
            if mid.date() in bad or daily.in_session(cal, state, mid.date()) != in_sess:
                continue
            # A gap during a fleet-wide outage (3+ states quiet together, replay.fleet) isn't
            # this state's normal: early July's 7-13 day outage would otherwise set it.
            if any(d in fleet_days for d in daily.day_range(a.date(), b.date())):
                continue
            out.append(days_)
        return {"max_days": round(max(out), 2) if out else None, "p99_days": round(pct(out, 0.99), 2) if out else None,
                "count": len(out)}

    # In session, a long quiet run is not taken as normal: it may be a freeze nobody listed
    # (PA: 191 days). It's reported, and the threshold is set from the shorter runs.
    suspects = [{"from": str(a), "days": n} for a, n in quiet_runs(ins) if n > SUSPECT_QUIET_DAYS]
    q_in, q_out = quiet(ins, SUSPECT_QUIET_DAYS), quiet(outs)
    g_in, g_out = gaps(True), gaps(False)
    fields = {r["field"]: {"latest": r["share_latest"], "best": r["best_share"]} for r in con.execute(
        "SELECT field, share_latest, best_share FROM fields WHERE state = ? AND kind = 'top' ORDER BY field", (state,))}
    mm = [r["votes_count_mismatch"] / r["votes"] for d in healthy for r in d.rows if r["votes"]]
    has_votes = con.execute("SELECT SUM(votes) > 0 FROM scrapes WHERE state = ?", (state,)).fetchone()[0]
    switches = []
    prev = None
    for d in ds:
        for r in d.rows:
            if prev is not None and r["bills"]:
                before, after = json.loads(prev["bills_by_session"]), json.loads(r["bills_by_session"])
                left = {s: n for s, n in before.items() if s not in after}
                if left and set(after) - set(before):
                    switches.append({"at": r["committed_at"][:10], "left": left, "now": sorted(set(after) - set(before))})
            if r["bills"]:
                prev = r
    thin = len(healthy) < THIN_DAYS or len(ins) < 10
    th = {}

    def setting(name, value, how):
        th[name] = {"value": value, "how": how}

    if g_in["max_days"] is not None and len(ins) >= 10:
        setting("no_scrape_in_session_days",
                min(IN_SESSION_NO_SCRAPE_CAP, max(DEFAULTS["no_scrape_in_session_days"], math.ceil(g_in["max_days"]) + 1)),
                f"longest healthy in-session gap ({g_in['max_days']} days) + 1, at least "
                f"{DEFAULTS['no_scrape_in_session_days']}, at most {IN_SESSION_NO_SCRAPE_CAP}")
    if g_out["max_days"] is not None and len(outs) >= 10:
        setting("no_scrape_out_of_session_days", max(DEFAULTS["no_scrape_out_of_session_days"], math.ceil(g_out["max_days"]) + 1),
                f"longest healthy out-of-session gap ({g_out['max_days']} days) + 1, at least {DEFAULTS['no_scrape_out_of_session_days']}")
    if len(ins) >= 10:
        setting("unchanged_in_session_days", min(UNCHANGED_CAP, max(DEFAULTS["unchanged_in_session_days"], q_in + 2)),
                f"longest healthy in-session quiet run of at most {SUSPECT_QUIET_DAYS} days ({q_in}) + 2, at least "
                f"{DEFAULTS['unchanged_in_session_days']}, at most {UNCHANGED_CAP}" + (f"; longer runs are suspected freezes: {suspects}" if suspects else ""))
    return {
        "state": state,
        "source": {"kind": "raw history", "raw_repo": run["raw_repo"] if run else None,
                   "raw_head": run["raw_head"] if run else None, "scrapes": len([r for d in ds for r in d.rows]),
                   "first": str(ds[0].d), "last_scrape": max(str(d.d) for d in ds if d.scrapes)},
        "thin": thin,
        "session": {"calendar_2026": [str(w[0]), str(w[1])] if w else None,
                "full_time": state in daily.FULL_TIME,
                    "healthy_days_in_session": len(ins), "healthy_days_out_of_session": len(outs),
                    "unhealthy_days": len(bad)},
        "filing": filing(con, state, cal, con.execute("SELECT MIN(committed_at) FROM scrapes WHERE state = ?",
                                                      (state,)).fetchone()[0]),
        "activity": {"in_session": act(ins), "out_of_session": act(outs)},
        "quiet": {"longest_in_session_days": q_in, "longest_out_of_session_days": q_out,
                  "suspected_freezes_in_session": suspects},
        "scrape_gaps": {"in_session": g_in, "out_of_session": g_out},
        "fields": fields,
        "votes": {"has_votes": bool(has_votes),
                  "count_mismatch_share_median": round(pct(mm, 0.5), 4) if mm else None,
                  "count_mismatch_share_p90": round(pct(mm, 0.9), 4) if mm else None},
        "session_switches": switches,
        "thresholds": th,
        "caveats": known_events.CAVEATS.get(state, []),
    }


def fleet_fallback(profiles: dict[str, dict]) -> dict[str, dict]:
    """{setting: {value, how}}: the fleet's median of the states that measured it, else the default."""
    out = {}
    for name, default in DEFAULTS.items():
        vals = sorted(p["thresholds"][name]["value"] for p in profiles.values()
                      if name in p.get("thresholds", {}) and not p.get("thin")
                      and not p["thresholds"][name].get("how", "").startswith(("fleet", "uniform")))  # measured only
        fleet = vals[len(vals) // 2] if vals else default
        if name == "no_scrape_in_session_days":
            fleet = min(fleet, IN_SESSION_NO_SCRAPE_CAP)
        if name == "unchanged_in_session_days":
            fleet = min(fleet, UNCHANGED_CAP)
        out[name] = {"value": fleet, "measured_by": len(vals)}
    return out


def fill_defaults(profiles: dict[str, dict], fallback: dict = None) -> None:
    """A setting a state couldn't measure (thin, or no healthy in-session days) takes the fleet's
    median of the states that could (or the frozen fleet values, for a held-out test)."""
    fallback = fallback or fleet_fallback(profiles)
    for name in DEFAULTS:
        fleet, vals = fallback[name]["value"], fallback[name].get("measured_by", 0)
        for p in profiles.values():
            th = p.setdefault("thresholds", {})
            if p.get("thin") or name not in th:
                why = "too little healthy history" if p.get("thin") else "not measurable from this state's healthy days"
                th[name] = {"value": fleet, "how": f"fleet median of the measured states ({why})" if vals
                            else f"uniform default ({why})"}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("states", nargs="*")
    p.add_argument("--all", action="store_true")
    p.add_argument("--db", type=Path)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--raw-root", type=Path, default=Path("/Volumes/govbot-data/raw-scrapers"))
    p.add_argument("--frozen", type=Path, help="frozen-settings.json: use its fleet fallback values, for a held-out test")
    a = p.parse_args(argv)
    con = sqlite3.connect(str(a.db or a.out / "history.sqlite"))
    states = [r[0] for r in con.execute("SELECT state FROM runs ORDER BY state")] if a.all else [s.lower() for s in a.states]
    cal = daily.calendar()
    commits = daily.commit_times(a.raw_root)
    import replay  # the fleet check, to keep fleet-wide outages out of each state's normal gaps
    fleet_days = set(replay.fleet(commits))
    profiles = {s: build(con, s, cal, commits.get(s, []), fleet_days) for s in states}
    fill_defaults(profiles, json.loads(a.frozen.read_text())["fleet_fallback"] if a.frozen else None)
    (a.out / "profiles").mkdir(parents=True, exist_ok=True)
    for s, prof in profiles.items():
        (a.out / "profiles" / f"{s}.json").write_text(json.dumps(prof, indent=2, ensure_ascii=False) + "\n")
    print(f"{len(profiles)} profiles in {a.out / 'profiles'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
