#!/usr/bin/env python3
"""
One-time audit: how prevalent is redline (strikethrough/underline) markup
in each state's bill PDFs?

Samples up to SAMPLE_SIZE bills per state from govbot-data's most recent
session, downloads each bill's earliest and latest available PDF version
directly from its original government source URL, and runs the same
geometry-based visual-markup check used in production extraction
(actions/extract/utils/pdf_extractor.py's _has_visual_markup).

Not part of the recurring pipeline -- this is research to decide which
states can safely stay on cheap plain-text extraction versus which need
full-fidelity (e.g. vision-LLM) handling by default.

Usage:
    python3 audit_pdf_visual_markup.py [--sample-size N] [--states al,ak,...]

Writes incremental results to audit_pdf_visual_markup_results.jsonl (one
JSON object per checked document) so progress survives a crash/interrupt,
and prints a per-state summary at the end (or run with --summarize-only
to just re-summarize an existing results file).
"""

import argparse
import base64
import json
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.pdf_extractor import _has_visual_markup  # noqa: E402

RESULTS_FILE = Path(__file__).parent / "audit_pdf_visual_markup_results.jsonl"

# Production already prefers text/xml > text/html > application/pdf > text/plain
# (see MEDIA_TYPE_PREFERENCE in utils/text_extraction.py), so states offering an
# HTML/XML/msword alternative never actually hit the PDF path in practice --
# auditing PDF markup for them is moot. This is the "PDF only" list from
# actions/scrape/docs/bill-format-audit.md (2026-07-02); update if that audit
# is refreshed and a state's format mix changes.
PDF_ONLY_STATES = [
    "al", "co", "ct", "dc", "fl", "ga", "gu", "ia", "id", "in", "ky", "la",
    "ma", "md", "me", "mo", "mp", "nc", "nd", "ne", "nv", "ok", "or", "ri",
    "tn", "vi", "vt", "wy",
]

GH_TOKEN = subprocess.run(
    ["gh", "auth", "token"], capture_output=True, text=True, check=True
).stdout.strip()
GH_HEADERS = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"}


def gh_api(path: str):
    r = requests.get(f"https://api.github.com/{path}", headers=GH_HEADERS, timeout=30)
    if r.status_code != 200:
        return None
    return r.json()


def get_all_states() -> list:
    repos = gh_api("orgs/govbot-data/repos?per_page=100")
    if not repos:
        return []
    return sorted(r["name"][: -len("-legislation")] for r in repos if r["name"].endswith("-legislation"))


def list_sample_bills(state: str, limit: int) -> list:
    """Return [(session, bill_dir), ...] from the most recent-looking session."""
    repo = f"govbot-data/{state}-legislation"
    sessions_dir = gh_api(f"repos/{repo}/contents/country:us/state:{state}/sessions")
    if not sessions_dir:
        return []
    sessions = sorted(d["name"] for d in sessions_dir if d["type"] == "dir")
    if not sessions:
        return []
    session = sessions[-1]  # most recent-looking (lexicographic, e.g. "2026" or "20252026")
    bills_dir = gh_api(f"repos/{repo}/contents/country:us/state:{state}/sessions/{session}/bills")
    if not bills_dir:
        return []
    bill_names = [d["name"] for d in bills_dir if d["type"] == "dir"][:limit]
    return [(session, b) for b in bill_names]


def get_metadata(state: str, session: str, bill: str) -> dict:
    repo = f"govbot-data/{state}-legislation"
    path = f"country:us/state:{state}/sessions/{session}/bills/{bill}/metadata.json"
    data = gh_api(f"repos/{repo}/contents/{path}")
    if not data or "content" not in data:
        return None
    try:
        return json.loads(base64.b64decode(data["content"]))
    except Exception:
        return None


