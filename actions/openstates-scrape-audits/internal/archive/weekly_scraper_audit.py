#!/usr/bin/env python3
"""The real weekly scraper-health audit -- combines the two durable,
committed signals built this session (new_bills_seen, warning_history),
fetched live via raw.githubusercontent.com so it never depends on a local
clone (a stale local clone falsely flagged usa/mi/oh/pa/vi as frozen
2026-10-02 -- confirmed via fleet-monitor's live poll that all 5 had
committed within the prior 14 hours; see 56-state-audit-plan.md's
"methodology correction" section). No GITHUB_TOKEN required for these
fetches (raw.githubusercontent.com is unauthenticated, no rate limit in
practice for 56 small files).

Scope, deliberately bounded (per Tamara, 2026-10-02): bill-discovery
health only -- not text extraction, not field completeness (sponsors,
abstracts), not orphan tracking. Those are separate tools with their own
cadence.

Two checks:
  1. New-bill flatline: in-session states with 7+ consecutive days of zero
     new distinct bills. Hard-flagged -- zero is unambiguous (see
     check_frontloaded_states.py for why a low-but-nonzero trickle is NOT
     flagged). Exceptions: gu, or, nv (session-structure front-loading,
     confirmed empirically, not guessed).
  2. Warning history: surfaced as a trend for human review, NOT
     auto-flagged -- confirmed this session (categorize_warnings.py) that
     raw warning count alone is unreliable (NY's 22,000 is almost entirely
     one benign fallback message; DE's 459 is real vote-fetch failures).
     Severity needs reading actual message content, which this script
     doesn't attempt -- it just makes the trend visible.

"Flagged vs. investigated" tracking (the idea pulled from
actions/pipeline-manager/docs/staleness-audit-spec.md, never built until
now): a small committed state file, audit_tracking.json, so a known issue
doesn't re-alarm as if new every single week. A state flagged for the
first time shows as NEW; a state still flagged from a prior run shows as
STILL OPEN with how long it's been known, not a fresh alarm.

Usage: python3 weekly_scraper_audit.py
"""
import json
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
PIPELINE_MANAGER = REPO_ROOT / "actions" / "pipeline-manager"
SESSION_CALENDAR = REPO_ROOT / "tamara-notes" / "session-dates" / "session-calendar-2026.md"
TRACKING_FILE = Path(__file__).parent / "audit_tracking.json"

DATA_ORG = "govbot-data"
SCRAPER_ORG = "govbot-openstates-scrapers"
FLATLINE_THRESHOLD_DAYS = 7

EXCEPTIONS = {
    "gu": "year-round legislature, 0 action logs ever -- this signal doesn't apply",
    "or": "short 35-day session -- bills legitimately front-load, confirmed 93% in one week",
    "nv": "special session -- bills legitimately front-load, confirmed 89% in one week",
}


def fetch_raw(org: str, repo: str, path: str) -> dict | None:
    url = f"https://raw.githubusercontent.com/{org}/{repo}/main/{path}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        print(f"  fetch error {url}: HTTP {e.code}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  fetch error {url}: {e}", file=sys.stderr)
        return None


def load_scraper_status() -> dict[str, str]:
    with open(PIPELINE_MANAGER / "chn-openstates-scrape.yml") as f:
        cfg = yaml.safe_load(f)
    return {
        code: ("paused" if "paused" in loc.get("template", "") else "active")
        for code, loc in cfg["locales"].items()
    }


def load_session_info() -> dict[str, dict]:
    text = SESSION_CALENDAR.read_text()
    rows = re.findall(r"^\| (\w+) \| [^|]+\| ([^|]+)\| ([^|]+)\| (✅|⏸️|❓) \|", text, re.M)
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


def find_zero_stretch(histogram: dict[str, int], as_of: datetime) -> int | None:
    if not histogram:
        return None
    dated_days = sorted(histogram.keys())
    earliest = datetime.strptime(dated_days[0], "%Y-%m-%d")
    if (as_of - earliest).days < FLATLINE_THRESHOLD_DAYS:
        return None
    last_nonzero = None
    for day in dated_days:
        if histogram[day] > 0:
            last_nonzero = day
    if last_nonzero is None:
        return (as_of - earliest).days
    return (as_of - datetime.strptime(last_nonzero, "%Y-%m-%d")).days


