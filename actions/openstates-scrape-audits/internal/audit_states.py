#!/usr/bin/env python3
"""First-pass 56-state data audit, built around what-does-healthy-mean.md's
5 dimensions. Reads local clones only (no network calls except for the
session/scraper status, which comes from committed config + the session
calendar doc -- same source of truth the GitHub topics were derived from).

Dimensions covered today:
  1. Process liveness   -- git commit recency (proxy; action_log_files_created
                            isn't populated in any repo yet, see note below)
  2. Content currency    -- vote_events/events watermark + bill count
  3. Session-awareness   -- scraper active/paused + in/out of session
  4. Signal integrity    -- implausible_date_fallbacks, when present
  5. Completeness        -- NOT attempted here. Still blocked on the LegiScan
                            API key (see what-does-healthy-mean.md). Every
                            row's bill count is "what we have," never
                            presented as "what exists."

Note on dimensions 1 & 4: PR #181 (the action_log_files_created /
implausible_date_fallbacks fields) only affects what a *future* format run
writes -- it doesn't backfill already-committed .windycivi files. As of this
script's first run, zero local repos have these fields yet. Falling back to
git commit recency for liveness until enough real runs have happened
post-merge for the new fields to be meaningful.

IMPORTANT CONTEXT (Tamara, 2026-10-02): this data snapshot is LAST SEASON'S
session data, not a live/current scrape. A large days_since_commit number
here does NOT mean "the pipeline is broken right now" -- most of these
repos simply haven't had a reason to commit recently regardless of health,
since most states are between sessions. days_since_commit is reported as
raw information only; do not read it as a liveness red flag on its own,
and do not compare it against dimension 3 (session status) as if a big gap
for an out-of-session state means anything is wrong. This audit is about
understanding the shape/quality of what we already have, not about
catching a pipeline that stopped running today.

Usage: python3 audit_states.py [--govbot-dir ~/govbot_data_local]
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_MANAGER = REPO_ROOT / "actions" / "pipeline-manager"
SESSION_CALENDAR = REPO_ROOT / "tamara-notes" / "session-dates" / "session-calendar-2026.md"


def load_scraper_status() -> dict[str, str]:
    with open(PIPELINE_MANAGER / "chn-openstates-scrape.yml") as f:
        cfg = yaml.safe_load(f)
    return {
        code: ("paused" if "paused" in loc.get("template", "") else "active")
        for code, loc in cfg["locales"].items()
    }


def load_session_status() -> dict[str, str]:
    text = SESSION_CALENDAR.read_text()
    rows = re.findall(r"^\| (\w+) \| [^|]+\|[^|]+\|[^|]+\|[^|]+\| (✅|⏸️|❓) \|", text, re.M)
    return {code: {"✅": "in", "⏸️": "out", "❓": "unknown"}[s] for code, s in rows}


def git_last_commit(repo_dir: Path) -> datetime | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_dir), "log", "-1", "--format=%cI"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        return datetime.fromisoformat(out.stdout.strip())
    except Exception:
        return None


def count_bills(repo_dir: Path) -> int | None:
    country_dir = repo_dir / "country:us"
    if not country_dir.is_dir():
        return None
    try:
        out = subprocess.run(
            ["find", str(country_dir), "-type", "d", "-path", "*/bills/*", "-not", "-path", "*/bills/*/*"],
            capture_output=True, text=True, timeout=30,
        )
        return len([l for l in out.stdout.splitlines() if l.strip()])
    except Exception:
        return None


# Log filenames encode the government's own recorded action date, e.g.
# "20250116T180038Z_h09_mineralsrecommend..." or
# "20250114T223718Z.classification.introduction.lower.json" -- always a
# 15-char YYYYMMDDTHHMMSSZ prefix before the first "_" or ".".
_LOG_TS_RE = re.compile(r"^(\d{8}T\d{6}Z)")


def log_date_range(repo_dir: Path) -> tuple[str | None, str | None, int, dict[str, int]]:
    """Scan every bill's logs/*.json filename (not contents -- fast) and
    return (earliest, latest, count, daily histogram) across the whole state.

    IMPORTANT distinction from .windycivi's action_log_files_created: that
    field is keyed by the date *we ran format*, deliberately independent of
    bill content, specifically so a garbage source date can't corrupt it
    (see timestamp_tracker.py's docstrings). The histogram built here is the
    opposite axis on purpose -- it's keyed by each action's own
    *government-recorded* date (same field write_action_logs() uses for the
    filename), bucketed across every log file we already have on disk. The
    two answer different questions: that field asks "did OUR pipeline run
    that day," this one asks "did a real action HAPPEN that day, per the
    government's own record." Don't merge these into one signal -- same
    reasoning that kept the two original fields independent cross-checks.

    This one is retroactively computable right now from already-committed
    data (no future format run needed), which is what makes it useful for
    this first-pass audit while action_log_files_created is still empty
    everywhere.
    """
    country_dir = repo_dir / "country:us"
    if not country_dir.is_dir():
        return None, None, 0, {}
    try:
        out = subprocess.run(
            ["find", str(country_dir), "-path", "*/logs/*.json"],
            capture_output=True, text=True, timeout=60,
        )
    except Exception:
        return None, None, 0, {}

    timestamps = []
    for line in out.stdout.splitlines():
        name = line.rsplit("/", 1)[-1]
        m = _LOG_TS_RE.match(name)
        if m:
            timestamps.append(m.group(1))

    if not timestamps:
        return None, None, 0, {}

    histogram: dict[str, int] = {}
    for ts in timestamps:
        day = ts[:8]  # YYYYMMDD
        histogram[day] = histogram.get(day, 0) + 1

    return min(timestamps), max(timestamps), len(timestamps), histogram


def read_timestamp_file(repo_dir: Path) -> dict:
    f = repo_dir / ".windycivi" / "latest_timestamp_seen.txt"
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text())
    except Exception:
        return {}


def read_orphan_count(repo_dir: Path) -> int:
    """Count of bills with vote_events/events referencing them but no actual
    bill data -- written by actions/format/postprocessors/cleanup_placeholders.py,
    ONLY when non-empty (confirmed: cleanup_placeholders() itself runs
    unconditionally every main.py run, so a missing file means a real zero,
    not "never ran"). Flagged in what-does-healthy-mean.md as a real,
    already-computed signal not yet folded into the health picture -- this
    is that fold-in.
    """
    f = repo_dir / ".windycivi" / "errors" / "orphaned_placeholders_tracking.json"
    if not f.exists():
        return 0
    try:
        return len(json.loads(f.read_text()))
    except Exception:
        return 0


def bill_index(repo_dir: Path) -> list[dict]:
    """Per-bill summary row, not a full action dump -- the audit's job is to
    be a fast index an AI agent can scan to decide which bill to go read in
    full, not to duplicate every action already sitting in that bill's own
    metadata.json. One row per bill: id, title, latest action (date +
    description), total action count. Actions aren't reliably pre-sorted
    (seen newest-first in some states) so latest is computed by max date,
    not by position.
    """
    country_dir = repo_dir / "country:us"
    if not country_dir.is_dir():
        return []

    bills = []
    for metadata_path in country_dir.glob("*/sessions/*/bills/*/metadata.json"):
        try:
            data = json.loads(metadata_path.read_text())
        except Exception:
            continue

        actions = data.get("actions", [])
        latest_date, latest_desc = None, None
        for a in actions:
            d = a.get("date")
            if d and (latest_date is None or d > latest_date):
                latest_date, latest_desc = d, a.get("description")

        bills.append({
            "id": data.get("identifier"),
            "title": data.get("title"),
            "session": metadata_path.parent.parent.parent.name,
            "action_count": len(actions),
            "latest_action_date": latest_date,
            "latest_action_description": latest_desc,
        })
    return bills


def load_fleet_monitor_snapshot() -> dict[str, dict]:
    """Infrastructure-layer health, from Nate's fleet-monitor (not this
    script) -- workflow run status + hours since the last data commit, polled
    live from GitHub via actions/fleet-monitor/fleet_poller.py (run
    fetch_fleet_monitor_data.py first to produce this file). Deliberately a
    SEPARATE signal from everything else in this script: fleet-monitor never
    reads bill content, it only knows whether a workflow ran/succeeded and
    when a commit last landed. See what-does-healthy-mean.md's "Two layers
    of healthy" section for why these aren't merged into one score.

    Returns {code: {"data_repo": {...}, "scraper_repo": {...}}} -- a fleet
    snapshot has one record per repo, and each jurisdiction has two repos
    (govbot-data and govbot-openstates-scrapers), so group them by state.
    """
    snapshot_path = Path(__file__).parent / "fleet_monitor_snapshot.json"
    if not snapshot_path.exists():
        return {}
    records = json.loads(snapshot_path.read_text())
    by_state: dict[str, dict] = {}
    for r in records:
        code = r["state"]
        slot = "data_repo" if r["config"] == "chn-openstates-files.yml" else "scraper_repo"
        by_state.setdefault(code, {})[slot] = {
            "data_commit_age_hours": r.get("data_commit_age_hours"),
            "workflows": r.get("workflows", []),
        }
    return by_state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--govbot-dir", default=str(Path.home() / "govbot_data_local"))
    parser.add_argument(
        "--no-bill-index", action="store_true",
        help="Skip the per-bill index (faster; summary stats only).",
    )
    args = parser.parse_args()

    repos_dir = Path(args.govbot_dir) / "repos"
    out_dir = Path(__file__).parent / "audit_output"
    out_dir.mkdir(exist_ok=True)
    scraper_status = load_scraper_status()
    session_status = load_session_status()
    fleet_monitor = load_fleet_monitor_snapshot()
    if not fleet_monitor:
        print(
            "Note: no fleet_monitor_snapshot.json found -- run "
            "fetch_fleet_monitor_data.py first to include infrastructure-layer "
            "data (workflow status, commit age) in this audit.",
            file=sys.stderr,
        )
    now = datetime.now(timezone.utc)

    rows = []
    for code in sorted(scraper_status.keys()):
        repo_dir = repos_dir / f"{code}-legislation"
        present = repo_dir.is_dir()
        row = {
            "code": code,
            "present": present,
            "scraper": scraper_status.get(code, "?"),
            "session": session_status.get(code, "?"),
            # Infrastructure layer, from GitHub live via fleet-monitor -- independent
            # of whether we have a local clone at all. See load_fleet_monitor_snapshot.
            "fleet_monitor": fleet_monitor.get(code),
        }
        if present:
            last_commit = git_last_commit(repo_dir)
            row["last_commit"] = last_commit.isoformat() if last_commit else None
            row["days_since_commit"] = (
                round((now - last_commit).total_seconds() / 86400, 1) if last_commit else None
            )
            row["bill_count"] = count_bills(repo_dir)
            log_min, log_max, log_count, log_histogram = log_date_range(repo_dir)
            row["log_date_min"] = log_min
            row["log_date_max"] = log_max
            row["log_file_count"] = log_count
            row["log_histogram_by_day"] = log_histogram
            row["distinct_active_days"] = len(log_histogram)
            if log_histogram:
                busiest_day, busiest_count = max(log_histogram.items(), key=lambda kv: kv[1])
                row["busiest_day"] = busiest_day
                row["busiest_day_count"] = busiest_count
                row["busiest_day_share"] = round(busiest_count / log_count, 2)
            row["logs_per_bill"] = (
                round(log_count / row["bill_count"], 1)
                if row["bill_count"] else None
            )
            ts = read_timestamp_file(repo_dir)
            row["vote_events_watermark"] = ts.get("vote_events")
            row["events_watermark"] = ts.get("events")
            row["has_new_fields"] = "action_log_files_created" in ts
            row["implausible_fallbacks"] = ts.get("implausible_date_fallbacks", {})
            row["orphan_count"] = read_orphan_count(repo_dir)

            if not args.no_bill_index:
                bills = bill_index(repo_dir)
                row["bills_indexed"] = len(bills)
                # Per-state file, not one giant combined file -- AI-sized
                # and addressable by jurisdiction code on its own.
                state_out = {
                    "code": code,
                    "generated_at": now.isoformat(),
                    "summary": {k: v for k, v in row.items() if k != "log_histogram_by_day"},
                    "bills": bills,
                }
                (out_dir / f"{code}.json").write_text(json.dumps(state_out, indent=2, default=str))
        rows.append(row)

    missing = [r["code"] for r in rows if not r["present"]]
    present_rows = [r for r in rows if r["present"]]

    print(f"# State audit — {now.strftime('%Y-%m-%d %H:%M UTC')}\n")
    print(f"{len(present_rows)}/56 states present locally. Missing: {', '.join(missing) or 'none'}\n")

    print("## Signal integrity — any implausible-date fallbacks ever recorded?")
    flagged = [r for r in present_rows if r.get("implausible_fallbacks")]
    if flagged:
        for r in flagged:
            print(f"  ⚠️  {r['code']}: {r['implausible_fallbacks']}")
    else:
        print("  None found (expected — no repo has run format since PR #181 merged yet).\n")

    print("## Process liveness — new action_log_files_created field present?")
    have_new = [r["code"] for r in present_rows if r.get("has_new_fields")]
    print(f"  {len(have_new)}/{len(present_rows)} repos have it. "
          f"{'(' + ', '.join(have_new) + ')' if have_new else '(none yet — needs a post-PR#181 format run)'}\n")

    print("## Bill count vs. log date range — flagged anomalies")
    print("  (bills with zero logs, or a suspiciously thin logs-per-bill ratio — worth a")
    print("   closer look, not necessarily broken: GU is already known to have 0 actions")
    print("   on every bill per pdf-only-bill-detail-audit.md, so that's not new.)\n")
    zero_logs = [r for r in present_rows if r.get("bill_count") and not r.get("log_file_count")]
    thin = [
        r for r in present_rows
        if r.get("logs_per_bill") is not None and 0 < r["logs_per_bill"] < 1 and r["code"] not in {z["code"] for z in zero_logs}
    ]
    if zero_logs:
        print("  Zero log files despite having bills:")
        for r in zero_logs:
            print(f"    {r['code']}: {r['bill_count']} bills, 0 logs")
    if thin:
        print("  Thin logs-per-bill ratio (<1):")
        for r in thin:
            print(f"    {r['code']}: {r['bill_count']} bills, {r['log_file_count']} logs ({r['logs_per_bill']}/bill)")
    if not zero_logs and not thin:
        print("  None found.")
    print()

    print("## Infrastructure layer (fleet-monitor) — scrape workflow not succeeding")
    print("  (the raw scrape workflow's last successful run is >7 days old for an")
    print("   IN-SESSION, non-paused jurisdiction -- format/extract can still look healthy")
    print("   while the underlying scrape is stuck, exactly like FL. Checked independently")
    print("   of everything else in this script -- see what-does-healthy-mean.md.)\n")
    scrape_stuck = []
    for r in present_rows:
        fm = r.get("fleet_monitor")
        if not fm or r["scraper"] != "active" or r["session"] != "in":
            continue
        scraper_wf = (fm.get("scraper_repo") or {}).get("workflows", [])
        for w in scraper_wf:
            if "scrape" in w["workflow"] and (w["hours_since_success"] is None or w["hours_since_success"] > 168):
                scrape_stuck.append((r["code"], w["workflow"], w["hours_since_success"], w["latest_conclusion"]))
    if scrape_stuck:
        for code, wf, hrs, concl in scrape_stuck:
            hrs_str = f"{hrs:.0f}h" if hrs is not None else "never"
            print(f"    ⚠️  {code}: {wf} last succeeded {hrs_str} ago (latest run: {concl})")
    else:
        print("  None found.")
    print()

    print("## Daily activity histogram — bulk-backfill signature check")
    print("  (states where one single day holds >50% of all log files ever written --")
    print("   usually means a one-time historical import, not real day-by-day legislative")
    print("   activity. Not necessarily wrong, just worth knowing before trusting")
    print("   'distinct active days' as a measure of how often this state is really busy.)\n")
    backfill_like = [
        r for r in present_rows
        if r.get("busiest_day_share") is not None and r["busiest_day_share"] > 0.5 and r.get("log_file_count", 0) > 10
    ]
    if backfill_like:
        for r in sorted(backfill_like, key=lambda r: -r["busiest_day_share"]):
            print(
                f"    {r['code']}: {r['busiest_day_share']:.0%} of {r['log_file_count']} logs landed on "
                f"{r['busiest_day']} (spread across {r['distinct_active_days']} distinct days total)"
            )
    else:
        print("  None found.")
    print()

    print("## Full table\n")
    header = (
        f"{'code':<5} {'scraper':<8} {'session':<8} {'bills':>6} {'logs':>7} {'logs/bill':>9} "
        f"{'log range (min → max)':<35} {'last commit':<12} {'days ago':>9}"
    )
    print(header)
    print("-" * len(header))
    for r in present_rows:
        log_range = f"{(r.get('log_date_min') or '?')[:8]} → {(r.get('log_date_max') or '?')[:8]}"
        print(
            f"{r['code']:<5} {r['scraper']:<8} {r['session']:<8} "
            f"{str(r.get('bill_count', '?')):>6} "
            f"{str(r.get('log_file_count', '?')):>7} "
            f"{str(r.get('logs_per_bill', '?')):>9} "
            f"{log_range:<35} "
            f"{(r.get('last_commit') or '?')[:10]:<12} "
            f"{str(r.get('days_since_commit', '?')):>9}"
        )

    summary_path = Path(__file__).parent / "audit_states_output.json"
    summary_path.write_text(json.dumps(rows, indent=2, default=str))
    total_bills = sum(r.get("bills_indexed", 0) for r in present_rows)
    print(
        f"\nState-level summary: {summary_path}\n"
        f"Per-bill index (primary, AI-consumption-sized, one file per state): "
        f"{out_dir}/<code>.json ({total_bills} bills indexed across {len(present_rows)} states)"
    )


if __name__ == "__main__":
    main()
