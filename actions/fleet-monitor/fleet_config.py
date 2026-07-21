"""Read pipeline-manager fleet configs into jurisdiction records.

This module is the only place that knows the pipeline-manager config format or
the paused-template convention; everything downstream of it consumes records.
"""

import re
from pathlib import Path

import yaml

# Defaults match pipeline-manager's render.py when the config omits them.
DEFAULT_MARKER_OPEN = "✏️{"
DEFAULT_MARKER_CLOSE = "}✏️"
DEFAULT_RUNNER = "ubuntu-latest"


def read_fleet(config_dir):
    """Yield one jurisdiction record per locale per fleet config in config_dir.

    A fleet config is any top-level *.yml/*.yaml file with a `locales` mapping;
    the fleet name is the file's stem. Records are sorted by (fleet, state) so
    output is deterministic.
    """
    config_dir = Path(config_dir)
    records = []
    for config_path in sorted(config_dir.glob("*.yml")) + sorted(config_dir.glob("*.yaml")):
        with open(config_path) as f:
            config = yaml.safe_load(f)
        if not isinstance(config, dict) or "locales" not in config:
            continue
        records.extend(_read_one_config(config_path.stem, config, config_dir))
    return sorted(records, key=lambda r: (r["fleet"], r["state"]))


def _read_one_config(fleet, config, config_dir):
    org = config.get("org", {}).get("username", "")
    markers = config.get("template_markers", {})
    marker_open = markers.get("open", DEFAULT_MARKER_OPEN)
    marker_close = markers.get("close", DEFAULT_MARKER_CLOSE)
    templates = config.get("templates", {})

    for code, locale in sorted(config.get("locales", {}).items()):
        template = locale.get("template", "")
        yield {
            "fleet": fleet,
            "state": code,
            "name": locale.get("name", ""),
            "org": org,
            "repo": _repo_name(templates, template, code, marker_open, marker_close),
            "template": template,
            "paused": template.endswith("-paused"),
            "runner": locale.get("runner", DEFAULT_RUNNER),
            "expected_workflows": _expected_workflows(config_dir, template, locale),
        }


def _repo_name(templates, template, code, marker_open, marker_close):
    """Substitute the locale code into the template's folder-name pattern."""
    folder_name = templates.get(template, {}).get("folder-name", "")
    marker = re.escape(marker_open) + r"\s*locale\.key\s*" + re.escape(marker_close)
    return re.sub(marker, code, folder_name)


def _expected_workflows(config_dir, template, locale):
    """Workflow files the template ships, minus the locale's disabled_jobs.

    disabled_jobs entries are workflow basenames without the .yml extension,
    matching pipeline-manager's render.py.
    """
    disabled = set(locale.get("disabled_jobs") or [])
    workflows_dir = Path(config_dir) / "templates" / template / ".github" / "workflows"
    return sorted(
        p.name
        for p in workflows_dir.glob("*.yml")
        if p.stem not in disabled
    )
