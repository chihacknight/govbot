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

    def test_hearing_without_bills_links_its_own_page(self):
        row = json.loads((RAW / "il_active.json").read_text())[0]
        row = dict(row, subjectMatter="Subject matter only", longDescription="Revenue")
        h = main.parse_il_hearings(json.dumps([row]), "house")[0]
        self.assertEqual(h["bills"], [])
        self.assertEqual(h["witness_slip_url"], h["details_url"])

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

    def test_public_hearing_links_sign_in_on_that_meeting(self):
        # A meeting with bills up for public hearing opens Committee Sign-In on that
        # exact meeting (committee + meeting preselected), not CSI's front page.
        m = next(m for m in main.parse_wa_meetings((RAW / "wa_meetings.xml").read_text())
                 if m["_signin"][0] == "Joint")
        agency, cid = m["_signin"]
        agenda = m["_agenda_id"]
        main.wa_attach_bills(m, ["HB1234"])
        self.assertEqual(m["witness_slip_url"],
                         f"https://app.leg.wa.gov/csi/Joint?selectedCommittee={cid}&selectedMeeting={agenda}")
        self.assertNotIn("_signin", m)
        self.assertNotIn("_agenda_id", m)

    def test_work_session_has_no_sign_in(self):
        # Interim work sessions take no sign-in testimony (CSI doesn't list them).
        m = main.parse_wa_meetings((RAW / "wa_meetings.xml").read_text())[0]
        main.wa_attach_bills(m, [])
        self.assertIsNone(m["witness_slip_url"])
        self.assertTrue(m["details_url"].startswith("https://app.leg.wa.gov/committeeschedules/Home/Agenda/"))

    def test_sign_in_needs_a_csi_chamber(self):
        self.assertIsNone(main.wa_signin_url("Other", "21488", "33497"))
        self.assertIsNone(main.wa_signin_url("Senate", "", "33497"))


class MassachusettsParser(unittest.TestCase):
    def _hearing(self, eid):
        return main.parse_ma_hearing((RAW / f"ma_hearing_{eid}.json").read_text())

    def test_list_ids_extracted_in_order(self):
        ids = main.parse_ma_hearing_list((RAW / "ma_hearings.json").read_text())
        self.assertEqual(ids[:2], [5769, 5774])

    def test_hearing_with_bills(self):
        h = self._hearing(5769)
        self.assertEqual(h["id"], "ma-joint-5769")
        self.assertEqual(h["chamber"], "joint")
        self.assertEqual(h["status"], "scheduled")
        self.assertEqual(h["scheduled_iso"], "2026-09-10T09:00:00")
        bills = {b["id"]: b for b in h["bills"]}
        self.assertIn("H5516", bills)
        self.assertTrue(bills["H5516"]["url"].startswith("https://malegislature.gov/Bills/194/"))
        # The bill name is carried from MA's own feed (MA isn't in govbot data).
        self.assertIn("condominium", bills["H5516"]["title"].lower())
        # Written testimony is submitted on the hearing's own page.
        self.assertEqual(h["witness_slip_url"], "https://malegislature.gov/Events/Hearings/Detail/5769")
        self.assertEqual(h["witness_slip_url"], h["details_url"])

    def test_location_has_room_and_address(self):
        # "437" alone is context-free; the room is labeled and the State House
        # address folded in.
        self.assertEqual(self._hearing(5697)["location"],
                         "Room 437 · 24 Beacon Street · Boston, MA")

    def test_canceled_status(self):
        self.assertEqual(self._hearing(5675)["status"], "canceled")

    def test_null_heavy_record_is_tolerated(self):
        # 5768 has null Name/CommitteeCode/GeneralCourtNumber; must not crash and
        # falls back to the Description for its title.
        h = self._hearing(5768)
        self.assertEqual(h["committee"], "Committee")
        self.assertTrue(h["title"])

    def test_bad_json_is_none_not_crash(self):
        self.assertIsNone(main.parse_ma_hearing("<html>nope</html>"))
        self.assertEqual(main.parse_ma_hearing_list("nope"), [])


