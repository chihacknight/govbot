#!/usr/bin/env python3
"""Break down each top-offender state's warnings by normalized message type,
not just raw count -- the sweep's raw counts conflate benign per-bill
fallback logging (e.g. NY's "assuming first", a scraper decision, not a
failure) with genuine silent data loss (e.g. DE's "No actions returned for
HB 481" after exhausted retries). Re-downloads each state's already-known
run log (from warning_sweep_output.json) and groups matches by template
(bill ID / version ID / numbers stripped out).

Usage: python3 categorize_warnings.py <code> [<code> ...]
"""
import json
import re
import subprocess
import sys
from pathlib import Path
from collections import Counter

ORG = "govbot-openstates-scrapers"
WARNING_RE = re.compile(r"\bWARNING\b")
EXCLUDE_RE = re.compile(
    r"( INFO |scrape attempt|retry|retrying|resolved|recovered|succeeded|SKIPPED BILL)",
    re.IGNORECASE,
)
# Strip bill IDs, version IDs, URLs, numbers to get a normalized template.
NORMALIZE_RES = [
    (re.compile(r"https?://\S+"), "<URL>"),
    (re.compile(r"\b[A-Z]{1,4}\s?\d+[A-Za-z]?\b"), "<BILL_ID>"),
    (re.compile(r"\b\d+\b"), "<N>"),
]


def normalize(msg: str) -> str:
    for pattern, repl in NORMALIZE_RES:
        msg = pattern.sub(repl, msg)
    return msg.strip()


def main():
    codes = sys.argv[1:]
    sweep = json.loads((Path(__file__).parent / "warning_sweep_output.json").read_text())

    for code in codes:
        row = next((r for r in sweep if r["code"] == code), None)
        if not row or "run_id" not in row:
            print(f"{code}: no run data")
            continue

        out = subprocess.run(
            ["gh", "run", "view", str(row["run_id"]), "--repo", f"{ORG}/{code}-legislation", "--log"],
            capture_output=True, text=True, timeout=120,
        )
        lines = out.stdout.splitlines()
        matches = [l for l in lines if WARNING_RE.search(l) and not EXCLUDE_RE.search(l)]

        templates = Counter()
        for m in matches:
            # Keep just the message part after the last known log-prefix marker.
            msg = m.split("WARNING", 1)[-1]
            templates[normalize(msg)] += 1

        print(f"\n=== {code}: {len(matches)} total warnings, {len(templates)} distinct templates ===")
        for tmpl, count in templates.most_common(8):
            print(f"  {count:>6}  {tmpl[:140]}")


if __name__ == "__main__":
    main()
