#!/usr/bin/env python3
"""Offline snapshot tests for the hearings scraper.

Pure parsers are exercised against the raw fixtures under __snapshots__/raw/,
and the whole offline build is diffed against __snapshots__/expected_hearings.json.
No network. Run: python3 actions/scrape-hearings/test_scrape_hearings.py
Regenerate the snapshot after an intentional change: ./render-snapshots.sh
"""

import json
import unittest
from pathlib import Path

import main

HERE = Path(__file__).parent
RAW = HERE / "__snapshots__" / "raw"
EXPECTED = HERE / "__snapshots__" / "expected_hearings.json"
REQUIRED = {"id", "jurisdiction", "chamber", "committee", "status", "bills", "source"}


class IllinoisParser(unittest.TestCase):
    def test_active_hearing_with_bills(self):
        hearings = main.parse_il_hearings((RAW / "il_active.json").read_text(), "house")
        self.assertEqual(len(hearings), 1)
        h = hearings[0]
        self.assertEqual(h["id"], "il-house-3201-24010")
        self.assertEqual(h["status"], "scheduled")
        self.assertEqual([b["id"] for b in h["bills"]], ["HB25", "SB1486", "HB3049"])
        self.assertEqual(h["scheduled_iso"], "2026-09-09T14:00:00")
        self.assertIn("BillStatus", h["witness_slip_url"])

    def test_canceled_hearing_flagged(self):
        hearings = main.parse_il_hearings((RAW / "il_house.json").read_text(), "house")
        self.assertEqual(hearings[0]["status"], "canceled")

    def test_bad_json_is_empty_not_crash(self):
        self.assertEqual(main.parse_il_hearings("<html>nope</html>", "house"), [])

    def test_bill_links_use_reliable_bill_status_page(self):
        # Regression: the direct WitnessSlips endpoint returns an error page, so
        # user-facing links must point at the always-200 Bill Status page.
        hearings = main.parse_il_hearings((RAW / "il_active.json").read_text(), "house")
        h = hearings[0]
        self.assertIn("BillStatus", h["witness_slip_url"])
        self.assertNotIn("WitnessSlips", h["witness_slip_url"])
        for b in h["bills"]:
            self.assertIn("BillStatus", b["url"])
            self.assertIn(b["id"].replace("HB", "").replace("SB", ""), b["url"])


class WitnessSlips(unittest.TestCase):
    def test_error_page_returns_none(self):
        self.assertIsNone(main.parse_slip_counts((RAW / "il_slips_error.html").read_text()))

    def test_counts_parsed(self):
        counts = main.parse_slip_counts((RAW / "il_slips_counts.html").read_text())
        self.assertEqual(counts, {"proponents": 1204, "opponents": 318, "no_position": 45})


class WashingtonParser(unittest.TestCase):
    def test_meetings_parsed(self):
        meetings = main.parse_wa_meetings((RAW / "wa_meetings.xml").read_text())
        self.assertEqual(len(meetings), 8)
        self.assertTrue(all(m["timezone"] == "America/Los_Angeles" for m in meetings))
        self.assertTrue(all(m["id"].startswith("wa-") for m in meetings))

    def test_empty_items(self):
        self.assertEqual(main.parse_wa_items((RAW / "wa_items_empty.xml").read_text()), [])

    def test_bad_xml_is_empty(self):
        self.assertEqual(main.parse_wa_meetings("not xml"), [])


class WashingtonCommittee(unittest.TestCase):
    def setUp(self):
        # Inject a fake leg.wa.gov index so matching is tested without network.
        main._wa_index_cache["loaded"] = True
        main._wa_index_cache["entries"] = [
            (main._cmte_tokens("Select Committee on Pension Policy (SCPP)"),
             "https://leg.wa.gov/.../joint/scpp/"),
            (main._cmte_tokens("Joint Legislative Audit & Review Committee (JLARC)"),
             "https://leg.wa.gov/.../joint/jlarc/"),
            (main._cmte_tokens("Senate Transportation Committee"),
             "https://leg.wa.gov/.../senate/tran/"),
        ]

    def tearDown(self):
        main._wa_index_cache["loaded"] = False
        main._wa_index_cache["entries"] = []

    def test_matches_despite_reordered_acronym(self):
        # SOAP name has the acronym in front; index has it in parentheses.
        self.assertIn("jlarc", main.wa_committee_url(
            "JLARC - Joint Legislative Audit & Review Committee"))

    def test_matches_subset_with_parenthetical_acronym(self):
        self.assertIn("scpp", main.wa_committee_url("Select Committee on Pension Policy"))

    def test_no_false_match(self):
        # "Joint Transportation" must not match "Senate Transportation".
        self.assertIsNone(main.wa_committee_url("Joint Transportation Committee"))


