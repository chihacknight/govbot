#!/usr/bin/env python3
"""Offline tests for the re-audit helpers.  python3 test_reaudit.py"""
import unittest
from collections import Counter
from datetime import date
from pathlib import Path

import lists as Li
import patterns as P
import reaudit as R


class ReauditTest(unittest.TestCase):
    def test_run_class(self):
        self.assertEqual(R.run_class(date(2026, 1, 6), Counter()), "no_record")
        self.assertEqual(R.run_class(date(2026, 2, 1), Counter()), "off")
        self.assertEqual(R.run_class(date(2026, 2, 1), Counter(failure=1, cancelled=1)), "failed")
        self.assertEqual(R.run_class(date(2026, 2, 1), Counter(failure=1, success=1)), "ok")

    def test_kind(self):
        self.assertEqual(R.kind("failed", 5, "in_session"), "new")  # a failed run's auto-save can bring data
        self.assertEqual(R.kind("ok", 0, "special"), "quiet_in")
        self.assertEqual(R.kind("ok", 0, "no_regular_session"), "quiet_out")
        self.assertEqual(R.kind("ok", 0, "unknown"), "quiet_unknown")
        self.assertEqual(R.kind("ok", 0, "in_session", "gu"), "quiet_year_round")
        self.assertEqual(R.kind("no_record", 0, "out_of_session"), "no_record_out")
        self.assertEqual(R.kind("off", 0, "in_session"), "off")

    def test_label_is_majority(self):
        self.assertEqual(R.label(Counter(off=10, quiet_in=4)), "scraper off")
        self.assertEqual(R.label(Counter(no_record_in=3, no_record_out=3, quiet_in=4)), "before run history")
        self.assertEqual(R.label(Counter(quiet_in=4, quiet_out=4)), "ran, nothing new, in session")


