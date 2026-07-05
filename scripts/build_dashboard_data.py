#!/usr/bin/env python3
"""Aggregate cloned govbot repos into a single data file for the Pages dashboard.

Scans every ``metadata.json`` under ``<govbot-dir>/repos/*/**/bills/*/`` and
emits one compact JSON document consumed by ``docs/src/dashboard/index.html``.

Topics come from ``govbot tag`` output (``tags/*.tag.json`` next to each
session's ``bills/`` folder) when present. When a session has no tag files,
an optional keyword config (``--tags-config``) provides a fallback that
mirrors govbot's own keyword-only tagging mode — this is what powers the
committed demo data built from ``actions/govbot/mocks``.

Usage:
    # Demo data from the in-repo mocks (what is committed):
    python3 scripts/build_dashboard_data.py \
        --govbot-dir actions/govbot/mocks/.govbot \
        --tags-config scripts/dashboard_tags.json \
        --output docs/src/dashboard/data.json

    # Real data after `govbot clone all` (+ `govbot tag` for topics):
    python3 scripts/build_dashboard_data.py --output docs/src/dashboard/data.json

Only the Python standard library is used.
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

MAX_SPONSORS = 5


def parse_org_classification(raw):
    """from_organization is stored as '~{"classification": "lower"}'."""
    if not isinstance(raw, str) or not raw.startswith("~"):
        return None
    try:
        return json.loads(raw[1:]).get("classification")
    except (json.JSONDecodeError, AttributeError):
        return None


def load_tag_files(session_dir):
    """Read govbot tag output: tags/<name>.tag.json -> {bill_id: [tag, ...]}."""
    bill_tags = {}
    tags_dir = session_dir / "tags"
    if not tags_dir.is_dir():
        return bill_tags
    for tag_file in sorted(tags_dir.glob("*.tag.json")):
        tag_name = tag_file.name[: -len(".tag.json")]
        try:
            data = json.loads(tag_file.read_text())
        except (json.JSONDecodeError, OSError) as err:
            print(f"warning: skipping unreadable tag file {tag_file}: {err}", file=sys.stderr)
            continue
        threshold = (data.get("tag_config") or {}).get("threshold", 0.0)
        for bill_id, entry in (data.get("bills") or {}).items():
            score = (entry.get("score") or {}).get("final_score", 0.0)
            if score >= threshold:
                bill_tags.setdefault(bill_id, []).append(tag_name)
    return bill_tags


def compile_keyword_tags(config_path):
    """Compile --tags-config keywords into [(tag_name, [regex, ...])]."""
    config = json.loads(Path(config_path).read_text())
    compiled = []
    for name, spec in config.get("tags", {}).items():
        patterns = [
            re.compile(r"\b" + re.escape(kw.lower()).replace(r"\ ", r"\s+") + r"\b")
            for kw in spec.get("include_keywords", [])
        ]
        if patterns:
            compiled.append((name, patterns))
    return compiled


def keyword_tags_for(metadata, compiled_tags):
    texts = [metadata.get("title") or ""]
    texts += [t.get("title", "") for t in metadata.get("other_titles", [])]
    texts += [a.get("abstract", "") for a in metadata.get("abstracts", [])]
    haystack = " ".join(texts).lower()
    return [name for name, patterns in compiled_tags if any(p.search(haystack) for p in patterns)]


def summarize_bill(metadata, session_id, tags):
    actions = metadata.get("actions") or []
    dates = sorted(a["date"][:10] for a in actions if a.get("date"))
    latest = max(actions, key=lambda a: a.get("date") or "") if actions else {}
    sponsors = [s.get("name", "") for s in metadata.get("sponsorships") or []]
    url = next((s["url"] for s in metadata.get("sources") or [] if s.get("url")), None)
    jurisdiction = metadata.get("jurisdiction") or {}
    division = jurisdiction.get("division_id") or ""
    code = division.rsplit(":", 1)[-1] if ":" in division else None
    return {
        "state": code,
        "state_name": jurisdiction.get("name") or (code or "").upper(),
        "session": session_id,
        "id": metadata.get("identifier", ""),
        "title": metadata.get("title", ""),
        "chamber": parse_org_classification(metadata.get("from_organization")),
        "classification": metadata.get("classification") or [],
        "first_action": dates[0] if dates else None,
        "latest_action": dates[-1] if dates else None,
        "latest_action_desc": latest.get("description"),
        "sponsors": sponsors[:MAX_SPONSORS],
        "url": url,
        "tags": sorted(tags),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--govbot-dir", default=str(Path.home() / ".govbot"),
                        help="Directory containing repos/ (default: ~/.govbot)")
    parser.add_argument("--tags-config", default=None,
                        help="JSON file of keyword tag definitions used when a "
                             "session has no tags/*.tag.json files")
    parser.add_argument("--output", "-o", default="-",
                        help="Output path (default: stdout)")
    args = parser.parse_args()

    repos_dir = Path(args.govbot_dir) / "repos"
    if not repos_dir.is_dir():
        parser.error(f"no repos directory at {repos_dir} — run `govbot clone` first")

    compiled_tags = compile_keyword_tags(args.tags_config) if args.tags_config else []
    tag_descriptions = {}
    if args.tags_config:
        config = json.loads(Path(args.tags_config).read_text())
        tag_descriptions = {
            name: spec.get("description", "")
            for name, spec in config.get("tags", {}).items()
        }

    bills = []
    for metadata_path in sorted(repos_dir.glob("*/**/bills/*/metadata.json")):
        session_dir = metadata_path.parent.parent.parent
        try:
            metadata = json.loads(metadata_path.read_text())
        except (json.JSONDecodeError, OSError) as err:
            print(f"warning: skipping unreadable {metadata_path}: {err}", file=sys.stderr)
            continue
        session_tags = load_tag_files(session_dir)
        tags = session_tags.get(metadata.get("identifier", ""), [])
        if not tags and compiled_tags:
            tags = keyword_tags_for(metadata, compiled_tags)
        bills.append(summarize_bill(metadata, session_dir.name, tags))

    if not bills:
        print(f"error: no metadata.json files found under {repos_dir}", file=sys.stderr)
        return 1

    states = sorted(
        {(b["state"], b["state_name"]) for b in bills if b["state"]},
        key=lambda pair: pair[1],
    )
    tag_names = sorted({t for b in bills for t in b["tags"]})
    output = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": str(repos_dir),
        "states": [{"code": code, "name": name} for code, name in states],
        "tags": [{"name": name, "description": tag_descriptions.get(name, "")}
                 for name in tag_names],
        "bills": bills,
    }

    text = json.dumps(output, indent=1, ensure_ascii=False) + "\n"
    if args.output == "-":
        sys.stdout.write(text)
    else:
        Path(args.output).write_text(text)
        print(f"wrote {len(bills)} bills from {len(states)} jurisdictions "
              f"to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
