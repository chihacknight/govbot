#!/usr/bin/env python3
"""The weekly scraper-health audit -- combines two durable, committed
signals (new_bills_seen in govbot-data's .windycivi/latest_timestamp_seen.txt,
warning_history in govbot-openstates-scrapers' .windycivi/warning_history.json),
fetched live via raw.githubusercontent.com so it never depends on a local
clone (a stale local clone falsely flagged usa/mi/oh/pa/vi as frozen on
2026-10-02 -- confirmed via fleet-monitor's live poll that all 5 had
committed within the prior 14 hours; see
tamara-notes/scraper-status/56-state-audit-plan.md's "methodology
correction" section for the full story). No GITHUB_TOKEN required for
these fetches (raw.githubusercontent.com is unauthenticated).

Scope, deliberately bounded (per Tamara, 2026-10-02): bill-discovery
health only -- not text extraction, not field completeness (sponsors,
abstracts), not orphan tracking. Those are separate tools with their own
cadence.

Three checks:
  1. New-bill flatline: in-session states with 7+ consecutive days of zero
     new distinct bills. Hard-flagged -- zero is unambiguous (confirmed a
     low-but-nonzero trickle late in a session is normal, no per-state
     baseline needed to tell it apart from a stuck scraper). Exceptions:
     gu, or, nv (session-structure front-loading, confirmed empirically
     via a bill-introduction-date concentration scan, not guessed).
  2. Warning history: surfaced as a trend for human review, NOT
     auto-flagged -- raw warning count alone is unreliable (NY's 22,000
     was almost entirely one benign fallback message; DE's 459 was real
     vote-fetch failures). Severity needs reading actual message content,
     which this script doesn't attempt -- it just makes the trend visible.
  3. Behind the legislature (added 2026-10-09 after Illinois): for EVERY state,
     paused or running, compare OpenStates' most recent bill action with the
     newest action on our site (the published bills/index.json). Hard-flagged
     when OpenStates shows an action in the last 14 days that is 7+ days newer
     than ours -- the legislature is acting and we aren't collecting it. This is
     the blind spot checks 1-2 can't see: a paused state has no histogram to
     flatline (Illinois was paused 2026-09-30 while still filing bills). Needs
     OPENSTATES_API_KEY; without it the check is skipped and the report says so.

Also writes output/weekly_bill_counts.json -- for all 56 states (not just
flagged ones), the sum of new_bills_seen over the last 7 recorded days.
Built 2026-10-03 to feed docs/src/state-status-reference.md's "Weekly Bill
Count" column from real data on this script's own cadence, instead of a
separate manual lookup that would immediately go stale the way the rest of
that table did. This script already fetches the exact histogram needed for
the flatline check above; this just also sums it for every state, not only
the ones that flatlined.

"Flagged vs. investigated" tracking (the idea pulled from
actions/pipeline-manager/docs/staleness-audit-spec.md, never built until
now): a small committed state file, output/audit_tracking.json, so a
known issue doesn't re-alarm as if new every single week. The calling
workflow is responsible for committing this file back after each run --
see .github/workflows/weekly-scraper-audit.yml. It lives in output/,
separate from this script, so the directory's git history distinguishes
"the audit code changed" from "a scheduled run's output updated."

This script lives in its own action (actions/openstates-scrape-audits/),
scoped specifically to the OpenStates-based bill scraper pipeline
(actions/scrape/, chn-openstates-scrape.yml) -- it has no visibility into
the other scraper pipelines in this repo (actions/scrape-elections/,
actions/scrape-hearings/, actions/scrape-maps/), hence the explicit
"openstates" in the name. Separate from actions/pipeline-manager/
(repo/template provisioning) -- the only functional tie to
pipeline-manager is reading its locale config (chn-openstates-scrape.yml)
for the active/paused state list, via the relative path below, not shared
ownership of any file here.

Usage: python3 weekly-scraper-audit.py [--report-file path.md]
"""
import argparse
import importlib.util
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import date, datetime
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
PIPELINE_MANAGER = REPO_ROOT / "actions" / "pipeline-manager"
SESSION_CALENDAR = REPO_ROOT / "tamara-notes" / "session-dates" / "session-calendar-2026.md"
TRACKING_FILE = SCRIPT_DIR / "output" / "audit_tracking.json"
WEEKLY_BILL_COUNTS_FILE = SCRIPT_DIR / "output" / "weekly_bill_counts.json"

