#!/usr/bin/env python3
"""Offline tests for the history scanner: a tiny raw scraper repo and data repo are built with
git inside a temp folder, scanned, and the database checked.

usage: python3 test_scan.py
"""
from __future__ import annotations

import copy
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import report  # noqa: E402
import scan  # noqa: E402

ST = "xx"


def run_git(repo: Path, *args: str, date: str = "2026-01-01T05:00:00+00:00") -> None:
    env = dict(os.environ, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com",
                    "-c", "commit.gpgsign=false", *args], check=True, capture_output=True, env=env)


def commit(repo: Path, files: dict[str, bytes], date: str) -> None:
    """Replace _data/xx/ with `files` (name -> bytes) and commit it at `date`."""
    d = repo / "_data" / ST
    if d.exists():
        for f in d.iterdir():
            f.unlink()
    d.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (d / name).write_bytes(data)
    run_git(repo, "add", "-A", date=date)
    run_git(repo, "commit", "-q", "--allow-empty", "-m", f"scrape {date}", date=date)


def bill(session, ident, **over):
    d = {
        "legislative_session": session, "identifier": ident, "title": f"Title of {ident}",
        "abstracts": [{"abstract": "An act.", "note": "summary"}],
        "sponsorships": [{"name": "Dan Ugaste", "classification": "primary", "primary": True}],
        "actions": [{"date": "2026-01-01", "description": "First Reading", "organization_id": "lower"},
                    {"date": "2026-01-02", "description": "Referred", "organization_id": "lower"}],
        "versions": [{"note": "Introduced", "links": [{"url": "https://x/1.pdf", "media_type": "application/pdf"}]}],
        "documents": [], "extras": {"bdr": "12"}, "custom_field": "state-specific",
    }
    d.update(over)
    d["scraped_at"] = str(uuid.uuid4())  # differs every scrape, as in the real files
    d["_id"] = str(uuid.uuid4())
    return d


def vote(session, ident, voters, **over):
    d = {"identifier": "RC1", "motion_text": "Passage", "start_date": "2026-01-02", "organization": "lower",
         "legislative_session": session, "bill_identifier": ident, "result": "pass",
         "votes": [{"option": "yes", "voter_name": n} for n in voters],
         "counts": [{"option": "yes", "value": len(voters)}], "_id": str(uuid.uuid4())}
    d.update(over)
    return d


def files(*objs) -> dict[str, bytes]:
    out = {"jurisdiction_x.json": b'{"name": "X"}'}
    for kind, d in objs:
        out[f"{kind}_{uuid.uuid4()}.json"] = d if isinstance(d, bytes) else json.dumps(d).encode()
    return out


class ScanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.raw_root, cls.data_root, cls.archive_root = root / "raw", root / "data", root / "archive"
        raw = cls.raw_root / f"{ST}-legislation"
        raw.mkdir(parents=True)
        run_git(raw, "init", "-q")
        a = bill("s1", "HB1")
        b = bill("s1", "HB2")
        v = vote("s1", "HB1", ["Ann", "Bob"])
        # 0: two bills, one vote.
        commit(raw, files(("bill", a), ("bill", b), ("vote_event", v)), "2026-01-01T05:00:00+00:00")
        # 1: nothing changed but scraped_at/_id.
        commit(raw, files(("bill", bill("s1", "HB1")), ("bill", bill("s1", "HB2")), ("vote_event", vote("s1", "HB1", ["Ann", "Bob"]))),
               "2026-01-02T05:00:00-05:00")  # a self-hosted runner's local time
        # 2: HB1 loses its sponsors, one action reworded, one changed only in whitespace, plus a
        # duplicate file; HB2 is only in a file with conflict markers; the roll call is emptied.
        a2 = bill("s1", "HB1", sponsorships=[],
                  actions=[{"date": "2026-01-01", "description": "First  Reading", "organization_id": "lower"},
                           {"date": "2026-01-02", "description": "Referred to Rules", "organization_id": "lower"}])
        conflicted = b'<<<<<<< HEAD\n{"legislative_session": "s1", "identifier": "HB2"}\n=======\n{}\n>>>>>>> x\n'
        commit(raw, files(("bill", a2), ("bill", copy.deepcopy(a2)), ("bill", conflicted),
                          ("vote_event", vote("s1", "HB1", []))), "2026-01-03T05:00:00+00:00")
        # 3: an empty scrape (no bill files).
        commit(raw, files(), "2026-01-04T05:00:00+00:00")
        # 4: both back (HB1 with sponsors), a new bill in a new session, an error page as a voter.
        commit(raw, files(("bill", bill("s1", "HB1")), ("bill", bill("s1", "HB2")), ("bill", bill("s2", "SB1")),
                          ("vote_event", vote("s1", "HB1", ["Ann", "Service Unavailable"]))), "2026-01-05T05:00:00+00:00")
        # 5: HB2 gone for good while s1 goes on; the vote is gone while HB1 is present.
        commit(raw, files(("bill", bill("s1", "HB1")), ("bill", bill("s2", "SB1"))), "2026-01-06T05:00:00+00:00")

        data = cls.data_root / f"{ST}-legislation"
        mdir = data / "country:us" / f"state:{ST}" / "sessions" / "s1" / "bills" / "HB1"
        mdir.mkdir(parents=True)
        (mdir / "metadata.json").write_text("{}")
        run_git(data, "init", "-q")
        run_git(data, "add", "-A")
        run_git(data, "commit", "-q", "-m", "data")
        (cls.archive_root / f"{ST}-legislation").mkdir(parents=True)  # a clone still starting: no HEAD

        cls.db = root / "out" / "history.sqlite"
        cls.args = (ST, cls.raw_root, cls.data_root, cls.archive_root, cls.db, root / "out")
        cls.msg = scan.run_state(*cls.args)
        cls.con = sqlite3.connect(str(cls.db))
        cls.con.row_factory = sqlite3.Row

    @classmethod
    def tearDownClass(cls):
        cls.con.close()
        cls.tmp.cleanup()

    def scrape(self, idx):
        return self.con.execute("SELECT * FROM scrapes WHERE state = ? AND idx = ?", (ST, idx)).fetchone()

    def field(self, idx, f):
        return self.con.execute("SELECT * FROM scrape_fields WHERE state = ? AND idx = ? AND field = ?",
                                (ST, idx, f)).fetchone()

    def test_scrapes_in_order_in_utc(self):
        rows = self.con.execute("SELECT committed_at FROM scrapes WHERE state = ? ORDER BY idx", (ST,)).fetchall()
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[1][0], "2026-01-02T10:00:00+00:00")

    def test_identical_content_ignores_scraped_at_and_id(self):
        s = self.scrape(1)
        self.assertEqual((s["identical_content"], s["identical_blobs"], s["bills_changed"]), (1, 0, 0))

    def test_field_loss_and_comeback(self):
        f = self.field(2, "sponsorships")
        self.assertEqual((f["have"], f["had"], f["lost"], f["lost_back"]), (0, 1, 1, 1))
        self.assertIn("s1 HB1", f["examples"])
        self.assertEqual(self.field(4, "sponsorships")["gained"], 1)

    def test_actions_reworded_and_whitespace(self):
        s = self.scrape(2)
        self.assertEqual((s["actions_reworded"], s["actions_ws_only"], s["actions_new"], s["actions_gone"]), (1, 1, 0, 0))
        self.assertIn("Referred -> Referred to Rules", s["examples"])

    def test_unreadable_bill_is_not_gone(self):
        s = self.scrape(2)
        self.assertEqual((s["bad_conflict"], s["bad_bills"], s["bills_gone"], s["bills"]), (1, 1, 0, 1))
        self.assertEqual((s["bill_files"], s["dup_ratio"], s["dup_bills_conflicting"]), (3, 2.0, 0))
        bad = self.con.execute("SELECT problem, session, identifier FROM bad_files WHERE state = ?", (ST,)).fetchall()
        self.assertEqual([tuple(r) for r in bad], [("conflict", "s1", "HB2")])

    def test_empty_scrape_and_return(self):
        s3, s4 = self.scrape(3), self.scrape(4)
        self.assertEqual((s3["bill_files"], s3["bills"], s3["bills_gone"], s3["bills_gone_back"]), (0, 0, 2, 2))
        self.assertEqual((s4["bills_returned"], s4["bills_new"]), (2, 1))

    def test_votes(self):
        self.assertEqual((self.scrape(2)["votes_emptied"], self.scrape(2)["votes_changed"]), (1, 1))
        s4 = self.scrape(4)
        self.assertEqual((s4["votes_returned"], s4["votes_error_voters"]), (1, 1))
        self.assertIn("Service Unavailable", s4["examples"])
        self.assertEqual(self.scrape(5)["votes_gone"], 1)

    def test_bill_life_story(self):
        hb1 = self.con.execute("SELECT * FROM bills WHERE state = ? AND identifier = 'HB1'", (ST,)).fetchone()
        hb2 = self.con.execute("SELECT * FROM bills WHERE state = ? AND identifier = 'HB2'", (ST,)).fetchone()
        self.assertEqual((hb1["times_missing"], hb1["longest_missing_scrapes"], hb1["gone_for_good"]), (1, 1, 0))
        self.assertEqual((hb1["votes_ever"], hb1["votes_gone_for_good"]), (1, 1))
        self.assertEqual(json.loads(hb1["field_last_filled"])["sponsorships"], "2026-01-06T05:00:00+00:00")
        self.assertEqual((hb2["last_idx"], hb2["gone_for_good"], hb2["session_continued"]), (4, 1, 1))

    def test_sessions_compare_raw_data_and_archive(self):
        rows = {r["session"]: r for r in self.con.execute("SELECT * FROM sessions WHERE state = ?", (ST,))}
        self.assertEqual((rows["s1"]["raw_bills"], rows["s1"]["data_repo_bills"]), (2, 1))
        self.assertEqual((rows["s2"]["raw_bills"], rows["s2"]["data_repo_bills"]), (1, 0))
        self.assertIsNone(rows["s1"]["archive_bills"])  # clone not finished: unknown, not zero
        self.assertIsNone(rows["s1"]["archive_pre_rebuild_bills"])
        got = {r[0]: tuple(r[1:]) for r in self.con.execute(
            "SELECT identifier, in_data_repo, in_archive FROM bills WHERE state = ?", (ST,))}
        self.assertEqual(got, {"HB1": (1, None), "HB2": (0, None), "SB1": (0, None)})

    def test_field_inventory(self):
        inv = {r["field"]: r for r in self.con.execute("SELECT * FROM fields WHERE state = ?", (ST,))}
        self.assertEqual(inv["custom_field"]["unusual"], 1)
        self.assertEqual(inv["extras.bdr"]["kind"], "extras")
        self.assertEqual(inv["versions.media=pdf"]["share_latest"], 1.0)
        self.assertEqual(inv["sponsorships"]["best_share"], 1.0)
        self.assertIn("sponsorships[].name", inv)

    def test_rescan_gives_same_contents(self):
        def dump():
            return {t: sorted(tuple(r) for r in self.con.execute(f"SELECT * FROM {t} WHERE state = ?", (ST,)))
                    for t in scan.TABLES if t != "runs"}
        before = dump()
        # In fresh processes with different hash seeds, so nothing depends on set order.
        for seed in ("1", "2"):
            subprocess.run([sys.executable, str(Path(scan.__file__)), "--no-report", "--db", str(self.db),
                            "--raw-root", str(self.raw_root), "--data-root", str(self.data_root),
                            "--archive-root", str(self.archive_root), ST],
                           check=True, capture_output=True, env=dict(os.environ, PYTHONHASHSEED=seed))
            self.assertEqual(dump(), before)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM runs WHERE state = ?", (ST,)).fetchone()[0], 1)

    def test_report_written(self):
        text = (Path(self.tmp.name) / "out" / ST / "report.md").read_text()
        self.assertIn("Scrapes with 0 readable bills: 1", text)
        self.assertIn("1 with conflict markers", text)
        self.assertIn("| `s2` | 2026-01-05 → 2026-01-06 | 1 (1) | 0 | — | — | not in data repo; archive unread |", text)
        self.assertIn("Bills gone for good while their session went on: 1", text)