class PastFilter(unittest.TestCase):
    def test_past_hearings_dropped_future_kept(self):
        from datetime import datetime, timezone
        base = {"jurisdiction": "il", "chamber": "house", "committee": "C",
                "status": "scheduled", "bills": [], "source": "ilga.gov"}
        hearings = [
            {**base, "id": "past", "scheduled_iso": "2026-08-01T10:00:00"},
            {**base, "id": "today", "scheduled_iso": "2026-08-28T09:00:00"},
            {**base, "id": "future", "scheduled_iso": "2026-09-10T10:00:00"},
            {**base, "id": "undated", "scheduled_iso": None},
        ]
        doc = main.assemble(hearings, ["il"], "src", datetime(2026, 8, 28, tzinfo=timezone.utc))
        ids = {h["id"] for h in doc["hearings"]}
        self.assertEqual(ids, {"today", "future", "undated"})


class GovbotEnrichment(unittest.TestCase):
    def test_matches_bills_and_attaches_title_tags(self):
        import tempfile, os
        fake = {"bills": [
            {"state": "il", "id": "HB 1643", "title": "Restorative justice pilot",
             "tags": ["criminal justice"]},
            {"state": "il", "id": "HB25", "title": "Housing credit", "tags": ["housing"]},
        ]}
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(fake, f); f.close()
        try:
            hearings = main.build_from_fixtures(RAW)
            matched = main.enrich_from_govbot(hearings, f.name)
        finally:
            os.unlink(f.name)
        self.assertEqual(matched, 2)
        bills = {b["id"]: b for h in hearings for b in h["bills"]}
        self.assertEqual(bills["HB1643"]["govbot_title"], "Restorative justice pilot")
        self.assertEqual(bills["HB25"]["govbot_tags"], ["housing"])
        # a bill govbot doesn't track gets no enrichment
        self.assertNotIn("govbot_title", bills["SB1486"])

    def test_missing_data_is_noop(self):
        hearings = main.build_from_fixtures(RAW)
        self.assertEqual(main.enrich_from_govbot(hearings, "/no/such/data.json"), 0)


class Snapshot(unittest.TestCase):
    def test_offline_build_matches_snapshot(self):
        from datetime import datetime, timezone
        hearings = main.build_from_fixtures(RAW)
        doc = main.assemble(hearings, ["us", "il", "wa"], "fixtures (offline snapshot)",
                            datetime(2026, 8, 28, tzinfo=timezone.utc))
        expected = json.loads(EXPECTED.read_text())
        self.assertEqual(doc, expected,
                         "offline build drifted from snapshot; run render-snapshots.sh "
                         "if the change was intentional")

    def test_every_record_has_required_fields(self):
        expected = json.loads(EXPECTED.read_text())
        for h in expected["hearings"]:
            self.assertTrue(REQUIRED.issubset(h), f"{h.get('id')} missing fields")


class RssFeed(unittest.TestCase):
    def test_feed_is_well_formed_and_complete(self):
        import xml.etree.ElementTree as ET
        doc = json.loads(EXPECTED.read_text())
        xml = main.to_rss(doc)
        root = ET.fromstring(xml)  # raises if malformed
        items = root.findall(".//item")
        self.assertEqual(len(items), len(doc["hearings"]))
        # every item carries a title, link and stable guid
        for it in items:
            self.assertTrue((it.findtext("title") or "").strip())
            self.assertTrue((it.findtext("guid") or "").strip())

    def test_canceled_hearing_flagged_in_title(self):
        doc = json.loads(EXPECTED.read_text())
        xml = main.to_rss(doc)
        self.assertIn("[CANCELED]", xml)


