#!/usr/bin/env python3
"""Rebuild catalog.json's repo list from actions/pipeline-manager/jurisdictions.yml.

    python3 scripts/build_catalog.py           # rewrite catalog.json
    python3 scripts/build_catalog.py --check   # exit 1 if catalog.json is out of date

catalog.json is the machine-readable directory llms.txt points AI assistants to. Since
the 2026-11 repo reorg a jurisdiction can have several data repos: its old repo (moved to
govbot-history for most states; still in govbot-data for the ones running there) and one
repo per session with its own pair. The written fields (description, path pattern, bill
fields) are kept as they are; only the repo fields are generated.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yaml  # noqa: E402
from data_repos import JURISDICTIONS, pair_key  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "catalog.json"
RAW = "https://raw.githubusercontent.com"


def repo_entry(full, status, sessions):
    return {
        "repo": full,
        "status": status,
        "sessions": sessions,
        "browse": f"https://github.com/{full}",
        "data_json": f"{RAW}/{full}/HEAD/data.json",
    }


def build(catalog, config):
    data_org = config["orgs"]["data"]
    types = {j["code"]: j.get("type", "state") for j in catalog.get("jurisdictions", [])}
    jurisdictions = []
    for code, st in sorted(config["states"].items()):
        old = st["old_repos"]
        pair_ids = [str(s["id"]) for s in st.get("sessions") or []]
        repos = [repo_entry(
            old["data"],
            "history" if old["status"] == "history" else "live",
            "every session without its own repo below" if pair_ids else "all",
        )]
        repos += [repo_entry(f"{data_org}/{pair_key(code, sid)}", "session", [sid]) for sid in pair_ids]
        jurisdictions.append({"code": code, "name": st["name"], "type": types.get(code, "state"),
                              "repos": repos})
    out = dict(catalog)
    out.update({
        "description": "U.S. legislation for every state, D.C., the territories, and the federal "
                       "Congress, published as ordinary public GitHub repositories: one repo per "
                       "jurisdiction for older sessions, and one repo per legislative session from "
                       "2027 on.",
        "canonical_org": "https://github.com/govbot-data",
        "orgs": {
            "govbot-data": "live data repos: one per legislative session, plus the old "
                           "one-repo-per-jurisdiction repos still running there",
            "govbot-history": "the old one-repo-per-jurisdiction repos, with their full git history "
                              "(sessions up to 2026)",
        },
        "repo_naming": "Session repos: govbot-data/{code}-{session id, lower-cased} (e.g. Texas 90R "
                       "-> govbot-data/tx-90r). Older sessions: govbot-history/{code}-legislation-data "
                       "(e.g. Illinois -> govbot-history/il-legislation-data). Each jurisdiction's "
                       "repos[] lists its repos and which sessions each holds.",
        "repo_status": {
            "live": "updated by the scrapers",
            "history": "read-only record of earlier sessions; full git history",
            "session": "one session's own repo; it can be listed shortly before its first scrape "
                       "creates it, so a 404 means 'not created yet'",
        },
        "raw_file_base": RAW + "/{repo}/HEAD/{path}",
        "how_to_discover": {
            "list_sessions": "https://api.github.com/repos/{repo}/contents/country:us/state:{code}/sessions",
            "list_bills_in_session": "https://api.github.com/repos/{repo}/contents/country:us/state:{code}/sessions/{session_id}/bills",
            "list_everything_recursive": "https://api.github.com/repos/{repo}/git/trees/HEAD?recursive=1",
            "note": "{repo} is owner/name from a jurisdiction's repos[] (e.g. govbot-history/il-legislation-data).",
        },
        "jurisdictions": jurisdictions,
    })
    return out


def render(doc):
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    current = json.loads(CATALOG.read_text())
    config = yaml.safe_load(JURISDICTIONS.read_text())
    text = render(build(current, config))
    if args.check:
        if CATALOG.read_text() != text:
            sys.exit("catalog.json is out of date: run python3 scripts/build_catalog.py")
        print("catalog.json matches jurisdictions.yml")
        return
    CATALOG.write_text(text)
    print("wrote catalog.json")


if __name__ == "__main__":
    main()
