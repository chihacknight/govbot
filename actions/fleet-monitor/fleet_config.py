"""Read pipeline-manager's jurisdictions.yml into jurisdiction records.

This module is the only place that knows the pipeline-manager config format or
the paused-template convention; everything downstream of it consumes records.
The record shape is locked by schemas/fleet-record.schema.json.

Since the 2026-11 repo reorg, jurisdictions.yml is the single source of truth. The
repos the monitor watches are the ones that run:

- each state's old repos while they are `manual` (still running; managed by hand), and
- every session pair (`sessions:`), whose repos jurisdictions.py creates.

`history` repos (moved to govbot-history, workflows off) are not monitored. Records keep
the fleet names the dashboards and alerts already use: `chn-openstates-scrape` for
scraper repos, `chn-openstates-files` for data repos, `chn-openstates-test` for the
govbot-test mirror (excluded by default).
"""

import re
from pathlib import Path

import yaml

CONFIG_NAME = "jurisdictions.yml"
SCRAPE_FLEET = "chn-openstates-scrape"
FILES_FLEET = "chn-openstates-files"
TEST_FLEET = "chn-openstates-test"

# jurisdictions.yml runner -> the runner label the templates render
RUNNERS = {"github": "ubuntu-latest", "proxy": "self-hosted", "self-hosted": "self-hosted"}

# Fleets discovery finds but the monitor skips by default.
#
# `chn-openstates-test` mirrors the files fleet against the govbot-test org; its locales
# are expected to fail, and monitoring it would put permanent expected-red on the board
# and take the hourly sweep over the GITHUB_TOKEN ceiling (56 repos x 2 workflows).
#
# A default, not a law: `--exclude-fleet` overrides it (name nothing and the whole fleet
# is monitored), so the config stays the authority on what exists and this is only a
# visible, reversible statement about what is worth alerting on.
EXCLUDED_FLEETS = (TEST_FLEET,)


def pair_key(state, session_id):
    """<state>-<id> lower-cased; characters outside [a-z0-9._-] become '-' (as jurisdictions.py)."""
    return re.sub(r"[^a-z0-9._-]", "-", f"{state}-{session_id}".lower())


def read_fleet(config_dir, exclude_fleets=EXCLUDED_FLEETS):
    """Return one jurisdiction record per monitored repo in config_dir/jurisdictions.yml.

    Records are sorted by (fleet, state, repo) so output is deterministic. Raises
    ValueError on malformed input: a missing file, no `orgs`, a state or section that
    isn't a mapping, a non-string state key, an unknown `old_repos.status` or runner, or
    a template with no workflow files on disk.
    """
    config_dir = Path(config_dir)
    path = config_dir / CONFIG_NAME
    if not path.is_file():
        raise ValueError(f"no {CONFIG_NAME} in {config_dir}")
    config = yaml.safe_load(path.read_text())
    if not isinstance(config, dict):
        raise ValueError(f"{CONFIG_NAME}: top level must be a mapping")
    orgs = _mapping(config, "orgs")
    for kind in ("scraper", "data"):
        if not orgs.get(kind):
            raise ValueError(f"{CONFIG_NAME}: orgs.{kind} is missing")
    defaults = _mapping(config, "defaults")
    states = _mapping(config, "states")
    excluded = set(exclude_fleets or ())
    workflows = {}

    def record(fleet, code, name, org, repo, template, runner):
        if template not in workflows:
            workflows[template] = _template_workflows(template, config_dir)
        return {
            "fleet": fleet,
            "config": CONFIG_NAME,
            "state": code,
            "name": name,
            "org": org,
            "repo": repo,
            "template": template,
            # The -paused suffix is this module's convention to own: downstream
            # consumers key durable per-template facts (like data paths) off
            # base_template so pausing a locale never changes its identity.
            "base_template": template.removesuffix("-paused"),
            "paused": template.endswith("-paused"),
            "runner": runner,
            "expected_workflows": workflows[template],
        }

    records = []
    for code, state in states.items():
        # YAML 1.1 turns bare words like on/no/off/yes into booleans; a state code
        # written unquoted arrives as True/False. That's a quoting mistake to flag.
        if not isinstance(code, str):
            raise ValueError(f"{CONFIG_NAME}: state key {code!r} is not a string — quote YAML words "
                             f"like on/no/off/yes that parse as booleans")
        if not isinstance(state, dict):
            raise ValueError(f"{CONFIG_NAME}: state '{code}' must be a mapping, not {type(state).__name__}")
        name = state.get("name") or ""
        runner_key = state.get("runner") or defaults.get("runner") or "github"
        if runner_key not in RUNNERS:
            raise ValueError(f"{CONFIG_NAME}: state '{code}' has unknown runner {runner_key!r}")
        old = state.get("old_repos")
        if not isinstance(old, dict) or old.get("status") not in ("history", "manual"):
            raise ValueError(f"{CONFIG_NAME}: state '{code}' old_repos.status must be history or manual")
        if old["status"] == "manual":
            for fleet, full, template in ((SCRAPE_FLEET, old["scraper"], "openstates-scrape"),
                                          (FILES_FLEET, old["data"], "openstates-to-ocd-files")):
                org, repo = full.split("/", 1)
                records.append(record(fleet, code, name, org, repo, template, RUNNERS[runner_key]))
        for session in state.get("sessions") or []:
            if not isinstance(session, dict) or "id" not in session:
                raise ValueError(f"{CONFIG_NAME}: state '{code}' has a session without an id")
            key = pair_key(code, session["id"])
            s_runner = session.get("runner") or runner_key
            if s_runner not in RUNNERS:
                raise ValueError(f"{CONFIG_NAME}: {key} has unknown runner {s_runner!r}")
            manual = session.get("schedule") == "manual"
            label = f"{name} ({session['id']})"
            records.append(record(SCRAPE_FLEET, code, label, orgs["scraper"], f"{key}-scraper",
                                  "openstates-scrape-paused" if manual else "openstates-scrape",
                                  RUNNERS[s_runner]))
            records.append(record(FILES_FLEET, code, label, orgs["data"], key,
                                  "openstates-to-ocd-files", "ubuntu-latest"))

    test = config.get("test_fleet")
    if test:
        if not isinstance(test, dict):
            raise ValueError(f"{CONFIG_NAME}: test_fleet must be a mapping")
        for code in test.get("states") or []:
            name = (states.get(code) or {}).get("name") or ""
            records.append(record(TEST_FLEET, code, name, test["org"], f"{code}-legislation",
                                  test["template"], "ubuntu-latest"))

    records = [r for r in records if r["fleet"] not in excluded]
    return sorted(records, key=lambda r: (r["fleet"], r["state"], r["repo"]))


def _mapping(config, key):
    """Return config[key] as a mapping, defaulting {} when absent/blank."""
    value = config.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{CONFIG_NAME}: '{key}' must be a mapping, not {type(value).__name__}")
    return value


def _template_workflows(template, config_dir):
    """Workflow files the template ships, rendered names (a trailing .j2 is stripped)."""
    workflows_dir = Path(config_dir) / "templates" / template / ".github" / "workflows"
    names = set()
    if workflows_dir.is_dir():
        for path in workflows_dir.iterdir():
            rendered = path.name[: -len(".j2")] if path.name.endswith(".j2") else path.name
            if rendered.endswith((".yml", ".yaml")):
                names.add(rendered)
    if not names:
        raise ValueError(f"{CONFIG_NAME}: template '{template}' has no workflow files under {workflows_dir}")
    return sorted(names)
