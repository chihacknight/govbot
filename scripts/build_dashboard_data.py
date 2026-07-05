#!/usr/bin/env python3
"""Aggregate cloned govbot repos into a single data file for the Pages dashboard.

Scans every ``metadata.json`` under ``<govbot-dir>/repos/*/**/bills/*/`` and
emits one compact JSON document consumed by ``docs/src/dashboard/index.html``.

Two bill formats are recognized:

* govbot OCD-files layout: ``**/bills/<ID>/metadata.json`` (any depth)
* raw OpenStates scraper output: ``**/bill_<uuid>.json`` (e.g. the
  ``_data/<locale>/`` folders committed by the scraper repos in the
  govbot-openstates-scrapers org; see schemas/openstates.bill.schema.json)

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

# Payload discipline: at ~140k bills every byte per bill is ~140KB of
# output, and GitHub Pages rejects files over 100MB. Ship only fields the
# dashboard page reads, truncated to what it can display.
MAX_SPONSORS = 3
MAX_TITLE = 300
MAX_ACTION_DESC = 200

# Display names for jurisdiction codes; raw OpenStates scrape output carries
# only an OCD jurisdiction ID string, not a display name.
STATE_NAMES = {
    "al": "Alabama", "ak": "Alaska", "az": "Arizona", "ar": "Arkansas",
    "ca": "California", "co": "Colorado", "ct": "Connecticut", "de": "Delaware",
    "fl": "Florida", "ga": "Georgia", "hi": "Hawaii", "id": "Idaho",
    "il": "Illinois", "in": "Indiana", "ia": "Iowa", "ks": "Kansas",
    "ky": "Kentucky", "la": "Louisiana", "me": "Maine", "md": "Maryland",
    "ma": "Massachusetts", "mi": "Michigan", "mn": "Minnesota",
    "ms": "Mississippi", "mo": "Missouri", "mt": "Montana", "ne": "Nebraska",
    "nv": "Nevada", "nh": "New Hampshire", "nj": "New Jersey",
    "nm": "New Mexico", "ny": "New York", "nc": "North Carolina",
    "nd": "North Dakota", "oh": "Ohio", "ok": "Oklahoma", "or": "Oregon",
    "pa": "Pennsylvania", "ri": "Rhode Island", "sc": "South Carolina",
    "sd": "South Dakota", "tn": "Tennessee", "tx": "Texas", "ut": "Utah",
    "vt": "Vermont", "va": "Virginia", "wa": "Washington",
    "wv": "West Virginia", "wi": "Wisconsin", "wy": "Wyoming",
    "dc": "District of Columbia", "pr": "Puerto Rico", "gu": "Guam",
    "vi": "U.S. Virgin Islands", "mp": "Northern Mariana Islands",
    "as": "American Samoa", "usa": "United States",
}


def parse_org_classification(raw):
    """from_organization is stored as '~{"classification": "lower"}'."""
    if not isinstance(raw, str) or not raw.startswith("~"):
        return None
    try:
        return json.loads(raw[1:]).get("classification")
    except (json.JSONDecodeError, AttributeError):
        return None


def looks_like_bill(metadata):
    return (isinstance(metadata, dict)
            and metadata.get("identifier")
            and "title" in metadata
            and "jurisdiction" in metadata)


def parse_jurisdiction(jurisdiction, fallback_code):
    """(code, name) from either the OCD-files dict or a raw OCD ID string."""
    if isinstance(jurisdiction, dict):
        division = jurisdiction.get("division_id") or jurisdiction.get("id") or ""
        name = jurisdiction.get("name")
    else:
        division = str(jurisdiction or "")
        name = None
    match = re.search(r"(?:state|territory|district):([a-z]{2})\b", division)
    code = match.group(1) if match else None
    if not code and "country:us" in division:
        code = "usa"
    if not code:
        code = fallback_code
    if not name:
        name = STATE_NAMES.get(code, (code or "?").upper())
    return code, name


def find_tags_dir(bill_dir, repo_dir):
    """Nearest ancestor of the bill dir (up to the repo root) with a tags/ dir.

    govbot tag writes tags/ next to a session's bills/, but repo layouts vary,
    so walk upward instead of assuming a fixed depth.
    """
    for ancestor in [bill_dir, *bill_dir.parents]:
        if (ancestor / "tags").is_dir():
            return ancestor
        if ancestor == repo_dir:
            break
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


def session_for(metadata, metadata_path):
    """Prefer the bill's own field; fall back to a .../sessions/<id>/... path."""
    session = metadata.get("legislative_session")
    if session:
        return str(session)
    parts = metadata_path.parts
    if "sessions" in parts:
        idx = parts.index("sessions")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return ""


