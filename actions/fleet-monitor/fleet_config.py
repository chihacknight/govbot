"""Read pipeline-manager fleet configs into jurisdiction records.

This module is the only place that knows the pipeline-manager config format or
the paused-template convention; everything downstream of it consumes records.
The record shape is locked by record.schema.json.
"""

import re
from pathlib import Path

import yaml

# Defaults match pipeline-manager's render.py when the config omits them.
DEFAULT_MARKER_OPEN = "✏️{"
DEFAULT_MARKER_CLOSE = "}✏️"
DEFAULT_RUNNER = "ubuntu-latest"


def read_fleet(config_dir):
    """Return one jurisdiction record per locale per fleet config in config_dir.

    A fleet config is any top-level *.yml/*.yaml file with a `locales` mapping;
    the fleet name is the file's stem. Records are sorted by (fleet, state) so
    output is deterministic. Raises ValueError on a config that references a
    template it doesn't define or that has no workflow files on disk.
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
    templates = config.get("templates") or {}
    workflows_by_template = {
        name: _template_workflows(fleet, name, config_dir) for name in templates
    }

    for code, locale in sorted((config.get("locales") or {}).items()):
        locale = locale or {}  # a bare `xx:` line parses to None
        template = locale.get("template", "")
        if template not in templates:
            raise ValueError(
                f"{fleet}: locale '{code}' references unknown template '{template}'"
            )
        disabled = set(locale.get("disabled_jobs") or [])
        yield {
            "fleet": fleet,
            "state": code,
            "name": locale.get("name", ""),
            "org": org,
            "repo": _repo_name(templates, template, code, marker_open, marker_close),
            "template": template,
            "paused": template.endswith("-paused"),
            "runner": locale.get("runner", DEFAULT_RUNNER),
            "expected_workflows": [
                w for w in workflows_by_template[template]
                # disabled_jobs entries are basenames without the extension,
                # matching pipeline-manager's render.py
                if Path(w).stem not in disabled
            ],
        }


def _repo_name(templates, template, code, marker_open, marker_close):
    """Substitute the locale code into the template's folder-name pattern."""
    folder_name = (templates.get(template) or {}).get("folder-name")
    if not folder_name:
        return code  # render.py's fallback: the bare locale code
    marker = re.escape(marker_open) + r"\s*locale\.key\s*" + re.escape(marker_close)
    return re.sub(marker, code, folder_name)


def _template_workflows(fleet, template, config_dir):
    """Workflow files the template ships, as they will exist in rendered repos.

    render.py strips a trailing .j2 when rendering, so `scrape.yml.j2` runs as
    `scrape.yml`; mirror that here before filtering to workflow extensions.
    """
    workflows_dir = Path(config_dir) / "templates" / template / ".github" / "workflows"
    if not workflows_dir.is_dir():
        raise ValueError(
            f"{fleet}: template '{template}' has no workflows directory at {workflows_dir}"
        )
    names = set()
    for path in workflows_dir.iterdir():
        name = path.name[: -len(".j2")] if path.name.endswith(".j2") else path.name
        if name.endswith((".yml", ".yaml")):
            names.add(name)
    return sorted(names)
