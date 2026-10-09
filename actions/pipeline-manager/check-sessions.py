#!/usr/bin/env python3
"""
Check OpenStates API for active legislative sessions and update pipeline config.

Reads chn-openstates-scrape.yml, queries the OpenStates v3 API for each locale,
and flips the template between 'openstates-scrape' (in session) and
'openstates-scrape-paused' (out of session) based on today's date.

Usage:
    OPENSTATES_API_KEY=your_key python3 check-sessions.py
    OPENSTATES_API_KEY=your_key python3 check-sessions.py --dry-run
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import date
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "chn-openstates-scrape.yml"

ACTIVE_TEMPLATE = "openstates-scrape"
PAUSED_TEMPLATE = "openstates-scrape-paused"

# OCD jurisdiction IDs for non-state codes
OCD_ID_MAP = {
    "dc":  "ocd-jurisdiction/country:us/district:dc/government",
    "pr":  "ocd-jurisdiction/country:us/territory:pr/government",
    "gu":  "ocd-jurisdiction/country:us/territory:gu/government",
    "vi":  "ocd-jurisdiction/country:us/territory:vi/government",
    "mp":  "ocd-jurisdiction/country:us/territory:mp/government",
    "usa": "ocd-jurisdiction/country:us/government",
}


def ocd_id_for(code: str) -> str:
    return OCD_ID_MAP.get(code, f"ocd-jurisdiction/country:us/state:{code}/government")


def fetch_sessions(ocd_id: str, api_key: str, max_retries: int = 5) -> list:
    url = f"https://v3.openstates.org/jurisdictions/{ocd_id}?include=legislative_sessions&apikey={api_key}"
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.loads(resp.read())
                return data.get("legislative_sessions", [])
        except urllib.error.HTTPError as e:
            if e.code == 429:
                # OpenStates doesn't reliably send a Retry-After header, so the
                # fallback default matters — 5s wasn't enough for the token
                # bucket to refill in practice, so start higher and ramp faster.
                retry_after = int(e.headers.get("Retry-After", 15))
                wait = max(retry_after, 2 ** (attempt + 3))
                print(f"    ⏳ rate limited, waiting {wait}s (attempt {attempt + 1}/{max_retries})", file=sys.stderr)
                time.sleep(wait)
                continue
            print(f"    ⚠️  HTTP {e.code} — {e.reason}", file=sys.stderr)
            return []
        except Exception as e:
            print(f"    ⚠️  {e}", file=sys.stderr)
            return []
    print(f"    ⚠️  gave up after {max_retries} retries", file=sys.stderr)
    return []


YEAR_RANGE_RE = re.compile(r"(20\d{2})\D{0,3}(20\d{2})")


def corrected_end_date(session: dict, end_date: date) -> date:
    """
    OpenStates has a known data bug where biennium sessions (e.g. "2025-2026
    Regular Session") have end_date stuck somewhere in the *first* year
    instead of extending into the second — confirmed on DC (Dec 31), MI
    (Dec 31), PA (Nov 30), and NC (Jul 1) as of 2026-06-30. The truncated
    day/month varies by jurisdiction, so rather than matching a specific
    day/month, we just check whether the session's own name/identifier
    implies a year exactly one later than the recorded end_date's year —
    if so, trust the name and extend through Dec 31 of the implied year.
    Capped at exactly +1 year to avoid over-correcting on a coincidental
    regex match.
    """
    # Search name first — identifier is sometimes a bare single year (e.g. NC's
    # "2025"), and concatenating identifier + name before searching can trick
    # the regex into matching across the two fields (identifier's lone year +
    # the first year of name's range) instead of the real range in the name.
    match = YEAR_RANGE_RE.search(session.get("name", "")) or YEAR_RANGE_RE.search(
        session.get("identifier", "")
    )
    if not match:
        return end_date
    implied_year = int(match.group(2))
    if implied_year - end_date.year == 1:
        return date(implied_year, 12, 31)
    return end_date


def is_in_session(sessions: list, today: date) -> tuple[bool, str]:
    """Return (in_session, matching_session_name).

    The sessions array from the API is not strictly chronological, and some
    historical entries have a missing/null end_date (data quality issue, not
    an indication the session is still ongoing). To avoid matching stale old
    sessions, only consider sessions that started within the last 2 years.
    """
    cutoff_year = today.year - 2
    for session in sessions:
        start = session.get("start_date")
        end = session.get("end_date")
        if not start:
            continue
        start_date = date.fromisoformat(start)
        if start_date.year < cutoff_year:
            continue
        end_date = date.fromisoformat(end) if end else None
        if end_date is not None:
            end_date = corrected_end_date(session, end_date)
        if start_date <= today and (end_date is None or end_date >= today):
            return True, session.get("name", session.get("identifier", ""))
    return False, ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing them")
    parser.add_argument("--only", help="Comma-separated locale codes to check (e.g. ia,mt,or,wv,mp)")
    args = parser.parse_args()

    api_key = os.environ.get("OPENSTATES_API_KEY")
    if not api_key:
        print("❌ OPENSTATES_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    with open(CONFIG_FILE) as f:
        config = yaml.safe_load(f)

    today = date.today()
    print(f"📅 Checking sessions as of {today}\n")

    locales = config.get("locales", {})
    if args.only:
        wanted = {c.strip() for c in args.only.split(",")}
        locales = {c: cfg for c, cfg in locales.items() if c in wanted}
        missing = wanted - locales.keys()
        if missing:
            print(f"⚠️  Unknown locale code(s): {', '.join(sorted(missing))}", file=sys.stderr)

    changes = []
    errors = []

    for code, locale_cfg in locales.items():
        current_template = locale_cfg.get("template", ACTIVE_TEMPLATE)
        ocd_id = ocd_id_for(code)

        sessions = fetch_sessions(ocd_id, api_key)
        if not sessions:
            # Either rate-limited (retries exhausted) or OpenStates has no session
            # data at all for this jurisdiction (confirmed for mp — empty
            # legislative_sessions array, no scraper coverage). Either way, leave
            # the existing template untouched rather than guessing.
            errors.append(code)
            print(f"  {code:4s}  ⚠️  no data returned, skipping")
            time.sleep(1.2)
            continue

        in_session, session_name = is_in_session(sessions, today)
        new_template = ACTIVE_TEMPLATE if in_session else PAUSED_TEMPLATE
        changed = current_template != new_template

        status = "✅" if in_session else "⏸️ "
        flag = " ← CHANGED" if changed else ""
        label = f"({session_name})" if in_session and session_name else ""
        print(f"  {code:4s}  {status}  {new_template}{flag}  {label}")

        if changed:
            changes.append((code, current_template, new_template))
            if not args.dry_run:
                locale_cfg["template"] = new_template

        time.sleep(1.2)  # stay under 1 req/sec rate limit with margin

    print(f"\n{'─' * 60}")
    print(f"  {len(locales) - len(errors)} checked  |  {len(changes)} changed  |  {len(errors)} skipped")

    if errors:
        print(f"\n⚠️  Skipped (no API data): {', '.join(errors)}")

    if not changes:
        print("\n✅ All templates already correct — no changes needed")
        return 0

    if args.dry_run:
        print(f"\n🔍 Dry run — would update {len(changes)} locale(s):")
        for code, old, new in changes:
            print(f"   {code}: {old} → {new}")
        return 0

    # Write updated config preserving structure
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"\n✅ Updated {CONFIG_FILE.name} ({len(changes)} change(s)):")
    for code, old, new in changes:
        print(f"   {code}: {old} → {new}")

    # Write changed locale codes to GitHub Actions output for targeted apply
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output and changes:
        changed_codes = ",".join(code for code, _, _ in changes)
        with open(github_output, "a") as f:
            f.write(f"changed_locales={changed_codes}\n")

    return len(changes)


if __name__ == "__main__":
    result = main()
    sys.exit(0 if result == 0 or isinstance(result, int) else 1)
