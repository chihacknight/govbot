#!/usr/bin/env python3
"""
Offline tests for jurisdictions.yml and jurisdictions.py (repo reorg, step 5).

    python3 test_jurisdictions.py            # run the tests
    python3 test_jurisdictions.py --report   # print the field-by-field migration check

Part 1 checks that jurisdictions.yml holds every field of every state from the old configs
(chn-openstates-scrape.yml, -files.yml, -test.yml): each field is in
migrate_to_jurisdictions.FIELD_MAP, and its value reads back from the new file. Delete
part 1 with the old configs (PR B). Part 2 tests the tool; nothing touches the network.
"""

import importlib.util
import sys
import tempfile
import unittest
from collections import Counter, defaultdict
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migrate = load("migrate_to_jurisdictions")
tool = load("jurisdictions")
NEW = yaml.safe_load((HERE / "jurisdictions.yml").read_text())
OLD = {
    "scrape": yaml.safe_load((HERE / "chn-openstates-scrape.yml").read_text()),
    "files": yaml.safe_load((HERE / "chn-openstates-files.yml").read_text()),
    "test": yaml.safe_load((HERE / "chn-openstates-test.yml").read_text()),
}


def effective(st, key):
    """A state's value for `key` in the new file, falling back to the defaults."""
    return NEW["states"][st].get(key, NEW["defaults"].get(key))


def read_back(cfg, st, key, value):
    """Return (ok, where) for one old field: does the new file hold the same value?"""
    new = NEW["states"].get(st)
    if new is None:
        return False, "state missing"
    old_status = "manual" if not OLD["scrape"]["locales"][st].get("moved_to") else "history"
    if key == "name":
        return new["name"] == value, "name"
    if key == "toolkit_branch" and cfg != "test":
        return effective(st, "toolkit_branch") == value, "toolkit_branch"
    if key == "scrape_timeout_minutes":
        return effective(st, key) == int(value), key
    if key == "scrape_cron":
        return new["scrape_cron"] == value, key
    if key == "runner":
        want = "self-hosted" if str(OLD["scrape"]["locales"][st].get("force_self_hosted")).lower() == "true" else "proxy"
        return effective(st, "runner") == want, f"runner: {want}"
    if key == "force_self_hosted":
        return (effective(st, "runner") == "self-hosted") == (str(value).lower() == "true"), "runner: self-hosted"
    if key == "docker_image":
        return effective(st, key) == value, key
    if key == "labels":
        field = "scraper_labels" if cfg == "scrape" else "labels"
        return new.get(field) == value, field
    if key == "template" and cfg in ("scrape", "files"):
        running = not value.endswith("-paused")
        return (new["old_repos"]["status"] == "manual") == running == (old_status == "manual"), \
            f"old_repos.status: {new['old_repos']['status']}"
    if key == "moved_to":
        kind = "scraper" if cfg == "scrape" else "data"
        return new["old_repos"][kind] == value and new["old_repos"]["status"] == "history", f"old_repos.{kind}"
    if cfg == "test" and key in ("template", "toolkit_branch"):
        return NEW["test_fleet"][key] == value and st in NEW["test_fleet"]["states"], f"test_fleet.{key}"
    return False, "not mapped"


def field_report():
    """{(config, field): Counter(where)} plus failures."""
    seen, failures = defaultdict(Counter), []
    for cfg, doc in OLD.items():
        for st, fields in doc["locales"].items():
            for key, value in fields.items():
                if (cfg, key) not in migrate.FIELD_MAP:
                    failures.append(f"{cfg}.{st}.{key}: field not in FIELD_MAP")
                    continue
                ok, where = read_back(cfg, st, key, value)
                seen[(cfg, key)][where] += 1
                if not ok:
                    failures.append(f"{cfg}.{st}.{key}={value!r}: not found in jurisdictions.yml ({where})")
    return seen, failures


