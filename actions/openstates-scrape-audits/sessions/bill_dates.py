#!/usr/bin/env python3
"""Each bill's first and last action date, read once from the last scrape it appears in.

    python3 bill_dates.py --db <history.sqlite> --raw-root <raw-scrapers> [--jobs 8]

Writes `bill_dates` (state, session, identifier, first_action, last_action, first_idx, last_idx)
to the database, replaced per state. With the scan's `bills` table (first_idx, last_idx: the
scrapes a bill was in), this answers per scrape "is there a bill whose first action is on or after
this session's convene date?" without reading every scrape: a bill's first action doesn't change
between scrapes. (A bill missing for a while between first_idx and last_idx is counted as present;
those gaps are the empty-scrape and bill-drop rules' business.) Reads the raw repos only.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

from action_dates import blobs


def walk(args):
    db, raw_root, state = args
    con = sqlite3.connect(db)
    wanted = defaultdict(set)  # last_idx -> {(session, identifier)}
    first = {}
    for sess, ident, fi, li in con.execute("SELECT session, identifier, first_idx, last_idx FROM bills WHERE state = ?",
                                           (state,)):
        wanted[li].add((sess, ident))
        first[(sess, ident)] = fi
    shas = dict(con.execute("SELECT idx, sha FROM scrapes WHERE state = ?", (state,)).fetchall())
    con.close()
    repo = f"{raw_root}/{state}-legislation"
    out = []
    for li, keys in wanted.items():
        ls = subprocess.run(["git", "-C", repo, "ls-tree", "-r", shas[li], f"_data/{state}/"],
                            capture_output=True, text=True).stdout.splitlines()
        ids = [l.split()[2] for l in ls if "\t" in l and l.split("\t", 1)[1].rsplit("/", 1)[-1].startswith("bill_")]
        found = set()
        for raw in blobs(repo, ids):
            try:
                d = json.loads(raw)
            except ValueError:
                continue
            key = (d.get("legislative_session"), d.get("identifier"))
            if key not in keys or key in found:
                continue
            found.add(key)
            days = sorted(str(a.get("date") or "")[:10] for a in d.get("actions") or []
                          if isinstance(a, dict) and len(str(a.get("date") or "")[:10]) == 10)
            out.append((state, key[0], key[1], days[0] if days else None, days[-1] if days else None, first[key], li))
    return state, out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--raw-root", required=True)
    p.add_argument("--jobs", type=int, default=8)
    a = p.parse_args()
    con = sqlite3.connect(a.db)
    con.execute("CREATE TABLE IF NOT EXISTS bill_dates (state TEXT, session TEXT, identifier TEXT, first_action TEXT, "
                "last_action TEXT, first_idx INTEGER, last_idx INTEGER)")
    states = [r[0] for r in con.execute("SELECT DISTINCT state FROM bills ORDER BY state")]
    with ProcessPoolExecutor(a.jobs) as ex:
        for state, rows in ex.map(walk, [(a.db, a.raw_root, s) for s in states]):
            with con:
                con.execute("DELETE FROM bill_dates WHERE state = ?", (state,))
                con.executemany("INSERT INTO bill_dates VALUES (?,?,?,?,?,?,?)", rows)
    print(con.execute("SELECT COUNT(*), SUM(first_action IS NULL) FROM bill_dates").fetchone())


if __name__ == "__main__":
    main()