def session_line(info: dict | None) -> str:
    if not info:
        return "Session: unknown (not in calendar)"
    if info["convenes"] and info["adjourns"]:
        return f"Session: convenes {info['convenes']}, adjourns {info['adjourns']} (currently {info['status']} session)"
    return f"Session: no regular-session dates tracked (status: {info['status']})"


def load_tracking() -> dict:
    if TRACKING_FILE.exists():
        return json.loads(TRACKING_FILE.read_text())
    return {}


def save_tracking(tracking: dict) -> None:
    TRACKING_FILE.write_text(json.dumps(tracking, indent=2, sort_keys=True))


def main():
    scraper_status = load_scraper_status()
    session_info = load_session_info()
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    tracking = load_tracking()

    flagged_now = {}
    warning_trends = {}

    for i, code in enumerate(sorted(scraper_status.keys()), 1):
        print(f"[{i}/{len(scraper_status)}] {code}...", file=sys.stderr)

        # Flatline check: new_bills_seen lives in the data repo.
        ts_data = fetch_raw(DATA_ORG, f"{code}-legislation", ".windycivi/latest_timestamp_seen.txt")
        new_bills_hist = (ts_data or {}).get("new_bills_seen", {})
        zero_days = find_zero_stretch(new_bills_hist, now)
        info = session_info.get(code)
        in_session = bool(info and info["status"] == "in")

        if code not in EXCEPTIONS and zero_days is not None and in_session and zero_days >= FLATLINE_THRESHOLD_DAYS:
            flagged_now[code] = {"zero_days": zero_days, "session": session_line(info)}

        # Warning trend: warning_history lives in the scraper repo. Informational only.
        wh_data = fetch_raw(SCRAPER_ORG, f"{code}-legislation", ".windycivi/warning_history.json")
        if wh_data:
            recent_days = sorted(wh_data.keys())[-7:]
            recent_total = sum(wh_data[d].get("warning_count", 0) for d in recent_days)
            if recent_total > 0:
                warning_trends[code] = {"last_7_days_total": recent_total, "days_with_data": len(recent_days)}

    # Reconcile against tracking: distinguish NEW flags from STILL OPEN ones.
    new_flags = []
    still_open = []
    for code, details in flagged_now.items():
        if code in tracking:
            first_seen = tracking[code]["first_flagged"]
            days_known = (now - datetime.strptime(first_seen, "%Y-%m-%d")).days
            still_open.append((code, details, first_seen, days_known))
        else:
            tracking[code] = {"first_flagged": today_str}
            new_flags.append((code, details))

    # Clear tracking for states no longer flagged (resolved).
    resolved = [c for c in tracking if c not in flagged_now]
    for c in resolved:
        del tracking[c]

    save_tracking(tracking)

    print(f"\n# Weekly scraper-health audit -- {today_str}\n")

    print(f"## NEW flatline flags ({len(new_flags)})\n")
    if new_flags:
        for code, d in new_flags:
            print(f"  ⚠️  {code}: 0 new bills for {d['zero_days']} consecutive days")
            print(f"      {d['session']}")
    else:
        print("  None.")
    print()

    print(f"## STILL OPEN flatline flags ({len(still_open)})\n")
    if still_open:
        for code, d, first_seen, days_known in still_open:
            print(f"  ⚠️  {code}: known since {first_seen} ({days_known}d) -- still 0 new bills")
            print(f"      {d['session']}")
    else:
        print("  None.")
    print()

    if resolved:
        print(f"## Resolved since last run ({len(resolved)})")
        print(f"  {', '.join(resolved)}\n")

    print(f"## Warning-count trend, last 7 recorded days (informational -- not auto-flagged, see note below)\n")
    for code, d in sorted(warning_trends.items(), key=lambda kv: -kv[1]["last_7_days_total"])[:15]:
        print(f"  {code}: {d['last_7_days_total']} warnings across {d['days_with_data']} recorded days")
    print(
        "\n  Raw count is NOT severity -- confirmed this session that high counts are often\n"
        "  benign (NY's 22,000 was one fallback message) and low counts can be serious\n"
        "  (DE's 459 was real vote-fetch failures). Read the actual sample_warnings in\n"
        "  each state's .windycivi/warning_history.json before acting on this list."
    )


if __name__ == "__main__":
    main()
