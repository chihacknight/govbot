#!/usr/bin/env python3
"""Offline tests for build_people_roster.py (party + seat enrichment).

Writes a tiny fake openstates/people tree to a temp dir and checks the roster
shape. No network. Run: python3 scripts/test_build_people_roster.py
"""
import tempfile
import unittest
from pathlib import Path

import build_people_roster as r


def _write(dirpath, state, fname, text):
    leg = Path(dirpath) / "data" / state / "legislature"
    leg.mkdir(parents=True, exist_ok=True)
    (leg / fname).write_text(text, encoding="utf-8")


class AreaLabel(unittest.TestCase):
    def test_numeric_district(self):
        self.assertEqual(r._area({"type": "upper", "district": "5"}), "Senate District 5")
        self.assertEqual(r._area({"type": "lower", "district": "19"}), "House District 19")

    def test_alnum_district(self):
        self.assertEqual(r._area({"type": "lower", "district": "4B"}), "House District 4B")

    def test_named_district_kept_verbatim(self):
        self.assertEqual(r._area({"type": "lower", "district": "3rd Middlesex"}),
                         "House · 3rd Middlesex")

    def test_no_chamber_word_for_legislature(self):
        self.assertEqual(r._area({"type": "legislature", "district": "7"}), "District 7")

    def test_missing_district(self):
        self.assertEqual(r._area({"type": "upper", "district": ""}), "Senate")

    def test_none(self):
        self.assertEqual(r._area(None), "")


class Current(unittest.TestCase):
    def test_prefers_active_role(self):
        rows = [{"district": "1", "start_date": "2019", "end_date": "2021"},
                {"district": "9", "start_date": "2021"}]
        self.assertEqual(r._current(rows)["district"], "9")

    def test_latest_when_all_ended(self):
        rows = [{"district": "1", "start_date": "2015", "end_date": "2017"},
                {"district": "3", "start_date": "2019", "end_date": "2021"}]
        self.assertEqual(r._current(rows)["district"], "3")


class Roster(unittest.TestCase):
    def test_emits_party_and_area(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "ak", "hall.yml",
                   "name: Carolyn Hall\n"
                   "given_name: Carolyn\n"
                   "family_name: Hall\n"
                   "party:\n  - name: Democratic\n"
                   "roles:\n  - type: lower\n    district: '19'\n")
            # A prior party role that ended must not win over the active one.
            _write(d, "ak", "smith.yml",
                   "name: Bob Smith\n"
                   "given_name: Bob\n"
                   "family_name: Smith\n"
                   "party:\n"
                   "  - name: Republican\n    end_date: '2020-01-01'\n"
                   "  - name: Independent\n"
                   "roles:\n"
                   "  - type: upper\n    district: '3'\n    end_date: '2019'\n"
                   "  - type: upper\n    district: '7'\n")
            roster, count = r.build_roster(d)
        self.assertEqual(count, 2)
        self.assertEqual(roster["ak"]["hall"], [["Carolyn", "Carolyn Hall",
                                                 "Democratic", "House District 19"]])
        self.assertEqual(roster["ak"]["smith"], [["Bob", "Bob Smith",
                                                  "Independent", "Senate District 7"]])

    def test_missing_party_and_role_degrade_to_empty(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "wy", "doe.yml",
                   "name: Jane Doe\ngiven_name: Jane\nfamily_name: Doe\n")
            roster, _ = r.build_roster(d)
        self.assertEqual(roster["wy"]["doe"], [["Jane", "Jane Doe", "", ""]])

    def test_skips_us_and_nameless(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "us", "rep.yml",
                   "name: Fed Person\ngiven_name: Fed\nfamily_name: Person\n")
            _write(d, "ak", "bad.yml", "given_name: NoFamily\n")
            roster, count = r.build_roster(d)
        self.assertNotIn("us", roster)
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
