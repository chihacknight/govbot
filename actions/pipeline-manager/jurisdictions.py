#!/usr/bin/env python3
"""
Session repo pairs from jurisdictions.yml (repo reorg, step 5). Replaces apply.py.

Every `sessions:` entry of a state in jurisdictions.yml is one pair:

    govbot-openstates-scrapers/<st>-<id>-scraper   runs the OpenStates scrapers with session=<id>
    govbot-data/<st>-<id>                          the formatted bills for that session

    python3 jurisdictions.py plan  [--session tx-90r ...]   dry run; reads GitHub, writes nothing
    python3 jurisdictions.py render [-o DIR]                render every pair's files (offline)
    python3 jurisdictions.py apply --session tx-90r ...     create or update the named pairs

What it will and won't do:
- It only ever writes to the session pairs it generates. A state's `old_repos` (status
  `history` or `manual`) are never written: the tool refuses any target that is one of them.
- It never deletes a repository. There is no delete code in this file (a test checks).
  Updating a pair replaces its `.github/` folder with the rendered one; data is untouched.
- It creates a repo only after moved.refuse_to_create confirms the name is free (a 404),
  so a name that redirects to a moved repo is never taken. Repos are created public: the
  orgs' secrets are shared with public repos.
- It updates a repo only when GitHub answers with exactly that name (no redirect).
"""

import argparse
import contextlib
import importlib.util
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "jurisdictions.yml"
MARKER_OPEN, MARKER_CLOSE = "✏️{", "}✏️"
SESSION_ID = re.compile(r"^[A-Za-z0-9._-]+$")
SCRAPERS = re.compile(r"^[a-z_]+( [a-z_]+)*$")
CRON = re.compile(r"^\S+ \S+ \S+ \S+ \S+$")
RUNNERS = {  # jurisdictions.yml runner -> the templates' (runner, force_self_hosted)
    "github": ("ubuntu-latest", "false"),
    "proxy": ("self-hosted", "false"),
    "self-hosted": ("self-hosted", "true"),
}
OVERRIDABLE = {"scrapers", "runner", "scrape_timeout_minutes", "docker_image", "toolkit_branch",
               "extract_runner"}


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


render_mod = _load("render")
moved_mod = _load("moved")


def pair_key(state, session_id):
    """<state>-<id> lower-cased; characters outside [a-z0-9._-] become '-'."""
    return re.sub(r"[^a-z0-9._-]", "-", f"{state}-{session_id}".lower())


class ConfigError(SystemExit):
    pass


def load_pairs(config):
    """Every session pair in the config, fully resolved; raises ConfigError on bad input."""
    orgs, defaults = config["orgs"], config["defaults"]
    old = set()
    for st, entry in config["states"].items():
        for kind in ("scraper", "data"):
            old.add(entry["old_repos"][kind].lower())
    pairs, seen = [], set()
    for st, entry in config["states"].items():
        for sess in entry.get("sessions") or []:
            sid = str(sess["id"])
            where = f"{st} {sid}"
            if not SESSION_ID.match(sid):
                raise ConfigError(f"❌ {where}: session id has characters a repo name can't hold")
            unknown = set(sess) - OVERRIDABLE - {"id", "schedule"}
            if unknown:
                raise ConfigError(f"❌ {where}: unknown session fields {sorted(unknown)}")
            s = {**defaults, **{k: v for k, v in entry.items() if k in OVERRIDABLE},
                 **{k: v for k, v in sess.items() if k in OVERRIDABLE}}
            schedule = sess.get("schedule", entry.get("scrape_cron"))
            if schedule != "manual" and not (schedule and CRON.match(str(schedule))):
                raise ConfigError(f"❌ {where}: schedule must be a 5-field cron or 'manual'")
            if not SCRAPERS.match(str(s["scrapers"])):
                raise ConfigError(f"❌ {where}: scrapers must be space-separated scraper names")
            if s["runner"] not in RUNNERS:
                raise ConfigError(f"❌ {where}: runner must be one of {sorted(RUNNERS)}")
            key = pair_key(st, sid)
            scraper_full, data_full = f"{orgs['scraper']}/{key}-scraper", f"{orgs['data']}/{key}"
            for full in (scraper_full, data_full):
                if full.lower() in old:
                    raise ConfigError(f"❌ {where}: {full} is an old repo; the tool never writes to those")
                if full.lower() in seen:
                    raise ConfigError(f"❌ {where}: {full} is generated twice")
                seen.add(full.lower())
            pairs.append({
                "key": key, "state": st, "session": sid, "name": entry["name"],
                "schedule": schedule, "settings": s,
                "repo_secrets": entry.get("repo_secrets") or [],
                "scraper_full": scraper_full, "data_full": data_full, "data_org": orgs["data"],
            })
    return pairs, old


