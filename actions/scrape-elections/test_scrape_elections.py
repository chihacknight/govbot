#!/usr/bin/env python3
"""Offline snapshot tests for the elections scraper.

Pure parsers are exercised against the raw fixtures under __snapshots__/raw/,
and the whole offline build is diffed against __snapshots__/expected_elections.json.
No network. Run: python3 actions/scrape-elections/test_scrape_elections.py
Regenerate the snapshot after an intentional change: ./render-snapshots.sh
"""

import json
import unittest
from pathlib import Path

import main

HERE = Path(__file__).parent
RAW = HERE / "__snapshots__" / "raw"
EXPECTED = HERE / "__snapshots__" / "expected_elections.json"
RACE_REQUIRED = {"id", "jurisdiction", "office", "office_group", "is_citywide",
                 "partisan", "status", "candidates", "source"}


class RaceMatching(unittest.TestCase):
    def test_citywide(self):
        self.assertEqual(main.race_id_for("Mayor", None), "chicago-mayor")
        self.assertEqual(main.race_id_for("City Clerk", ""), "chicago-city-clerk")
        self.assertEqual(main.race_id_for("City Treasurer", ""), "chicago-city-treasurer")

    def test_alderperson_ward(self):
        self.assertEqual(main.race_id_for("Alderperson", "Ward 1"),
                         "chicago-alderperson-ward-01")
        self.assertEqual(main.race_id_for("Alderman", "Ward 50"),
                         "chicago-alderperson-ward-50")

    def test_cps(self):
        self.assertEqual(main.race_id_for("President of the Board of Education", ""),
                         "cps-board-president")
        self.assertEqual(main.race_id_for("Member of the Board of Education", "Subdistrict 1A"),
                         "cps-board-member-1a")
        self.assertEqual(main.race_id_for("Member of the Board of Education", "Subdistrict 10B"),
                         "cps-board-member-10b")

    def test_police_district_council(self):
        self.assertEqual(main.race_id_for("Police District Councilmember", "Police District 14"),
                         "chicago-police-district-council-014")

    def test_unplaceable_returns_none(self):
        self.assertIsNone(main.race_id_for("State Representative", "District 5"))
        self.assertIsNone(main.race_id_for("Alderperson", "Ward 99"))  # out of range


class StatusNormalization(unittest.TestCase):
    def test_maps(self):
        self.assertEqual(main.normalize_status("On Ballot"), "on_ballot")
        self.assertEqual(main.normalize_status("OBJECTED"), "objected")
        self.assertEqual(main.normalize_status("Withdrawn"), "withdrawn")
        self.assertEqual(main.normalize_status("Removed from ballot"), "removed")
        self.assertEqual(main.normalize_status("Filed"), "filed")
        self.assertEqual(main.normalize_status("something odd"), "unknown")
        self.assertIsNone(main.normalize_status(""))


class ISBEParser(unittest.TestCase):
    def setUp(self):
        self.cands = main.parse_isbe_candidates((RAW / "isbe_who_is_running.txt").read_text())

    def test_row_count(self):
        # 4 CPS/valid rows + 1 unplaceable state race = 5 parsed candidates.
        self.assertEqual(len(self.cands), 5)

    def test_president_resolves(self):
        pres = [c for c in self.cands if c["_race_id"] == "cps-board-president"]
        self.assertEqual(len(pres), 1)
        self.assertEqual(pres[0]["name"], "Alex Q. Example")
        self.assertEqual(pres[0]["petition_status"], "on_ballot")
        self.assertEqual(pres[0]["filing_date"], "2026-03-20")

    def test_subdistrict_resolves(self):
        subs = {c["_race_id"] for c in self.cands}
        self.assertIn("cps-board-member-1a", subs)
        self.assertIn("cps-board-member-10b", subs)

    def test_objected_status(self):
        obj = [c for c in self.cands if c["name"] == "Pat Q. Placeholder"]
        self.assertEqual(obj[0]["petition_status"], "objected")

    def test_state_race_is_unplaceable(self):
        st = [c for c in self.cands if c["name"] == "Not A Chicago Race"]
        self.assertIsNone(st[0]["_race_id"])

    def test_bad_input_empty(self):
        self.assertEqual(main.parse_isbe_candidates("no header here\njust text"), [])


class ChicagoBOEParser(unittest.TestCase):
    def setUp(self):
        self.cands = main.parse_chicago_boe((RAW / "chicago_boe_candidates.html").read_text())

    def test_mayor_with_website(self):
        m = [c for c in self.cands if c["_race_id"] == "chicago-mayor"]
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0]["name"], "Casey R. Sample")
        self.assertEqual(m[0]["website"], "https://example.org/casey")
        self.assertEqual(m[0]["petition_status"], "on_ballot")

    def test_wards(self):
        ids = {c["_race_id"] for c in self.cands}
        self.assertIn("chicago-alderperson-ward-01", ids)
        self.assertIn("chicago-alderperson-ward-50", ids)

    def test_pdc(self):
        self.assertIn("chicago-police-district-council-014",
                      {c["_race_id"] for c in self.cands})

    def test_unplaceable_present_but_unresolved(self):
        u = [c for c in self.cands if c["name"] == "Unplaceable Person"]
        self.assertEqual(len(u), 1)
        self.assertIsNone(u[0]["_race_id"])

    def test_bad_html_empty(self):
        self.assertEqual(main.parse_chicago_boe("<p>no table</p>"), [])


