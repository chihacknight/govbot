#!/usr/bin/env python3
"""Offline tests for the nightly bill update: every bill processed every night,
new actions decided against the log, and the three guards (utils/bill_guards.py).

    cd actions/format && python3 test_bill_nightly.py

Each test runs whole nights through load_json_files + process_and_save, the
path main.py takes.
"""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from utils import bill_guards as G
from utils.io_utils import load_json_files
from utils.process_utils import process_and_save
from utils.timestamp_tracker import read_latest_timestamps

UPPER = '~{"classification": "upper"}'
LOWER = '~{"classification": "lower"}'
NIGHTS = [f"2026-12-0{n}T10:00:00+00:00" for n in range(1, 10)]


def action(desc, date="2026-01-14", org=UPPER, cls=None):
    return {"description": desc, "date": date, "organization_id": org, "classification": cls or []}


def bill(identifier="HB69", actions=None, **fields):
    data = {
        "legislative_session": "2026",
        "identifier": identifier,
        "title": f"A bill {identifier}",
        "actions": actions if actions is not None else [action("Introduced", cls=["introduction"])],
        "sponsorships": [{"name": "Rep. A", "primary": True}],
        "versions": [{"note": "Introduced", "links": [{"url": f"https://x/{identifier}/1.pdf"}]}],
        "sources": [{"url": f"https://x/{identifier}"}],
    }
    data.update(fields)
    return data


