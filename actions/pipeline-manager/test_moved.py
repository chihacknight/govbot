#!/usr/bin/env python3
"""
Offline tests for the `moved_to` marker and the redirect guard (moved.py).

Nothing here calls GitHub: every `gh api` answer is a fake. Run from this
directory:  python3 test_moved.py   (needs pyyaml, like close_session.py)
"""

import importlib.util
import os
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


moved = load("moved")
apply_mod = load("apply")
close_session = load("close_session")
rebuild = load("rebuild_data_repos")


def gh(answers):
    """A fake `gh api repos/<x>`: {full_repo: (code, stdout, stderr)}; else 404."""
    calls = []

    def run(full_repo):
        calls.append(full_repo)
        return answers.get(full_repo, (1, "", "gh: Not Found (HTTP 404)"))

    run.calls = calls
    return run


def found(full_name):
    return (0, '{"full_name": "%s", "archived": false}' % full_name, "")


class RepoStatus(unittest.TestCase):
    def test_missing(self):
        self.assertEqual(moved.repo_status("o/r", gh({})), ("missing", ""))

    def test_exists_ignores_case(self):
        run = gh({"govbot-data/wy-legislation": found("govbot-data/WY-legislation")})
        self.assertEqual(moved.repo_status("govbot-data/wy-legislation", run)[0], "exists")

    def test_redirect(self):
        # `gh api` follows the redirect; the answer names the new place.
        run = gh({"govbot-data/wy-legislation": found("govbot-history/wy-legislation-data")})
        self.assertEqual(
            moved.repo_status("govbot-data/wy-legislation", run),
            ("redirects", "govbot-history/wy-legislation-data"),
        )

    def test_other_errors_are_unknown_not_missing(self):
        run = gh({"o/r": (1, "", "gh: Bad credentials (HTTP 401)")})
        self.assertEqual(moved.repo_status("o/r", run)[0], "unknown")
        run = gh({"o/r": (0, "not json", "")})
        self.assertEqual(moved.repo_status("o/r", run)[0], "unknown")


class RefuseToCreate(unittest.TestCase):
    NEW = "govbot-history/wy-legislation-data"

    def test_free_name_is_allowed(self):
        self.assertIsNone(moved.refuse_to_create("govbot-data/wy-legislation", gh_run=gh({})))

    def test_redirecting_name_is_refused(self):
        run = gh({"govbot-data/wy-legislation": found(self.NEW)})
        reason = moved.refuse_to_create("govbot-data/wy-legislation", gh_run=run)
        self.assertIn("redirects to " + self.NEW, reason)
        self.assertIn("moved_to: " + self.NEW, reason)

    def test_allow_redirect_to_only_that_repo(self):
        run = gh({"govbot-data/ca-legislation": found("govbot-archive/ca-legislation-2025")})
        self.assertIsNone(moved.refuse_to_create(
            "govbot-data/ca-legislation", "govbot-archive/ca-legislation-2025", run))
        self.assertIsNotNone(moved.refuse_to_create(
            "govbot-data/ca-legislation", "govbot-history/ca-legislation-data", run))

    def test_existing_or_unknown_is_refused(self):
        run = gh({"o/a": found("o/a"), "o/b": (1, "", "connection reset")})
        self.assertIn("already exists", moved.refuse_to_create("o/a", gh_run=run))
        self.assertIn("couldn't confirm", moved.refuse_to_create("o/b", gh_run=run))


class Patched(unittest.TestCase):
    """Swap in a fake `gh api` and record every shell command apply.py runs."""

    def setUp(self):
        self.shell = []
        self._saved = [
            (moved, "_gh_repo", moved._gh_repo),
            (apply_mod.moved_mod, "_gh_repo", apply_mod.moved_mod._gh_repo),
            (apply_mod, "run_shell", apply_mod.run_shell),
        ]
        apply_mod.run_shell = lambda cmd, **kw: self.shell.append(cmd) or ""

    def tearDown(self):
        for obj, name, value in self._saved:
            setattr(obj, name, value)

    def fake_gh(self, module, answers):
        module._gh_repo = gh(answers)
        return module._gh_repo


class CreateRepo(Patched):
    def test_refuses_a_redirecting_name_even_for_real(self):
        self.fake_gh(apply_mod.moved_mod, {
            "govbot-data/wy-legislation": found("govbot-history/wy-legislation-data")})
        ok = apply_mod.create_repo(
            "govbot-data", "wy-legislation", "wy", Path("/nonexistent"), dry_run=False)
        self.assertFalse(ok)
        self.assertEqual(self.shell, [], "nothing may run once the name is refused")

    def test_dry_run_still_checks_the_name(self):
        run = self.fake_gh(apply_mod.moved_mod, {
            "govbot-data/wy-legislation": found("govbot-history/wy-legislation-data")})
        self.assertFalse(apply_mod.create_repo(
            "govbot-data", "wy-legislation", "wy", Path("/nonexistent"), dry_run=True))
        self.assertEqual(run.calls, ["govbot-data/wy-legislation"])

    def test_free_name_dry_run_goes_ahead(self):
        self.fake_gh(apply_mod.moved_mod, {})
        self.assertTrue(apply_mod.create_repo(
            "govbot-data", "zz-legislation", "zz", Path("/nonexistent"), dry_run=True))
        self.assertEqual(self.shell, [])


