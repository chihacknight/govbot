#!/usr/bin/env python3
"""
Offline tests for the redirect guard (moved.py).

Nothing here calls GitHub: every `gh api` answer is a fake. Run from this
directory:  python3 test_moved.py
"""

import importlib.util
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


moved = load("moved")


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


    def test_existing_or_unknown_is_refused(self):
        run = gh({"o/a": found("o/a"), "o/b": (1, "", "connection reset")})
        self.assertIn("already exists", moved.refuse_to_create("o/a", gh_run=run))
        self.assertIn("couldn't confirm", moved.refuse_to_create("o/b", gh_run=run))


if __name__ == "__main__":
    unittest.main(verbosity=2)
