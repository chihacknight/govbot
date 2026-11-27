#!/usr/bin/env python3
"""When each action first reached the raw history, against the date it carries (step 6).

    python3 action_dates.py --db <history.sqlite> --raw-root <raw-scrapers> [--jobs 8] [states...]

For each state, walks the raw repo's scrapes in order (the scan's `scrapes` table: its first
scrape, then every scrape where the scan counted a new action) and keeps the set of actions
seen so far, keyed by bill (session + identifier) + date + chamber + description. Each action
not seen before is counted on the UTC day of the scrape that first had it.

Writes `action_seen` (state, seen_day, action_day, n), replaced per state:
- lag = seen_day - action_day, over the full raw history (the brief: not `first_seen`, which
  before the 07-21 rebuild is the rebuild's date);
- the first scrape's actions are kept as seen_day NULL (a backlog, not a lag);
- an action dated after the day it was seen (a scheduled hearing) has a negative lag.

Reads the raw repos only (git ls-tree / cat-file); never writes to them.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path


def blobs(repo: str, ids: list[str]):
    p = subprocess.Popen(["git", "-C", repo, "cat-file", "--batch"], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE)
    import threading

    def feed():
        for i in ids:
            p.stdin.write(i.encode() + b"\n")
        p.stdin.close()
    t = threading.Thread(target=feed)
    t.start()
    out = p.stdout
    for _ in ids:
        hdr = out.readline().split()
        if len(hdr) < 3 or hdr[1] != b"blob":
            continue
        data = out.read(int(hdr[2]))
        out.read(1)
        yield data
    t.join()
    p.wait()


def actions_of(raw: bytes):
    try:
        d = json.loads(raw)
    except ValueError:
        return
    if not isinstance(d, dict):
        return
    bill = (d.get("legislative_session"), d.get("identifier"))
    for a in d.get("actions") or []:
        if not isinstance(a, dict):
            continue
        day = str(a.get("date") or "")[:10]
        if len(day) != 10:
            continue
        org = a.get("organization_id") or a.get("organization") or a.get("chamber") or ""
        if isinstance(org, dict):
            org = org.get("classification") or org.get("name") or ""
        yield (bill, day, str(org), " ".join(str(a.get("description") or "").split())), day


def walk(args):
    db, raw_root, state = args
    con = sqlite3.connect(db)
    rows = con.execute("SELECT idx, sha, committed_at, subject FROM scrapes WHERE state = ? "
                       "AND (idx = 0 OR actions_new > 0) ORDER BY idx", (state,)).fetchall()
    con.close()
    repo = f"{raw_root}/{state}-legislation"
    seen: set = set()
    counts: Counter = Counter()
    for idx, sha, at, _subject in rows:
        ls = subprocess.run(["git", "-C", repo, "ls-tree", "-r", sha, f"_data/{state}/"],
                            capture_output=True, text=True).stdout.splitlines()
        ids = [l.split()[2] for l in ls if "\t" in l and l.split("\t", 1)[1].rsplit("/", 1)[-1].startswith("bill_")]
        seen_day = None if idx == 0 else at[:10]
        for raw in blobs(repo, ids):
            for key, day in actions_of(raw):
                if key not in seen:
                    seen.add(key)
                    counts[(seen_day, day)] += 1
    return state, [(state, s, d, n) for (s, d), n in counts.items()]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--raw-root", required=True)
    p.add_argument("--jobs", type=int, default=8)
    p.add_argument("states", nargs="*")
    a = p.parse_args()
    con = sqlite3.connect(a.db)
    con.execute("CREATE TABLE IF NOT EXISTS action_seen (state TEXT, seen_day TEXT, action_day TEXT, n INTEGER)")
    states = a.states or [r[0] for r in con.execute("SELECT DISTINCT state FROM scrapes ORDER BY state")]
    with ProcessPoolExecutor(a.jobs) as ex:
        for state, rows in ex.map(walk, [(a.db, a.raw_root, s) for s in states]):
            with con:
                con.execute("DELETE FROM action_seen WHERE state = ?", (state,))
                con.executemany("INSERT INTO action_seen VALUES (?,?,?,?)", rows)
            print(state, sum(r[3] for r in rows), flush=True)


if __name__ == "__main__":
    main()
