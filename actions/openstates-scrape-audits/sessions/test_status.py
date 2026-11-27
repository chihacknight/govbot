#!/usr/bin/env python3
"""Offline tests for status.py.  python3 test_status.py"""
import unittest
from datetime import date
from pathlib import Path

import status as S

CAL = S.load(Path(__file__).parent / "__snapshots__" / "sessions_fixture.csv")


def st(state, day):
    return S.status(CAL, state, date.fromisoformat(day))


class StatusTest(unittest.TestCase):
    def test_regular_and_after(self):
        self.assertEqual(st("ak", "2026-03-01").status, "in_session")
        self.assertEqual(st("ak", "2026-05-21").status, "out_of_session")

    def test_manual_special_only_rows_say_nothing_outside_their_dates(self):
        s = st("ak", "2026-03-01")
        self.assertIsNone(s.sources["manual"])
        self.assertFalse(s.disagree)
        self.assertEqual(st("ak", "2026-07-01").status, "special")

    def test_disagree_when_sources_differ(self):
        s = st("nc", "2026-10-01")  # LegiScan ends Aug 31, MultiState Dec 18
        self.assertEqual(s.status, "in_session")
        self.assertTrue(s.disagree)
        self.assertEqual(s.sources, {"legiscan": "out_of_session", "multistate": "in_session",
                                     "congress": None, "manual": None})
        self.assertFalse(st("nc", "2026-05-01").disagree)

    def test_special_inside_out_of_session(self):
        s = st("wi", "2026-04-20")
        self.assertEqual(s.status, "special")
        self.assertTrue(s.disagree)  # LegiScan's newest PDF dropped the special

    def test_biennium_new_year_gap(self):
        s = st("wi", "2026-01-05")
        self.assertEqual(s.sources["multistate"], "in_session")
        self.assertEqual(s.sources["legiscan"], "out_of_session")

    def test_missing_end_gets_default_and_is_estimated(self):
        s = st("md", "2026-08-20")
        self.assertEqual(s.status, "special")
        self.assertTrue(s.estimated)
        self.assertEqual(st("md", "2026-09-02").status, "out_of_session")  # day 31
        self.assertEqual(st("ar", "2026-05-07").status, "in_session")

    def test_no_end_special_borrows_the_other_sources_end(self):
        self.assertEqual(st("sc", "2026-05-19").status, "special")
        self.assertEqual(st("sc", "2026-05-20").status, "out_of_session")  # not the 30-day default
        self.assertEqual(st("sc", "2026-05-15").sources["legiscan"], "special")

    def test_recess_and_lame_duck(self):
        self.assertEqual(st("nj", "2025-08-01").status, "out_of_session")
        self.assertEqual(st("nj", "2025-11-06").status, "veto_or_lame_duck")
        self.assertEqual(st("nj", "2025-11-07").status, "in_session")

    def test_informal_does_not_count(self):
        self.assertEqual(st("ma", "2026-09-01").status, "out_of_session")

    def test_veto_session(self):
        self.assertEqual(st("il", "2026-11-20").status, "veto_or_lame_duck")
        self.assertEqual(st("il", "2026-12-04").status, "out_of_session")

    def test_no_regular_session_and_prefiling(self):
        self.assertEqual(st("tx", "2026-06-01").status, "no_regular_session")
        s = st("tx", "2026-11-25")
        self.assertEqual(s.status, "prefiling")
        self.assertTrue(s.estimated is False)
        self.assertEqual(st("tx", "2026-11-22").status, "no_regular_session")
        self.assertEqual(st("tx", "2027-02-01").status, "in_session")

    def test_open_congress_session(self):
        self.assertEqual(st("usa", "2026-12-20").status, "in_session")

    def test_older_biennium_row_ends_at_the_newer_row(self):
        self.assertEqual(st("ny", "2025-03-01").sources["legiscan"], "in_session")
        self.assertEqual(st("ny", "2025-07-01").sources["legiscan"], "out_of_session")  # interim recess
        self.assertEqual(st("ny", "2026-01-07").sources["legiscan"], "in_session")
        self.assertEqual(st("ny", "2026-09-01").sources["legiscan"], "out_of_session")  # not the 2025 row to 2027

    def test_unknown(self):
        s = st("dc", "2025-06-01")
        self.assertEqual(s.status, "unknown")
        self.assertFalse(s.disagree)
        self.assertEqual(st("tx", "2025-06-01").status, "unknown")


if __name__ == "__main__":
    unittest.main()
