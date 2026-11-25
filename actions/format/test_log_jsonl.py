#!/usr/bin/env python3
"""Offline tests for utils/log_jsonl.py: the per-bill action/vote .jsonl logs.

    cd actions/format && python3 test_log_jsonl.py
"""

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

from utils import log_jsonl as L

SEEN_1 = "2026-09-28T10:46:01+00:00"
SEEN_2 = "2026-09-29T10:33:32+00:00"
SOURCES = [{"url": "https://wyoleg.gov/Legislation/2025/SF0015", "note": ""}]


def action(desc, date="2025-01-14T21:05:15+00:00", cls=None, org='~{"classification": "upper"}'):
    return {"description": desc, "date": date, "classification": cls or [], "organization_id": org}


def vote(motion="SF0001S2001: Amendment adopted", counts=((("yes", 20), ("no", 11))), identifier="",
         start="2026-02-17T18:10:05+00:00", result="pass", rows=None, url="https://lso.wyoleg.gov/x"):
    return {
        "identifier": identifier,
        "motion_text": motion,
        "motion_classification": [],
        "start_date": start,
        "result": result,
        "organization": '~{"classification": "upper"}',
        "legislative_session": "2026",
        "bill": "e53afd06-bbfa-11f1-ad59-beabf7e4c37f",
        "bill_action": None,
        "bill_identifier": "SF0001",
        "votes": rows if rows is not None else [
            {"option": "yes", "voter_name": "Anderson", "voter_id": '~{"name": "Anderson"}', "note": ""},
            {"option": "no", "voter_name": "Baker", "voter_id": '~{"name": "Baker"}', "note": ""},
        ],
        "counts": [{"option": o, "value": v} for o, v in counts],
        "sources": [{"url": url, "note": ""}],
        "extras": {},
    }


def lines(path):
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


class Tmp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.bill = Path(self._tmp.name) / "bill"
        self.bill.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def add_actions(self, actions, seen=SEEN_1):
        return L.append_actions(self.bill, [L.action_line(a, "SF0015", SOURCES, "2025", seen) for a in actions])

    def add_votes(self, votes, seen=SEEN_1, state=None):
        return L.append_votes(self.bill, [L.vote_event_line(v, seen) for v in votes], state)

    def last_vote(self):
        return lines(self.bill / L.VOTE_EVENT_LOG_FILE)[-1]["vote_event"]


class ActionLogTests(Tmp):
    def test_line_shape(self):
        self.add_actions([action("Introduced", cls=["introduction"])])
        [line] = lines(self.bill / L.ACTION_LOG_FILE)
        self.assertEqual(list(line), ["id", "first_seen", "chamber", "action", "bill_id"])
        self.assertEqual(line["id"], "20250114T210515Z.classification.introduction.upper")
        self.assertEqual(line["first_seen"], SEEN_1)
        self.assertEqual(line["chamber"], "upper")
        self.assertEqual(line["action"]["occurred_at"], "2025-01-14T21:05:15+00:00")
        self.assertEqual(line["action"]["sources"], SOURCES)  # kept on purpose: a lone line leads back to the bill
        self.assertEqual(line["bill_id"], "SF0015")

    def test_rerun_adds_nothing(self):
        self.assertEqual(self.add_actions([action("A"), action("B", date="2025-01-15")]), 2)
        before = (self.bill / L.ACTION_LOG_FILE).read_bytes()
        self.assertEqual(self.add_actions([action("A"), action("B", date="2025-01-15")], seen=SEEN_2), 0)
        self.assertEqual((self.bill / L.ACTION_LOG_FILE).read_bytes(), before)

    def test_append_only_in_first_seen_order(self):
        # A late-posted action dated BEFORE existing ones still goes at the end:
        # the file's order is the order we saw things, so git diff = only new lines.
        self.add_actions([action("Later", date="2025-03-01")])
        self.add_actions([action("Backdated", date="2025-01-01")], seen=SEEN_2)
        got = lines(self.bill / L.ACTION_LOG_FILE)
        self.assertEqual([l["action"]["description"] for l in got], ["Later", "Backdated"])
        self.assertEqual([l["first_seen"] for l in got], [SEEN_1, SEEN_2])

    def test_whitespace_only_difference_is_the_same_action(self):
        # KY's 2026-09-29 scrape started emitting line breaks inside descriptions.
        self.add_actions([action("reported favorably, 1st reading, to Calendar with Committee Substitute (1)")])
        added = self.add_actions(
            [action("reported favorably, 1st reading, to Calendar with Committee\r\n                    Substitute (1)")],
            seen=SEEN_2,
        )
        self.assertEqual(added, 0)

    def test_same_action_in_two_chambers_is_two_actions(self):
        self.add_actions([action("Read first time"), action("Read first time", org='~{"classification": "lower"}')])
        self.assertEqual(len(lines(self.bill / L.ACTION_LOG_FILE)), 2)

    def test_colliding_old_style_ids_get_a_suffix(self):
        # Same second + same slug used to overwrite one file with the other.
        self.add_actions([action("Read first time"), action("Read first time", org='~{"classification": "lower"}')])
        ids = [l["id"] for l in lines(self.bill / L.ACTION_LOG_FILE)]
        self.assertEqual(ids[0], "20250114T210515Z_read_first_time")
        self.assertTrue(ids[1].startswith("20250114T210515Z_read_first_time~"))
        self.assertEqual(len(set(ids)), 2)

    def test_interrupted_write_is_not_glued_to_the_next_line(self):
        self.add_actions([action("A")])
        path = self.bill / L.ACTION_LOG_FILE
        path.write_text(path.read_text().rstrip("\n"))  # lost the final newline
        self.add_actions([action("B", date="2025-02-01")])
        self.assertEqual(len(lines(path)), 2)

    def test_damaged_line_stops_the_run(self):
        (self.bill / L.ACTION_LOG_FILE).write_text('{"id": "x"\n')
        with self.assertRaises(ValueError):
            self.add_actions([action("A")])