class TimingTest(unittest.TestCase):
    def test_finished_runs_only(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            runs, jobs = Path(d) / "runs", Path(d) / "jobs"
            runs.mkdir(), jobs.mkdir()
            rows = [
                # starts 02-01 evening, finishes 02-02 green: 02-01 running, 02-02 ok
                {"id": 1, "status": "completed", "conclusion": "success", "created_at": "2026-02-01T20:00:00Z",
                 "updated_at": "2026-02-02T03:00:00Z"},
                # runs 03-01 to 03-04 (jobs say so; updated_at was moved to November): 03-01, 03-02
                # running (under 24h at the end of 03-01; 03-02 ends at 32h -> failed), 03-04 failed
                {"id": 2, "status": "completed", "conclusion": "cancelled", "created_at": "2026-03-01T16:00:00Z",
                 "updated_at": "2026-11-20T00:00:00Z"},
                # queued forever from 09-13
                {"id": 3, "status": "queued", "conclusion": None, "created_at": "2026-09-13T08:00:00Z",
                 "updated_at": "2026-09-13T08:00:00Z"},
            ]
            (runs / "fl.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
            (jobs / "fl-2.json").write_text(json.dumps([{"completed_at": "2026-03-04T10:00:00Z"}]))
            t = R.run_days_timed(runs, jobs, date(2026, 9, 15))["fl"]
        self.assertEqual(t[date(2026, 2, 1)], "running")
        self.assertEqual(t[date(2026, 2, 2)], "ok")
        self.assertEqual(t[date(2026, 3, 1)], "running")
        self.assertEqual(t[date(2026, 3, 2)], "failed")
        self.assertEqual(t[date(2026, 3, 4)], "failed")
        self.assertEqual(t[date(2026, 9, 13)], "running")
        self.assertEqual(t[date(2026, 9, 14)], "failed")
        self.assertEqual(R.kind("running", 0, "in_session"), "running")


class PatternsTest(unittest.TestCase):
    def test_pct(self):
        self.assertEqual(P.pct(Counter({0: 5, 1: 4, 10: 1}), 0.5), 0)
        self.assertEqual(P.pct(Counter({0: 5, 1: 4, 10: 1}), 0.9), 1)
        self.assertEqual(P.pct(Counter({0: 5, 1: 4, 10: 1}), 1.0), 10)
        self.assertIsNone(P.pct(Counter(), 0.5))

    def test_blocks(self):
        rows = [("2026-01-01", "out_of_session"), ("2026-01-02", "in_session"), ("2026-01-03", "special"),
                ("2026-01-04", "out_of_session"), ("2026-01-05", "prefiling")]
        self.assertEqual(P.blocks(rows), [(date(2026, 1, 2), date(2026, 1, 3)), (date(2026, 1, 5), date(2026, 1, 5))])


class ListsTest(unittest.TestCase):
    def test_item_stays_one_line_across_a_short_gap(self):
        it = Li.Items()
        for k in (1, 2, 3, 5, 6):  # a 1-day gap (day 4): still the same item
            it.mark("needs_you", "quiet_14", "wi", date(2026, 2, k))
        for k in (20, 21):         # a long gap: a new item
            it.mark("needs_you", "quiet_14", "wi", date(2026, 2, k))
        got = sorted((x[3], x[4]) for x in it.items())
        self.assertEqual(got, [(date(2026, 2, 1), date(2026, 2, 6)), (date(2026, 2, 20), date(2026, 2, 21))])

    def test_group_is_one_item_whatever_the_gaps(self):
        it = Li.Items()
        for k in (1, 2, 20, 21):  # revised ready_off: one item per out-of-session period
            it.mark("ready_off", "ready_off", "ut", date(2026, 3, k), group="2026-03-07")
        self.assertEqual(len(it.items()), 1)

    def test_failed_reopen_window(self):
        it = Li.Items({"failed_3": 7})
        for k in (1, 2, 3, 9, 10):  # back within 7 days: the same item
            it.mark("needs_you", "failed_3", "fl", date(2026, 2, k))
        self.assertEqual(len(it.items()), 1)

    def test_fleet_broken(self):
        d = date(2026, 6, 26)
        xs = [("needs_you", "empty_scrape", st, d, d, 1, "x") for st in ("ct", "hi", "la")] + \
             [("needs_you", "empty_scrape", "nm", date(2026, 6, 27), date(2026, 6, 27), 1, "x")]
        out = Li.fleet_broken(xs)
        self.assertEqual(sorted(x[2] for x in out), ["fleet: ct hi la", "nm"])

    def test_starts_include_prefiling(self):
        st = Li.starts_from(Path(__file__).parent / "__snapshots__" / "sessions_fixture.csv")
        tx = sorted(st["tx"])
        self.assertIn((date(2026, 11, 23), "prefiling for 90th Legislature", "sources/legiscan/2027/2026-11-23.pdf"), tx)
        self.assertIn(date(2027, 1, 12), [x[0] for x in tx])

    def test_accepted_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "accepted.csv"
            f.write_text("state,kind,reason,date\nIL,field_loss,abstracts gone,2026-12-01\n")
            self.assertEqual(Li.load_accepted(f), {("il", "field_loss"): date(2026, 12, 1)})
            f.write_text("state,kind,reason,date\n")
            self.assertEqual(Li.load_accepted(f), {})

    def test_sessions_from_two_sources_are_one(self):
        import status as St
        cal = St.load(Path(__file__).parent / "__snapshots__" / "sessions_fixture.csv")
        sc = [x for x in Li.session_spans(cal, "sc") if x[2] == "special"]
        self.assertEqual(sc, [(date(2026, 5, 15), date(2026, 5, 19), "special")])  # LegiScan 05-15 + MultiState 05-17
        wi = [x for x in Li.session_spans(cal, "wi") if x[2] == "regular" and x[0].year == 2026]
        self.assertEqual(wi, [(date(2026, 1, 13), date(2026, 3, 19), "regular")])  # 03-17 and 03-19 merged

    def test_openstates_listing(self):
        os_starts = {"ak": [date(2025, 1, 21)], "tn": [date(2026, 5, 5)]}
        self.assertFalse(Li.os_lists(os_starts, "ak", date(2026, 5, 21), "special"))  # AK's specials
        self.assertTrue(Li.os_lists(os_starts, "ak", date(2026, 1, 20), "regular"))   # regular: always listed
        self.assertTrue(Li.os_lists(os_starts, "tn", date(2026, 5, 5), "special"))    # TN 114S2
        self.assertTrue(Li.os_lists({}, "md", date(2026, 8, 3), "special"))           # no data: assume listed

    def test_limits(self):
        self.assertEqual((Li.limit("wi"), Li.limit("gu"), Li.limit("vi"), Li.limit("mp")), (14, 45, 45, 21))


if __name__ == "__main__":
    unittest.main()
