"""Which data repo holds a state's session (repo reorg, 2026-11).

Read from actions/pipeline-manager/jurisdictions.yml, the single source of truth:

- a session with its own pair (`sessions:`) lives in `govbot-data/<st>-<id>`;
- every other session lives in the state's old repo (`old_repos.data`): the govbot-history
  pair for moved states, today's govbot-data repo for the ones still running.

Used by the site build (bill-card links, summaries) and the CLI-side readers. The local
clone folder of a repo (from `govbot clone`) is `<st>-legislation` for the old repo and
the repo's own name for a session pair; `state_of_folder` reads the state from the files.
"""

import re
from functools import lru_cache
from pathlib import Path

import yaml

JURISDICTIONS = Path(__file__).resolve().parent.parent / "actions" / "pipeline-manager" / "jurisdictions.yml"


def pair_key(state, session_id):
    """<state>-<id> lower-cased; characters outside [a-z0-9._-] become '-' (as jurisdictions.py)."""
    return re.sub(r"[^a-z0-9._-]", "-", f"{state}-{session_id}".lower())


@lru_cache(maxsize=None)
def repo_map(path=str(JURISDICTIONS)):
    """{state: {"repo": old data repo, "sessions": {session id: pair data repo}}}."""
    config = yaml.safe_load(Path(path).read_text())
    data_org = config["orgs"]["data"]
    out = {}
    for st, entry in config["states"].items():
        out[st] = {
            "repo": entry["old_repos"]["data"],
            "sessions": {str(s["id"]): f"{data_org}/{pair_key(st, s['id'])}"
                         for s in entry.get("sessions") or []},
        }
    return out


def repo_for(state, session, repos=None):
    """owner/name of the data repo holding `state`'s `session`, or None for an unknown state."""
    entry = (repos or repo_map()).get(state)
    if entry is None:
        return None
    return entry["sessions"].get(str(session), entry["repo"])


def state_of_folder(repo_dir):
    """The state a cloned data repo holds, from its `country:us/state:<st>/` folder; else
    the folder name without `-legislation`."""
    repo_dir = Path(repo_dir)
    states = sorted(p.name.split(":", 1)[1] for p in (repo_dir / "country:us").glob("state:*") if p.is_dir())
    if states:
        return states[0].lower()
    return repo_dir.name.removesuffix("-legislation").lower()
