#!/usr/bin/env python3
"""
Cross-check govbot-data bill counts against LegiScan's own master bill list.

This is the "outside source" step 56-state-audit-plan.md flags as still open:
session dates (session-dates-comparison.md) tell us *whether* a state should
have bills right now, not whether we're actually missing any. LegiScan's
getMasterList operation returns the real bill_number list for a session, so
we can diff our committed identifiers against it directly instead of trusting
"the pipeline didn't error."

Read-only / report-only — this never writes to govbot-data or any config
file. It answers "are we missing bills," it doesn't fix anything.

Status: written 2026-08-07, NOT YET RUN LIVE. A LegiScan public API key was
requested the same day but is still pending approval (30,000 queries/month
once granted -- see tamara-notes/session-dates/LegiScan_API_User_Manual.pdf).
Every LegiScan-facing function below is written against the documented API
shape but unverified against a live response. Run `--self-test` to check the
identifier-normalization/diff logic, which needs no network access.

Known gap: GU, MP, PR, VI are not LegiScan jurisdictions at all (confirmed in
session-dates-comparison.md -- their session dates there are sourced from
each territory's own legislature site instead). They're skipped here with a
"no LegiScan coverage" note, not silently dropped.

Usage:
    LEGISCAN_API_KEY=your_key python3 legiscan-audit.py
    LEGISCAN_API_KEY=your_key python3 legiscan-audit.py --only nc,pa,wy
    python3 legiscan-audit.py --self-test
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "chn-openstates-scrape.yml")

# Jurisdictions LegiScan does not track at all (confirmed via
# session-dates-comparison.md). Flagged as "no coverage," never silently
# skipped without a reason in the output.
NO_LEGISCAN_COVERAGE = {"gu", "mp", "pr", "vi"}

# LegiScan's state parameter for non-state jurisdictions we do cover.
LEGISCAN_STATE_CODE = {
    "usa": "US",
    "dc": "DC",
}

REQUEST_DELAY_SECONDS = 1.0  # courtesy throttle; LegiScan publishes no documented per-second cap


def legiscan_state_code(locale: str) -> str:
    return LEGISCAN_STATE_CODE.get(locale, locale.upper())


def legiscan_get(op: str, api_key: str, **params) -> dict:
    query = "&".join([f"key={api_key}", f"op={op}"] + [f"{k}={v}" for k, v in params.items()])
    url = f"https://api.legiscan.com/?{query}"
    with urllib.request.urlopen(url, timeout=20) as resp:
        data = json.loads(resp.read())
    if data.get("status") != "OK":
        raise RuntimeError(f"LegiScan {op} returned status={data.get('status')!r}: {data.get('alert', data)}")
    return data


def fetch_session_list(locale: str, api_key: str) -> list:
    data = legiscan_get("getSessionList", api_key, state=legiscan_state_code(locale))
    return data.get("sessions", [])


def pick_current_session(sessions: list, today: date) -> dict | None:
    """Pick the session whose year range brackets today, preferring a Regular
    session over a Special one and skipping anything LegiScan marks `prior`
    (its own "this is superseded/legacy" flag). Mirrors the spirit of
    check-sessions.py's is_in_session(), adapted to LegiScan's schema
    (year_start/year_end instead of start_date/end_date, no explicit
    corrected_end_date bug to work around -- that was an OpenStates-specific
    data quality issue).
    """
    candidates = [s for s in sessions if not s.get("prior") and s.get("year_start", 0) <= today.year <= s.get("year_end", 0)]
    if not candidates:
        return None
    regular = [s for s in candidates if not s.get("special")]
    return (regular or candidates)[0]


def fetch_master_list(session_id: int, api_key: str) -> dict:
    """Returns {normalized_bill_number: raw_bill_number}."""
    data = legiscan_get("getMasterList", api_key, id=session_id)
    masterlist = data.get("masterlist", {})
    out = {}
    for key, bill in masterlist.items():
        if key == "session":  # getMasterList's dict sometimes includes a "session" metadata entry alongside numeric keys
            continue
        number = bill.get("number")
        if number:
            out[normalize_identifier(number)] = number
    return out


IDENTIFIER_RE = re.compile(r"^([A-Za-z]+)\s*0*(\d+)([A-Za-z]*)$")


def normalize_identifier(raw: str) -> str:
    """Normalize a bill identifier for cross-source comparison.

    Our own metadata uses e.g. "HB0006" (zero-padded, no space); LegiScan
    uses e.g. "HB6" or "HB 6" (no padding, space varies). Strip whitespace,
    uppercase, and drop leading zeros on the numeric portion so both land on
    the same key ("HB6"). Anything that doesn't match the letters+digits
    shape is passed through uppercased/stripped rather than dropped, so an
    unexpected format shows up as a mismatch instead of silently vanishing.
    """
    cleaned = raw.strip().upper().replace(" ", "")
    match = IDENTIFIER_RE.match(cleaned)
    if not match:
        return cleaned
    prefix, digits, suffix = match.groups()
    return f"{prefix}{int(digits)}{suffix}"


YEAR_RE = re.compile(r"20\d{2}")


def pick_our_session_dir(session_dirs: list, legiscan_session: dict) -> str | None:
    """Match one of our own sessions/{dir} names to the LegiScan session's
    year range by the first 4-digit year found in the directory name (e.g.
    "2026", "2025-2026", "2026ss1" all yield 2026). Ambiguous by design if a
    state has two of our session dirs land on the same year -- that's a real
    "which one is current" question, not something to silently guess at, so
    we return the first match and flag multiple below.
    """
    year_start, year_end = legiscan_session.get("year_start"), legiscan_session.get("year_end")
    for d in session_dirs:
        m = YEAR_RE.search(d)
        if m and year_start <= int(m.group()) <= year_end:
            return d
    return None


def gh_api(path: str) -> list | dict | None:
    result = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


def fetch_our_session_dirs(locale: str) -> list:
    contents = gh_api(f"repos/govbot-data/{locale}-legislation/contents/country:us/state:{locale}/sessions")
    if not contents:
        return []
    return [item["name"] for item in contents if item.get("type") == "dir"]


def fetch_our_identifiers(locale: str, session_dir: str) -> dict:
    """Returns {normalized_bill_number: raw_bill_number} from our committed
    bills/ directory names -- the directory name *is* the identifier
    (confirmed via mocks/govbot_data, e.g. sessions/2026/bills/HB0006/), so
    this is a single directory listing, not a metadata.json fetch per bill.
    """
    path = f"repos/govbot-data/{locale}-legislation/contents/country:us/state:{locale}/sessions/{session_dir}/bills"
    contents = gh_api(path)
    if not contents:
        return {}
    return {normalize_identifier(item["name"]): item["name"] for item in contents if item.get("type") == "dir"}


def diff_bills(ours: dict, legiscan: dict) -> dict:
    ours_keys, legiscan_keys = set(ours), set(legiscan)
    return {
        "matched": len(ours_keys & legiscan_keys),
        "missing_from_ours": sorted(legiscan[k] for k in legiscan_keys - ours_keys),
        "extra_in_ours": sorted(ours[k] for k in ours_keys - legiscan_keys),
    }


def audit_locale(locale: str, api_key: str, today: date) -> dict:
    if locale in NO_LEGISCAN_COVERAGE:
        return {"locale": locale, "status": "no_legiscan_coverage"}

    sessions = fetch_session_list(locale, api_key)
    if not sessions:
        return {"locale": locale, "status": "no_legiscan_session_data"}

    session = pick_current_session(sessions, today)
    if session is None:
        return {"locale": locale, "status": "no_current_legiscan_session"}

    legiscan_bills = fetch_master_list(session["session_id"], api_key)

    our_session_dirs = fetch_our_session_dirs(locale)
    our_dir = pick_our_session_dir(our_session_dirs, session)
    if our_dir is None:
        return {
            "locale": locale,
            "status": "no_matching_our_session",
            "legiscan_session": session.get("session_title"),
            "our_session_dirs": our_session_dirs,
            "legiscan_bill_count": len(legiscan_bills),
        }

    our_bills = fetch_our_identifiers(locale, our_dir)
    diff = diff_bills(our_bills, legiscan_bills)

    return {
        "locale": locale,
        "status": "compared",
        "legiscan_session": session.get("session_title"),
        "our_session_dir": our_dir,
        "legiscan_bill_count": len(legiscan_bills),
        "our_bill_count": len(our_bills),
        **diff,
    }


def run_self_test() -> int:
    """Exercises normalize_identifier/pick_current_session/diff_bills against
    fixtures -- no network access needed. This is the part of the script that
    CAN be verified before the LegiScan API key is approved.
    """
    failures = []

    def check(label, actual, expected):
        if actual != expected:
            failures.append(f"{label}: expected {expected!r}, got {actual!r}")

    check("normalize HB0006", normalize_identifier("HB0006"), "HB6")
    check("normalize HB 6", normalize_identifier("HB 6"), "HB6")
    check("normalize AB1", normalize_identifier("AB1"), "AB1")
    check("normalize lowercase", normalize_identifier("hb0006"), "HB6")
    check("normalize suffix", normalize_identifier("SB0012A"), "SB12A")
    check("normalize passthrough", normalize_identifier("???"), "???")

    sessions = [
        {"session_id": 1, "year_start": 2023, "year_end": 2024, "prior": 1, "special": 0},
        {"session_id": 2, "year_start": 2025, "year_end": 2026, "prior": 0, "special": 1},
        {"session_id": 3, "year_start": 2025, "year_end": 2026, "prior": 0, "special": 0},
    ]
    picked = pick_current_session(sessions, date(2026, 1, 1))
    check("pick_current_session prefers regular over special", picked and picked["session_id"], 3)
    check("pick_current_session skips prior", pick_current_session(sessions[:1], date(2024, 1, 1)), None)

    ours = {"HB6": "HB0006", "HB7": "HB0007"}
    legiscan = {"HB6": "HB6", "HB8": "HB8"}
    check(
        "diff_bills",
        diff_bills(ours, legiscan),
        {"matched": 1, "missing_from_ours": ["HB8"], "extra_in_ours": ["HB0007"]},
    )

    if failures:
        print(f"❌ {len(failures)} self-test failure(s):", file=sys.stderr)
        for f in failures:
            print(f"   {f}", file=sys.stderr)
        return 1
    print("✅ all self-tests passed")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="Comma-separated locale codes to check (e.g. nc,pa,wy)")
    parser.add_argument("--out", help="Write JSON report to this path instead of stdout")
    parser.add_argument("--self-test", action="store_true", help="Run offline unit checks and exit (no API key/network needed)")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(run_self_test())

    api_key = os.environ.get("LEGISCAN_API_KEY")
    if not api_key:
        print("❌ LEGISCAN_API_KEY not set (key still pending approval as of 2026-08-07 -- run --self-test instead)", file=sys.stderr)
        sys.exit(1)

    import yaml

    with open(CONFIG_FILE) as f:
        config = yaml.safe_load(f)
    locales = sorted(config.get("locales", {}))
    if args.only:
        wanted = {c.strip() for c in args.only.split(",")}
        locales = [c for c in locales if c in wanted]

    today = date.today()
    results = []
    for locale in locales:
        print(f"  {locale:4s}  checking...", file=sys.stderr)
        try:
            result = audit_locale(locale, api_key, today)
        except Exception as e:
            result = {"locale": locale, "status": "error", "error": str(e)}
        results.append(result)
        status = result["status"]
        flag = ""
        if status == "compared" and (result["missing_from_ours"] or result["extra_in_ours"]):
            flag = f"  ⚠️  {len(result['missing_from_ours'])} missing, {len(result['extra_in_ours'])} extra"
        print(f"  {locale:4s}  {status}{flag}", file=sys.stderr)
        time.sleep(REQUEST_DELAY_SECONDS)

    output = json.dumps({"generated": today.isoformat(), "results": results}, indent=2)
    if args.out:
        with open(args.out, "w") as f:
            f.write(output)
        print(f"\nWrote report to {args.out}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