class BillFeeds(unittest.TestCase):
    def _distinct_bills(self, doc):
        keys = set()
        for h in doc["hearings"]:
            for b in h.get("bills", []):
                keys.add((h["jurisdiction"], main._norm_bill_id(b["id"])))
        return keys

    def test_one_wellformed_feed_per_distinct_bill(self):
        import xml.etree.ElementTree as ET
        doc = json.loads(EXPECTED.read_text())
        feeds = main.bill_feeds(doc)
        self.assertEqual(len(feeds), len(self._distinct_bills(doc)))
        for fname, xml in feeds.items():
            self.assertTrue(fname.endswith(".xml"))
            root = ET.fromstring(xml)  # raises if malformed
            self.assertTrue(root.findall(".//item"))

    def test_feed_lists_only_that_bills_hearings(self):
        doc = json.loads(EXPECTED.read_text())
        feeds = main.bill_feeds(doc)
        for h in doc["hearings"]:
            for b in h.get("bills", []):
                fname = main.bill_feed_name(h["jurisdiction"], b["id"])
                self.assertIn(fname, feeds)
                # the hearing's committee title appears in its bill's feed
                self.assertIn(h["id"], feeds[fname])

    def test_feed_name_normalizes_id(self):
        self.assertEqual(main.bill_feed_name("il", "HB 1643"), "il-HB1643.xml")
        self.assertEqual(main.bill_feed_name("wa", "SB-5001"), "wa-SB5001.xml")


class JurisdictionAndHearingFeeds(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads(EXPECTED.read_text())

    def test_one_feed_per_jurisdiction(self):
        import xml.etree.ElementTree as ET
        feeds = main.jurisdiction_feeds(self.doc)
        codes = {h["jurisdiction"] for h in self.doc["hearings"]}
        self.assertEqual(set(feeds), {main.jurisdiction_feed_name(c) for c in codes})
        for code in codes:
            xml = feeds[main.jurisdiction_feed_name(code)]
            root = ET.fromstring(xml)
            n = sum(h["jurisdiction"] == code for h in self.doc["hearings"])
            self.assertEqual(len(root.findall(".//item")), n)

    def test_one_feed_per_hearing_single_item(self):
        import xml.etree.ElementTree as ET
        feeds = main.hearing_feeds(self.doc)
        self.assertEqual(len(feeds), len(self.doc["hearings"]))
        for h in self.doc["hearings"]:
            xml = feeds[main.hearing_feed_name(h["id"])]
            self.assertEqual(len(ET.fromstring(xml).findall(".//item")), 1)

    def test_hearing_feed_name_is_prefixed_and_safe(self):
        self.assertEqual(main.hearing_feed_name("wa-other-33551"),
                         "hearing-wa-other-33551.xml")
        self.assertEqual(main.hearing_feed_name("il/house 1"), "hearing-il-house-1.xml")

    def test_all_feeds_names_are_unique_across_types(self):
        # bill, jurisdiction, and hearing filenames must never collide.
        names = list(main.bill_feeds(self.doc)) + \
            list(main.jurisdiction_feeds(self.doc)) + \
            list(main.hearing_feeds(self.doc))
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(main.all_feeds(self.doc)), set(names))


class Federal(unittest.TestCase):
    def test_seed_records_are_wellformed(self):
        recs = main.fetch_us(use_api=False)
        self.assertTrue(recs, "federal seed should not be empty")
        for h in recs:
            self.assertEqual(h["jurisdiction"], "us")
            self.assertTrue(REQUIRED.issubset(h), f"{h.get('id')} missing fields")
            self.assertEqual(h["source"], "regulations.gov")
            # the docket title rides along on the single bill so the UI shows it
            self.assertTrue(h["bills"][0].get("title"))

    def test_us_sorts_first(self):
        from datetime import datetime, timezone
        hearings = main.build_from_fixtures(RAW)
        doc = main.assemble(hearings, ["us", "il", "wa"], "x",
                            datetime(2026, 8, 28, tzinfo=timezone.utc))
        self.assertEqual(doc["hearings"][0]["jurisdiction"], "us")
        self.assertEqual(doc["jurisdictions"][0]["code"], "us")


if __name__ == "__main__":
    unittest.main(verbosity=2)