class KeyChangeTest(unittest.TestCase):
    def test_chamber_swap_and_rekeyed_vote(self):
        """TN from 07-02: the same actions under the other chamber; a vote whose chamber changed."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw" / f"{ST}-legislation"
            raw.mkdir(parents=True)
            run_git(raw, "init", "-q")
            commit(raw, files(("bill", bill("s1", "SB1")), ("vote_event", vote("s1", "SB1", ["Ann"]))),
                   "2026-01-01T05:00:00+00:00")
            swapped = [{"date": "2026-01-01", "description": "First Reading", "organization_id": "upper"},
                       {"date": "2026-01-02", "description": "Referred", "organization_id": "upper"}]
            commit(raw, files(("bill", bill("s1", "SB1", actions=swapped)),
                              ("vote_event", vote("s1", "SB1", ["Ann"], organization="upper"))), "2026-01-02T05:00:00+00:00")
            db = root / "h.sqlite"
            scan.run_state(ST, root / "raw", root / "data", root / "archive", db, None)
            con = sqlite3.connect(str(db))
            row = con.execute("SELECT actions_chamber_swapped, actions_gone, actions_new, actions_reworded, votes_gone, "
                              "votes_rekeyed, examples FROM scrapes WHERE idx = 1").fetchone()
            self.assertEqual(row[:6], (2, 0, 0, 0, 1, 1))
            self.assertIn("lower -> upper (2)", row[6])
            self.assertIn("chamber (1)", row[6])
            b = con.execute("SELECT actions_gone_for_good, votes_gone_for_good, actions_chamber_swapped, votes_rekeyed "
                            "FROM bills").fetchone()
            self.assertEqual(b, (0, 0, 2, 1))
            con.close()


class VoteMatchTest(unittest.TestCase):
    def test_vote_naming_its_bill_another_way_and_double_copies(self):
        """USA: "SJ RES 5" for SJRES 5 attaches to the bill. AZ: a roll call listed twice in one
        scrape, once without voters, is not emptied; one that loses its voters in every copy is."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw" / f"{ST}-legislation"
            raw.mkdir(parents=True)
            run_git(raw, "init", "-q")
            full, two = vote("s1", "SJRES 5", ["Ann", "Bo"]), vote("s1", "SB2", ["Ann"], identifier="RC2")
            commit(raw, files(("bill", bill("s1", "SJRES 5")), ("bill", bill("s1", "SB2")),
                              ("vote_event", vote("s1", "SJ RES 5", ["Ann", "Bo"])), ("vote_event", two)),
                   "2026-01-01T05:00:00+00:00")
            commit(raw, files(("bill", bill("s1", "SJRES 5")), ("bill", bill("s1", "SB2")),
                              ("vote_event", vote("s1", "SJRes 5", ["Ann", "Bo"])),
                              ("vote_event", vote("s1", "SJRES 5", [])),
                              ("vote_event", vote("s1", "SB2", [], identifier="RC2"))), "2026-01-02T05:00:00+00:00")
            db = root / "h.sqlite"
            scan.run_state(ST, root / "raw", root / "data", root / "archive", db, None)
            con = sqlite3.connect(str(db))
            self.assertEqual(con.execute("SELECT votes_orphan FROM scrapes ORDER BY idx").fetchall(), [(0,), (0,)])
            self.assertEqual(con.execute("SELECT votes_emptied FROM scrapes WHERE idx = 1").fetchone(), (1,))
            self.assertEqual(con.execute("SELECT votes_ever FROM bills WHERE identifier = 'SJRES 5'").fetchone(), (1,))
            con.close()
        self.assertEqual(scan.norm_ident("HJ Res. 1"), "HJRES1")


