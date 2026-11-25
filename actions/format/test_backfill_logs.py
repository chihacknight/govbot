#!/usr/bin/env python3
"""Offline test for backfill_logs.py: replays a tiny raw scraper repo built here.

    cd actions/format && python3 test_backfill_logs.py
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
NIGHTS = ["2026-01-05T10:00:00+00:00", "2026-01-06T10:00:00+00:00", "2026-01-07T10:00:00+00:00",
          "2026-01-08T10:00:00+00:00"]
UPPER = '~{"classification": "upper"}'


def bill(identifier, actions, session="2026"):
    return {"identifier": identifier, "legislative_session": session,
            "sources": [{"url": f"https://example.gov/{identifier}", "note": ""}],
            "actions": [{"description": d, "date": t, "classification": [], "organization_id": UPPER} for d, t in actions]}


def vote(identifier, yes, no, rc="RC 1", start="2026-01-04T15:00:00+00:00"):
    return {"identifier": rc, "motion_text": "Third reading", "motion_classification": [], "start_date": start,
            "result": "pass" if yes > no else "fail", "organization": UPPER, "legislative_session": "2026",
            "bill_identifier": identifier, "votes": [],
            "counts": [{"option": "yes", "value": yes}, {"option": "no", "value": no}], "sources": [], "extras": {}}


def when(stamp):
    """first_seen as an instant: git writes UTC as "Z" or "+00:00" depending on version."""
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def lines(path):
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


class BackfillTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.raw, self.repo, self.reports = root / "raw", root / "repo", root / "reports"
        self.bills = self.repo / "country:us" / "state:zz" / "sessions" / "2026" / "bills"
        for b in ("SB1", "SB2"):
            (self.bills / b).mkdir(parents=True)
            (self.bills / b / "metadata.json").write_text("{}")
        self.raw.mkdir()
        self.git("init", "-q")
        intro = ("Introduced", "2026-01-02")
        nights = [
            [bill("SB 1", [intro]), vote("SB 1", 20, 10)],
            # New action listed first (scrapers list in any order), a correction of
            # the vote, a late vote from before, and a bill with no folder.
            [bill("SB 1", [("Passed", "2026-01-04"), ("Referred", "2026-01-03"), intro]),
             vote("SB 1", 21, 9), vote("SB 2", 5, 30, rc="RC 0", start="2025-12-01T15:00:00+00:00"),
             bill("SB 9", [intro])],
        ]
        nights.append(nights[1])  # night 3: the same data, new filenames
        # Night 4: the scraper rewords an action it already published.
        nights.append([bill("SB 1", [("Passed", "2026-01-04"), ("Referred", "2026-01-03"), ("Introduced in Senate", "2026-01-02")]),
                       vote("SB 1", 21, 9), vote("SB 2", 5, 30, rc="RC 0", start="2025-12-01T15:00:00+00:00")])
        for night, records in zip(NIGHTS, nights):
            self.commit_scrape(night, records)
        # A commit that doesn't touch _data/ (template update): ignored.
        (self.raw / "README.md").write_text("x")
        self.git("add", "-A")
        self.git("commit", "-qm", "template", env_date=NIGHTS[-1])

    def tearDown(self):
        self._tmp.cleanup()

    def git(self, *args, env_date=None):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
        if env_date:
            env.update(GIT_AUTHOR_DATE=env_date, GIT_COMMITTER_DATE=env_date)
        subprocess.run(["git", "-C", str(self.raw), *args], check=True, env=env)

    def commit_scrape(self, night, records):
        data = self.raw / "_data" / "zz"
        if data.exists():
            for f in data.iterdir():
                f.unlink()
        data.mkdir(parents=True, exist_ok=True)
        for r in records:
            kind = "vote_event" if "motion_text" in r else "bill"
            (data / f"{kind}_{uuid.uuid4()}.json").write_text(json.dumps(r))
        (data / "jurisdiction_x.json").write_text("{}")
        self.git("add", "-A")
        self.git("commit", "-qm", f"scrape {night}", env_date=night)

    def run_backfill(self, *extra):
        return subprocess.run([sys.executable, str(HERE / "backfill_logs.py"), str(self.repo), str(self.raw),
                               "--report-dir", str(self.reports), *extra], capture_output=True, text=True, cwd=HERE)

    def test_replay(self):
        done = self.run_backfill()
        self.assertEqual(done.returncode, 0, done.stderr)
        acts = lines(self.bills / "SB1" / "action_logs.jsonl")
        self.assertEqual([(a["action"]["description"], when(a["first_seen"])) for a in acts],
                         [("Introduced", when(NIGHTS[0])), ("Referred", when(NIGHTS[1])), ("Passed", when(NIGHTS[1])),
                          ("Introduced in Senate", when(NIGHTS[3]))])
        self.assertEqual(acts[3]["id"], acts[0]["id"])  # a rewording, not a new action
        votes = lines(self.bills / "SB1" / "vote_event_logs.jsonl")
        self.assertEqual([(v["vote_event"]["counts"][0]["value"], when(v["first_seen"])) for v in votes],
                         [(20, when(NIGHTS[0])), (21, when(NIGHTS[1]))])
        self.assertEqual(votes[0]["id"], votes[1]["id"])  # a correction keeps the id
        [late] = lines(self.bills / "SB2" / "vote_event_logs.jsonl")
        self.assertEqual(when(late["first_seen"]), when(NIGHTS[1]))
        self.assertFalse((self.bills / "SB9").exists())  # never created

        report = json.loads((self.reports / "log_backfill-zz.json").read_text())
        self.assertEqual(report["scrapes_replayed"], 4)
        self.assertEqual(report["action_corrections"], 1)
        self.assertEqual(report["action_rewordings_unpaired"], 0)
        self.assertEqual(report["vote_corrections"], 1)
        self.assertEqual(report["bills_missing_list"], [{"bill": "2026/SB9", "raw_files": 1}])

        # Re-run: resumes after the last scrape, changes nothing.
        before = {p: p.read_bytes() for p in self.bills.rglob("*.jsonl")}
        again = self.run_backfill()
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual({p: p.read_bytes() for p in self.bills.rglob("*.jsonl")}, before)

    def test_refuses_repo_with_logs_and_no_cursor(self):
        (self.bills / "SB1" / "action_logs.jsonl").write_text("")
        done = self.run_backfill()
        self.assertEqual(done.returncode, 2)
        self.assertIn("already has .jsonl logs", done.stderr)

    def test_dry_run_writes_nothing(self):
        done = self.run_backfill("--dry-run")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(list(self.bills.rglob("*.jsonl")), [])
        self.assertFalse(self.reports.exists())


if __name__ == "__main__":
    unittest.main()