class RewordingTests(Tmp):
    LOWER = '~{"classification": "lower"}'

    def a(self, desc, date="2025-02-26T15:00:00+00:00"):
        return action(desc, date=date, org=self.LOWER)

    def test_mt_first_reading_is_a_correction_not_a_new_action(self):
        # MT 2026-08-10: "(H) First Reading" -> "(H) 1st Reading" on every past bill.
        before = [self.a("(H) Introduced", "2025-02-25T15:00:00+00:00"), self.a("(H) First Reading")]
        after = [self.a("(H) Introduced", "2025-02-25T15:00:00+00:00"), self.a("(H) 1st Reading")]
        L.append_actions(self.bill, [L.action_line(x, "HB794", SOURCES, "2025", SEEN_1) for x in before])
        added = L.append_actions(self.bill, [L.action_line(x, "HB794", SOURCES, "2025", SEEN_2) for x in after],
                                 rewordings=L.find_rewordings(before, after))
        self.assertEqual(added, 1)
        got = lines(self.bill / L.ACTION_LOG_FILE)
        self.assertEqual([g["action"]["description"] for g in got], ["(H) Introduced", "(H) First Reading", "(H) 1st Reading"])
        self.assertEqual(got[1]["id"], got[2]["id"])  # same action, new wording
        # A later rewording of the rewording stays under the same id.
        again = [after[0], self.a("(H) 1st Reading (Floor)")]
        L.append_actions(self.bill, [L.action_line(x, "HB794", SOURCES, "2025", SEEN_2) for x in again],
                         rewordings=L.find_rewordings(after, again))
        self.assertEqual(lines(self.bill / L.ACTION_LOG_FILE)[3]["id"], got[1]["id"])

    def test_pairs_changed_actions_slot_by_slot(self):
        day = "2025-03-01"
        before = [self.a("A", day), self.a("B", day), self.a("C", day)]
        after = [self.a("A", day), self.a("B2", day), self.a("C2", day)]
        r = L.find_rewordings(before, after)
        self.assertEqual(r.pairs, {L.raw_action_key(after[1]): L.raw_action_key(before[1]),
                                   L.raw_action_key(after[2]): L.raw_action_key(before[2])})
        self.assertEqual(r.unpaired, 0)

    def test_different_count_on_the_date_is_not_paired(self):
        day = "2025-03-01"
        r = L.find_rewordings([self.a("Referred to Committee on Judiciary", day)],
                              [self.a("Referred to Senate Committee on Judiciary", day), self.a("Hearing", day)])
        self.assertEqual((r.pairs, r.unpaired), ({}, 2))

    def test_unchanged_actions_reordered_is_not_paired(self):
        day = "2025-03-01"
        r = L.find_rewordings([self.a("A", day), self.a("B", day), self.a("C", day)],
                              [self.a("B", day), self.a("A", day), self.a("C2", day)])
        self.assertEqual((r.pairs, r.unpaired), ({}, 1))

    def test_new_bill_and_new_date_have_nothing_to_reword(self):
        self.assertEqual(L.find_rewordings(None, [self.a("A")]).pairs, {})
        r = L.find_rewordings([self.a("A", "2025-03-01")], [self.a("A", "2025-03-01"), self.a("B", "2025-03-02")])
        self.assertEqual((r.pairs, r.unpaired), ({}, 0))  # a new date is just new