class OrderTest(unittest.TestCase):
    def test_examples_do_not_depend_on_hash_seed(self):
        """8 bills vanish at once; the examples kept must be the same in every process."""
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw" / f"{ST}-legislation"
            raw.mkdir(parents=True)
            run_git(raw, "init", "-q")
            commit(raw, files(*[("bill", bill("s1", f"HB{n}")) for n in range(8)]), "2026-01-01T05:00:00+00:00")
            commit(raw, files(("bill", bill("s1", "SB1"))), "2026-01-02T05:00:00+00:00")
            code = ("import json, sys; sys.path.insert(0, sys.argv[1]); import scan; from pathlib import Path; "
                    "print(scan.scan_state('xx', Path(sys.argv[2]), log=lambda m: None)['scrapes'][1][-1])")
            out = {subprocess.run([sys.executable, "-c", code, str(Path(scan.__file__).parent), str(raw)],
                                  check=True, capture_output=True, text=True,
                                  env=dict(os.environ, PYTHONHASHSEED=seed)).stdout for seed in "1234"}
            self.assertEqual(len(out), 1, out)


class ReplayTest(unittest.TestCase):
    def setUp(self):
        global daily, replay
        import daily
        import replay

    def test_calendar(self):
        cal = daily.calendar()
        self.assertEqual(cal["ky"], (date(2026, 1, 6), date(2026, 4, 15)))
        self.assertIsNone(cal["tx"])  # "No Regular Session"
        self.assertTrue(daily.in_session(cal, "ky", date(2026, 2, 1)))
        self.assertFalse(daily.in_session(cal, "tx", date(2026, 2, 1)))

    def test_episodes_merge_consecutive_days(self):
        fired = {date(2026, 1, 1): "a", date(2026, 1, 2): "b", date(2026, 1, 5): "c"}
        self.assertEqual(replay.episodes(fired), [(date(2026, 1, 1), date(2026, 1, 2), 2, "a"),
                                                  (date(2026, 1, 5), date(2026, 1, 5), 1, "c")])

    def test_gap_events_and_fleet(self):
        t = lambda d: datetime(2026, 1, d, 6, tzinfo=timezone.utc)
        steady = [t(d) for d in range(1, 31)]
        quiet = [t(1), t(2), t(3), t(25)]  # silent from Jan 4 to 24: a 22-day gap
        gaps = replay.gap_events("aa", quiet)
        self.assertEqual([(g.start, g.end) for g in gaps][0], ("2026-01-04", "2026-01-25"))
        self.assertEqual(replay.gap_events("bb", steady)[:-1], [])  # only the run-up to the pause
        commits = {"aa": quiet, "bb": quiet, "cc": quiet, "dd": quiet, "ee": steady}
        fired = replay.fleet(commits)
        first = min(fired)
        self.assertEqual(first, date(2026, 1, 5))  # 2 days after the last commit
        self.assertEqual(fired[first][1], {"aa", "bb", "cc", "dd"})

    def test_unchanged(self):
        ds = []
        for n in range(10):
            d = daily.Day(date(2026, 2, 1) + timedelta(days=n))
            d.scrapes, d.bills = 1, 100
            d.new_actions = 5 if n < 3 else 0  # nothing new from Feb 4
            ds.append(d)
        th = {"unchanged_in_session_days": {"value": 5}}
        fired = replay.check_unchanged("ky", ds, [], daily.calendar(), th, None)
        self.assertEqual(min(fired), date(2026, 2, 8))  # Feb 4-8: 5 quiet days


    def test_hand_commits_are_not_scrapes(self):
        for subj in ("🕷️ Scrape data for wy - 2026-07-01 08:00:00 UTC", "🔄 Auto-save in-progress scrape (12 files)",
                     "🔄 Auto-merge: kept scraped data", "Merge branch 'main' of https://github.com/x/ma-legislation"):
            self.assertTrue(daily.is_scrape(subj), subj)
        for subj in ("chore: clear duplicate-accumulated scrape data for a clean re-scrape", "Delete _data/sd directory",
                     "fix: restore nh bill/vote data wiped by scrape.sh's fallback bug", None):
            self.assertFalse(daily.is_scrape(subj), subj)

    def test_no_scrape_waits_during_a_fleet_outage(self):
        t = lambda m, d: datetime(2026, m, d, 6, tzinfo=timezone.utc)
        commits = [t(8, d) for d in range(1, 6)] + [t(8, 14)] + [t(8, 15), t(9, 20)]
        th = {"no_scrape_in_session_days": {"value": 3}, "no_scrape_out_of_session_days": {"value": 7}}
        alone = replay.check_no_scrape("tx", [], commits, daily.calendar(), th, None)
        self.assertIn(date(2026, 8, 13), alone)  # 8 days quiet, out of session: over 7
        fleet = {date(2026, 8, 7): ("3 states", {"tx", "aa", "bb"})}
        held = replay.check_no_scrape("tx", [], commits, daily.calendar(), th, None, fleet_days=fleet)
        self.assertNotIn(date(2026, 8, 13), held)  # the fleet alarm said it
        self.assertIn(date(2026, 8, 23), held)  # the 08-15 silence did not start in a fleet alarm
        self.assertEqual(min(d for d in held if d > date(2026, 8, 15)), date(2026, 8, 22))  # 7.75 days > 7

    def test_bill_drop_needs_two_scrapes(self):
        def row(bills, gone=0):
            return {"bills": bills, "bills_gone": gone, "bills_gone_back": gone, "bills_by_session": json.dumps({"s1": bills})}
        def ds(*rows):
            out = []
            for n, r in enumerate(rows):
                d = daily.Day(date(2026, 3, 1) + timedelta(days=n))
                d.rows = [r]
                out.append(d)
            return out
        brief = ds(row(1000), row(600, 400), row(1000), row(1000))
        self.assertEqual(replay.check_bill_drop("xx", brief, [], {}, {}, None), {})
        kept = ds(row(1000), row(600, 400), row(610), row(610))
        self.assertEqual(list(replay.check_bill_drop("xx", kept, [], {}, {}, None)), [date(2026, 3, 3)])


