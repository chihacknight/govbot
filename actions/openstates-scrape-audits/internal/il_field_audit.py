#!/usr/bin/env python3
"""Illinois field audit: how complete and how accurate is govbot-data/il-legislation?

Answers the three "next steps" from a volunteer's ilga.gov scan (2026-10, see
tamara-notes/state-specific/il.md):

  1. For each metadata.json field we capture, how often is it empty — and when it is,
     does ilga.gov have that information (so the gap is ours), or not?
  2. Which fields does an ilga.gov bill page show that we never capture?
  3. Where both have a value, how often do they differ?

Part 1's counts read every bill's metadata.json (a local clone; a sparse checkout of just
the metadata files is enough). Parts 1–3's ilga.gov checks fetch a stratified sample of
bill-status pages — politely: one request per second, an honest client name, verified TLS
(ilga.gov leaves out its intermediate certificate, completed the way browsers do via
scripts/fetch_sponsor_photos.py — never by switching verification off).

Investigation tooling (internal/), not a production check. The page reader is pure and
offline-tested: python3 il_field_audit.py --self-test

Usage:
    git clone --depth 1 --filter=blob:none --sparse https://github.com/govbot-data/il-legislation.git il
    git -C il sparse-checkout set --no-cone '/country:us/state:il/sessions/104th/bills/*/metadata.json'
    python3 il_field_audit.py --repo il --sample 200
"""

import argparse
import collections
import csv
import html
import json
import random
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "scripts"))
import fetch_sponsor_photos as fsp  # noqa: E402  (verified TLS with the missing-intermediate fix)

SESSION_DIR = "country:us/state:il/sessions/104th/bills"
# ilga.gov (like Michigan's site) answers 403 to a User-Agent containing "bot" or a URL.
USER_AGENT = "chihacknight-civic-data/1.0"
SNAPSHOTS = HERE / "__snapshots__" / "il_field_audit"

# Our metadata.json fields, with what ilga.gov's bill-status page shows for the same thing
# (None = the page has no counterpart, so an empty field there can't be "our" gap).
FIELDS = {
    "title": "short description (page heading)",
    "abstracts": "Synopsis As Introduced",
    "citations": "Statutes Amended In Order of Appearance",
    "sponsorships": "House / Senate Sponsors",
    "actions": "Actions table",
    "versions": "Full Text tab (not fetched; counted from our side only)",
    "documents": "Public Act link + fiscal/other notes (Full Text tab)",
    "subject": None,
    "other_titles": None,
    "related_bills": None,
    "sources": "the bill-status URL itself",
}


# ---------------------------------------------------------------------------------------
# Reading ilga.gov's bill-status page (pure; tested against saved pages)
# ---------------------------------------------------------------------------------------
def _text(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def parse_bill_status(page):
    """The fields an ilga.gov BillStatus page shows, as plain data."""
    out = {"short_description": "", "public_act": "", "sponsors": {}, "statutes": [],
           "synopsis": "", "amendment_synopses": 0, "actions": [], "last_action": ""}
    m = re.search(r'<div class="tab-content[^"]*">.*?<h2 class="h5 fw-bold">(.*?)</h2>', page, re.S)
    if m:
        out["short_description"] = _text(m.group(1))
    m = re.search(r'/PublicActs/View/(\d+-\d+)', page, re.I)
    if m:
        out["public_act"] = m.group(1)
    m = re.search(r'<div id="sponsorDiv">(.*?)</div>', page, re.S)
    if m:
        for chamber, body in re.findall(r'(House|Senate) Sponsors</span>(.*?)(?=<span class="fw-bold[^"]*">(?:House|Senate) Sponsors|$)',
                                        m.group(1), re.S):
            names = [_text(n) for n in re.findall(r'<a class="notranslate"[^>]*>(.*?)</a>', body, re.S)]
            out["sponsors"][chamber.lower()] = names          # first name = chief sponsor
    m = re.search(r'Statutes Amended In Order of Appearance</h2>(.*?)(?:<h2|$)', page, re.S)
    if m:
        out["statutes"] = [_text(a) for a in re.findall(r'<a [^>]*>(.*?)</a>', m.group(1), re.S)]
    m = re.search(r'Synopsis As Introduced</h2>\s*<div[^>]*>\s*<span[^>]*>(.*?)</span>', page, re.S)
    if m:
        out["synopsis"] = _text(m.group(1))
    out["amendment_synopses"] = len(re.findall(r'>(?:House|Senate) (?:Committee |Floor )?Amendment No\. \d+</a></span>\s*<div class="list-group"', page))
    m = re.search(r'>Actions</h2>\s*<table.*?<tbody>(.*?)</tbody>', page, re.S)
    if m:
        for row in re.findall(r'<tr>(.*?)</tr>', m.group(1), re.S):
            cells = [_text(c) for c in re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)]
            if len(cells) >= 3 and re.match(r'\d{1,2}/\d{1,2}/\d{4}$', cells[0]):
                out["actions"].append((_iso(cells[0]), cells[1], cells[2]))
    m = re.search(r'>Last Action</h2>(.*?)</div>\s*</div>', page, re.S)
    if m:
        out["last_action"] = _text(m.group(1))
    return out


