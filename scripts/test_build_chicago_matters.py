#!/usr/bin/env python3
"""Offline tests for build_chicago_matters.py (a real eLMS /matter page, no network).

    python3 scripts/test_build_chicago_matters.py
"""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_chicago_matters as m  # noqa: E402
from build_dashboard_data import compile_keyword_tags  # noqa: E402

PAGE = (HERE / "__snapshots__" / "chicago" / "matters_page.json").read_text()
TAGS = compile_keyword_tags(HERE / "dashboard_tags.json")
TODAY = "2026-11-24"


class ChicagoMatters(unittest.TestCase):
    def setUp(self):
        self.bills, self.rows = m.parse_matters(PAGE, TAGS, TODAY)
        self.by_id = {b["id"]: b for b in self.bills}

    def test_only_legislation_kept(self):
        rows = json.loads(PAGE)["data"]
        self.assertEqual(self.rows, len(rows))
        kept_types = {r["type"] for r in rows if r["recordNumber"] in self.by_id}
        self.assertLessEqual(kept_types, m.KEEP_TYPES)
        self.assertTrue(any(r["type"] == "Communication" for r in rows))   # dropped
        self.assertTrue(all(b["state"] == "chi" and b["session"] == "2023-2027" for b in self.bills))

    def test_record_shape_matches_state_bills(self):
        b = self.by_id["O2026-0029651"]
        self.assertEqual(set(b), {"state", "session", "id", "title", "chamber", "latest_action",
                                  "latest_action_desc", "sponsors", "url", "tags"})
        self.assertEqual(b["chamber"], "council")
        self.assertTrue(b["url"].startswith("https://chicityclerkelms.chicago.gov/Matter/?matterId="))

    def test_sponsor_name_flipped_and_offices_dropped(self):
        self.assertEqual(self.by_id["O2026-0029651"]["sponsors"], ["Michael D. Rodriguez"])
        self.assertIsNone(m.sponsor_name({"filingSponsor": "Dept./Agency"}))

    def test_latest_action_never_in_the_future(self):
        self.assertTrue(all((b["latest_action"] or "") <= TODAY for b in self.bills))
        # Filed for the Dec 8 meeting: dated the day it was filed, not Dec 8.
        self.assertEqual(self.by_id["O2026-0029651"]["latest_action_desc"], "Submitted to Clerk: Accepted")

    def test_final_action_uses_its_outcome(self):
        final = [b for b in self.bills if b["latest_action_desc"] in ("Passed", "Adopted", "Approved", "Placed on File")]
        self.assertTrue(final)
        self.assertEqual(m.latest_action({"status": "90-Final", "subStatus": "Passed",
                                          "introductionDate": "2026-05-21T15:00:00+00:00",
                                          "finalActionDate": "2026-06-18T15:00:00+00:00"}, TODAY),
                         ("2026-06-18", "Passed"))

    def test_routine_matters_marked_aux(self):
        rows = {r["recordNumber"]: r for r in json.loads(PAGE)["data"]}
        aux = [b for b in self.bills if b.get("aux")]
        self.assertTrue(aux)
        self.assertTrue(all(rows[b["id"]]["routine"] == "YES" for b in aux))
        self.assertTrue(all(rows[b["id"]]["routine"] == "NO" for b in self.bills if not b.get("aux")))
        self.assertTrue(any(rows[b["id"]]["type"] == "Claim" for b in aux))   # vehicle claims kept, as aux

    def test_merge_is_idempotent(self):
        doc = {"states": [{"code": "il", "name": "Illinois"}], "bills": [{"state": "il", "id": "HB1"}]}
        once = m.merge(json.loads(json.dumps(doc)), self.bills)
        twice = m.merge(json.loads(json.dumps(once)), self.bills)
        self.assertEqual(once, twice)
        self.assertEqual([s["code"] for s in twice["states"]], ["il", "chi"])
        self.assertEqual(len(twice["bills"]), 1 + len(self.bills))

    def test_bad_input_is_empty_not_crash(self):
        self.assertEqual(m.parse_matters("<html>", TAGS, TODAY), ([], 0))
        self.assertEqual(m.parse_matters('{"data": [{"type": "Ordinance"}]}', TAGS, TODAY), ([], 1))


if __name__ == "__main__":
    unittest.main(verbosity=1)
