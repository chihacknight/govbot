#!/usr/bin/env python3
"""Give each govbot-data/<code>-legislation repo a clear description, a homepage and topics.

Search engines and AI assistants read a repo's description, homepage and topics first.
Run by an organization admin, once, with the GitHub CLI signed in (`gh auth login`):

    python3 .github/data-repo-setup/set_repo_metadata.py            # shows what would change
    python3 .github/data-repo-setup/set_repo_metadata.py --apply    # changes it
    python3 .github/data-repo-setup/set_repo_metadata.py --apply il mn   # only these

Safe to re-run. It only ever:
  * replaces a description that is still the placeholder "🏛️ XX legislative data pipeline"
    (a hand-written description is left alone),
  * fills in the homepage when it is empty,
  * ADDS topics (the pipeline's own govbot-scraper-* / govbot-session-* topics stay untouched).
The README is not touched: the pipeline-manager writes it from templates.
"""
import argparse
import json
import subprocess
import sys

ORG = "govbot-data"
HOMEPAGE = "https://chihacknight.github.io/govbot/"

# code -> (name used in the description, topic for the place)
JURISDICTIONS = {
    "al": ("Alabama", "alabama"), "ak": ("Alaska", "alaska"), "az": ("Arizona", "arizona"),
    "ar": ("Arkansas", "arkansas"), "ca": ("California", "california"), "co": ("Colorado", "colorado"),
    "ct": ("Connecticut", "connecticut"), "de": ("Delaware", "delaware"), "fl": ("Florida", "florida"),
    "ga": ("Georgia", "georgia-state"), "hi": ("Hawaii", "hawaii"), "id": ("Idaho", "idaho"),
    "il": ("Illinois", "illinois"), "in": ("Indiana", "indiana"), "ia": ("Iowa", "iowa"),
    "ks": ("Kansas", "kansas"), "ky": ("Kentucky", "kentucky"), "la": ("Louisiana", "louisiana"),
    "me": ("Maine", "maine"), "md": ("Maryland", "maryland"), "ma": ("Massachusetts", "massachusetts"),
    "mi": ("Michigan", "michigan"), "mn": ("Minnesota", "minnesota"), "ms": ("Mississippi", "mississippi"),
    "mo": ("Missouri", "missouri"), "mt": ("Montana", "montana"), "ne": ("Nebraska", "nebraska"),
    "nv": ("Nevada", "nevada"), "nh": ("New Hampshire", "new-hampshire"), "nj": ("New Jersey", "new-jersey"),
    "nm": ("New Mexico", "new-mexico"), "ny": ("New York", "new-york"), "nc": ("North Carolina", "north-carolina"),
    "nd": ("North Dakota", "north-dakota"), "oh": ("Ohio", "ohio"), "ok": ("Oklahoma", "oklahoma"),
    "or": ("Oregon", "oregon"), "pa": ("Pennsylvania", "pennsylvania"), "ri": ("Rhode Island", "rhode-island"),
    "sc": ("South Carolina", "south-carolina"), "sd": ("South Dakota", "south-dakota"),
    "tn": ("Tennessee", "tennessee"), "tx": ("Texas", "texas"), "ut": ("Utah", "utah"),
    "vt": ("Vermont", "vermont"), "va": ("Virginia", "virginia"), "wa": ("Washington State", "washington-state"),
    "wv": ("West Virginia", "west-virginia"), "wi": ("Wisconsin", "wisconsin"), "wy": ("Wyoming", "wyoming"),
    "dc": ("District of Columbia", "washington-dc"), "gu": ("Guam", "guam"),
    "mp": ("Northern Mariana Islands", "northern-mariana-islands"), "pr": ("Puerto Rico", "puerto-rico"),
    "vi": ("U.S. Virgin Islands", "us-virgin-islands"), "usa": ("U.S. Congress (federal)", "congress"),
}

SHARED_TOPICS = [
    "legislation", "legislative-data", "open-data", "government-data", "civic-tech",
    "bills", "govbot", "openstates",
]


def placeholder(code):
    return f"🏛️ {code.upper()} legislative data pipeline"


def description(code):
    name = JURISDICTIONS[code][0]
    return (f"{name} legislation as plain files you can clone: every bill with its sponsors, "
            f"actions and full text. Open data from Govbot, by Chi Hack Night. CC BY 4.0.")


def plan(code, current):
    """What to change for one repo. `current` = {description, homepage, topics} as GitHub has it."""
    changes = {}
    if (current.get("description") or "").strip() in ("", placeholder(code)):
        changes["description"] = description(code)
    if not (current.get("homepage") or "").strip():
        changes["homepage"] = HOMEPAGE
    have = set(current.get("topics") or [])
    add = [t for t in SHARED_TOPICS + [JURISDICTIONS[code][1]] if t not in have]
    if add:
        changes["add_topics"] = add
    return changes


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def current_state(repo):
    d = json.loads(gh("api", f"repos/{repo}"))
    return {"description": d.get("description"), "homepage": d.get("homepage"), "topics": d.get("topics") or []}


def apply_changes(repo, changes, current):
    fields = [f"{k}={changes[k]}" for k in ("description", "homepage") if k in changes]
    if fields:
        gh("api", "-X", "PATCH", f"repos/{repo}", *[a for f in fields for a in ("-f", f)])
    if "add_topics" in changes:  # the topics endpoint replaces the whole list, so send old + new
        names = current["topics"] + changes["add_topics"]
        gh("api", "-X", "PUT", f"repos/{repo}/topics", *[a for n in names for a in ("-f", f"names[]={n}")])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="make the changes (default: only show them)")
    ap.add_argument("codes", nargs="*", help="only these jurisdiction codes, e.g. il mn usa")
    args = ap.parse_args()
    codes = [c.lower() for c in args.codes] or list(JURISDICTIONS)
    unknown = [c for c in codes if c not in JURISDICTIONS]
    if unknown:
        sys.exit(f"Unknown code(s): {', '.join(unknown)}")
    failed = 0
    for code in codes:
        repo = f"{ORG}/{code}-legislation"
        try:
            current = current_state(repo)
            changes = plan(code, current)
            if not changes:
                print(f"{repo}: already done")
                continue
            print(f"{repo}: {json.dumps(changes, ensure_ascii=False)}")
            if args.apply:
                apply_changes(repo, changes, current)
        except subprocess.CalledProcessError as e:
            failed += 1
            print(f"{repo}: FAILED ({(e.stderr or '').strip() or e})", file=sys.stderr)
    if not args.apply:
        print("\nNothing was changed. Re-run with --apply to make these changes.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