class Migration(unittest.TestCase):
    def test_same_states_everywhere(self):
        for cfg, doc in OLD.items():
            self.assertEqual(sorted(doc["locales"]), sorted(NEW["states"]), cfg)

    def test_every_field_of_every_state_is_kept(self):
        _, failures = field_report()
        self.assertEqual(failures, [])

    def test_org_and_fixed_settings(self):
        self.assertEqual(NEW["orgs"], {"scraper": OLD["scrape"]["org"]["username"],
                                       "data": OLD["files"]["org"]["username"]})
        self.assertEqual(NEW["test_fleet"]["org"], OLD["test"]["org"]["username"])
        for doc in OLD.values():  # the tool uses these markers and the same folder naming
            self.assertEqual(doc["template_markers"], {"open": tool.MARKER_OPEN, "close": tool.MARKER_CLOSE})
            for t in doc["templates"].values():
                self.assertEqual(t["folder-name"], "✏️{ locale.key }✏️-legislation")

    def test_manual_old_repos_are_todays_repos(self):
        for st, entry in NEW["states"].items():
            if entry["old_repos"]["status"] == "manual":
                self.assertEqual(entry["old_repos"]["scraper"], f"govbot-openstates-scrapers/{st}-legislation")
                self.assertEqual(entry["old_repos"]["data"], f"govbot-data/{st}-legislation")
        manual = sorted(s for s, e in NEW["states"].items() if e["old_repos"]["status"] == "manual")
        self.assertEqual(manual, "dc gu mi mp nj oh pa usa vi".split())

    def test_nothing_added_except_the_known_additions(self):
        # The reverse check: every setting in the new file comes from an old field, or is one
        # of the three stated additions (scrapers from step 4b, repo secrets read from GitHub,
        # the first session pair).
        additions = {"scrapers", "repo_secrets", "sessions"}
        from_old = {"name", "scrape_cron", "labels", "old_repos", "toolkit_branch",
                    "scrape_timeout_minutes", "runner", "docker_image", "scraper_labels"}
        for st, entry in NEW["states"].items():
            self.assertEqual(set(entry) - additions - from_old, set(), st)
            s = OLD["scrape"]["locales"][st]
            if "runner" in entry:
                self.assertEqual(s.get("runner"), "self-hosted", st)
            if "scrape_timeout_minutes" in entry:
                self.assertNotEqual(int(s["scrape_timeout_minutes"]), 720, st)
            if "docker_image" in entry:
                self.assertEqual(s.get("docker_image"), entry["docker_image"], st)
            if "scraper_labels" in entry:
                self.assertEqual(s.get("labels"), entry["scraper_labels"], st)
        self.assertEqual({s for s, e in NEW["states"].items() if "scrapers" in e},
                         set("ct ia ks ma md nm or pr tx va".split()))
        self.assertEqual({s for s, e in NEW["states"].items() if e["sessions"]}, {"tx"})

    def test_file_is_what_the_old_configs_generate(self):
        self.assertEqual((HERE / "jurisdictions.yml").read_text(), migrate.render_text(migrate.build()))


def gh(answers):
    calls = []

    def run(full):
        calls.append(full)
        return answers.get(full, (1, "", "gh: Not Found (HTTP 404)"))
    run.calls = calls
    return run


def found(name):
    return (0, '{"full_name": "%s"}' % name, "")


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
    if "--report" in sys.argv:
        seen, failures = field_report()
        print(f"{'old config.field':38} {'states':>6}  lands in jurisdictions.yml")
        for (cfg, key), where in sorted(seen.items()):
            print(f"{cfg + '.' + key:38} {sum(where.values()):>6}  " +
                  "; ".join(f"{w} ({n})" for w, n in where.most_common()))
        print(f"\nfailures: {len(failures)}")
        for f in failures:
            print("  " + f)
        sys.exit(1 if failures else 0)
    unittest.main(verbosity=2)
