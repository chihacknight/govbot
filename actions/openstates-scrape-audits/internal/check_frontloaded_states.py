#!/usr/bin/env python3
"""Which states front-load all their bills at session start (like GU) vs. a
steady stream throughout? For each bill, the EARLIEST action date is a proxy
for "when this bill was first introduced" (not exactly "when we first saw
it," but close and usable -- and unlike relying on action-log dates alone,
this still works for most states since most bills do have at least one
action). Buckets each state's bills by week of earliest-action-date and
reports what fraction falls in the single busiest week -- a state near 100%
is GU-like (front-loaded, flatlining afterward is normal); a state spread
across many weeks is not.

Note: GU itself can't be measured this way (0 action logs at all, confirmed
separately) -- it's the one state we already know is front-loaded by a
different kind of evidence (bill_count=277, log_file_count=0). This script
is for finding OTHER states with the same front-loaded pattern that GU's
zero-logs signature wouldn't reveal on its own.

Usage: python3 check_frontloaded_states.py [--govbot-dir ~/govbot_data_local]
"""
import argparse
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path


def week_bucket(date_str: str) -> str:
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d")
    except Exception:
        return "unknown"
    monday = d - timedelta(days=d.weekday())
    return monday.strftime("%Y-%m-%d")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--govbot-dir", default=str(Path.home() / "govbot_data_local"))
    args = parser.parse_args()
    repos_dir = Path(args.govbot_dir) / "repos"

    results = []
    for repo_dir in sorted(repos_dir.glob("*-legislation")):
        code = repo_dir.name.replace("-legislation", "")
        country_dir = repo_dir / "country:us"
        if not country_dir.is_dir():
            continue

        earliest_dates = []
        for metadata_path in country_dir.glob("*/sessions/*/bills/*/metadata.json"):
            try:
                data = json.loads(metadata_path.read_text())
            except Exception:
                continue
            actions = data.get("actions", [])
            dates = [a.get("date") for a in actions if a.get("date")]
            if dates:
                earliest_dates.append(min(dates))

        if not earliest_dates:
            results.append({"code": code, "bills_with_dates": 0, "note": "no bills have any dated action"})
            continue

        buckets = Counter(week_bucket(d) for d in earliest_dates)
        busiest_week, busiest_count = buckets.most_common(1)[0]
        total = len(earliest_dates)
        results.append({
            "code": code,
            "bills_with_dates": total,
            "distinct_weeks": len(buckets),
            "busiest_week": busiest_week,
            "busiest_week_share": round(busiest_count / total, 2),
        })
        print(f"{code}: {total} bills, {len(buckets)} distinct weeks, "
              f"busiest week {busiest_week} holds {busiest_count/total:.0%}")

    out_path = Path(__file__).parent / "frontloaded_check_output.json"
    out_path.write_text(json.dumps(results, indent=2))

    print("\n# Candidates for GU-style front-loaded exception (busiest week >= 50%)\n")
    for r in sorted(results, key=lambda r: -r.get("busiest_week_share", 0)):
        if r.get("busiest_week_share", 0) >= 0.5:
            print(f"  {r['code']}: {r['busiest_week_share']:.0%} in week of {r['busiest_week']} "
                  f"({r['bills_with_dates']} bills, {r['distinct_weeks']} distinct weeks total)")


if __name__ == "__main__":
    main()