class Assemble(unittest.TestCase):
    def setUp(self):
        self.seed = main.load_seed()
        cands = main.build_from_fixtures(RAW)
        now = main.datetime(2026, 9, 7, tzinfo=main.timezone.utc)
        self.doc, self.placed = main.assemble(cands, self.seed, "test", now)
        self.by_id = {r["id"]: r for r in self.doc["races"]}

    def test_structure_preserved(self):
        # Seed race count is preserved regardless of candidate matches.
        self.assertEqual(len(self.doc["races"]), len(self.seed["races"]))

    def test_candidates_placed(self):
        self.assertGreater(self.placed, 0)
        self.assertEqual([c["name"] for c in self.by_id["chicago-mayor"]["candidates"]],
                         ["Casey R. Sample"])
        self.assertEqual(len(self.by_id["cps-board-member-1a"]["candidates"]), 2)

    def test_populated_race_marked_on_ballot(self):
        self.assertEqual(self.by_id["chicago-mayor"]["status"], "on_ballot")
        # An untouched race keeps its seed status.
        self.assertEqual(self.by_id["chicago-city-treasurer"]["status"], "upcoming")

    def test_every_race_has_required_fields(self):
        for r in self.doc["races"]:
            self.assertTrue(RACE_REQUIRED.issubset(r), f"missing fields in {r['id']}")

    def test_no_internal_race_id_leaks(self):
        for r in self.doc["races"]:
            for c in r["candidates"]:
                self.assertNotIn("_race_id", c)


class Feeds(unittest.TestCase):
    def setUp(self):
        seed = main.load_seed()
        cands = main.build_from_fixtures(RAW)
        now = main.datetime(2026, 9, 7, tzinfo=main.timezone.utc)
        self.doc, _ = main.assemble(cands, seed, "test", now)

    def test_whole_feed_valid_xml(self):
        import xml.etree.ElementTree as ET
        root = ET.fromstring(main.to_rss(self.doc))
        items = root.findall(".//item")
        self.assertEqual(len(items), len(self.doc["races"]))

    def test_granular_feeds_present(self):
        feeds = main.all_feeds(self.doc)
        self.assertIn("group-citywide.xml", feeds)
        self.assertIn("race-chicago-mayor.xml", feeds)
        import xml.etree.ElementTree as ET
        for xml in feeds.values():
            ET.fromstring(xml)  # each must be well-formed


class Springfield(unittest.TestCase):
    def setUp(self):
        self.leg = json.loads((RAW / "il_legislation.json").read_text())
        self.hear = json.loads((RAW / "il_hearings.json").read_text())
        self.sf = main.build_springfield(self.leg, self.hear)

    def test_only_il_matching_topics(self):
        ids = [b["id"] for b in self.sf]
        self.assertEqual(set(ids), {"HB1234", "SB0056", "HB0777"})
        self.assertNotIn("HB0009", ids)   # health care — wrong topic
        self.assertNotIn("AB0100", ids)   # elections, but California

    def test_sorted_newest_first(self):
        dates = [b["latest_action"] for b in self.sf]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_matched_tags_only(self):
        hb = next(b for b in self.sf if b["id"] == "HB1234")
        self.assertEqual(hb["tags"], ["education", "elections & voting"])  # sorted, no "government operations"

    def test_hearing_crossref(self):
        hb = next(b for b in self.sf if b["id"] == "HB1234")
        self.assertIsNotNone(hb["hearing"])
        self.assertIn("Elections", hb["hearing"]["committee"])
        sb = next(b for b in self.sf if b["id"] == "SB0056")
        self.assertIsNone(sb["hearing"])

    def test_missing_inputs_empty(self):
        self.assertEqual(main.build_springfield(None, None), [])
        self.assertEqual(main.build_springfield({"bills": []}, None), [])

    def test_feed_is_valid_xml(self):
        import xml.etree.ElementTree as ET
        doc = {"generated_at": "2026-09-07T00:00:00Z", "springfield": self.sf}
        feeds = main.springfield_feed(doc)
        self.assertIn("springfield.xml", feeds)
        items = ET.fromstring(feeds["springfield.xml"]).findall(".//item")
        self.assertEqual(len(items), 3)


