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

    def test_seed_copies_one_session_with_provenance_and_never_twice(self):
        import subprocess
        def git(*a, cwd=None):
            subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            # the old (history) data repo: two sessions, one bill each, with a log
            work = base / "work-src"
            for sid in ("104th", "103rd"):
                bill = work / f"country:us/state:il/sessions/{sid}/bills/HB1"
                bill.mkdir(parents=True)
                (bill / "metadata.json").write_text('{"identifier": "HB1"}')
                (bill / "action_logs.jsonl").write_text('{"id": "a1", "first_seen": "2025-01-09"}\n')
            git("init", "-q", "-b", "main", cwd=work); git("add", "-A", cwd=work)
            git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "history", cwd=work)
            for name, src in (("govbot-history/il-legislation-data", work), ("govbot-data/il-104th", None)):
                bare = base / f"{name}.git"; bare.parent.mkdir(parents=True, exist_ok=True)
                if src:
                    git("clone", "-q", "--bare", str(src), str(bare))
                else:
                    git("init", "-q", "--bare", "-b", "main", str(bare))
                    seed_work = base / "work-dst"; seed_work.mkdir()
                    (seed_work / "README.md").write_text("pair")
                    git("init", "-q", "-b", "main", cwd=seed_work); git("add", "-A", cwd=seed_work)
                    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init", cwd=seed_work)
                    git("push", "-q", str(bare), "main", cwd=seed_work)
                git("config", "uploadpack.allowFilter", "true", cwd=bare)
            pair = {"data_full": "govbot-data/il-104th", "seed_from": "govbot-history/il-legislation-data",
                    "state": "il", "session": "104th", "key": "il-104th"}
            saved = tool.GITHUB
            tool.GITHUB = "file://" + str(base)
            try:
                self.assertTrue(tool.seed_data_repo(pair, {"govbot-history/il-legislation-data"}, now="2026-11-28"))
                self.assertFalse(tool.seed_data_repo(pair, set(), now="2026-11-28"), "never seeds twice")
                with self.assertRaises(SystemExit):  # never into an old repo
                    tool.seed_data_repo({**pair, "data_full": "govbot-history/il-legislation-data"},
                                        {"govbot-history/il-legislation-data"})
            finally:
                tool.GITHUB = saved
            out = base / "check"
            git("clone", "-q", str(base / "govbot-data/il-104th.git"), str(out))
            self.assertTrue((out / "country:us/state:il/sessions/104th/bills/HB1/action_logs.jsonl").is_file())
            self.assertFalse((out / "country:us/state:il/sessions/103rd").exists(), "only the one session")
            seed_md = (out / "SEED.md").read_text()
            self.assertIn("govbot-history/il-legislation-data", seed_md)
            self.assertIn("1 bills", seed_md)

    def test_seed_flag_is_read_from_the_file(self):
        pairs, _ = tool.load_pairs(NEW)
        seeded = sorted(p["key"] for p in pairs if p["seed_from"])
        # NC 2025E1 isn't in the old NC repo (it never held that session): starts empty
        self.assertEqual(seeded, ["il-104th", "ma-194th", "nc-2025"])
        self.assertTrue(all(p["seed_from"].startswith("govbot-history/") for p in pairs if p["seed_from"]))

    def test_apply_needs_named_sessions(self):
        with self.assertRaises(SystemExit):
            tool.main(["apply"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
