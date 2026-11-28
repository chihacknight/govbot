#!/usr/bin/env python3
"""
One-off: build jurisdictions.yml from today's three pipeline-manager configs (repo reorg, step 5).

    python3 migrate_to_jurisdictions.py            # writes jurisdictions.yml
    python3 migrate_to_jurisdictions.py --check    # exits 1 if jurisdictions.yml differs

Where every old field goes is listed in FIELD_MAP below and checked field by field by
test_jurisdictions.py. Delete this script, FIELD_MAP and that test together with the old
configs (PR B).
"""

import argparse
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SCRAPE = HERE / "chn-openstates-scrape.yml"
FILES = HERE / "chn-openstates-files.yml"
TEST = HERE / "chn-openstates-test.yml"
OUT = HERE / "jurisdictions.yml"

DEFAULTS = {
    "toolkit_branch": "main",
    "runner": "github",
    "scrape_timeout_minutes": 720,
    "docker_image": "openstates/scrapers:latest",
    "scrapers": "bills",
}

# Where each old (config, field) lands. test_jurisdictions.py checks every field of every
# state against this, so a field missing here fails the test.
FIELD_MAP = {
    ("scrape", "name"): "name",
    ("files", "name"): "name (same value in both configs)",
    ("scrape", "toolkit_branch"): "defaults.toolkit_branch, or the state's toolkit_branch if different",
    ("files", "toolkit_branch"): "defaults.toolkit_branch, or the state's toolkit_branch if different",
    ("scrape", "scrape_timeout_minutes"): "defaults.scrape_timeout_minutes, or the state's if different",
    ("scrape", "scrape_cron"): "scrape_cron (the state's daily time; sessions use it unless they set schedule)",
    ("scrape", "runner"): "runner: proxy (self-hosted label = GitHub-hosted + tinyproxy) or self-hosted (with force_self_hosted)",
    ("scrape", "force_self_hosted"): "runner: self-hosted",
    ("scrape", "docker_image"): "docker_image",
    ("scrape", "labels"): "scraper_labels",
    ("files", "labels"): "labels",
    ("scrape", "template"): "old_repos.status: openstates-scrape = manual (running), -paused = history",
    ("files", "template"): "old_repos.status (same split as the scrape config)",
    ("scrape", "moved_to"): "old_repos.scraper",
    ("files", "moved_to"): "old_repos.data",
    ("test", "template"): "test_fleet.template",
    ("test", "toolkit_branch"): "test_fleet.toolkit_branch",
    ("test", "name"): "name (same value)",
}

# Repo-level secrets found on GitHub on 2026-11-27 (`gh api repos/<repo>/actions/secrets`).
# A new pair's repos need them set again: repo secrets don't carry over.
REPO_SECRETS = {
    "dc": ["DC_API_KEY"],
    "in": ["INDIANA_API_KEY", "USER_AGENT"],
    "ny": ["NEW_YORK_API_KEY"],
    "va": ["VIRGINIA_API_KEY"],
    "wv": ["PROXY_URL"],
}

# Step 4b: states whose roll calls come from a separate `votes` scraper
# (openstates-scrapers 4efc135). VA keeps its current csv_bills until a test run of
# csv_bills vs bills decides.
SCRAPERS = {s: "bills votes" for s in "ct ia ks ma md nm or pr tx".split()}
SCRAPERS["va"] = "csv_bills"

# The first session pair (step 5 dry run); step 6 adds the other 2027 sessions.
SESSIONS = {"tx": [{"id": "90R"}]}


def runner_of(scrape):
    if str(scrape.get("force_self_hosted", "")).lower() == "true":
        return "self-hosted"
    if scrape.get("runner") == "self-hosted":
        return "proxy"
    return "github"


def build():
    scrape = yaml.safe_load(SCRAPE.read_text())
    files = yaml.safe_load(FILES.read_text())
    test = yaml.safe_load(TEST.read_text())
    states = {}
    for st in sorted(files["locales"]):
        s, f = scrape["locales"][st], files["locales"][st]
        moved = bool(s.get("moved_to"))
        entry = {"name": f["name"]}
        branch = s.get("toolkit_branch", "main")
        if branch != DEFAULTS["toolkit_branch"]:
            entry["toolkit_branch"] = branch
        entry["scrape_cron"] = s["scrape_cron"]
        timeout = int(s.get("scrape_timeout_minutes", 720))
        if timeout != DEFAULTS["scrape_timeout_minutes"]:
            entry["scrape_timeout_minutes"] = timeout
        if runner_of(s) != DEFAULTS["runner"]:
            entry["runner"] = runner_of(s)
        if s.get("docker_image") and s["docker_image"] != DEFAULTS["docker_image"]:
            entry["docker_image"] = s["docker_image"]
        if st in SCRAPERS:
            entry["scrapers"] = SCRAPERS[st]
        if st in REPO_SECRETS:
            entry["repo_secrets"] = REPO_SECRETS[st]
        entry["labels"] = list(f.get("labels") or [])
        if s.get("labels"):
            entry["scraper_labels"] = list(s["labels"])
        entry["sessions"] = SESSIONS.get(st, [])
        if moved:
            entry["old_repos"] = {"status": "history", "scraper": s["moved_to"], "data": f["moved_to"]}
        else:
            entry["old_repos"] = {
                "status": "manual",
                "scraper": f"{scrape['org']['username']}/{st}-legislation",
                "data": f"{files['org']['username']}/{st}-legislation",
            }
        states[st] = entry
    return {
        "orgs": {"scraper": scrape["org"]["username"], "data": files["org"]["username"]},
        "defaults": dict(DEFAULTS),
        "states": states,
        "test_fleet": {
            "org": test["org"]["username"],
            "template": sorted({v["template"] for v in test["locales"].values()})[0],
            "toolkit_branch": sorted({v["toolkit_branch"] for v in test["locales"].values()})[0],
            "states": sorted(test["locales"]),
        },
    }


HEADER = """\
# The single source of truth for every jurisdiction's repos (repo reorg, step 5).
# Read and written by `jurisdictions.py`, which replaces apply.py. Generated once from the
# old chn-openstates-scrape.yml / -files.yml / -test.yml by migrate_to_jurisdictions.py;
# edit this file from now on.
#
# Per state:
#   name, scrape_cron (its daily time, UTC), labels ("working" = in `govbot clone all`)
#   runner: github | proxy (GitHub-hosted through tinyproxy; a manual run can pick
#           self-hosted) | self-hosted (always the home runner)
#   scrapers (default bills), scrape_timeout_minutes, docker_image, toolkit_branch
#   repo_secrets: repo-level secrets a new pair's scraper repo needs set by hand
#   sessions: one entry per session pair:
#       id        OpenStates session identifier, exactly as in scrapers/<st>/__init__.py
#       schedule  optional: a cron, or "manual" (no schedule); default: the state's scrape_cron
#       anything else = an override of the state's settings, only where the session differs
#     -> govbot-openstates-scrapers/<st>-<id>-scraper + govbot-data/<st>-<id>
#        (lower-cased; characters outside [a-z0-9._-] become "-")
#   old_repos: the one-repo-per-state pair. status: history (moved to govbot-history,
#              read-only for the tool) or manual (still running, managed by hand).
#              jurisdictions.py never writes to either.
"""


def render_text(doc):
    return HEADER + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    text = render_text(build())
    if args.check:
        if OUT.read_text() != text:
            sys.exit("jurisdictions.yml differs from what the old configs generate")
        print("jurisdictions.yml matches the old configs")
        return
    OUT.write_text(text)
    print(f"wrote {OUT.name}")


if __name__ == "__main__":
    main()