class ExpectedRepos(unittest.TestCase):
    """get_expected_repos runs render.py, so build a throwaway copy of the folder."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copy(HERE / "render.py", self.tmp / "render.py")
        os.symlink(HERE / "templates", self.tmp / "templates")
        self.config = self.tmp / "fleet.yml"
        self.config.write_text(textwrap.dedent("""\
            template_markers:
              open: ✏️{
              close: '}✏️'
            org:
              username: govbot-data
            templates:
              openstates-to-ocd-files-paused:
                folder-name: ✏️{ locale.key }✏️-legislation
                fully_override_dirs:
                - .github
            locales:
              ut:
                template: openstates-to-ocd-files-paused
                name: Utah
              wy:
                template: openstates-to-ocd-files-paused
                name: Wyoming
                moved_to: govbot-history/wy-legislation-data
            """))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_moved_locale_is_neither_created_nor_updated(self):
        expected, org = apply_mod.get_expected_repos(
            self.config, self.tmp / "generated", test_states="ut,wy")
        self.assertEqual(org, "govbot-data")
        self.assertEqual(sorted(expected), ["ut-legislation"])

    def test_moved_name_is_still_never_a_deletion_candidate(self):
        # Kept in the full-config name set, so a stray repo under the old
        # name could never look "not in config" and be deleted.
        names = apply_mod.get_all_expected_repo_names(self.config)
        self.assertEqual(names, {"ut-legislation", "wy-legislation"})


def write_config(path, wy_extra):
    path.write_text(textwrap.dedent("""\
        org:
          username: govbot-data
        templates:
          openstates-to-ocd-files-paused:
            folder-name: ✏️{ locale.key }✏️-legislation
        locales:
          wy:
            template: openstates-to-ocd-files-paused
            name: Wyoming
            session: "2025"
        """) + wy_extra)


class SessionTools(unittest.TestCase):
    """close_session.py / rebuild_data_repos.py must never act on a moved repo."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.config = self.tmp / "chn-openstates-files.yml"
        self.lookups = []
        self.saved = [
            (close_session, "get_repo_info", close_session.get_repo_info),
            (close_session, "transfer_repo", close_session.transfer_repo),
            (rebuild.close_session_mod, "get_repo_info", rebuild.close_session_mod.get_repo_info),
            (rebuild.close_session_mod, "rename_repo", rebuild.close_session_mod.rename_repo),
        ]
        for module in (close_session, rebuild.close_session_mod):
            module.transfer_repo = module.rename_repo = self.fail_if_called

    def tearDown(self):
        for obj, name, value in self.saved:
            setattr(obj, name, value)
        shutil.rmtree(self.tmp)

    def fail_if_called(self, *args, **kwargs):
        raise AssertionError(f"must not move anything: {args}")

    def answer(self, mapping):
        def get_repo_info(full_repo):
            self.lookups.append(full_repo)
            return mapping.get(full_repo)
        close_session.get_repo_info = get_repo_info
        rebuild.close_session_mod.get_repo_info = get_repo_info

    def test_close_session_refuses_moved_locale_before_any_lookup(self):
        write_config(self.config, "    moved_to: govbot-history/wy-legislation-data\n")
        self.answer({})
        with self.assertRaises(SystemExit) as ctx:
            close_session.close_session(self.config, "wy", "govbot-archive", None, dry_run=True)
        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(self.lookups, [])

    def test_close_session_refuses_a_redirect_without_the_marker(self):
        write_config(self.config, "")
        self.answer({"govbot-data/wy-legislation": {
            "full_name": "govbot-history/wy-legislation-data", "archived": False}})
        with self.assertRaises(SystemExit) as ctx:
            close_session.close_session(self.config, "wy", "govbot-archive", None, dry_run=True)
        self.assertEqual(ctx.exception.code, 1)

    def test_rebuild_refuses_moved_locale_before_any_lookup(self):
        write_config(self.config, "    moved_to: govbot-history/wy-legislation-data\n")
        self.answer({})
        self.assertFalse(rebuild.rebuild_locale(
            self.config, "wy", "pre-rebuild-x", "govbot-archive", True, dry_run=True))
        self.assertEqual(self.lookups, [])

    def test_rebuild_refuses_a_redirect_without_the_marker(self):
        write_config(self.config, "")
        self.answer({"govbot-data/wy-legislation": {
            "full_name": "govbot-history/wy-legislation-data", "archived": False}})
        self.assertFalse(rebuild.rebuild_locale(
            self.config, "wy", "pre-rebuild-x", "govbot-archive", True, dry_run=True))


class RealConfigs(unittest.TestCase):
    def test_every_moved_to_is_owner_slash_name(self):
        import yaml
        for name in ("chn-openstates-scrape.yml", "chn-openstates-files.yml",
                     "chn-openstates-test.yml"):
            config = yaml.safe_load((HERE / name).read_text())
            for code, cfg in (config.get("locales") or {}).items():
                target = moved.moved_to(cfg)
                if target:
                    self.assertRegex(target, r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$", f"{name}: {code}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
