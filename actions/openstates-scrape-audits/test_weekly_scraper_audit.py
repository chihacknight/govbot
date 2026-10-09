#!/usr/bin/env python3
"""Offline tests for weekly-scraper-audit.py's "behind the legislature" check (check 3).

No network: GitHub raw fetches, the site's bills/index.json and the OpenStates API are all
replaced with fakes, and the committed output/ files are redirected to a temp dir.
Run: python3 actions/openstates-scrape-audits/test_weekly_scraper_audit.py
"""

import importlib.util
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("audit", HERE / "weekly-scraper-audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def run():
    today = date.today()
    d = lambda n: today - timedelta(days=n)  # noqa: E731

    # --- the rule itself -------------------------------------------------------
    assert audit.behind_legislature(d(20), d(2), today) == 18, "acting now, our newest is 18 days older"
    assert audit.behind_legislature(d(3), d(2), today) is None, "a day behind is normal lag"
    assert audit.behind_legislature(d(60), d(30), today) is None, "legislature quiet for 30 days: no flag"
    assert audit.behind_legislature(None, d(1), today) is not None, "we have nothing, they're acting"
    assert audit.behind_legislature(d(5), None, today) is None, "no OpenStates data: no flag"
    assert audit.behind_legislature(d(40), today + timedelta(days=5), today) is None, "future-dated action ignored"

    # --- a whole run with fakes -----------------------------------------------
    class FakeCS:
        latest = {"il": d(1), "ny": d(2), "ia": d(80), "oh": d(1)}

        @staticmethod
        def ocd_id_for(code):
            return code

        @classmethod
        def fetch_latest_action(cls, ocd, key, max_retries=3):
            return cls.latest.get(ocd)

    tmp = Path(tempfile.mkdtemp())
    audit.TRACKING_FILE = tmp / "audit_tracking.json"
    audit.WEEKLY_BILL_COUNTS_FILE = tmp / "weekly_bill_counts.json"
    audit.fetch_raw = lambda org, repo, path: None
    audit.load_scraper_status = lambda: {"il": "active", "ny": "paused", "ia": "paused", "oh": "active"}
    audit.load_session_info = lambda: {}
    audit.time.sleep = lambda s: None
    audit.our_newest_actions = lambda: {"il": d(15), "ny": d(11), "ia": d(85), "oh": d(1)}
    audit._check_sessions = lambda: FakeCS
    os.environ["OPENSTATES_API_KEY"] = "test"
    sys.argv = ["weekly-scraper-audit.py"]

    buf = io.StringIO()
    with redirect_stdout(buf):
        audit.main()
    report = buf.getvalue()
    tracking = json.loads(audit.TRACKING_FILE.read_text())
    assert set(tracking) == {"behind:il", "behind:ny"}, tracking
    assert "**il** (active)" in report and "**ny** (paused)" in report, report
    assert "**ia**" not in report and "**oh**" not in report, "quiet or up-to-date states aren't flagged"

    # Without a key the check is skipped, says so, and keeps its open flags.
    del os.environ["OPENSTATES_API_KEY"]
    buf = io.StringIO()
    with redirect_stdout(buf):
        audit.main()
    assert "Skipped: no OPENSTATES_API_KEY" in buf.getvalue()
    assert set(json.loads(audit.TRACKING_FILE.read_text())) == {"behind:il", "behind:ny"}, \
        "a skipped run must not mark the flags resolved"
    print("ok - weekly-scraper-audit behind-the-legislature check: all assertions passed")


if __name__ == "__main__":
    run()