class AlaskaParser(unittest.TestCase):
    def setUp(self):
        self.hearings = main.parse_ak_meetings((RAW / "ak_meetings.json").read_text())
        self.by_id = {h["id"]: h for h in self.hearings}

    def test_standing_committee_parsed(self):
        h = next(h for h in self.hearings if h["committee"] == "Resources" and h["chamber"] == "house")
        self.assertEqual(h["scheduled_iso"], "2026-09-10T13:00:00")
        self.assertEqual(h["status"], "scheduled")
        self.assertEqual(h["jurisdiction"], "ak")
        self.assertEqual(h["bills"], [])
        self.assertTrue(h["details_url"].startswith("https://www.akleg.gov/"))
        self.assertNotIn(" ", h["details_url"])  # spaces encoded
        # Alaska has no per-meeting comment form, so the row links the meeting page.
        self.assertIsNone(h["witness_slip_url"])

    def test_all_caps_committee_titlecased(self):
        self.assertTrue(any(h["committee"] == "Legislative Council" for h in self.hearings))

    def test_joint_committee_deduped_across_chambers(self):
        # LEGISLATIVE COUNCIL is listed once per chamber; collapses to one joint row.
        lc = [h for h in self.hearings if h["committee"] == "Legislative Council"]
        self.assertEqual(len(lc), 1)
        self.assertEqual(lc[0]["chamber"], "joint")

    def test_canceled_status(self):
        self.assertTrue(any(h["status"] == "canceled" for h in self.hearings))

    def test_location_abbreviations_expanded(self):
        h = next(h for h in self.hearings if h["committee"] == "Resources")
        self.assertEqual(h["location"], "Anchorage Legislative Information Office DENALI Room")

    def test_bad_json_is_empty_not_crash(self):
        self.assertEqual(main.parse_ak_meetings("<html>nope</html>"), [])
        self.assertEqual(main.parse_ak_meetings('{"Basis": {}}'), [])


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
        doc = main.assemble(hearings, ["us", "il", "wa", "ma", "ak"], "fixtures (offline snapshot)",
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

    def test_stylesheet_pi(self):
        # Root feed points at feed.xsl; granular feeds one dir down at ../feed.xsl.
        doc = json.loads(EXPECTED.read_text())
        self.assertIn('<?xml-stylesheet type="text/xsl" href="feed.xsl"?>',
                      main.to_rss(doc))
        feeds = main.jurisdiction_feeds(doc)
        self.assertTrue(feeds)
        self.assertIn('href="../feed.xsl"', next(iter(feeds.values())))

    def test_central_time_pubdate(self):
        # Feed dates are Central (CST/CDT), not UTC.
        xml = main.to_rss(json.loads(EXPECTED.read_text()))
        self.assertTrue(("-0500" in xml) or ("-0600" in xml))
        self.assertNotIn("+0000", xml)


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
    def setUp(self):
        self.recs = main.parse_fr_documents((RAW / "fr_documents.json").read_text())

    def test_open_comment_periods_parsed(self):
        self.assertEqual(len(self.recs), 20)   # 6 rules + 2 notices of each of 7 kinds
        for h in self.recs:
            self.assertEqual(h["jurisdiction"], "us")
            self.assertTrue(REQUIRED.issubset(h), f"{h.get('id')} missing fields")
            self.assertEqual(h["source"], "federalregister.gov")
            self.assertTrue(h["scheduled_display"].startswith("Comments due "))
            # the rule's title rides along on the single "bill" so the UI shows it
            self.assertTrue(h["bills"][0].get("title"))
        closes = [h["scheduled_iso"] for h in self.recs]
        self.assertEqual(closes, sorted(closes))  # soonest-closing first

    def test_link_is_the_rules_own_comment_form(self):
        census = next(h for h in self.recs if h["committee"] == "Census Bureau" and not h.get("category"))
        self.assertTrue(census["witness_slip_url"].startswith("https://www.regulations.gov/commenton/"))
        self.assertEqual(census["bills"][0]["id"], census["witness_slip_url"].rsplit("/", 1)[-1])
        self.assertTrue(census["details_url"].startswith("https://www.federalregister.gov/documents/"))

    def test_no_online_form_links_the_federal_register_page(self):
        fdic = next(h for h in self.recs if h["committee"] == "Federal Deposit Insurance Corporation"
                    and not h.get("category"))
        self.assertEqual(fdic["witness_slip_url"], fdic["details_url"])
        self.assertEqual(fdic["location"], "Online · Federal Register")

    def test_bad_json_is_empty(self):
        self.assertEqual(main.parse_fr_documents("<html>down</html>"), [])

    def test_preview_shows_soonest_twelve_percent(self):
        from datetime import date
        # 208 open rules (today's real count) -> the 25 closing soonest.
        rule = next(h for h in self.recs if not h.get("category"))
        many = [dict(rule, id=f"us-{i:03d}", scheduled_iso=f"2026-{10 + i % 3}-{1 + i % 28:02d}")
                for i in range(208)]
        shown, meta = main.federal_preview(many, date(2026, 10, 10))
        self.assertEqual(len(shown), 25)
        self.assertEqual(shown, sorted(many, key=lambda h: (h["scheduled_iso"], h["id"]))[:25])
        self.assertEqual(meta["open_total"], 208)
        self.assertEqual(meta["full_list_url"],
                         "https://www.federalregister.gov/documents/search?"
                         "conditions%5Bcomment_date%5D%5Bgte%5D=10%2F10%2F2026"
                         "&conditions%5Btype%5D%5B%5D=PRORULE&conditions%5Btype%5D%5B%5D=RULE")
        # A short list still shows at least one.
        rules = [h for h in self.recs if not h.get("category")]
        self.assertEqual(len(main.federal_preview(rules[:2], date(2026, 10, 10))[0]), 1)

    def test_notice_categories(self):
        cat = main.fr_notice_category
        self.assertEqual(cat("Agency Information Collection Activities; Comment Request"), "paperwork")
        self.assertEqual(cat("Request for Information: Nationwide Implementation of Prehospital Blood Transfusion"), "rfi")
        self.assertEqual(cat("Privacy Act of 1974; System of Records"), "privacy")
        self.assertEqual(cat("Draft Environmental Impact Statement for the Ambler Road"), "environment")
        self.assertEqual(cat("Sunshine Act Meetings"), "meetings")
        self.assertEqual(cat("Application for Permit To Drill"), "permits")
        self.assertEqual(cat("New Postal Products"), "other")
        # The fixture's 6 rules carry no category; its 14 notices all do.
        self.assertEqual(sum(1 for h in self.recs if not h.get("category")), 6)

    def test_preview_keeps_a_few_notices_per_kind(self):
        from datetime import date
        shown, meta = main.federal_preview(self.recs, date(2026, 10, 10))
        notices = [h for h in shown if h.get("category")]
        self.assertEqual(meta["notice_total"], 14)
        self.assertEqual([c["key"] for c in meta["notice_categories"]],
                         ["rfi", "environment", "permits", "meetings", "privacy", "paperwork", "other"])
        self.assertTrue(all(c["total"] == 2 for c in meta["notice_categories"]))
        self.assertEqual(len(notices), 14)   # every kind has <= NOTICES_PER_CATEGORY here
        self.assertIn("conditions%5Btype%5D%5B%5D=NOTICE", meta["notice_list_url"])

    def test_us_sorts_first(self):
        from datetime import datetime, timezone
        hearings = main.build_from_fixtures(RAW)
        doc = main.assemble(hearings, ["us", "il", "wa"], "x",
                            datetime(2026, 8, 28, tzinfo=timezone.utc))
        self.assertEqual(doc["hearings"][0]["jurisdiction"], "us")
        self.assertEqual(doc["jurisdictions"][0]["code"], "us")


if __name__ == "__main__":
    unittest.main(verbosity=2)