class VoteLogTests(Tmp):
    def test_rerun_adds_nothing(self):
        self.assertEqual(self.add_votes([vote()]), 1)
        self.assertEqual(self.add_votes([vote()], seen=SEEN_2), 0)

    def test_raw_duplicates_in_one_scrape_are_logged_once(self):
        # PA's scraper writes each vote ~5 times.
        self.assertEqual(self.add_votes([vote()] * 5), 1)

    def test_cosmetic_changes_are_not_corrections(self):
        self.add_votes([vote()])
        v = vote(url="http://LSO.wyoleg.gov/X", identifier="RCS#1413")  # URL format + roll-call number filled in later
        v["votes"] = list(reversed(v["votes"]))  # CA reorders voter rows
        v["bill"] = "another-scraper-uuid"
        v["bill_action"] = "(S) 3rd Reading Concurred"
        self.assertEqual(self.add_votes([v], seen=SEEN_2), 0)

    def test_correction_is_appended_under_the_same_id(self):
        self.add_votes([vote()])
        fixed = vote(identifier="RCS#7")
        fixed["votes"][1]["option"] = "yes"  # a member's vote corrected; counts stay the same
        self.assertEqual(self.add_votes([fixed], seen=SEEN_2), 1)
        first, second = lines(self.bill / L.VOTE_EVENT_LOG_FILE)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(second["first_seen"], SEEN_2)
        self.assertEqual(second["vote_event"]["votes"][1]["option"], "yes")

    def test_in_scrape_flip_flop_logs_once(self):
        # OH HB 14: each scrape holds the same 6-0 vote as both pass and fail.
        self.assertEqual(self.add_votes([vote(result="pass"), vote(result="fail")]), 1)
        for seen in (SEEN_2, "2026-09-30T10:00:00+00:00", "2026-10-01T10:00:00+00:00"):
            self.assertEqual(self.add_votes([vote(result="fail"), vote(result="pass")], seen=seen), 0)
        self.assertEqual(len(lines(self.bill / L.VOTE_EVENT_LOG_FILE)), 1)

    def test_revert_is_logged_so_the_last_line_matches_the_scrape(self):
        # DE SB 315: pass -> fail -> pass. The reader shows the last line.
        self.add_votes([vote(result="pass")])
        self.assertEqual(self.add_votes([vote(result="fail")], seen=SEEN_2), 1)
        self.assertEqual(self.add_votes([vote(result="pass")], seen="2026-09-30T10:00:00+00:00"), 1)
        got = lines(self.bill / L.VOTE_EVENT_LOG_FILE)
        self.assertEqual([v["vote_event"]["result"] for v in got], ["pass", "fail", "pass"])
        self.assertEqual(len({v["id"] for v in got}), 1)

    def test_two_new_versions_in_one_scrape_log_one_correction(self):
        self.add_votes([vote(result="pass")])
        self.assertEqual(self.add_votes([vote(result="fail"), vote(result="fail", counts=(("yes", 20), ("no", 11)), rows=[])], seen=SEEN_2), 1)
        self.assertEqual(self.last_vote()["result"], "fail")

    def test_nd_service_unavailable_night_logs_nothing(self):
        self.add_votes([vote()], state="nd")
        bad = vote(rows=[{"option": "yes", "voter_name": "Service Unavailable", "voter_id": "~{}", "note": ""},
                         {"option": "no", "voter_name": "Baker", "voter_id": "~{}", "note": ""}])
        self.assertEqual(self.add_votes([bad], seen=SEEN_2, state="nd"), 0)
        self.assertEqual(self.add_votes([vote()], seen="2026-09-30T10:00:00+00:00", state="nd"), 0)
        self.assertEqual(self.last_vote()["votes"][0]["voter_name"], "Anderson")
        # A new vote seen only on a bad night waits for a good one.
        self.assertEqual(self.add_votes([dict(bad, motion_text="Another motion")], seen=SEEN_2, state="nd"), 0)

    def test_tn_empty_roll_call_logs_nothing(self):
        self.add_votes([vote()], state="tn")
        self.assertEqual(self.add_votes([vote(rows=[])], seen=SEEN_2, state="tn"), 0)
        self.assertEqual(self.add_votes([vote()], seen="2026-09-30T10:00:00+00:00", state="tn"), 0)
        self.assertEqual(len(lines(self.bill / L.VOTE_EVENT_LOG_FILE)), 1)
        # A vote first seen with no voters is still logged: no earlier names to lose.
        self.assertEqual(self.add_votes([vote(motion="Another motion", rows=[])], seen=SEEN_2, state="tn"), 1)

    def test_change_to_an_empty_roll_call_is_logged_elsewhere(self):
        # OK HB 2374: ['STRIKE THE TITLE - ADOPTED'] -> [] is the scraper fixing its parsing.
        junk = [{"option": "yes", "voter_name": "STRIKE THE TITLE - ADOPTED", "voter_id": "~{}", "note": ""}]
        self.add_votes([vote(rows=junk)], state="ok")
        self.assertEqual(self.add_votes([vote(rows=[])], seen=SEEN_2, state="ok"), 1)
        self.assertEqual(self.last_vote()["votes"], [])

    def test_matching_roll_call_numbers_are_the_same_vote(self):
        self.add_votes([vote(identifier="RCS#9")])
        changed_counts = vote(identifier="RCS#9", counts=(("yes", 21), ("no", 10)))
        self.add_votes([changed_counts], seen=SEEN_2)
        got = lines(self.bill / L.VOTE_EVENT_LOG_FILE)
        self.assertEqual(len(got), 2)
        self.assertEqual(got[0]["id"], got[1]["id"])  # a correction, not a new vote

    def test_reused_identifier_on_different_votes_is_not_one_vote(self):
        # VA: the bill's document number on every procedural entry, same day.
        # MT: a committee vote and the later floor vote share one id.
        va = [vote(identifier="26200060D", motion=m, counts=(("yes", 0), ("no", 0)), result="fail")
              for m in ("Presented 26200060D", "Laid on Clerk's Desk")]
        mt = [vote(identifier="2025-SB 80-562", motion="do_pass", start="2025-01-30T22:29:58+00:00", counts=(("yes", 11), ("no", 0))),
              vote(identifier="2025-SB 80-562", motion="Do Pass", start="2025-02-04T20:21:02+00:00", counts=(("yes", 50), ("no", 0)))]
        self.assertEqual(self.add_votes(va + mt), 4)
        # Every later night: nothing, not a "correction" per entry.
        self.assertEqual(self.add_votes(va + mt, seen=SEEN_2), 0)
        self.assertEqual(len({l["id"] for l in lines(self.bill / L.VOTE_EVENT_LOG_FILE)}), 4)

    def test_two_roll_calls_on_one_motion_are_two_votes(self):
        # PA HB 1549: roll calls 649 and 650 on the same tabling motion, same time.
        self.add_votes([vote(counts=(("yes", 15), ("no", 8))), vote(counts=(("yes", 11), ("no", 14)), result="fail")])
        got = lines(self.bill / L.VOTE_EVENT_LOG_FILE)
        self.assertEqual(len(got), 2)
        self.assertNotEqual(got[0]["id"], got[1]["id"])

    def test_same_old_filename_different_votes_both_kept(self):
        # The old layout overwrote these (same second, result, chamber).
        self.add_votes([vote(motion="Amendment 1 adopted"), vote(motion="Amendment 2 adopted")])
        ids = [l["id"] for l in lines(self.bill / L.VOTE_EVENT_LOG_FILE)]
        self.assertEqual(ids[0], "20260217T181005Z.vote_event.pass.upper")
        self.assertTrue(ids[1].startswith("20260217T181005Z.vote_event.pass.upper~"))

    def test_vote_without_a_date_is_still_logged(self):
        self.add_votes([vote(start=None)])
        [line] = lines(self.bill / L.VOTE_EVENT_LOG_FILE)
        self.assertTrue(line["id"].startswith("unknown"))


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.session = self.repo / "country:us" / "state:wy" / "sessions" / "2025"
        self.bill = self.session / "bills" / "SF0015"
        (self.bill / "logs").mkdir(parents=True)
        (self.session / "logs").mkdir()
        old_action = {"action": L.action_line(action("Introduced", cls=["introduction"]), "SF0015", SOURCES, "2025", None)["action"], "bill_id": "SF0015"}
        older_action = {"action": L.action_line(action("Number assigned", date="2024-12-05T02:27:42+00:00"), "SF0015", SOURCES, "2025", None)["action"], "bill_id": "SF0015"}
        self.write("20250114T210515Z.classification.introduction.upper.json", old_action)
        self.write("20241205T022742Z_number_assigned.json", older_action)
        self.write("20260217T181005Z.vote_event.pass.upper.json", vote())
        (self.bill / "logs" / "notes.txt").write_text("not a log")
        (self.bill / "metadata.json").write_text(json.dumps({"actions": [
            dict(action("Introduced", cls=["introduction"]), _processing={"log_file_created": "2026-07-01T07:00:00Z"}),
        ]}))
        for name in os.listdir(self.bill / "logs"):
            if name.endswith(".json"):
                os.symlink(f"../bills/SF0015/logs/{name}", self.session / "logs" / name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name, obj):
        (self.bill / "logs" / name).write_text(json.dumps(obj, indent=2))

    def test_convert_repo(self):
        self.assertTrue(L.has_legacy_logs(self.repo))
        stats = L.convert_repo(self.repo).as_dict()
        self.assertEqual(stats["files_folded"], 3)
        self.assertEqual(stats["symlinks_removed"], 3)
        self.assertEqual(len(stats["left_in_place"]), 1)  # notes.txt: unknown, kept
        self.assertTrue((self.bill / "logs" / "notes.txt").exists())
        self.assertFalse((self.session / "logs").exists())

        acts = lines(self.bill / L.ACTION_LOG_FILE)
        # Converted entries are ordered by the government's date (what the old filenames sorted by).
        self.assertEqual([a["id"] for a in acts], ["20241205T022742Z_number_assigned", "20250114T210515Z.classification.introduction.upper"])
        # first_seen from metadata.json's _processing.log_file_created where the pipeline recorded it.
        self.assertEqual([a["first_seen"] for a in acts], [None, "2026-07-01T07:00:00Z"])
        [v] = lines(self.bill / L.VOTE_EVENT_LOG_FILE)
        self.assertEqual(v["id"], "20260217T181005Z.vote_event.pass.upper")
        self.assertIsNone(v["first_seen"])  # filled in by the backfill from raw history

    def test_old_action_shape_is_converted_not_merged(self):
        # GA HB 14: two "Senate Committee Favorably Reported By Substitute" actions
        # (Mar 27 and Mar 31) stored in OpenStates' own action shape.
        for day in ("27", "31"):
            self.write(f"202503{day}T000000Z_senate_committee_favorably_reported_by_substitute.json", {
                "action": {"description": "Senate Committee Favorably Reported  By Substitute", "date": f"2025-03-{day}",
                           "organization_id": '~{"classification": "upper"}', "classification": ["committee-passage-favorable"],
                           "related_entities": []},
                "bill_id": "HB 14"})
        L.convert_bill(self.bill)
        got = [a for a in lines(self.bill / L.ACTION_LOG_FILE) if "Favorably" in a["action"]["description"]]
        self.assertEqual([a["action"]["occurred_at"] for a in got], ["2025-03-27", "2025-03-31"])
        a = got[0]["action"]
        self.assertEqual(sorted(a), sorted(["description", "occurred_at", "jurisdiction_id", "session_id", "entity_type", "classifications", "related_entities", "sources"]))
        self.assertEqual(a["session_id"], "2025")
        self.assertEqual(a["classifications"], ["committee-passage-favorable"])
        self.assertEqual(got[0]["chamber"], "upper")

    def test_convert_is_idempotent(self):
        L.convert_repo(self.repo)
        snapshot = {p: p.read_bytes() for p in self.bill.glob("*.jsonl")}
        again = L.convert_repo(self.repo).as_dict()
        self.assertEqual(again["files_folded"], 0)
        self.assertEqual({p: p.read_bytes() for p in self.bill.glob("*.jsonl")}, snapshot)

    def test_converted_lines_go_before_newer_ones(self):
        later = L.action_line(action("Signed", date="2025-02-24"), "SF0015", SOURCES, "2025", SEEN_2)
        dup = L.action_line(action("Introduced", cls=["introduction"]), "SF0015", SOURCES, "2025", SEEN_2)
        L.append_actions(self.bill, [later, dup])
        L.convert_bill(self.bill)
        acts = lines(self.bill / L.ACTION_LOG_FILE)
        self.assertEqual([a["action"]["description"] for a in acts], ["Number assigned", "Introduced", "Signed"])

    def test_duplicate_action_keeps_backfill_line_with_old_id_and_earlier_first_seen(self):
        # The old file says 2026-07-01 (a reformat's run time); the backfill saw it
        # in the 2026-09-28 scrape, so the old stamp is earlier and wins here.
        dup = L.action_line(action("Introduced", cls=["introduction"]), "SF0015", SOURCES, "2025", SEEN_1)
        dup["id"] = "20250114T210515Z.classification.introduction.upper~abcd1234"  # backfill had a collision
        L.append_actions(self.bill, [dup])
        stats = L.convert_bill(self.bill)
        acts = lines(self.bill / L.ACTION_LOG_FILE)
        [intro] = [a for a in acts if a["action"]["description"] == "Introduced"]
        self.assertEqual(intro["id"], "20250114T210515Z.classification.introduction.upper")
        self.assertEqual(intro["first_seen"], "2026-07-01T07:00:00Z")
        self.assertEqual(stats.duplicates_dropped, 1)

    def test_duplicate_action_takes_backfill_first_seen_when_earlier(self):
        early = "2025-11-27T10:00:00+00:00"
        L.append_actions(self.bill, [L.action_line(action("Introduced", cls=["introduction"]), "SF0015", SOURCES, "2025", early)])
        L.convert_bill(self.bill)
        [intro] = [a for a in lines(self.bill / L.ACTION_LOG_FILE) if a["action"]["description"] == "Introduced"]
        self.assertEqual(intro["first_seen"], early)

    def test_duplicate_vote_keeps_backfill_first_seen_and_old_id(self):
        backfilled = L.vote_event_line(vote(), SEEN_1)
        backfilled["id"] = "something_else"
        L.append_votes(self.bill, [backfilled])
        L.convert_bill(self.bill)
        [v] = lines(self.bill / L.VOTE_EVENT_LOG_FILE)
        self.assertEqual(v["id"], "20260217T181005Z.vote_event.pass.upper")
        self.assertEqual(v["first_seen"], SEEN_1)  # the old file had null

    def test_conversion_keeps_a_backfilled_revert(self):
        # The backfill logged A, B, then A again (a real revert); conversion keeps all three.
        b = vote()
        b["votes"][1]["option"] = "yes"
        for v, seen in ((vote(), SEEN_1), (b, SEEN_2), (vote(), "2026-09-30T10:00:00+00:00")):
            L.append_votes(self.bill, [L.vote_event_line(v, seen)])
        L.convert_bill(self.bill)
        got = lines(self.bill / L.VOTE_EVENT_LOG_FILE)
        self.assertEqual([v["vote_event"]["votes"][1]["option"] for v in got], ["no", "yes", "no"])
        self.assertEqual(len({v["id"] for v in got}), 1)

    def test_older_vote_version_goes_first_under_the_same_id(self):
        # The old file holds 20-11; the raw history only ever saw 21-10 then 21-9.
        # (Counts are part of the fallback key, so the roll-call identifier is what
        # makes these one vote.)
        self.write("20260217T181005Z.vote_event.pass.upper.json", vote(identifier="RC 12"))
        L.append_votes(self.bill, [L.vote_event_line(vote(identifier="RC 12", counts=(("yes", 21), ("no", 10))), SEEN_1)])
        L.append_votes(self.bill, [L.vote_event_line(vote(identifier="RC 12", counts=(("yes", 21), ("no", 9))), SEEN_2)])
        L.convert_bill(self.bill)
        got = lines(self.bill / L.VOTE_EVENT_LOG_FILE)
        self.assertEqual([[c["value"] for c in v["vote_event"]["counts"]] for v in got], [[20, 11], [21, 10], [21, 9]])
        self.assertEqual({v["id"] for v in got}, {"20260217T181005Z.vote_event.pass.upper"})
        self.assertEqual([v["first_seen"] for v in got], [None, SEEN_1, SEEN_2])

    def test_existing_new_layout_lines_keep_their_order(self):
        # Two nights, appended in first-seen order (the second backdated).
        L.append_actions(self.bill, [L.action_line(action("Signed", date="2025-03-01"), "SF0015", SOURCES, "2025", SEEN_1)])
        L.append_actions(self.bill, [L.action_line(action("Amended", date="2025-02-01"), "SF0015", SOURCES, "2025", SEEN_2)])
        L.convert_bill(self.bill)
        got = [a["action"]["description"] for a in lines(self.bill / L.ACTION_LOG_FILE)]
        self.assertEqual(got, ["Number assigned", "Introduced", "Signed", "Amended"])

    def test_one_batch_reads_forwards(self):
        tmp = self.bill.parent / "fresh"
        tmp.mkdir()
        L.append_actions(tmp, [L.action_line(action(d, date=f"2025-0{m}-01"), "SF0015", SOURCES, "2025", SEEN_1)
                               for d, m in (("third", 3), ("first", 1), ("second", 2))])
        got = [a["action"]["description"] for a in lines(tmp / L.ACTION_LOG_FILE)]
        self.assertEqual(got, ["first", "second", "third"])

    def test_conversion_keeps_a_rewordings_shared_id(self):
        # Backfilled: "Signed" then its new wording, one id. The old files hold neither.
        before = [action("Signed", date="2025-02-24")]
        after = [action("Signed by Governor", date="2025-02-24")]
        L.append_actions(self.bill, [L.action_line(before[0], "SF0015", SOURCES, "2025", SEEN_1)])
        L.append_actions(self.bill, [L.action_line(after[0], "SF0015", SOURCES, "2025", SEEN_2)],
                         rewordings=L.find_rewordings(before, after))
        L.convert_bill(self.bill)
        got = [a for a in lines(self.bill / L.ACTION_LOG_FILE) if a["action"]["description"].startswith("Signed")]
        self.assertEqual([a["action"]["description"] for a in got], ["Signed", "Signed by Governor"])
        self.assertEqual(got[0]["id"], got[1]["id"])
        self.assertNotIn("~", got[0]["id"])

    def test_old_logs_folder_jsonl_is_folded(self):
        # IL, 2026-09-22..25: the formatter wrote {"action", "bill_id"} lines to
        # bills/<id>/logs/action_logs.jsonl (Taha's first JSONL step).
        amended = L.action_line(action("Added Co-Sponsor Rep. Regan Deering", date="2026-09-21"), "SF0015", SOURCES, "2025", None)
        intro = L.action_line(action("Introduced", cls=["introduction"]), "SF0015", SOURCES, "2025", None)  # also an old .json file
        (self.bill / "logs" / L.ACTION_LOG_FILE).write_text(
            "".join(json.dumps({"action": l["action"], "bill_id": "SF0015"}) + "\n" for l in (amended, intro)))
        stats = L.convert_bill(self.bill)
        self.assertNotIn(str(self.bill / "logs" / L.ACTION_LOG_FILE), stats.left_in_place)
        self.assertFalse((self.bill / "logs" / L.ACTION_LOG_FILE).exists())
        acts = lines(self.bill / L.ACTION_LOG_FILE)
        self.assertEqual([a["id"] for a in acts], [
            "20241205T022742Z_number_assigned",
            "20250114T210515Z.classification.introduction.upper",
            "20260921T000000Z_added_cosponsor_rep_regan_deering",
        ])

    def test_unrecognised_line_leaves_the_old_jsonl_in_place(self):
        (self.bill / "logs" / L.ACTION_LOG_FILE).write_text('{"something": "else"}\n')
        stats = L.convert_bill(self.bill)
        self.assertIn(str(self.bill / "logs" / L.ACTION_LOG_FILE), stats.left_in_place)
        self.assertTrue((self.bill / "logs" / L.ACTION_LOG_FILE).exists())

    def test_session_symlink_folder_keeps_real_files(self):
        (self.session / "logs" / "real.json").write_text("{}")
        stats = L.convert_repo(self.repo).as_dict()
        self.assertIn(str(self.session / "logs" / "real.json"), stats["left_in_place"])
        self.assertTrue((self.session / "logs" / "real.json").exists())


if __name__ == "__main__":
    unittest.main()