def pick_pdf_versions(metadata: dict) -> list:
    """Return up to 2 (note, url) pairs: earliest and latest PDF versions available."""
    pdf_versions = []
    for v in metadata.get("versions", []):
        for link in v.get("links", []):
            if "pdf" in link.get("media_type", "").lower():
                pdf_versions.append((v.get("note", "") or v.get("date", ""), link["url"]))
                break
    if len(pdf_versions) <= 2:
        return pdf_versions
    return [pdf_versions[0], pdf_versions[-1]]


def download_and_check(url: str):
    """Returns True/False for visual markup detected, or None on download/parse failure."""
    try:
        # verify=False matches actions/extract/utils/common.py's own
        # download_with_retry() -- several state legislature sites (e.g.
        # cga.ct.gov, legislature.vermont.gov) serve an incomplete cert
        # chain that strict clients reject even with an up-to-date trust
        # bundle; production already made this tradeoff deliberately.
        resp = requests.get(
            url,
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0 (govbot-audit-script)"},
            verify=False,
        )
        if resp.status_code != 200 or not resp.content:
            return None
        return _has_visual_markup(resp.content)
    except Exception:
        return None


def append_result(record: dict):
    with open(RESULTS_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")


def already_checked() -> set:
    """Set of (state, bill, note) already recorded, for resuming a partial run."""
    if not RESULTS_FILE.exists():
        return set()
    seen = set()
    with open(RESULTS_FILE) as f:
        for line in f:
            try:
                r = json.loads(line)
                seen.add((r["state"], r["bill"], r["note"]))
            except Exception:
                continue
    return seen


def summarize():
    if not RESULTS_FILE.exists():
        print("No results file yet.")
        return
    by_state = defaultdict(list)
    errors = defaultdict(int)
    with open(RESULTS_FILE) as f:
        for line in f:
            r = json.loads(line)
            if r["has_visual_markup"] is None:
                errors[r["state"]] += 1
                continue
            by_state[r["state"]].append(r["has_visual_markup"])

    print(f"\n{'State':<6}{'Checked':<10}{'Markup':<10}{'%':<8}{'Errors'}")
    print("-" * 45)
    total_checked, total_markup = 0, 0
    for state in sorted(by_state):
        vals = by_state[state]
        n_markup = sum(vals)
        pct = 100 * n_markup / len(vals) if vals else 0
        total_checked += len(vals)
        total_markup += n_markup
        print(f"{state:<6}{len(vals):<10}{n_markup:<10}{pct:<7.0f}{errors.get(state, 0)}")
    print("-" * 45)
    overall_pct = 100 * total_markup / total_checked if total_checked else 0
    print(f"{'TOTAL':<6}{total_checked:<10}{total_markup:<10}{overall_pct:<7.0f}{sum(errors.values())}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-size", type=int, default=10)
    parser.add_argument(
        "--states",
        default=None,
        help="Comma-separated state codes; default: the 28 PDF-only states "
        "(others already use HTML/XML in production, see bill-format-audit.md)",
    )
    parser.add_argument(
        "--all-states", action="store_true", help="Audit all 56 states, not just PDF-only ones"
    )
    parser.add_argument("--summarize-only", action="store_true")
    args = parser.parse_args()

    if args.summarize_only:
        summarize()
        return

    if args.states:
        states = args.states.split(",")
    elif args.all_states:
        states = get_all_states()
    else:
        states = PDF_ONLY_STATES
    print(f"Auditing {len(states)} states, up to {args.sample_size} bills each")

    seen = already_checked()

    for state in states:
        bills = list_sample_bills(state, args.sample_size)
        print(f"=== {state}: {len(bills)} bills sampled ===")
        for session, bill in bills:
            metadata = get_metadata(state, session, bill)
            if not metadata:
                continue
            for note, url in pick_pdf_versions(metadata):
                if (state, bill, note) in seen:
                    continue
                markup = download_and_check(url)
                print(f"   {bill} [{note}]: has_visual_markup={markup}")
                append_result(
                    {
                        "state": state,
                        "bill": bill,
                        "note": note,
                        "url": url,
                        "has_visual_markup": markup,
                    }
                )
                time.sleep(0.3)  # be polite to state government servers

    summarize()


if __name__ == "__main__":
    main()
