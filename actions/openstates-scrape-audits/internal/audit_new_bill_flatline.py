#!/usr/bin/env python3
"""Weekly audit: flag any in-session state with zero new distinct bills for
7+ consecutive days, despite GitHub Actions reporting "success" the whole
time -- the real UT pattern, found 2026-10-02 (flat at the same bill count
for weeks, green every single day). Reads the new_bills_seen daily
histogram in .windycivi/latest_timestamp_seen.txt (actions/format's
handlers/bill.py, hooked into the "New bill" branch -- counts a bill the
moment it's first seen, independent of whether it has any actions at all,
so it works for GU too, which has 277 real bills and zero action logs ever).

Rule, confirmed deliberately simple (see tamara-notes session notes
2026-10-02): flag on a GENUINE ZERO stretch only, not a low rate. A trickle
of 1-9 new bills/week late in a session is normal and not flagged --
empirically confirmed via check_frontloaded_states.py that regular sessions
taper naturally. No per-state baseline needed to tell a healthy trickle
apart from a stuck scraper; only true zero is the signal.

Exceptions (session-structure-driven, not scraper bugs -- confirmed
empirically via check_frontloaded_states.py, 2026-10-02):
  - gu: year-round legislature, 0 action logs ever -- this signal doesn't
    apply at all (included in the output as "exempt", not silently skipped)
  - or: short 35-day session -- 93% of bills land in one week, genuinely
    flat afterward is normal
  - nv: special session -- 89% of bills in one week, same reasoning

IMPORTANT CAVEAT: new_bills_seen only started being recorded with this
fix (2026-10-02) -- it has ZERO historical depth across all 56 states as of
this writing. This script will mostly report "not enough history yet"
until real format runs accumulate a few weeks of data. Built now so it's
ready when that history exists, same reasoning as PR #181's
action_log_files_created/implausible_date_fallbacks fields.

Usage: python3 audit_new_bill_flatline.py [--govbot-dir ~/govbot_data_local]
"""
import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_MANAGER = REPO_ROOT / "actions" / "pipeline-manager"
SESSION_CALENDAR = REPO_ROOT / "tamara-notes" / "session-dates" / "session-calendar-2026.md"

FLATLINE_THRESHOLD_DAYS = 7

EXCEPTIONS = {
    "gu": "year-round legislature, 0 action logs ever -- this signal doesn't apply",
    "or": "short 35-day session -- bills legitimately front-load, confirmed 93% in one week",
    "nv": "special session -- bills legitimately front-load, confirmed 89% in one week",
}


def load_scraper_status() -> dict[str, str]:
    with open(PIPELINE_MANAGER / "chn-openstates-scrape.yml") as f:
        cfg = yaml.safe_load(f)
    return {
        code: ("paused" if "paused" in loc.get("template", "") else "active")
        for code, loc in cfg["locales"].items()
    }


def load_session_info() -> dict[str, dict]:
    """Returns {code: {"status": "in"|"out"|"unknown", "convenes": date|None, "adjourns": date|None}}."""
    text = SESSION_CALENDAR.read_text()
    rows = re.findall(
        r"^\| (\w+) \| [^|]+\| ([^|]+)\| ([^|]+)\| (✅|⏸️|❓) \|",
        text, re.M,
    )
    out = {}
    for code, convenes_raw, adjourns_raw, status in rows:
        def parse(raw):
            m = re.match(r"\s*(\d{4}-\d{2}-\d{2})", raw)
            return m.group(1) if m else None
        out[code] = {
            "status": {"✅": "in", "⏸️": "out", "❓": "unknown"}[status],
            "convenes": parse(convenes_raw),
            "adjourns": parse(adjourns_raw),
        }
    return out


def read_new_bills_histogram(repo_dir: Path) -> dict[str, int]:
    f = repo_dir / ".windycivi" / "latest_timestamp_seen.txt"
    if not f.exists():
        return {}
    try:
        data = json.loads(f.read_text())
    except Exception:
        return {}
    return data.get("new_bills_seen", {})


def find_zero_stretch(histogram: dict[str, int], as_of: datetime) -> int | None:
    """Days since the most recent day with any new bills, walking back from
    the earliest recorded day in the histogram. Returns None if there's no
    history at all yet (can't tell flatline from "never ran")."""
    if not histogram:
        return None
    dated_days = sorted(histogram.keys())
    earliest = datetime.strptime(dated_days[0], "%Y-%m-%d")
    # Only meaningful once we have enough history to judge a 7-day stretch.
    if (as_of - earliest).days < FLATLINE_THRESHOLD_DAYS:
        return None
    last_nonzero = None
    for day in dated_days:
        if histogram[day] > 0:
            last_nonzero = day
    if last_nonzero is None:
        return (as_of - earliest).days
    last_nonzero_dt = datetime.strptime(last_nonzero, "%Y-%m-%d")
    return (as_of - last_nonzero_dt).days


def session_line(info: dict) -> str:
    if not info:
        return "Session: unknown (not in calendar)"
    if info["convenes"] and info["adjourns"]:
        return f"Session: convenes {info['convenes']}, adjourns {info['adjourns']} (currently {info['status']} session)"
    return f"Session: no regular-session dates tracked (status: {info['status']})"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--govbot-dir", default=str(Path.home() / "govbot_data_local"))
    args = parser.parse_args()
    repos_dir = Path(args.govbot_dir) / "repos"

    scraper_status = load_scraper_status()
    session_info = load_session_info()
    now = datetime.now()

    flagged = []
    exempt_with_data = []
    no_history = []

    for code in sorted(scraper_status.keys()):
        repo_dir = repos_dir / f"{code}-legislation"
        if not repo_dir.is_dir():
            continue

        histogram = read_new_bills_histogram(repo_dir)
        zero_days = find_zero_stretch(histogram, now)
        info = session_info.get(code)
        in_session = info and info["status"] == "in"

        if code in EXCEPTIONS:
            if histogram:
                exempt_with_data.append((code, EXCEPTIONS[code]))
            continue

        if zero_days is None:
            no_history.append(code)
            continue

        if in_session and zero_days >= FLATLINE_THRESHOLD_DAYS:
            flagged.append((code, zero_days, info))

    print(f"# New-bill flatline audit -- {now.strftime('%Y-%m-%d')}\n")
    print(f"Rule: in-session states with {FLATLINE_THRESHOLD_DAYS}+ consecutive days of zero new "
          f"distinct bills, despite the pipeline reporting success throughout.\n")

    print(f"## Flagged ({len(flagged)})\n")
    if flagged:
        for code, zero_days, info in flagged:
            print(f"  ⚠️  {code}: 0 new bills for {zero_days} consecutive days")
            print(f"      {session_line(info)}")
    else:
        print("  None.")
    print()

    print(f"## Exempt states with real data (front-loaded by session structure, not flagged) ({len(exempt_with_data)})")
    for code, reason in exempt_with_data:
        print(f"  {code}: {reason}")
    print()

    print(f"## Not enough history yet to judge ({len(no_history)})")
    print(f"  {', '.join(no_history) if no_history else 'none'}")
    print(
        "\n  Expected right now -- new_bills_seen only started being recorded 2026-10-02 "
        "(this fix). Needs real format runs to accumulate history before this check "
        "becomes meaningful. Re-run this script periodically as that builds up."
    )


if __name__ == "__main__":
    main()
