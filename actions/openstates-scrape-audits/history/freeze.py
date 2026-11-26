#!/usr/bin/env python3
"""Freeze the auditor's check settings before a held-out test (plan doc, overnight step 2).

Writes <out>/frozen-settings.json: every check's rule and limits, how a state's own settings are
made, the fleet fallback values a thin state takes, the in-sample states' settings, and the
sha256 of the code that applies them. replay.py --frozen refuses to score with settings that
differ from it, so held-out scores can't be tuned after the fact.

usage: python3 freeze.py [--out ...]       (after profiles.py --all on the in-sample states)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import daily  # noqa: E402
import profiles  # noqa: E402
import replay  # noqa: E402

CODE = ("scan.py", "daily.py", "profiles.py", "replay.py")


def settings() -> dict:
    """The settings as this code applies them (no data needed)."""
    return {
        "checks": {
            "no_scrape": {"rule": "no scrape commit touching _data/<st>/ for more than N days (commits touching only "
                                  ".windycivi/ or workflows, and hand commits, don't count); while the silence began "
                                  "in a fleet alarm naming the state, it waits until the silence passes 14 days",
                          "N": "per state, in session and out (profile_method)"},
            "fleet_no_scrape": {"rule": "K+ states each reach N days without a data commit within W days",
                                "K": replay.FLEET_K, "N": replay.FLEET_N, "W": replay.FLEET_WINDOW},
            "unchanged": {"rule": "in session (whole window), scrapes committed but no new bill, action or vote "
                                  "for N days", "N": "per state (profile_method)"},
            "no_new_bills": {"rule": "in session, new actions but no new bill for N days", "N": "per state",
                             "status": "dropped for 2027 (review of the overnight work): needs per-state filing deadlines"},
            "empty_scrape": {"rule": "a committed scrape with 0 readable bills, after one with bills"},
            "field_loss": {"rule": "a top-level field emptied on at least half of the 20+ bills that had it",
                           "min_had": 20, "share": 0.5},
            "broken_votes": {"rule": "in one scrape, error-page voters >= E, or roll calls emptied >= M",
                             "E": replay.ERROR_VOTERS_MIN, "M": replay.EMPTIED_VOTES_MIN},
            "chamber_swap": {"rule": "actions back under another chamber, same date and words, >= M in one scrape",
                             "M": 50},
            "bill_drop": {"rule": "5%+ of bills (20+) gone in one scrape and still gone in the next, not a whole "
                                  "session leaving", "status": "not ready: no test case"},
        },
        "profile_method": {
            "healthy_days": "outside every known_events.EVENTS window and every gap of over "
                            f"{profiles.LONG_GAP_DAYS} days without a data commit",
            "no_scrape_in_session_days": f"longest healthy in-session gap + 1, at least "
                                         f"{profiles.DEFAULTS['no_scrape_in_session_days']}, at most "
                                         f"{profiles.IN_SESSION_NO_SCRAPE_CAP}",
            "no_scrape_out_of_session_days": f"longest healthy out-of-session gap + 1, at least "
                                             f"{profiles.DEFAULTS['no_scrape_out_of_session_days']}",
            "gaps_left_out": "gaps overlapping a fleet_no_scrape alarm day",
            "unchanged_in_session_days": f"longest healthy in-session quiet run of at most "
                                         f"{profiles.SUSPECT_QUIET_DAYS} days + 2, at least "
                                         f"{profiles.DEFAULTS['unchanged_in_session_days']}, at most "
                                         f"{profiles.UNCHANGED_CAP}; longer runs are suspected freezes",
            "thin": f"fewer than {profiles.THIN_DAYS} healthy days or fewer than 10 in session: every setting "
                    "from fleet_fallback",
            "in_session": "the 2026 calendar window (session-calendar-2026.md), or all year for FULL_TIME",
            "scrapes": "commits whose subject a scrape writes (daily.SCRAPE_SUBJECTS); hand commits are left out",
            "full_time": sorted(daily.FULL_TIME),
            "defaults": profiles.DEFAULTS,
        },
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, default=Path("/Volumes/govbot-data/scratch/history-analysis"))
    a = p.parse_args(argv)
    profs = {f.stem: json.loads(f.read_text()) for f in sorted((a.out / "profiles").glob("*.json"))}
    doc = settings()
    doc["frozen_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    doc["code_sha256"] = {f: hashlib.sha256((HERE / f).read_bytes()).hexdigest() for f in CODE}
    doc["answer_key_sha256"] = hashlib.sha256((HERE / "known_events.py").read_bytes()).hexdigest()
    doc["in_sample_states"] = sorted(profs)
    doc["fleet_fallback"] = profiles.fleet_fallback(profs)
    doc["per_state_thresholds"] = {s: {k: v["value"] for k, v in p["thresholds"].items()} for s, p in profs.items()}
    out = a.out / "frozen-settings.json"
    out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    print(out, hashlib.sha256(out.read_bytes()).hexdigest(), doc["frozen_at"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