def render_pair(pair, out_dir):
    """Render both repos of a pair into out_dir/<owner>/<repo>/; returns {full name: folder}."""
    s = pair["settings"]
    runner, force = RUNNERS[s["runner"]]
    extract_runner = RUNNERS[s.get("extract_runner", "github")][0]
    manual = pair["schedule"] == "manual"
    extra = [
        f"name={pair['name']} ({pair['session']})",
        f"label={pair['state']} {pair['session']}",
        f"scrape_session={pair['session']}",
        f"scrapers={'' if s['scrapers'] == 'bills' else s['scrapers']}",
        f"scrape_cron={'' if manual else pair['schedule']}",
        f"scrape_timeout_minutes={s['scrape_timeout_minutes']}",
        f"data_org={pair['data_org']}",
        f"data_repo={pair['key']}",
        f"scraper_repo={pair['scraper_full']}",
        "config_file=jurisdictions.yml",
        "config_tool=jurisdictions.py",
    ]
    plan = [
        (pair["scraper_full"], "openstates-scrape-paused" if manual else "openstates-scrape", runner),
        (pair["data_full"], "openstates-to-ocd-files", extract_runner),
    ]
    out = {}
    for full, template, run_on in plan:
        folder = Path(out_dir) / full
        if folder.exists():
            shutil.rmtree(folder)
        tdir = HERE / "templates" / template
        for src in sorted(p for p in tdir.rglob("*") if p.is_file() and not p.name.startswith(".")):
            dest = folder / src.relative_to(tdir)
            if dest.suffix == ".j2":
                dest = dest.with_suffix("")
            with contextlib.redirect_stdout(io.StringIO()):
                render_mod.render_template(str(src), str(dest), pair["state"], s["toolkit_branch"],
                                           "true", run_on, force, s["docker_image"], extra,
                                           MARKER_OPEN, MARKER_CLOSE)
        leftover = [str(p) for p in folder.rglob("*") if p.is_file() and MARKER_OPEN in p.read_text()]
        if leftover:
            raise ConfigError(f"❌ unrendered template markers in {leftover}")
        out[full] = folder
    return out


def run(cmd, cwd=None):
    """Run a command (a list, never a shell string); raise on failure."""
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True).stdout


def check_target(full, old):
    """Refuse to write anywhere but a generated pair."""
    if full.lower() in old:
        raise SystemExit(f"❌ {full} is an old repo (history or manual); refusing to write to it")


def create_repo(full, folder, old, description, gh_run=None):
    check_target(full, old)
    reason = moved_mod.refuse_to_create(full, gh_run=gh_run)
    if reason:
        print(f"  ❌ not creating {full}: {reason}")
        return False
    run(["gh", "repo", "create", full, "--public", "--description", description])
    push_files(full, folder, "Initial files from jurisdictions.yml")
    print(f"  ✅ created {full}")
    return True


def update_repo(full, folder, old, gh_run=None):
    check_target(full, old)
    status, detail = moved_mod.repo_status(full, gh_run)
    if status != "exists":
        print(f"  ❌ not updating {full}: GitHub says {status} {detail}".rstrip())
        return False
    push_files(full, folder, "chore: update workflow files from jurisdictions.yml")
    return True


def push_files(full, folder, message):
    """Copy the rendered files into the repo; .github/ is replaced as a whole."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        run(["git", "clone", "--depth", "1", "--quiet", f"https://github.com/{full}.git", str(repo)])
        if (repo / ".github").exists():
            shutil.rmtree(repo / ".github")
        for src in folder.rglob("*"):
            if src.is_file():
                dest = repo / src.relative_to(folder)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
        run(["git", "add", "-A"], cwd=repo)
        if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo).returncode == 0:
            print(f"  ℹ️  {full}: no changes")
            return
        run(["git", "-c", "user.name=github-actions[bot]",
             "-c", "user.email=github-actions[bot]@users.noreply.github.com",
             "commit", "-q", "-m", message], cwd=repo)
        run(["git", "push", "-q", "origin", "HEAD:main"], cwd=repo)
        print(f"  ✅ pushed {full}")


WANTED = re.compile(
    r"^\s*(name: (OpenStates Scrape|Format Data|Text Extraction)|- cron:|STATE_CODE:|SCRAPER_REPO:|"
    r"session: \$|scrapers:|owner:|repositories:|gh api \"repos/.*dispatches|workflows: \[|"
    r"timeout-minutes:|uses: chihacknight)")


def describe(folder):
    for wf in sorted((folder / ".github" / "workflows").glob("*.yml")):
        text = wf.read_text()
        yield wf.name, [l.strip() for l in text.splitlines() if WANTED.match(l)], \
            sorted(set(re.findall(r"secrets\.([A-Z_]+)", text)))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=["plan", "render", "apply"])
    ap.add_argument("-c", "--config", default=str(CONFIG))
    ap.add_argument("-o", "--out", default=str(HERE / "generated" / "jurisdictions"))
    ap.add_argument("--session", action="append", default=[], help="pair key, e.g. tx-90r")
    args = ap.parse_args(argv)

    config = yaml.safe_load(Path(args.config).read_text())
    pairs, old = load_pairs(config)
    if args.session:
        unknown = set(args.session) - {p["key"] for p in pairs}
        if unknown:
            raise SystemExit(f"❌ no such session pair: {sorted(unknown)}")
        pairs = [p for p in pairs if p["key"] in args.session]
    elif args.command == "apply":
        raise SystemExit("❌ apply needs --session for each pair to create or update")

    for pair in pairs:
        rendered = render_pair(pair, args.out)
        print(f"\n═══ {pair['key']}: {pair['name']}, session {pair['session']}")
        if args.command == "render":
            for full, folder in rendered.items():
                print(f"  {full}: {folder}")
            continue
        for full, folder in rendered.items():
            status, detail = moved_mod.repo_status(full)
            if args.command == "plan":
                if status == "missing":
                    what = "name free (404) → would create, public"
                elif status == "exists":
                    what = "exists → would update .github/ and README"
                else:
                    what = f"would NOT touch: {status} {detail}"
                print(f"\n  {full}  [{what}]")
                for name, lines, secrets in describe(folder):
                    print(f"    {name}:")
                    for line in lines:
                        print(f"      {line}")
                    print(f"      secrets: {', '.join(secrets)}")
            else:
                desc = f"🏛️ {pair['name']}, session {pair['session']}"
                if status == "missing":
                    create_repo(full, folder, old, desc)
                else:
                    update_repo(full, folder, old)
        if args.command == "plan" and pair["repo_secrets"]:
            print(f"\n  set by hand on {pair['scraper_full']}: {', '.join(pair['repo_secrets'])}")


if __name__ == "__main__":
    main()