class Money(unittest.TestCase):
    def setUp(self):
        self.dir = RAW / "sbe"
        self.now = main.datetime(2026, 9, 7, tzinfo=main.timezone.utc)
        keys = {main._name_key(n) for n in
                ["Casey R. Sample", "Morgan Placeholder", "Sam T. Example", "Lee Q. Testcase"]}
        self.idx = main.build_money_index(str(self.dir), keys, self.now)

    def test_name_key(self):
        self.assertEqual(main._name_key("Casey R. Sample"), "caseysample")
        self.assertEqual(main._name_key("Sample, Casey R."), "caseysample")

    def test_aggregates_multiple_committees(self):
        m = self.idx[main._name_key("Casey R. Sample")]
        self.assertEqual(m["committees"], 2)
        self.assertEqual(m["funds_raised"], 90000.0)
        self.assertEqual(m["funds_spent"], 54000.0)
        self.assertEqual(m["cash_on_hand"], 41000.0)
        self.assertEqual(m["committee_name"], "Friends of Casey Sample")  # most cash

    def test_latest_d2_by_max_id(self):
        # committee 900 has filings id 10 and 20; the id-20 receipts (80000) win.
        m = self.idx[main._name_key("Casey R. Sample")]
        self.assertNotIn(50000.0, [m["funds_raised"]])  # not the older filing

    def test_ambiguous_name_skipped(self):
        # "Morgan Placeholder" appears twice in Candidates.txt -> no money.
        self.assertNotIn(main._name_key("Morgan Placeholder"), self.idx)

    def test_no_committee_skipped(self):
        self.assertNotIn(main._name_key("Lee Q. Testcase"), self.idx)

    def test_missing_dir_empty(self):
        self.assertEqual(main.build_money_index("/no/such/dir", {"caseysample"}, self.now), {})

    def test_enrich_money_attaches(self):
        doc = {"races": [{"candidates": [{"name": "Casey R. Sample"}, {"name": "Nobody Here"}]}]}
        n = main.enrich_money(doc, str(self.dir), self.now)
        self.assertEqual(n, 1)
        self.assertEqual(doc["races"][0]["candidates"][0]["money"]["committees"], 2)
        self.assertNotIn("money", doc["races"][0]["candidates"][1])


class Results(unittest.TestCase):
    def setUp(self):
        self.now = main.datetime(2026, 11, 3, 20, 0, tzinfo=main.timezone.utc)
        self.rows = main.parse_results_rows((RAW / "boe_results.csv").read_text())

    def test_parses_and_resolves(self):
        ids = {str(r["_race_id"]) for r in self.rows}
        self.assertIn("chicago-mayor", ids)
        self.assertIn("chicago-alderperson-ward-01", ids)
        # A non-Chicago contest doesn't resolve to a race.
        self.assertIn("None", ids)

    def test_attach_percentages_and_winner(self):
        doc = {"races": [{"id": "chicago-mayor", "candidates": [{"name": "Casey R. Sample"}]}]}
        n = main.attach_results(doc, self.rows, self.now, "https://chicagoelections.gov/results")
        self.assertEqual(n, 1)
        res = doc["races"][0]["results"]
        self.assertTrue(res["reported"] and res["complete"])
        self.assertEqual(res["total_votes"], 218570)
        top = res["candidates"][0]
        self.assertEqual(top["name"], "Casey R. Sample")
        self.assertEqual(top["pct"], 55.1)
        self.assertTrue(top["winner"])
        self.assertFalse(res["candidates"][1]["winner"])

    def test_counts_all_reported_candidates(self):
        # Ward 1 has two reported candidates even though only one is in our roster;
        # results are authoritative, so both are counted (pct not distorted).
        doc = {"races": [{"id": "chicago-alderperson-ward-01", "candidates": [{"name": "Sam T. Example"}]}]}
        main.attach_results(doc, self.rows, self.now)
        res = doc["races"][0]["results"]
        self.assertEqual(len(res["candidates"]), 2)
        self.assertEqual(res["total_votes"], 8500)

    def test_no_results_when_unmatched(self):
        doc = {"races": [{"id": "cps-board-president", "candidates": []}]}
        self.assertEqual(main.attach_results(doc, self.rows, self.now), 0)
        self.assertIsNone(doc["races"][0].get("results"))

    def test_bad_input_empty(self):
        self.assertEqual(main.parse_results_rows("no header\njust text"), [])

    def test_enrich_missing_file_noop(self):
        doc = {"races": []}
        self.assertEqual(main.enrich_results(doc, "/no/such.csv", self.now), 0)


class Snapshot(unittest.TestCase):
    def test_matches_expected(self):
        if not EXPECTED.exists():
            self.skipTest("run ./render-snapshots.sh to create the expected snapshot")
        seed = main.load_seed()
        cands = main.build_from_fixtures(RAW)
        sf = main.build_springfield(
            main.load_json(str(RAW / "il_legislation.json")),
            main.load_json(str(RAW / "il_hearings.json")))
        now = main.datetime(2026, 9, 7, tzinfo=main.timezone.utc)
        doc, _ = main.assemble(cands, seed, "fixtures (offline snapshot)", now, springfield=sf)
        expected = json.loads(EXPECTED.read_text())
        self.assertEqual(doc, expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
