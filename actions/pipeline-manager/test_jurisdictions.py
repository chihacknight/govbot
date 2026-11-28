#!/usr/bin/env python3
"""
Offline tests for jurisdictions.yml and jurisdictions.py (repo reorg, step 5).

    python3 test_jurisdictions.py

Nothing touches the network: every `gh api` answer is a fake.
"""

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = load("jurisdictions")
NEW = yaml.safe_load((HERE / "jurisdictions.yml").read_text())


def gh(answers):
    calls = []

    def run(full):
        calls.append(full)
        return answers.get(full, (1, "", "gh: Not Found (HTTP 404)"))
    run.calls = calls
    return run


def found(name):
    return (0, '{"full_name": "%s"}' % name, "")


class Schema(unittest.TestCase):
    def test_the_file_matches_its_schema(self):
        import json
        from jsonschema import validate
        validate(NEW, json.loads((HERE / "jurisdictions.schema.json").read_text()))

    def test_every_state_has_its_old_repos_and_the_running_nine_are_manual(self):
        manual = sorted(c for c, e in NEW["states"].items() if e["old_repos"]["status"] == "manual")
        self.assertEqual(manual, "dc gu mi mp nj oh pa usa vi".split())
        for code, entry in NEW["states"].items():
            old = entry["old_repos"]
            if old["status"] == "history":
                self.assertEqual((old["scraper"], old["data"]),
                                 (f"govbot-history/{code}-legislation-scraper", f"govbot-history/{code}-legislation-data"))