class HelperTest(unittest.TestCase):
    def test_filled(self):
        self.assertFalse(scan.filled([{"name": " "}]))
        self.assertFalse(scan.filled({}))
        self.assertTrue(scan.filled([{"name": "A"}]))
        self.assertTrue(scan.filled(0))

    def test_conflict_markers_of_any_length(self):
        self.assertEqual(scan.bad_kind(b'<<<<<<<< HEAD:_data/tx/bill_1.json\n{}\n========\n{}\n>>>>>>>> x\n'), "conflict")
        self.assertEqual(scan.bad_kind(b'<<<<<<< HEAD\n{}\n'), "conflict")
        self.assertIsNone(scan.bad_kind(b'{"title": "<<<<<<< not at a line start"}'))

    def test_media_bucket(self):
        self.assertEqual(scan.media_bucket("text/html", ""), "html")
        self.assertEqual(scan.media_bucket("", "https://x/a.PDF?x=1"), "pdf")
        self.assertEqual(scan.media_bucket("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ""), "word")
        self.assertEqual(scan.media_bucket("application/xml", ""), "xml")
        self.assertEqual(scan.media_bucket("", ""), "none")

    def test_compare_actions_counts_real_losses(self):
        prev = (("d1", "o", "A"), ("d1", "o", "B"), ("d2", "o", "C"))
        now = (("d1", "o", "A "), ("d1", "o", "B2"))
        self.assertEqual(scan.compare_actions(prev, now)[:5], (0, 1, 1, 1, 0))  # C gone, B reworded, A whitespace
        swap = scan.compare_actions((("d1", "upper", "Filed"),), (("d1", "lower", "Filed"),))
        self.assertEqual(swap[:5], (0, 0, 0, 0, 1))

    def test_vote_count_mismatch(self):
        ok = scan.VoteVersion(vote("s", "HB1", ["A", "B"], counts=[{"option": "yes", "value": 1}, {"option": "other", "value": 1}],
                                   votes=[{"option": "yes", "voter_name": "A"}, {"option": "not voting", "voter_name": "B"}]))
        bad = scan.VoteVersion(vote("s", "HB1", ["A", "B"], counts=[{"option": "yes", "value": 5}]))
        self.assertEqual((ok.mismatch, bad.mismatch), (False, True))

    def test_numbering_gaps(self):
        gaps = report.numbering_gaps(["HB0002", "HB0003", "HB0004", "HB0005", "HB0006", "SF0001"])
        self.assertEqual(gaps, ["HB: 1 of 1–6 missing (HB0001)"])


if __name__ == "__main__":
    unittest.main()
