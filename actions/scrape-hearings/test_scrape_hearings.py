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
        self.assertIn("WitnessSlips", h["witness_slip_url"])

    def test_canceled_hearing_flagged(self):
        hearings = main.parse_il_hearings((RAW / "il_house.json").read_text(), "house")
        self.assertEqual(hearings[0]["status"], "canceled")

    def test_bad_json_is_empty_not_crash(self):
        self.assertEqual(main.parse_il_hearings("<html>nope</html>", "house"), [])


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


class Snapshot(unittest.TestCase):
    def test_offline_build_matches_snapshot(self):
        from datetime import datetime, timezone
        hearings = main.build_from_fixtures(RAW)
        doc = main.assemble(hearings, ["il", "wa"], "fixtures (offline snapshot)",
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