class Tool(unittest.TestCase):
    def config(self, **tx):
        cfg = yaml.safe_load((HERE / "jurisdictions.yml").read_text())
        cfg["states"]["tx"]["sessions"] = [{"id": "90R", **tx}]
        return cfg

    def test_pair_names(self):
        self.assertEqual(tool.pair_key("tx", "90R"), "tx-90r")
        self.assertEqual(tool.pair_key("ga", "2025_26"), "ga-2025_26")
        self.assertEqual(tool.pair_key("az", "58th-1st-regular"), "az-58th-1st-regular")
        pairs, _ = tool.load_pairs(self.config())
        tx = [p for p in pairs if p["key"] == "tx-90r"][0]
        self.assertEqual((tx["scraper_full"], tx["data_full"]),
                         ("govbot-openstates-scrapers/tx-90r-scraper", "govbot-data/tx-90r"))

    def test_session_inherits_and_overrides(self):
        pairs, _ = tool.load_pairs(self.config())
        tx = [p for p in pairs if p["key"] == "tx-90r"][0]
        self.assertEqual(tx["schedule"], NEW["states"]["tx"]["scrape_cron"])
        self.assertEqual(tx["settings"]["scrapers"], "bills votes")
        pairs, _ = tool.load_pairs(self.config(schedule="manual", scrapers="bills"))
        tx = [p for p in pairs if p["key"] == "tx-90r"][0]
        self.assertEqual((tx["schedule"], tx["settings"]["scrapers"]), ("manual", "bills"))

    def test_bad_entries_are_refused(self):
        for bad in ({"id": "90 R"}, {"id": "90R", "colour": "red"}, {"id": "90R", "schedule": "daily"},
                    {"id": "90R", "runner": "laptop"}, {"id": "90R", "scrapers": "bills; rm"}):
            cfg = self.config()
            cfg["states"]["tx"]["sessions"] = [bad]
            with self.assertRaises(SystemExit, msg=bad):
                tool.load_pairs(cfg)

    def test_a_pair_can_never_be_an_old_repo(self):
        cfg = self.config()
        cfg["orgs"]["data"] = "govbot-history"
        cfg["states"]["tx"]["old_repos"]["data"] = "govbot-history/tx-90r"
        with self.assertRaises(SystemExit):
            tool.load_pairs(cfg)

    def test_rendered_pair(self):
        pairs, _ = tool.load_pairs(self.config())
        tx = [p for p in pairs if p["key"] == "tx-90r"][0]
        with tempfile.TemporaryDirectory() as tmp:
            out = tool.render_pair(tx, tmp)
            scrape = (out["govbot-openstates-scrapers/tx-90r-scraper"] / ".github/workflows/openstates-scrape.yml").read_text()
            fmt = (out["govbot-data/tx-90r"] / ".github/workflows/format.yml").read_text()
            ext = (out["govbot-data/tx-90r"] / ".github/workflows/extract-text.yml").read_text()
        for line in ("name: OpenStates Scrape for tx 90R", "session: ${{ inputs.session || '90R' }}",
                     'scrapers: "bills votes"', "repositories: tx-90r",
                     'gh api "repos/govbot-data/tx-90r/dispatches"', '- cron: "0 5 * * *"'):
            self.assertIn(line, scrape)
        self.assertIn("SCRAPER_REPO: govbot-openstates-scrapers/tx-90r-scraper", fmt)
        self.assertIn("name: Format Data for tx 90R", fmt)
        self.assertIn('workflows: ["Format Data for tx 90R"]', ext)

    def test_manual_session_has_no_schedule(self):
        pairs, _ = tool.load_pairs(self.config(schedule="manual"))
        tx = [p for p in pairs if p["key"] == "tx-90r"][0]
        with tempfile.TemporaryDirectory() as tmp:
            out = tool.render_pair(tx, tmp)
            scrape = (out["govbot-openstates-scrapers/tx-90r-scraper"] / ".github/workflows/openstates-scrape.yml").read_text()
        self.assertNotIn("schedule:", scrape)

    def test_no_delete_code(self):
        src = (HERE / "jurisdictions.py").read_text()
        for needle in ("repo delete", '"delete"', "-X DELETE", "method=\"DELETE\"", "delete_repo",
                       "archive"):
            self.assertNotIn(needle, src)

    def test_create_only_after_a_404_and_public(self):
        calls = []
        saved = tool.run, tool.push_files
        tool.run = lambda cmd, cwd=None: calls.append(cmd) or ""
        tool.push_files = lambda *a: calls.append(["push", a[0]])
        try:
            folder = Path("/nonexistent")
            redirect = gh({"govbot-data/tx-90r": found("govbot-history/tx-90r")})
            self.assertFalse(tool.create_repo("govbot-data/tx-90r", folder, set(), "d", gh_run=redirect))
            exists = gh({"govbot-data/tx-90r": found("govbot-data/tx-90r")})
            self.assertFalse(tool.create_repo("govbot-data/tx-90r", folder, set(), "d", gh_run=exists))
            self.assertEqual(calls, [], "nothing runs unless the name is a confirmed 404")
            self.assertTrue(tool.create_repo("govbot-data/tx-90r", folder, set(), "d", gh_run=gh({})))
            self.assertEqual(calls[0][:4], ["gh", "repo", "create", "govbot-data/tx-90r"])
            self.assertIn("--public", calls[0])
        finally:
            tool.run, tool.push_files = saved

    def test_never_writes_to_old_repos_or_through_a_redirect(self):
        saved = tool.push_files
        pushed = []
        tool.push_files = lambda *a: pushed.append(a[0])
        try:
            old = {"govbot-data/oh-legislation"}
            with self.assertRaises(SystemExit):
                tool.update_repo("govbot-data/oh-legislation", Path("/x"), old, gh_run=gh({}))
            with self.assertRaises(SystemExit):
                tool.create_repo("govbot-data/oh-legislation", Path("/x"), old, "d", gh_run=gh({}))
            redirect = gh({"govbot-data/tx-90r": found("govbot-history/tx-90r")})
            self.assertFalse(tool.update_repo("govbot-data/tx-90r", Path("/x"), set(), gh_run=redirect))
            self.assertEqual(pushed, [])
        finally:
            tool.push_files = saved

    def test_apply_needs_named_sessions(self):
        with self.assertRaises(SystemExit):
            tool.main(["apply"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
