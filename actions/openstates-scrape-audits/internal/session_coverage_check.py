#!/usr/bin/env python3
"""Did each scraper's captured activity actually cover its real legislative
session? Compares log_date_max (most recent government-recorded action we
have, across the whole repo) against that state's own session Adjourns date
from session-calendar-2026.md.

Deliberately NOT comparing log_date_min against Convenes: a repo holds
every session it's ever captured, not just the current one (confirmed:
session folders are named inconsistently across states -- "2025-2028" for
PR, separate "2025"/"2026" for WY, "2025_26"/"2026_ss" for GA -- so there's
no reliable generic way to isolate just the current session's bills). That
makes log_date_min reflect the oldest action in the repo's whole history,
not this session's start -- comparing it to Convenes would flag nearly
every state as "started too early" for no real reason. log_date_max doesn't
have this problem: it's the single most recent action regardless of how
many old sessions are also in the repo, so "did activity reach/pass
Adjourns" stays a meaningful question.

Also separates two different explanations for a gap:
  - genuine_gap_days: Adjourns minus log_date_max. Positive = our data
    stops before the session was supposed to end.
  - clone_could_explain_gap: true when our own local clone's last git
    commit (last_commit) is ALSO before Adjourns -- meaning we simply
    haven't re-pulled since before the session ended, so the gap may be
    about clone staleness, not a broken scraper. Only trust a gap as a
    real scraper problem when this is false (i.e. we pulled recently
    enough that a real scraper should have caught up by now).

Reads the already-computed tamara-notes/processes/audit_states_output.json
(run audit_states.py first) -- doesn't re-scan the filesystem.

Usage: python3 session_coverage_check.py
"""
import json
import re
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SESSION_CALENDAR = REPO_ROOT / "tamara-notes" / "session-dates" / "session-calendar-2026.md"
AUDIT_OUTPUT = Path(__file__).parent / "audit_states_output.json"


def load_session_dates() -> dict[str, dict]:
    """Parse the Convenes/Adjourns columns from session-calendar-2026.md's
    main table. Returns {code: {"convenes": date|None, "adjourns": date|None}}.
    "—" (no regular session) and non-date notes both map to None.
    """
    text = SESSION_CALENDAR.read_text()
    rows = re.findall(
        r"^\| (\w+) \| [^|]+\| [^|]+\| ([^|]+)\| ([^|]+)\| (?:✅|⏸️|❓) \|",
        text, re.M,
    )
    out = {}
    for code, convenes_raw, adjourns_raw in rows:
        def parse(raw):
            raw = raw.strip()
            m = re.match(r"(\d{4}-\d{2}-\d{2})", raw)
            return date.fromisoformat(m.group(1)) if m else None
        out[code] = {"convenes": parse(convenes_raw), "adjourns": parse(adjourns_raw)}
    return out


def main():
    session_dates = load_session_dates()
    audit_rows = json.loads(AUDIT_OUTPUT.read_text())

    results = []
    for row in audit_rows:
        code = row["code"]
        if not row.get("present"):
            continue
        sd = session_dates.get(code, {})
        adjourns = sd.get("adjourns")
        log_max_raw = row.get("log_date_max")
        last_commit_raw = row.get("last_commit")

        entry = {
            "code": code,
            "scraper_status": row.get("scraper"),
            "session_status": row.get("session"),
            "adjourns": adjourns.isoformat() if adjourns else None,
            "log_date_max": log_max_raw,
        }

        if not adjourns or not log_max_raw:
            entry["note"] = (
                "no fixed Adjourns date (territory / no regular session / not a "
                "LegiScan jurisdiction)" if not adjourns else "no log files found"
            )
            results.append(entry)
            continue

        log_max_date = datetime.strptime(log_max_raw[:8], "%Y%m%d").date()
        genuine_gap_days = (adjourns - log_max_date).days
        entry["genuine_gap_days"] = genuine_gap_days

        if last_commit_raw:
            last_commit_date = datetime.fromisoformat(last_commit_raw).date()
            entry["last_commit"] = last_commit_date.isoformat()
            entry["clone_could_explain_gap"] = last_commit_date < adjourns
        else:
            entry["clone_could_explain_gap"] = None

        results.append(entry)

    with_dates = [r for r in results if "genuine_gap_days" in r]
    no_dates = [r for r in results if "genuine_gap_days" not in r]

    # A real concern: log coverage stops meaningfully before Adjourns, AND
    # our clone was pulled recently enough that staleness can't explain it.
    real_concerns = [
        r for r in with_dates
        if r["genuine_gap_days"] > 14 and r["clone_could_explain_gap"] is False
    ]
    clone_stale_only = [
        r for r in with_dates
        if r["genuine_gap_days"] > 14 and r["clone_could_explain_gap"] is True
    ]
    covers_through_end = [r for r in with_dates if r["genuine_gap_days"] <= 14]

    print(f"# Session coverage check — {len(with_dates)} states with a fixed Adjourns date, "
          f"{len(no_dates)} skipped (territories / no regular session)\n")

    print(f"## Covers through (or past) Adjourns — {len(covers_through_end)} states")
    print("  (gap <= 14 days; trailing post-session activity like signatures is expected and fine)\n")

    print(f"## Gap explained by stale local clone, not necessarily the scraper — {len(clone_stale_only)} states")
    for r in sorted(clone_stale_only, key=lambda r: -r["genuine_gap_days"]):
        print(f"    {r['code']}: log stops {r['genuine_gap_days']}d before Adjourns "
              f"({r['adjourns']}), but our clone itself was last pulled {r['last_commit']} "
              f"(also before Adjourns) — re-pull before trusting this as a real gap")
    print()

    print(f"## REAL CONCERN — gap persists even though our clone is recent enough — {len(real_concerns)} states")
    if real_concerns:
        for r in sorted(real_concerns, key=lambda r: -r["genuine_gap_days"]):
            print(f"    ⚠️  {r['code']}: log stops {r['genuine_gap_days']}d before Adjourns "
                  f"({r['adjourns']}), clone pulled {r['last_commit']} — scraper may have "
                  f"genuinely stopped early")
    else:
        print("    None.")
    print()

    out_path = Path(__file__).parent / "session_coverage_output.json"
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"Full results: {out_path}")


if __name__ == "__main__":
    main()