def summarize_bill(metadata, session_id, tags, code):
    actions = metadata.get("actions") or []
    dates = sorted(a["date"][:10] for a in actions if a.get("date"))
    latest = max(actions, key=lambda a: a.get("date") or "") if actions else {}
    sponsors = [s.get("name", "") for s in metadata.get("sponsorships") or []]
    url = next((s["url"] for s in metadata.get("sources") or [] if s.get("url")), None)
    desc = latest.get("description")
    return {
        "state": code,
        "session": session_id,
        "id": metadata.get("identifier", ""),
        "title": (metadata.get("title") or "")[:MAX_TITLE],
        "chamber": parse_org_classification(metadata.get("from_organization")),
        "latest_action": dates[-1] if dates else None,
        "latest_action_desc": desc[:MAX_ACTION_DESC] if desc else None,
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
    parser.add_argument("--source-label", default=None,
                        help="Human-readable data source shown in the dashboard "
                             "footer (default: the repos directory path)")
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
    tag_cache = {}
    state_names = {}
    empty_repos = {}  # code -> display name for repos that cloned but had no bills
    for repo_dir in sorted(p for p in repos_dir.iterdir() if p.is_dir()):
        repo_bills = 0
        repo_code = repo_dir.name.removesuffix("-legislation").lower()
        # Layout-agnostic: OCD-files metadata.json plus raw OpenStates
        # scrape output (bill_<uuid>.json), each at any depth.
        candidates = sorted(repo_dir.rglob("metadata.json")) + sorted(repo_dir.rglob("bill_*.json"))
        for metadata_path in candidates:
            if ".git" in metadata_path.parts:
                continue
            try:
                metadata = json.loads(metadata_path.read_text())
            except (json.JSONDecodeError, OSError) as err:
                print(f"warning: skipping unreadable {metadata_path}: {err}", file=sys.stderr)
                continue
            if not looks_like_bill(metadata):
                continue
            tags = []
            tags_home = find_tags_dir(metadata_path.parent, repo_dir)
            if tags_home is not None:
                if tags_home not in tag_cache:
                    tag_cache[tags_home] = load_tag_files(tags_home)
                tags = tag_cache[tags_home].get(metadata.get("identifier", ""), [])
            if not tags and compiled_tags:
                tags = keyword_tags_for(metadata, compiled_tags)
            code, name = parse_jurisdiction(metadata.get("jurisdiction"), repo_code)
            state_names.setdefault(code, name)
            bills.append(summarize_bill(
                metadata, session_for(metadata, metadata_path), tags, code))
            repo_bills += 1
        if repo_bills == 0:
            empty_repos[repo_code] = STATE_NAMES.get(repo_code, repo_code.upper())
        print(f"{repo_dir.name}: {repo_bills} bills", file=sys.stderr)

    # Re-scrapes can leave multiple files for the same bill; keep the one
    # with the most recent action, then sort for deterministic output.
    best = {}
    for b in bills:
        k = (b["state"], b["session"], b["id"])
        cur = best.get(k)
        if cur is None or (b["latest_action"] or "") > (cur["latest_action"] or ""):
            best[k] = b
    if len(best) < len(bills):
        print(f"deduplicated {len(bills) - len(best)} repeated bill files", file=sys.stderr)
    bills = sorted(best.values(), key=lambda b: (b["state"] or "", b["session"], b["id"]))

    if not bills:
        print(f"error: no metadata.json files found under {repos_dir}", file=sys.stderr)
        return 1

    states = sorted(
        ((code, name) for code, name in state_names.items() if code),
        key=lambda pair: pair[1],
    )
    tag_names = sorted({t for b in bills for t in b["tags"]})
    # Jurisdictions whose repo cloned but published no bills yet (upstream
    # scraper disabled or not producing) — surfaced so the dashboard can
    # say "pending" rather than silently omitting them.
    empty = sorted(
        ({"code": c, "name": n} for c, n in empty_repos.items() if c not in state_names),
        key=lambda e: e["name"],
    )
    output = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": args.source_label or str(repos_dir),
        "states": [{"code": code, "name": name} for code, name in states],
        "empty_jurisdictions": empty,
        "tags": [{"name": name, "description": tag_descriptions.get(name, "")}
                 for name in tag_names],
        "bills": bills,
    }

    # Compact separators: at 140k+ bills, indentation alone costs megabytes.
    text = json.dumps(output, separators=(",", ":"), ensure_ascii=False) + "\n"
    if args.output == "-":
        sys.stdout.write(text)
    else:
        Path(args.output).write_text(text)
        print(f"wrote {len(bills)} bills from {len(states)} jurisdictions "
              f"to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
