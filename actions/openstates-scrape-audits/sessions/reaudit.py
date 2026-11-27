#!/usr/bin/env python3
"""Re-audit of the 2026 history with run history and session status (steps 4-5 of
tamara-notes/processes/workstreams/shared-docs/session-status-brief.md).

    python3 reaudit.py --db <history.sqlite> --runs <dir of <st>.jsonl> \
        --sessions <sessions.csv> --csv-dir <dir> [--through YYYY-MM-DD]

Reads (never writes) the scan's `scrapes` table and adds these tables to the same database,
replacing them on every run (idempotent):

- days.run_timed / kind_timed: the same day judged by the timing rule (run_days_timed): only
  finished runs count; a run still queued or running is "running" (neutral), over 24 hours it is
  "failed".
- run_days: one row per state and UTC day: the Actions runs that started that day and how
  they ended. `run` = ok (a run succeeded) | failed (runs, none succeeded: failure, cancelled,
  startup_failure) | off (no run) | no_record (before RUNS_FROM: GitHub has no run history).
- status_days: one row per state and day, status.py's answer.
- days: the two joined with what the day's scrapes brought (new bills, actions, votes) and
  `kind` for a day with nothing new: off | failed | quiet_out | quiet_in | quiet_unknown, or
  no_record_<in|out|unknown> before RUNS_FROM. A day with new data has kind 'new'.
- quiet_segments: each run of consecutive days with nothing new and the same kind.
- quiet_stretches: each run of consecutive days with nothing new, with its days per kind.

A day's runs: by the run's start time (UTC date). The `<st>.jsonl` files are the raw repos'
`gh api .../actions/runs` (read-only), one JSON object per run.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "history"))
import status as S  # noqa: E402
import candidates  # noqa: E402,F401
from daily import is_scrape  # noqa: E402

RUNS_FROM = date(2026, 1, 7)  # first run on record in every raw repo (checked 2026-11-26)
# Territories whose hand rows say "year-round": the legislature exists all year but meets far
# less, so a quiet day there is its own kind (quiet_year_round), judged by a looser limit.
YEAR_ROUND = {"gu", "mp", "vi"}


def run_days(runs_dir: Path) -> dict[str, dict[date, Counter]]:
    out: dict[str, dict[date, Counter]] = defaultdict(lambda: defaultdict(Counter))
    for f in sorted(runs_dir.glob("*.jsonl")):
        for line in f.read_text().splitlines():
            r = json.loads(line)
            d = date.fromisoformat((r.get("run_started_at") or r["created_at"])[:10])
            out[f.stem][d][r.get("conclusion") or r.get("status") or "unknown"] += 1
    return out


def _t(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def run_days_timed(runs_dir: Path, jobs_dir: Path, through: date) -> dict[str, dict[date, str]]:
    """The timing rule: judge a day only on finished runs. Per state and day: ok (a run finished
    green that day) > failed (a run finished not green, or one queued or running for more than 24
    hours) > running (a run still queued or in progress at the end of the day, under 24 hours).
    A run's finish is its jobs' last completed_at (jobs_dir/<st>-<id>.json, from the jobs API)
    when fetched; else updated_at. updated_at is not trustworthy for old runs: GitHub moves it
    when it expires their logs (WI's March runs show November), so every run whose updated_at
    looks more than 24 hours after created_at had its jobs fetched. A run never finished
    (status queued: FL and OH since 2026-09-13) is unfinished through `through`."""
    rank = {"ok": 3, "failed": 2, "running": 1}
    out: dict[str, dict[date, str]] = defaultdict(dict)
    for f in sorted(runs_dir.glob("*.jsonl")):
        st = f.stem
        for line in f.read_text().splitlines():
            r = json.loads(line)
            created = _t(r["created_at"])
            end = None
            if r.get("status") == "completed":
                jf = jobs_dir / f"{st}-{r['id']}.json"
                if jf.exists():
                    done = [j["completed_at"] for j in json.loads(jf.read_text()) if j.get("completed_at")]
                    end = _t(max(done)) if done else _t(r["updated_at"])
                else:
                    end = _t(r["updated_at"])
                    if (end - created).total_seconds() > 86400:
                        # its jobs couldn't be fetched (404: the 56 first runs on 2026-01-07, their job
                        # records deleted) and updated_at was moved later: taken as finished the day it began
                        end = created
            last = end.date() if end else through
            d = created.date()
            while d <= last and d <= through:
                if end and d == end.date():
                    c = "ok" if r.get("conclusion") == "success" else "failed"
                else:
                    eod = datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc)
                    c = "failed" if (eod - created).total_seconds() > 86400 else "running"
                if rank[c] > rank.get(out[st].get(d), 0):
                    out[st][d] = c
                d += timedelta(days=1)
    return out


def run_class(d: date, c: Counter) -> str:
    if d < RUNS_FROM:
        return "no_record"
    if not c:
        return "off"
    return "ok" if c["success"] else "failed"


def new_by_day(con: sqlite3.Connection, state: str) -> dict[date, list[int]]:
    """{day: [scrapes, new bills, new actions, new votes]} from the scan (hand commits left out)."""
    out: dict[date, list[int]] = {}
    for idx, at, subj, nb, na, nv in con.execute(
            "SELECT idx, committed_at, subject, bills_new, actions_new, votes_new FROM scrapes "
            "WHERE state = ? ORDER BY idx", (state,)):
        if not is_scrape(subj):
            continue
        d = datetime.fromisoformat(at).date()
        row = out.setdefault(d, [0, 0, 0, 0])
        row[0] += 1
        if idx > 0:  # a state's first scrape: everything is "new"
            row[1] += nb or 0
            row[2] += na or 0
            row[3] += nv or 0
    return out


def session_side(status: str) -> str:
    return "in" if status in S.IN else "unknown" if status == "unknown" else "out"


def kind(run: str, new: int, status: str, state: str = "") -> str:
    if new:
        return "new"
    side = session_side(status)
    if side == "in" and state in YEAR_ROUND:
        side = "year_round"
    if run == "no_record":
        return f"no_record_{side}"
    if run in ("off", "failed", "running"):
        return run
    return f"quiet_{side}"


SCHEMA = """
DROP TABLE IF EXISTS run_days;
CREATE TABLE run_days (state TEXT, day TEXT, run TEXT, runs INTEGER, success INTEGER,
  failure INTEGER, cancelled INTEGER, other INTEGER, PRIMARY KEY (state, day));
DROP TABLE IF EXISTS status_days;
CREATE TABLE status_days (state TEXT, day TEXT, status TEXT, legiscan TEXT, multistate TEXT,
  congress TEXT, manual TEXT, disagree INTEGER, estimated INTEGER, PRIMARY KEY (state, day));
DROP TABLE IF EXISTS days;
CREATE TABLE days (state TEXT, day TEXT, run TEXT, status TEXT, disagree INTEGER,
  scrapes INTEGER, new_bills INTEGER, new_actions INTEGER, new_votes INTEGER, kind TEXT,
  run_timed TEXT, kind_timed TEXT, PRIMARY KEY (state, day));
DROP TABLE IF EXISTS quiet_segments;
CREATE TABLE quiet_segments (state TEXT, stretch INTEGER, start TEXT, end TEXT, days INTEGER,
  kind TEXT, statuses TEXT, disagree_days INTEGER, explained_by TEXT, PRIMARY KEY (state, start));
DROP TABLE IF EXISTS quiet_stretches;
CREATE TABLE quiet_stretches (state TEXT, stretch INTEGER, start TEXT, end TEXT, days INTEGER,
  off INTEGER, failed INTEGER, quiet_out INTEGER, quiet_in INTEGER, quiet_unknown INTEGER,
  quiet_year_round INTEGER, no_record INTEGER, disagree_days INTEGER, longest_quiet_in INTEGER,
  label TEXT, explained_by TEXT,
  PRIMARY KEY (state, stretch));
"""


LABELS = {"off": "scraper off", "failed": "ran and failed", "quiet_out": "ran, nothing new, out of session",
          "quiet_in": "ran, nothing new, in session", "quiet_unknown": "ran, nothing new, status unknown",
          "quiet_year_round": "ran, nothing new, territory (year-round)", "no_record": "before run history"}


def label(k: Counter) -> str:
    """The kind with the most days (no_record_* together), for reading; the counts are the facts."""
    merged = Counter()
    for kk, v in k.items():
        merged["no_record" if kk.startswith("no_record") else kk] += v
    return LABELS[max(merged, key=lambda x: (merged[x], x == "quiet_in"))]


def explain(st: str, a: str, b: str) -> str | None:
    """What already accounts for days a..b: a notes event, an overnight (unconfirmed) event, or
    a candidate event; None if nothing does. Overlap, not containment."""
    import known_events
    import candidates
    for e in known_events.events_for(st):
        if e.start <= b and e.end >= a:
            return ("overnight: " if "history scanner" in e.source else "notes: ") + f"{e.what} ({e.start})"
    for c in candidates.CANDIDATES:
        if st in c.states and c.start <= b and c.end >= a:
            return f"candidate: {c.name}"
    return None


def build(db: Path, runs_dir: Path, sessions: Path, through: date, jobs_dir: Path | None = None) -> None:
    con = sqlite3.connect(db)
    con.executescript(SCHEMA)
    cal = S.load(sessions)
    runs = run_days(runs_dir)
    timed = run_days_timed(runs_dir, jobs_dir or runs_dir.parent / "jobs", through)
    states = [r[0] for r in con.execute("SELECT DISTINCT state FROM scrapes ORDER BY state")]
    for st in states:
        new = new_by_day(con, st)
        if not new:
            continue
        rows, seq = [], []
        for d in S.days(min(new), through):
            c = runs[st].get(d, Counter())
            run = run_class(d, c)
            con.execute("INSERT INTO run_days VALUES (?,?,?,?,?,?,?,?)", (
                st, d.isoformat(), run, sum(c.values()), c["success"], c["failure"], c["cancelled"],
                sum(v for k, v in c.items() if k not in ("success", "failure", "cancelled"))))
            s = S.status(cal, st, d)
            con.execute("INSERT INTO status_days VALUES (?,?,?,?,?,?,?,?,?)", (
                st, d.isoformat(), s.status, *(s.sources[f] for f in S.FAMILIES), int(s.disagree),
                int(s.estimated)))
            sc, nb, na, nv = new.get(d, [0, 0, 0, 0])
            k = kind(run, nb + na + nv, s.status, st)
            rt = "no_record" if d < RUNS_FROM else timed[st].get(d, "off")
            rows.append((st, d.isoformat(), run, s.status, int(s.disagree), sc, nb, na, nv, k,
                         rt, kind(rt, nb + na + nv, s.status, st)))
            seq.append((d, k, s.status, s.disagree))
        con.executemany("INSERT INTO days VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        # Stretches: consecutive days with kind != new. Segments: same kind within a stretch.
        n, i = 0, 0
        while i < len(seq):
            if seq[i][1] == "new":
                i += 1
                continue
            j = i
            while j < len(seq) and seq[j][1] != "new":
                j += 1
            n += 1
            part = seq[i:j]
            kinds = Counter(k for _, k, _, _ in part)
            longest_in = 0
            a = 0
            while a < len(part):
                b = a
                while b < len(part) and part[b][1] == part[a][1]:
                    b += 1
                seg = part[a:b]
                if seg[0][1] == "quiet_in":
                    longest_in = max(longest_in, len(seg))
                sa, sb = seg[0][0].isoformat(), seg[-1][0].isoformat()
                con.execute("INSERT INTO quiet_segments VALUES (?,?,?,?,?,?,?,?,?)", (
                    st, n, sa, sb, len(seg), seg[0][1],
                    json.dumps(dict(Counter(x[2] for x in seg))), sum(x[3] for x in seg), explain(st, sa, sb)))
                a = b
            no_rec = sum(v for k, v in kinds.items() if k.startswith("no_record"))
            pa, pb = part[0][0].isoformat(), part[-1][0].isoformat()
            con.execute("INSERT INTO quiet_stretches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                st, n, pa, pb, len(part), kinds["off"], kinds["failed"], kinds["quiet_out"],
                kinds["quiet_in"], kinds["quiet_unknown"], kinds["quiet_year_round"], no_rec,
                sum(x[3] for x in part), longest_in, label(kinds), explain(st, pa, pb)))
            i = j
    con.commit()
    con.close()


def export(db: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    for table in ("days", "quiet_segments", "quiet_stretches"):
        cur = con.execute(f"SELECT * FROM {table} ORDER BY 1, 2")
        with open(out / f"{table}.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow([c[0] for c in cur.description])
            w.writerows(cur)
    con.close()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--runs", type=Path, required=True)
    p.add_argument("--sessions", type=Path, required=True)
    p.add_argument("--csv-dir", type=Path, required=True)
    p.add_argument("--through", type=date.fromisoformat, default=date.today() - timedelta(days=1))
    p.add_argument("--jobs", type=Path, help="jobs API answers, <st>-<run id>.json (default: <runs>/../jobs)")
    a = p.parse_args()
    build(a.db, a.runs, a.sessions, a.through, a.jobs)
    export(a.db, a.csv_dir)


if __name__ == "__main__":
    main()
