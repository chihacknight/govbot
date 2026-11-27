#!/usr/bin/env python3
"""Each state's bill-introduction deadline, from the MultiState PDFs' "Intro Deadlines" columns.

    python3 deadlines.py <session-dates dir> <out.csv>

Page 1 of each PDF (sources/multistate/<year>/<date>.pdf) has, per state, the House and Senate
introduction deadlines and the crossover date, in columns found by their x position under the
headers (House, Senate, Crossover). A state can have none, one or both. Each deadline is set
against that year's regular session start (same PDF), as days after convening.

`early`: both chambers' deadline (or the one given) falls within EARLY_DAYS of convening: the
state files nearly all its bills at the start, so a session with few new bills after that is
normal, not a freeze. A state with no deadline in the PDF can file bills any time.
"""
from __future__ import annotations

import csv
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

EARLY_DAYS = 31
COLS = {"house": (590, 640), "senate": (640, 700), "crossover": (700, 760)}
SESSION_X = (100, 590)
DATE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2})$")


def iso(text: str):
    m = DATE.match(text)
    return date(2000 + int(m[3]), int(m[1]), int(m[2])) if m else None


def read(path: Path, codes: dict) -> list[dict]:
    xml = subprocess.run(["pdftohtml", "-xml", "-i", "-stdout", "-f", "1", "-l", "1", str(path)],
                         capture_output=True, text=True, check=True).stdout
    items = sorted({(int(t.get("top")), int(t.get("left")), "".join(t.itertext()).strip())
                    for t in ET.fromstring(xml).iter("text") if "".join(t.itertext()).strip()})
    out = []
    for top, left, name in items:
        if left >= 100 or name not in codes:
            continue
        near = [(l, t) for tp, l, t in items if abs(tp - top) <= 4 and l >= 100]
        row = {"state": codes[name], "name": name, "year": int(path.parent.name), "source": str(path)}
        starts = [iso(d) for l, t in near if SESSION_X[0] <= l < SESSION_X[1] for d in t.split()]
        row["convenes"] = next((d for d in starts if d), None)
        for col, (a, b) in COLS.items():
            row[col] = next((iso(t) for l, t in near if a <= l < b and iso(t)), None)
        out.append(row)
    return out


def main(argv) -> None:
    here, out = Path(argv[1]), Path(argv[2])
    sys.path.insert(0, str(here))
    from build_sessions_csv import CODES
    rows = []
    for path in sorted((here / "sources" / "multistate").glob("*/*.pdf")):
        rows += read(path, CODES)
    for r in rows:
        dl = [d for d in (r["house"], r["senate"]) if d]
        if r["convenes"] and dl:
            r["latest_deadline_days"] = (max(dl) - r["convenes"]).days
            r["early"] = r["latest_deadline_days"] <= EARLY_DAYS
        else:
            r["latest_deadline_days"], r["early"] = None, None
    fields = ["state", "name", "year", "convenes", "house", "senate", "crossover", "latest_deadline_days",
              "early", "source"]
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in sorted(rows, key=lambda r: (r["state"], r["year"])):
            w.writerow({k: r.get(k) for k in fields})
    print(f"{len(rows)} rows to {out}")


if __name__ == "__main__":
    main(sys.argv)
