"""
The guard that stops anything from creating a repo under a name GitHub redirects.

After the 2026-11 repo reorg moved today's repos to `govbot-history` under new names,
GitHub redirects their old addresses (git clone, the API and raw files), but only until a
new repo takes the old name. jurisdictions.py creates a repo only after this module
confirms a 404.
"""

import json
import subprocess
from typing import Callable, Optional, Tuple


# (returncode, stdout, stderr) of `gh api repos/<owner>/<name>`; injectable so
# the tests never touch the network.
GhRun = Callable[[str], Tuple[int, str, str]]


def _gh_repo(full_repo: str) -> Tuple[int, str, str]:
    result = subprocess.run(
        ["gh", "api", f"repos/{full_repo}"], capture_output=True, text=True
    )
    return result.returncode, result.stdout, result.stderr


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


def refuse_to_create(full_repo: str, gh_run: Optional[GhRun] = None) -> Optional[str]:
    """
    Why `full_repo` must not be created, or None if it's safe.

    Only a confirmed 404 is safe. A name that redirects is refused, since creating it
    would end the redirect. A name that already exists, or an answer we can't read, is
    refused too: we can't confirm the name is free.
    """
    status, detail = repo_status(full_repo, gh_run)
    if status == "missing":
        return None
    if status == "redirects":
        return (
            f"{full_repo} redirects to {detail}: creating it would end that redirect "
            f"(old clones, links and raw URLs would stop reaching {detail})."
        )
    if status == "exists":
        return f"{full_repo} already exists"
    return f"couldn't confirm {full_repo} is free ({detail})"