def _iso(us_date):
    mo, d, y = us_date.split("/")
    return f"{y}-{int(mo):02d}-{int(d):02d}"


# ---------------------------------------------------------------------------------------
# Our side
# ---------------------------------------------------------------------------------------
def bill_type(identifier):
    m = re.match(r"[A-Z]+", identifier or "")
    return m.group(0) if m else "?"


def is_empty(value):
    return value in (None, "", [], {})


def norm_name(name):
    """'Rep. Katie Stuart' / 'Wayne A. Rosenthal' -> 'katie stuart' / 'wayne rosenthal'."""
    n = re.sub(r"^(rep|sen|representative|senator)\.?\s+", "", (name or "").strip(), flags=re.I)
    n = re.sub(r",?\s*(jr|sr|ii|iii|iv)\.?$", "", n, flags=re.I)
    parts = [p for p in re.split(r"[\s.]+", n.lower()) if len(p) > 1]
    return " ".join(parts)


def norm_text(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def compare(ours, page):
    """Field-by-field comparison of one bill. Returns {check: (status, detail)} where status is
    match / differs / ours_missing / both_missing / not_on_site."""
    r = {}
    t_ours, t_site = norm_text(ours.get("title")), norm_text(page["short_description"])
    r["title"] = (("match" if t_ours == t_site else "differs") if t_site else "not_on_site",
                  f"{ours.get('title')!r} vs {page['short_description']!r}")

    def presence(name, ours_has, site_has, detail=""):
        if ours_has and site_has:
            r[name] = ("match", detail)
        elif site_has:
            r[name] = ("ours_missing", detail)
        elif ours_has:
            r[name] = ("not_on_site", detail)
        else:
            r[name] = ("both_missing", detail)

    presence("synopsis (abstracts)", not is_empty(ours.get("abstracts")), bool(page["synopsis"]),
             page["synopsis"][:120])
    presence("statutes (citations)", not is_empty(ours.get("citations")), bool(page["statutes"]),
             "; ".join(page["statutes"][:3]))

    our_names = {norm_name(s.get("name")) for s in ours.get("sponsorships") or []}
    site_names = {norm_name(n) for names in page["sponsors"].values() for n in names}
    if not site_names:
        r["sponsors"] = ("not_on_site" if our_names else "both_missing", "")
    elif our_names == site_names:
        r["sponsors"] = ("match", f"{len(site_names)} names")
    else:
        r["sponsors"] = ("differs", f"only ours: {sorted(our_names - site_names)}; only ilga.gov: {sorted(site_names - our_names)}")
    chiefs_site = {c: names[0] for c, names in page["sponsors"].items() if names}
    chief_ok = True
    for s in ours.get("sponsorships") or []:
        if s.get("primary") or s.get("classification") == "primary":
            if norm_name(s.get("name")) not in {norm_name(n) for n in chiefs_site.values()}:
                chief_ok = False
    r["chief sponsor"] = (("match" if chief_ok else "differs") if chiefs_site else "not_on_site",
                          f"ilga.gov chiefs: {chiefs_site}")

    our_actions = ours.get("actions") or []
    if page["actions"]:
        same_count = len(our_actions) == len(page["actions"])
        r["action count"] = ("match" if same_count else "differs", f"ours {len(our_actions)} vs ilga.gov {len(page['actions'])}")
        site_last = page["actions"][-1]
        our_last = our_actions[-1] if our_actions else {}
        last_ok = (our_last.get("date", "")[:10] == site_last[0]
                   and norm_text(our_last.get("description")) == norm_text(site_last[2]))
        r["latest action"] = ("match" if last_ok else "differs",
                              f"ours {our_last.get('date', '')[:10]} {our_last.get('description', '')!r} vs ilga.gov {site_last[0]} {site_last[2]!r}")
    else:
        r["action count"] = ("not_on_site" if our_actions else "both_missing", "")

    if page["public_act"]:
        blob = json.dumps(ours.get("actions")) + json.dumps(ours.get("documents"))
        r["public act number"] = ("match" if page["public_act"] in blob or page["public_act"].replace("-", "-0") in blob else "ours_missing",
                                  page["public_act"])
    return r


# ---------------------------------------------------------------------------------------
# Fetching (polite) + the run
# ---------------------------------------------------------------------------------------
def fetch_page(url, retries=3):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    host = urllib.parse.urlsplit(url).hostname
    for attempt in range(retries + 1):
        try:
            with fsp._open_image(req, host, 30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001 - retried, then the bill is reported as unreachable
            if attempt == retries:
                raise
            print(f"  retry {url}: {exc}", file=sys.stderr)
            time.sleep(3 * (attempt + 1))


def stratified_sample(bills, n, seed):
    """Every bill type is represented (min 5 each), the rest proportional; within a type, a
    spread over time (sorted by latest action, then evenly spaced picks)."""
    rnd = random.Random(seed)
    by_type = collections.defaultdict(list)
    for b in bills:
        by_type[bill_type(b["identifier"])].append(b)
    total = len(bills)
    picks = []
    for t, group in sorted(by_type.items()):
        k = min(len(group), max(5, round(n * len(group) / total)))
        group = sorted(group, key=lambda b: ((b.get("actions") or [{}])[-1].get("date", ""), b["identifier"]))
        step = len(group) / k
        picks += [group[min(len(group) - 1, int(i * step + rnd.random() * step))] for i in range(k)]
    return picks


def vote_counts(repo):
    """Vote events are separate files (bills/<id>/logs/*.vote_event.*.json); count per bill from
    the git tree so a metadata-only sparse checkout is enough."""
    try:
        names = subprocess.run(["git", "-C", str(repo), "ls-tree", "-r", "--name-only", "HEAD", SESSION_DIR],
                               capture_output=True, text=True, check=True).stdout.splitlines()
    except Exception:  # noqa: BLE001 - not a git checkout: votes just aren't counted
        return None
    c = collections.Counter()
    for n in names:
        if ".vote_event." in n:
            c[n.split("/")[5]] += 1
    return c


def run(repo, sample_n, seed, out_dir, pause):
    repo = Path(repo)
    bills = []
    for f in sorted((repo / SESSION_DIR).glob("*/metadata.json")):
        bills.append(json.loads(f.read_text(encoding="utf-8")))
    votes = vote_counts(repo)
    print(f"{len(bills)} bills read", file=sys.stderr)

    # 1. completeness on our side, by bill type
    types = collections.Counter(bill_type(b["identifier"]) for b in bills)
    empty = {f: collections.Counter() for f in FIELDS}
    for b in bills:
        for f in FIELDS:
            if is_empty(b.get(f)):
                empty[f][bill_type(b["identifier"])] += 1
    with_votes = sum(1 for b in bills if votes and votes.get(b["identifier"]))
    newest = max(((b.get("actions") or [{}])[-1].get("date", "")[:10]) for b in bills)

    # 2 + 3. ilga.gov sample
    sample = stratified_sample(bills, sample_n, seed)
    rows, unreachable = [], []
    tally = collections.defaultdict(collections.Counter)
    site_fields_seen = collections.Counter()
    for i, b in enumerate(sample, 1):
        url = (b.get("sources") or [{}])[0].get("url", "")
        try:
            page = parse_bill_status(fetch_page(url))
        except Exception as exc:  # noqa: BLE001
            unreachable.append((b["identifier"], str(exc)))
            continue
        for k in ("synopsis", "statutes", "public_act", "amendment_synopses"):
            if page[k]:
                site_fields_seen[k] += 1
        for check, (status, detail) in compare(b, page).items():
            tally[check][status] += 1
            rows.append({"bill": b["identifier"], "check": check, "status": status, "detail": detail, "url": url})
        if i % 25 == 0:
            print(f"  {i}/{len(sample)} pages checked", file=sys.stderr)
        time.sleep(pause)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "il_field_audit.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["bill", "check", "status", "detail", "url"])
        w.writeheader()
        w.writerows(rows)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bills": len(bills), "newest_action": newest, "types": dict(types),
        "empty_by_field": {f: {"total": sum(c.values()), **dict(c)} for f, c in empty.items()},
        "bills_with_vote_files": with_votes if votes is not None else None,
        "sample_size": len(sample), "sample_checked": len(sample) - len(unreachable),
        "unreachable": unreachable, "comparison": {k: dict(v) for k, v in tally.items()},
        "site_fields_seen_in_sample": dict(site_fields_seen),
    }
    (out_dir / "il_field_audit.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


def self_test():
    failures = []

    def check(label, actual, expected):
        if actual != expected:
            failures.append(f"{label}: expected {expected!r}, got {actual!r}")

    p = parse_bill_status((SNAPSHOTS / "HB1062.html").read_text(encoding="utf-8"))
    check("HB1062 short description", p["short_description"], "IL-CENTURY-NETWORK-PRIORITIES")
    check("HB1062 public act", p["public_act"], "104-0166")
    check("HB1062 house sponsors", p["sponsors"].get("house"),
          ["Amy Briel", "Katie Stuart", "Dan Swanson", "Wayne A. Rosenthal", "Hoan Huynh"])
    check("HB1062 senate sponsors", p["sponsors"].get("senate"), ["Rachel Ventura"])
    check("HB1062 statutes", p["statutes"], ["20 ILCS 3921/8 new"])
    check("HB1062 synopsis start", p["synopsis"][:40], "Amends the Illinois Century Network Act.")
    check("HB1062 amendment synopses", p["amendment_synopses"], 1)
    check("HB1062 first action", p["actions"][0], ("2024-12-17", "House", "Prefiled with Clerk by Rep. Katie Stuart"))
    p2 = parse_bill_status((SNAPSHOTS / "HB5816.html").read_text(encoding="utf-8"))
    check("HB5816 no public act", p2["public_act"], "")
    check("HB5816 has actions", len(p2["actions"]) >= 1, True)
    check("norm_name", norm_name("Rep. Wayne A. Rosenthal"), "wayne rosenthal")
    ours = {"title": "IL-CENTURY-NETWORK-PRIORITIES", "abstracts": [], "citations": [],
            "sponsorships": [{"name": "Amy Briel", "primary": True}],
            "actions": [{"date": "2024-12-17", "description": "Prefiled with Clerk by Rep. Katie Stuart"}],
            "documents": []}
    c = compare(ours, p)
    check("compare title", c["title"][0], "match")
    check("compare synopsis gap is ours", c["synopsis (abstracts)"][0], "ours_missing")
    check("compare public act missing", c["public act number"][0], "ours_missing")
    check("compare chief sponsor", c["chief sponsor"][0], "match")
    check("stratified sample covers every type",
          {bill_type(b["identifier"]) for b in stratified_sample(
              [{"identifier": f"HB{i}"} for i in range(50)] + [{"identifier": "AM1"}], 10, 1)}, {"HB", "AM"})
    if failures:
        print(f"❌ {len(failures)} self-test failure(s):", file=sys.stderr)
        for f in failures:
            print(f"   {f}", file=sys.stderr)
        return 1
    print("✅ all self-tests passed")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", help="local il-legislation clone (metadata.json files are enough)")
    ap.add_argument("--sample", type=int, default=200, help="ilga.gov pages to check")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--pause", type=float, default=1.0, help="seconds between ilga.gov requests")
    ap.add_argument("--out-dir", default=str(HERE / "audit_output"))
    ap.add_argument("--self-test", action="store_true", help="offline checks of the page reader")
    args = ap.parse_args()
    if args.self_test:
        sys.exit(self_test())
    if not args.repo:
        ap.error("--repo is required (or use --self-test)")
    run(args.repo, args.sample, args.seed, args.out_dir, args.pause)


if __name__ == "__main__":
    main()