DATA_ORG = "govbot-data"
SCRAPER_ORG = "govbot-openstates-scrapers"
FLATLINE_THRESHOLD_DAYS = 7
BEHIND_DAYS = 7          # OpenStates' latest action this much newer than ours -> we're missing bills
# The site's per-state newest bills (scripts/build_site_slices.py), rebuilt with every deploy.
SITE_INDEX = "https://chihacknight.github.io/govbot/dashboard/bills/index.json"

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
    if not SESSION_CALENDAR.exists():
        return {}
    text = SESSION_CALENDAR.read_text()
    # Columns are: Code | Jurisdiction | Session | Convenes | Adjourns | In Session Now? | Notes
    # -- two columns (Jurisdiction, Session) between Code and Convenes, not one. A prior
    # version of this regex only skipped one, silently matching zero rows against the
    # current file (confirmed 2026-10-03: load_session_info() returned {} for all 56
    # states, meaning the flatline check below could never actually flag anything --
    # in_session was always False). Fixed to skip both.
    rows = re.findall(r"^\| (\w+) \| [^|]+\| [^|]+\| ([^|]+)\| ([^|]+)\| (✅|⏸️|❓) \|", text, re.M)
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


def _check_sessions():
    """The OpenStates helpers live in pipeline-manager's check-sessions.py (one copy);
    loaded by path since the filename has a hyphen."""
    spec = importlib.util.spec_from_file_location("check_sessions", PIPELINE_MANAGER / "check-sessions.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def our_newest_actions() -> dict[str, date]:
    """{state code: newest action date on our site}, from the published bills/index.json."""
    try:
        with urllib.request.urlopen(SITE_INDEX, timeout=30) as resp:
            recent = json.loads(resp.read().decode()).get("recent") or {}
    except Exception as e:  # noqa: BLE001 - the check is skipped, the report says so
        print(f"  fetch error {SITE_INDEX}: {e}", file=sys.stderr)
        return {}
    out = {}
    for code, bills in recent.items():
        dates = [b.get("latest_action", "")[:10] for b in bills or [] if b.get("latest_action")]
        if dates:
            out[code] = date.fromisoformat(max(dates))
    return out


def behind_legislature(ours, theirs, today: date) -> int | None:
    """Days our newest action trails OpenStates' when the legislature acted in the last
    14 days and we're BEHIND_DAYS+ behind (or have nothing); else None."""
    if theirs is None or not (0 <= (today - theirs).days <= 14):
        return None
    if ours is None:
        return (theirs - date(1900, 1, 1)).days
    lag = (theirs - ours).days
    return lag if lag >= BEHIND_DAYS else None


def load_tracking() -> dict:
    if TRACKING_FILE.exists():
        return json.loads(TRACKING_FILE.read_text())
    return {}


def save_tracking(tracking: dict) -> None:
    TRACKING_FILE.write_text(json.dumps(tracking, indent=2, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-file", default=None, help="Also write the report as markdown to this path")
    args = parser.parse_args()

    scraper_status = load_scraper_status()
    session_info = load_session_info()
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    tracking = load_tracking()

    flagged_now = {}
    warning_trends = {}
    weekly_bill_counts = {}

    # Check 3 setup: OpenStates' latest action vs ours, for every state.
    api_key = os.environ.get("OPENSTATES_API_KEY")
    ours = our_newest_actions() if api_key else {}
    cs = _check_sessions() if api_key and ours else None
    behind_note = ("" if cs else "Skipped: " + ("no OPENSTATES_API_KEY in this run." if not api_key
                                               else f"couldn't read {SITE_INDEX}."))
    flagged_behind = {}

    for i, code in enumerate(sorted(scraper_status.keys()), 1):
        print(f"[{i}/{len(scraper_status)}] {code}...", file=sys.stderr)

        ts_data = fetch_raw(DATA_ORG, f"{code}-legislation", ".windycivi/latest_timestamp_seen.txt")
        new_bills_hist = (ts_data or {}).get("new_bills_seen", {})
        zero_days = find_zero_stretch(new_bills_hist, now)
        info = session_info.get(code)
        in_session = bool(info and info["status"] == "in")

        # For every state, not just flagged ones -- feeds state-status-reference.md's
        # "Weekly Bill Count" column. A state with no histogram at all (never scraped,
        # or the .windycivi file doesn't exist yet) gets count 0 / days_with_data 0,
        # which is distinguishable from a real zero-bill week by days_with_data.
        recent_bill_days = sorted(new_bills_hist.keys())[-7:]
        weekly_bill_counts[code] = {
            "count": sum(new_bills_hist[d] for d in recent_bill_days),
            "days_with_data": len(recent_bill_days),
        }

        if code not in EXCEPTIONS and zero_days is not None and in_session and zero_days >= FLATLINE_THRESHOLD_DAYS:
            flagged_now[code] = {"zero_days": zero_days, "session": session_line(info)}

        if cs:
            theirs = cs.fetch_latest_action(cs.ocd_id_for(code), api_key)
            lag = behind_legislature(ours.get(code), theirs, now.date())
            if lag is not None:
                flagged_behind[f"behind:{code}"] = {
                    "status": scraper_status[code], "theirs": str(theirs),
                    "ours": str(ours.get(code) or "none"), "lag": lag}
            time.sleep(1.2)  # OpenStates rate limit

        wh_data = fetch_raw(SCRAPER_ORG, f"{code}-legislation", ".windycivi/warning_history.json")
        if wh_data:
            recent_days = sorted(wh_data.keys())[-7:]
            recent_total = sum(wh_data[d].get("warning_count", 0) for d in recent_days)
            if recent_total > 0:
                warning_trends[code] = {"last_7_days_total": recent_total, "days_with_data": len(recent_days)}

    new_flags = []
    still_open = []
    flagged_now.update(flagged_behind)   # one tracking file; "behind:<code>" keys for check 3
    for code, details in flagged_now.items():
        if code in tracking:
            first_seen = tracking[code]["first_flagged"]
            days_known = (now - datetime.strptime(first_seen, "%Y-%m-%d")).days
            still_open.append((code, details, first_seen, days_known))
        else:
            tracking[code] = {"first_flagged": today_str}
            new_flags.append((code, details))

    # A skipped check 3 (no key / site down) resolves nothing: keep its open flags as they were.
    resolved = [c for c in tracking if c not in flagged_now and (cs or not c.startswith("behind:"))]
    for c in resolved:
        del tracking[c]

    save_tracking(tracking)
    WEEKLY_BILL_COUNTS_FILE.write_text(json.dumps(
        {"as_of": today_str, "states": weekly_bill_counts}, indent=2, sort_keys=True
    ))

    behind_new = [(c, d) for c, d in new_flags if c.startswith("behind:")]
    behind_open = [x for x in still_open if x[0].startswith("behind:")]
    new_flags = [(c, d) for c, d in new_flags if not c.startswith("behind:")]
    still_open = [x for x in still_open if not x[0].startswith("behind:")]

    lines = [f"# Weekly scraper-health audit -- {today_str}", ""]
    lines.append(f"## Behind the legislature ({len(behind_new) + len(behind_open)})")
    lines.append("")
    lines.append("OpenStates shows recent bill activity we haven't collected -- for a paused state, "
                 "the legislature is still acting (the daily session check will switch it back on); "
                 "for a running one, the scraper has fallen behind.")
    lines.append("")
    if behind_note:
        lines.append(behind_note)
    elif behind_new or behind_open:
        for code, d in behind_new:
            lines.append(f"- 🆕 **{code[7:]}** ({d['status']}): OpenStates' latest action {d['theirs']}, ours {d['ours']}")
        for code, d, first_seen, days_known in behind_open:
            lines.append(f"- ⚠️ **{code[7:]}** ({d['status']}): known since {first_seen} ({days_known}d) -- "
                         f"OpenStates {d['theirs']}, ours {d['ours']}")
    else:
        lines.append("None -- every state with recent legislative activity is up to date.")
    lines.append("")
    lines.append(f"## NEW flatline flags ({len(new_flags)})")
    lines.append("")
    if new_flags:
        for code, d in new_flags:
            lines.append(f"- ⚠️ **{code}**: 0 new bills for {d['zero_days']} consecutive days")
            lines.append(f"  - {d['session']}")
    else:
        lines.append("None.")
    lines.append("")

    lines.append(f"## STILL OPEN flatline flags ({len(still_open)})")
    lines.append("")
    if still_open:
        for code, d, first_seen, days_known in still_open:
            lines.append(f"- ⚠️ **{code}**: known since {first_seen} ({days_known}d) -- still 0 new bills")
            lines.append(f"  - {d['session']}")
    else:
        lines.append("None.")
    lines.append("")

    if resolved:
        lines.append(f"## Resolved since last run ({len(resolved)})")
        lines.append("")
        lines.append(", ".join(resolved))
        lines.append("")

    lines.append("## Warning-count trend, last 7 recorded days (informational -- not auto-flagged)")
    lines.append("")
    for code, d in sorted(warning_trends.items(), key=lambda kv: -kv[1]["last_7_days_total"])[:15]:
        lines.append(f"- {code}: {d['last_7_days_total']} warnings across {d['days_with_data']} recorded days")
    lines.append("")
    lines.append(
        "Raw count is NOT severity -- high counts are often benign (NY's 22,000 was one "
        "fallback message) and low counts can be serious (DE's 459 was real vote-fetch "
        "failures). Read the actual `sample_warnings` in each state's "
        "`.windycivi/warning_history.json` before acting on this list."
    )

    report = "\n".join(lines)
    print("\n" + report)

    if args.report_file:
        Path(args.report_file).write_text(report)
        print(f"\nReport written to {args.report_file}", file=sys.stderr)


if __name__ == "__main__":
    main()