class Nights(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.repo = self.root / "repo"
        self.errors = self.repo / ".windycivi" / "errors"
        self.errors.mkdir(parents=True)
        self.night_no = 0

    def tearDown(self):
        self._tmp.cleanup()

    def night(self, *bills):
        """One night's scrape: write the bill files, run the formatter on them."""
        first_seen = NIGHTS[self.night_no]
        self.night_no += 1
        scrape = self.root / f"scrape{self.night_no}"
        scrape.mkdir()
        for n, b in enumerate(bills):
            (scrape / f"bill_{n}.json").write_text(json.dumps(b))
        with contextlib.redirect_stdout(io.StringIO()) as out:
            ts = read_latest_timestamps(self.repo)
            files = load_json_files(scrape, self.errors / "event_archive", self.errors, ts)
            process_and_save(
                "ga", files, self.errors, {"2026": {"name": "2026", "date_folder": "2026-2026"}},
                self.repo / ".windycivi" / "new_sessions_added.txt", self.repo, ts, self.repo,
                first_seen=first_seen,
            )
        return out.getvalue()

    def bill_dir(self, identifier="HB69"):
        return self.repo / "country:us" / "state:ga" / "sessions" / "2026" / "bills" / identifier

    def meta(self, identifier="HB69"):
        return json.loads((self.bill_dir(identifier) / "metadata.json").read_text())

    def log(self, identifier="HB69"):
        path = self.bill_dir(identifier) / "action_logs.jsonl"
        return [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []

    def snapshot(self):
        """Every file in the repo -> its bytes."""
        return {str(p.relative_to(self.repo)): p.read_bytes() for p in sorted(self.repo.rglob("*")) if p.is_file()}


class EveryBillEveryNight(Nights):
    def test_new_cosponsor_with_the_same_action_count_updates_metadata(self):
        # GA HB69: a cosponsor added, no new action. The old count skip never saw it.
        self.night(bill())
        sponsors = [{"name": "Rep. A", "primary": True}, {"name": "Rep. B", "primary": False}]
        self.night(bill(sponsorships=sponsors))
        self.assertEqual(self.meta()["sponsorships"], sponsors)
        self.assertEqual(len(self.log()), 1)

    def test_new_version_and_title_fix_update_metadata(self):
        # GA SR3 (a new version) and HR13 (a title fix).
        self.night(bill())
        versions = bill()["versions"] + [{"note": "Substitute", "links": [{"url": "https://x/HB69/2.pdf"}]}]
        self.night(bill(versions=versions, title="A bill, corrected"))
        self.assertEqual(self.meta()["versions"], versions)
        self.assertEqual(self.meta()["title"], "A bill, corrected")

    def test_other_chambers_identical_action_on_a_later_night_is_logged(self):
        # The old description + date pre-filter ignored chamber.
        read = action("Read first time", date="2026-02-01", org=UPPER)
        self.night(bill(actions=[read]))
        twin = action("Read first time", date="2026-02-01", org=LOWER)
        self.night(bill(actions=[read, twin]))
        self.assertEqual([l["chamber"] for l in self.log()], ["upper", "lower"])
        self.assertEqual([a["organization_id"] for a in self.meta()["actions"]], [UPPER, LOWER])

    def test_rewording_on_a_night_with_the_same_count_is_a_correction(self):
        # MT 2026-08-10: "(H) First Reading" -> "(H) 1st Reading", count unchanged.
        self.night(bill(actions=[action("(H) First Reading")]))
        self.night(bill(actions=[action("(H) 1st Reading")]))
        log = self.log()
        self.assertEqual(len(log), 2)
        self.assertEqual(log[0]["id"], log[1]["id"])
        self.assertEqual(log[1]["action"]["description"], "(H) 1st Reading")
        self.assertEqual(log[1]["first_seen"], NIGHTS[1])
        self.assertEqual(self.meta()["actions"][0]["description"], "(H) 1st Reading")

    def test_rewording_already_in_the_log_keeps_its_stamp(self):
        # WY HB0144: the backfill logged the rewording; metadata.json still had the
        # old wording. Tonight it takes the new wording and keeps the old stamp.
        self.night(bill(actions=[action("H COW:H Motion to move Bill up")]))
        stamp = self.meta()["actions"][0]["_processing"]
        self.night(bill(actions=[action("H Motion to move Bill up in General File")]))
        meta_path = self.bill_dir() / "metadata.json"
        meta = self.meta()
        meta["actions"] = [dict(meta["actions"][0], description="H COW:H Motion to move Bill up")]
        meta_path.write_text(json.dumps(meta, indent=2))  # as if the old skip had hidden the night
        self.night(bill(actions=[action("H Motion to move Bill up in General File")]))
        self.assertEqual(len(self.log()), 2)
        self.assertEqual(self.meta()["actions"][0]["description"], "H Motion to move Bill up in General File")
        self.assertEqual(self.meta()["actions"][0]["_processing"], stamp)

    def test_new_action_is_stamped_and_bumps_logs_latest_update(self):
        self.night(bill())
        first = self.meta()
        self.night(bill(actions=bill()["actions"] + [action("Referred", date="2026-01-20")]))
        meta = self.meta()
        self.assertEqual(meta["actions"][0]["_processing"], first["actions"][0]["_processing"])
        self.assertIn("log_file_created", meta["actions"][1]["_processing"])
        self.assertIn("logs_latest_update", meta["_processing"])
        self.assertEqual(len(self.log()), 2)

    def test_an_unchanged_night_writes_nothing(self):
        self.night(bill(), bill("HB70"))
        before = self.snapshot()
        mtime = (self.bill_dir() / "metadata.json").stat().st_mtime_ns
        self.night(bill(), bill("HB70"))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual((self.bill_dir() / "metadata.json").stat().st_mtime_ns, mtime)


class KeepNonEmpty(Nights):
    """Guard (a)."""

    def test_empty_field_keeps_last_nights_value_and_is_recorded(self):
        self.night(bill())
        self.night(bill(sponsorships=[]))  # KY 2026-09-29: no sponsors
        self.assertEqual(self.meta()["sponsorships"], [{"name": "Rep. A", "primary": True}])
        kept = json.loads((self.errors / G.KEPT_FILE).read_text())
        self.assertEqual(kept, {"2026/HB69": {"sponsorships": {"first_kept": NIGHTS[1]}}})

        # Still missing: the file doesn't change (a quiet night's diff stays empty),
        # the printed warning says it's ongoing.
        before = (self.errors / G.KEPT_FILE).read_bytes()
        out = self.night(bill(sponsorships=[]))
        self.assertEqual((self.errors / G.KEPT_FILE).read_bytes(), before)
        self.assertIn("Kept last night's sponsorships on 1 bills", out)

        back = [{"name": "Rep. C", "primary": True}]
        self.night(bill(sponsorships=back))
        self.assertEqual(self.meta()["sponsorships"], back)
        self.assertFalse((self.errors / G.KEPT_FILE).exists())

    def test_missing_field_and_empty_title_are_kept_too(self):
        self.night(bill())
        tonight = bill(title="  ")
        del tonight["versions"]
        self.night(tonight)
        self.assertEqual(self.meta()["title"], "A bill HB69")
        self.assertEqual(self.meta()["versions"], bill()["versions"])

    def test_a_field_that_was_empty_stays_empty(self):
        self.night(bill(documents=[]))
        self.night(bill(documents=[]))
        self.assertEqual(self.meta()["documents"], [])
        self.assertFalse((self.errors / G.KEPT_FILE).exists())

    def test_rewording_after_kept_actions_compares_with_the_kept_list(self):
        self.night(bill(actions=[action("(H) First Reading")]))
        self.night(bill(actions=[]))  # actions kept
        self.assertEqual(len(self.meta()["actions"]), 1)
        self.night(bill(actions=[action("(H) 1st Reading")]))
        log = self.log()
        self.assertEqual(len(log), 2)
        self.assertEqual(log[0]["id"], log[1]["id"])  # a correction, not a new action


class WhitespaceIsTheSameAction(Nights):
    """Guard (b)."""

    def test_line_break_in_a_description_is_not_a_new_action(self):
        self.night(bill(actions=[action("Referred to Committee on Health")]))
        stamp = self.meta()["actions"][0]["_processing"]["log_file_created"]
        self.night(bill(actions=[action("Referred to\nCommittee on  Health")]))
        self.assertEqual(len(self.log()), 1)
        self.assertEqual(len(self.meta()["actions"]), 1)
        self.assertEqual(self.meta()["actions"][0]["_processing"]["log_file_created"], stamp)


class Regression(Nights):
    """Guard (c)."""

    def bills(self, n, empty=0):
        return [bill(f"HB{i}", sponsorships=[] if i < empty else bill()["sponsorships"]) for i in range(n)]

    def test_most_bills_losing_a_field_fires(self):
        self.night(*self.bills(25))
        out = self.night(*self.bills(25, empty=13))  # 52%
        self.assertIn("::warning::", out)
        report = json.loads((self.errors / G.REGRESSION_FILE).read_text())
        self.assertEqual(report, [{"state": "ga", "night": NIGHTS[1], "field": "sponsorships",
                                   "bills_lost": 13, "bills_had": 25}])
        # The run went on and guard (a) kept the sponsors.
        self.assertEqual(self.meta("HB0")["sponsorships"], bill()["sponsorships"])

        # Still broken the next night: last night's kept values count as "had".
        self.night(*self.bills(25, empty=13))
        self.assertEqual(json.loads((self.errors / G.REGRESSION_FILE).read_text())[0]["night"], NIGHTS[2])

        # Fixed: the report goes away.
        self.night(*self.bills(25))
        self.assertFalse((self.errors / G.REGRESSION_FILE).exists())

    def test_half_or_fewer_does_not_fire(self):
        self.night(*self.bills(24))
        out = self.night(*self.bills(24, empty=12))  # exactly 50%
        self.assertNotIn("::warning::", out)
        self.assertFalse((self.errors / G.REGRESSION_FILE).exists())

    def test_too_few_bills_does_not_fire(self):
        self.night(*self.bills(19))
        out = self.night(*self.bills(19, empty=19))
        self.assertNotIn("::warning::", out)
        self.assertFalse((self.errors / G.REGRESSION_FILE).exists())


if __name__ == "__main__":
    unittest.main()
