"""
Locales whose repos have moved out of the org a config manages, and the guard
that stops anything re-creating a repo under a name that GitHub redirects.

Why this exists (repo reorg, Nov 2026): today's repos move to `govbot-history`
under new names (`govbot-data/wy-legislation` ->
`govbot-history/wy-legislation-data`). GitHub then redirects the old address
-- git clone, the API and raw files all keep working -- but only until a new
repo takes the old name. apply.py creates every config repo that's missing
from its org, so without this a routine `apply.py --all-states` would
re-create `govbot-data/wy-legislation` and break the redirect for good.

A locale stays in the configs (removing it would drop it from `govbot clone
all`, which is generated from chn-openstates-files.yml) and gets a marker:

    wy:
      template: openstates-to-ocd-files-paused
      moved_to: govbot-history/wy-legislation-data

apply.py, the fleet monitor, close_session.py and rebuild_data_repos.py all
skip or refuse a locale with `moved_to`.
"""

import json
import subprocess
from typing import Callable, Optional, Tuple

MOVED_KEY = "moved_to"

# (returncode, stdout, stderr) of `gh api repos/<owner>/<name>`; injectable so
# the tests never touch the network.
GhRun = Callable[[str], Tuple[int, str, str]]


def _gh_repo(full_repo: str) -> Tuple[int, str, str]:
    result = subprocess.run(
        ["gh", "api", f"repos/{full_repo}"], capture_output=True, text=True
    )
    return result.returncode, result.stdout, result.stderr


def moved_to(locale_cfg) -> str:
    """The `moved_to` value of a locale's config mapping, or "" if not moved."""
    if not isinstance(locale_cfg, dict):
        return ""
    value = locale_cfg.get(MOVED_KEY)
    return str(value).strip() if value else ""


def repo_status(full_repo: str, gh_run: Optional[GhRun] = None) -> Tuple[str, str]:
    """
    What GitHub says about `owner/name`, as (status, detail):

    - ("missing", "")             404: the name is free
    - ("exists", "owner/name")    a repo has this exact name
    - ("redirects", "new/name")   the name redirects to a repo that moved or
                                  was renamed (`gh api` follows the redirect,
                                  so the answer's full_name differs; checked
                                  live 2026-11-27 on chn-openstates-files/...)
    - ("unknown", "<reason>")     anything else (no auth, network, rate limit)
    """
    code, out, err = (gh_run or _gh_repo)(full_repo)
    if code != 0:
        if "HTTP 404" in err or '"status":"404"' in out.replace(" ", ""):
            return "missing", ""
        reason = (err or out).strip().splitlines()
        return "unknown", reason[-1] if reason else f"gh api exited {code}"
    try:
        full_name = json.loads(out)["full_name"]
    except (ValueError, KeyError, TypeError):
        return "unknown", "unreadable answer from gh api"
    if full_name.lower() == full_repo.lower():
        return "exists", full_name
    return "redirects", full_name


def refuse_to_create(
    full_repo: str,
    allow_redirect_to: Optional[str] = None,
    gh_run: Optional[GhRun] = None,
) -> Optional[str]:
    """
    Why `full_repo` must not be created, or None if it's safe.

    Only a confirmed 404 is safe. A name that redirects is refused, since
    creating it would end the redirect. `allow_redirect_to` lets
    close_session.py / rebuild_data_repos.py re-create a name they just moved
    themselves (their design, until the step-5 rewrite): the redirect must
    point at exactly that repo. A name that already exists, or an answer we
    can't read, is refused too: we can't confirm the name is free.
    """
    status, detail = repo_status(full_repo, gh_run)
    if status == "missing":
        return None
    if status == "redirects":
        if allow_redirect_to and detail.lower() == allow_redirect_to.lower():
            return None
        return (
            f"{full_repo} redirects to {detail}: creating it would end that redirect "
            f"(old clones, links and raw URLs would stop reaching {detail}). "
            f"If the locale has moved, mark it `{MOVED_KEY}: {detail}` in the config."
        )
    if status == "exists":
        return f"{full_repo} already exists"
    return f"couldn't confirm {full_repo} is free ({detail})"


def refuse_moved_locale(locale: str, locale_cfg, config_name: str) -> Optional[str]:
    """Error text for close_session.py / rebuild_data_repos.py, or None."""
    target = moved_to(locale_cfg)
    if not target:
        return None
    return (
        f"{locale} has `{MOVED_KEY}: {target}` in {config_name}: its repo has moved "
        f"out of this org. Refusing to transfer, rename or re-create anything for it."
    )
