"""Read pipeline-manager fleet configs into jurisdiction records.

This module is the only place that knows the pipeline-manager config format or
the paused-template convention; everything downstream of it consumes records.
The record shape is locked by schemas/fleet-record.schema.json.
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
    output is deterministic. Raises ValueError on malformed input — two fleet
    configs sharing a stem, a non-mapping top-level section, a config without
    org.username, a non-string locale key, a locale that isn't a mapping, a
    locale referencing a template the config doesn't define, a non-list
    disabled_jobs, or a referenced template with no workflow files on disk.
    """
    config_dir = Path(config_dir)
    records = []
    fleets_seen = {}
    for config_path in sorted(config_dir.glob("*.yml")) + sorted(config_dir.glob("*.yaml")):
        with open(config_path) as f:
            config = yaml.safe_load(f)
        if not isinstance(config, dict) or "locales" not in config:
            continue
        if config_path.stem in fleets_seen:
            raise ValueError(
                f"duplicate fleet '{config_path.stem}': "
                f"{fleets_seen[config_path.stem]} and {config_path.name}"
            )
        fleets_seen[config_path.stem] = config_path.name
        records.extend(_read_one_config(config_path, config, config_dir))
    return sorted(records, key=lambda r: (r["fleet"], r["state"]))


def _mapping(fleet, config, key):
    """Return config[key] as a mapping, defaulting {} when absent/blank.

    A scalar where a mapping is expected (`org: myorg`) is a config error, not
    something to dereference into an AttributeError.
    """
    value = config.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{fleet}: '{key}' must be a mapping, not {type(value).__name__}")
    return value


def _read_one_config(config_path, config, config_dir):
    fleet = config_path.stem
    org = _mapping(fleet, config, "org").get("username") or ""
    if not org:
        # org is required by pipeline-manager's config.schema.json
        raise ValueError(f"{fleet}: config has no org.username")
    markers = _mapping(fleet, config, "template_markers")
    marker_open = markers.get("open", DEFAULT_MARKER_OPEN)
    marker_close = markers.get("close", DEFAULT_MARKER_CLOSE)
    templates = _mapping(fleet, config, "templates")
    locales = _mapping(fleet, config, "locales")
    # YAML 1.1 turns bare words like on/no/off/yes into booleans, so a locale
    # code written unquoted arrives as True/False. Reject it before sorting —
    # render.py reads config as text and never hits this, so a boolean key is a
    # quoting mistake the author wants flagged, not silently coerced.
    for code in locales:
        if not isinstance(code, str):
            raise ValueError(
                f"{fleet}: locale key {code!r} is not a string — quote YAML words "
                f"like on/no/off/yes that parse as booleans"
            )
    # Resolved lazily, per referenced template: a defined-but-unreferenced
    # template without workflow files must not fail the listing (render.py
    # tolerates those too).
    workflows_cache = {}

    for code, locale in sorted(locales.items()):
        locale = locale or {}  # a bare `xx:` line parses to None
        if not isinstance(locale, dict):
            raise ValueError(
                f"{fleet}: locale '{code}' must be a mapping, not {type(locale).__name__}"
            )
        # render.py skips unmanaged locales entirely (process_locale). It reads
        # the value as text, so `managed: false` and quoted `"false"` both skip;
        # YAML 1.1 also collapses no/off to False, which the loader skips here —
        # an accepted divergence, since those are the same intent.
        managed = locale.get("managed", True)
        if managed is False or managed == "false":
            continue
        template = locale.get("template", "")
        if template not in templates:
            raise ValueError(
                f"{fleet}: locale '{code}' references unknown template '{template}'"
            )
        if template not in workflows_cache:
            workflows_cache[template] = _template_workflows(fleet, template, config_dir)
        disabled = _disabled_jobs(fleet, code, locale)
        yield {
            "fleet": fleet,
            "config": config_path.name,
            "state": code,
            # `or`-coercions: a key present with a blank value parses to None,
            # and render.py treats those as absent
            "name": locale.get("name") or "",
            "org": org,
            "repo": _repo_name(templates, template, code, marker_open, marker_close),
            "template": template,
            "paused": template.endswith("-paused"),
            "runner": locale.get("runner") or DEFAULT_RUNNER,
            "expected_workflows": [
                name
                for name, disable_key in workflows_cache[template]
                if disable_key not in disabled
            ],
        }


def _disabled_jobs(fleet, code, locale):
    """Set of disabled_jobs keys for a locale.

    render.py accepts a comma-separated string here as well as a list; a bare
    string would otherwise be exploded into a set of single characters, so
    require a list explicitly rather than mishandle the scalar silently.
    """
    raw = locale.get("disabled_jobs")
    if raw is None:
        return set()
    if not isinstance(raw, list):
        raise ValueError(
            f"{fleet}: locale '{code}' disabled_jobs must be a list, not "
            f"{type(raw).__name__}"
        )
    return set(raw)


def _repo_name(templates, template, code, marker_open, marker_close):
    """Substitute the locale code into the template's folder-name pattern."""
    folder_name = (templates.get(template) or {}).get("folder-name")
    if not folder_name:
        return code  # render.py's fallback: the bare locale code
    marker = re.escape(marker_open) + r"\s*locale\.key\s*" + re.escape(marker_close)
    return re.sub(marker, code, folder_name)


def _template_workflows(fleet, template, config_dir):
    """Workflow files the template ships, as (rendered name, disable key) pairs.

    render.py strips a trailing .j2 when rendering, so `nightly.yml.j2` runs as
    `nightly.yml` in real repos — but its disabled_jobs key is splitext of the
    on-disk name (`nightly.yml`), matching render.py's process_locale().
    """
    workflows_dir = Path(config_dir) / "templates" / template / ".github" / "workflows"
    pairs = {}
    if workflows_dir.is_dir():
        for path in sorted(workflows_dir.iterdir()):
            rendered = path.name[: -len(".j2")] if path.name.endswith(".j2") else path.name
            if rendered.endswith((".yml", ".yaml")):
                pairs[rendered] = path.stem  # one suffix stripped: nightly.yml.j2 -> nightly.yml
    if not pairs:
        raise ValueError(
            f"{fleet}: template '{template}' has no workflow files under {workflows_dir}"
        )
    return sorted(pairs.items())
