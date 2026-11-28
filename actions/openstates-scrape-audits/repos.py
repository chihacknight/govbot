"""Which repos the audits read, from pipeline-manager's jurisdictions.yml (repo reorg, 2026-11).

Per state: its old repos (`old_repos`: in govbot-history, or still running in the live
orgs when `manual`) and one scraper + data repo per session pair. A repo is "running" when
its workflows run: a manual state's old repos, and a session pair with a schedule.
"""

import re
from pathlib import Path

import yaml

JURISDICTIONS = Path(__file__).resolve().parent.parent / "pipeline-manager" / "jurisdictions.yml"


def pair_key(state, session_id):
    """<state>-<id> lower-cased; characters outside [a-z0-9._-] become '-' (as jurisdictions.py)."""
    return re.sub(r"[^a-z0-9._-]", "-", f"{state}-{session_id}".lower())


def state_repos(path=JURISDICTIONS):
    """{code: [{"label", "scraper", "data", "running"}, ...]}: old repos first, then pairs."""
    config = yaml.safe_load(Path(path).read_text())
    orgs = config["orgs"]
    out = {}
    for code, st in config["states"].items():
        old = st["old_repos"]
        repos = [{"label": code, "scraper": old["scraper"], "data": old["data"],
                  "running": old["status"] == "manual"}]
        for s in st.get("sessions") or []:
            key = pair_key(code, s["id"])
            repos.append({"label": key, "scraper": f"{orgs['scraper']}/{key}-scraper",
                          "data": f"{orgs['data']}/{key}", "running": s.get("schedule") != "manual"})
        out[code] = repos
    return out


def running_scrapers(path=JURISDICTIONS):
    """[(label, scraper repo)] for every scraper whose workflow runs, sorted by label."""
    return sorted((r["label"], r["scraper"]) for repos in state_repos(path).values()
                  for r in repos if r["running"])
