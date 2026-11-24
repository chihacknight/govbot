#!/usr/bin/env python3
"""Audit what structured bill detail the OpenStates scrapers give us for PDF-only states.

Per state: blobless-clone govbot-openstates-scrapers/{st}-legislation, randomly sample
bill files, bulk-fetch just those blobs, keep substantive bills (classification == bill,
non-procedural title), and measure how often each "detail" field is populated.
"""
import json, random, re, subprocess, sys, os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

STATES = "al co ct dc fl ga gu ia id in ky la ma md me mo mp nc nd ne nv ok or ri tn vi vt wy".split()
SAMPLE = 300
WORK = os.environ.get("AUDIT_WORKDIR", "/tmp/pdf-only-audit") + "/repos"
random.seed(42)

PROCEDURAL = re.compile(
    r"\b(rules? of the|adjourn|joint assembly|joint session|honou?ring|congratulat|commend|"
    r"memoriali|in memory of|recogniz|designat\w* .* (day|week|month)|proclaim|"
    r"organization of the|electing|appoint\w* .* committee|per diem|expense[s]? of the legislature|"
    r"legislative (expense|appropriation)|sine die|mourn|condolence|welcom)", re.I)

FIELDS = ["abstracts", "subject", "extras", "other_titles", "documents", "citations",
          "related_bills", "sponsorships", "versions", "votes_inline"]


def git(repo, *args, inp=None):
    return subprocess.run(["git", "-C", repo, *args], input=inp, capture_output=True, check=True).stdout


def load_state(st):
    repo = f"{WORK}/{st}"
    if not os.path.isdir(repo):
        subprocess.run(["git", "clone", "-q", "--filter=blob:none", "--no-checkout",
                        f"https://github.com/govbot-openstates-scrapers/{st}-legislation.git", repo],
                       check=True, capture_output=True)
    tree = git(repo, "ls-tree", "-r", "HEAD", "_data").decode().splitlines()
    oids = [l.split()[2] for l in tree if "/bill_" in l.split("\t")[-1]]
    if not oids:
        return st, len(oids), []
    pick = random.Random(st).sample(oids, min(SAMPLE, len(oids)))
    # one round trip for all sampled blobs (avoid per-blob lazy fetch)
    subprocess.run(["git", "-C", repo, "-c", "fetch.negotiationAlgorithm=noop", "fetch", "-q",
                    "--no-tags", "--no-write-fetch-head", "--filter=blob:none", "origin", *pick],
                   capture_output=True)
    out = git(repo, "cat-file", "--batch", inp="\n".join(pick).encode() + b"\n")
    bills, i = [], 0
    while i < len(out):
        nl = out.index(b"\n", i)
        size = int(out[i:nl].split()[2])
        bills.append(json.loads(out[nl + 1:nl + 1 + size]))
        i = nl + 1 + size + 1
    return st, len(oids), bills


def substantive(b):
    cls = b.get("classification") or []
    return cls == ["bill"] and not PROCEDURAL.search(b.get("title") or "")


def has(b, f):
    if f == "votes_inline":
        return False
    v = b.get(f)
    return bool(v)


def analyze(st, total, bills):
    sub = [b for b in bills if substantive(b)]
    n = len(sub)
    r = {"state": st, "total_bill_files": total, "sampled": len(bills), "substantive": n}
    if not n:
        return r
    for f in FIELDS[:-1]:
        r[f] = round(100 * sum(has(b, f) for b in sub) / n)
    r["extras_keys"] = Counter(k for b in sub for k in (b.get("extras") or {})).most_common(12)
    r["doc_notes"] = Counter(re.sub(r"\d+", "#", d.get("note", ""))[:40] for b in sub
                             for d in b.get("documents") or []).most_common(8)
    r["doc_media"] = Counter(l.get("media_type") for b in sub for d in b.get("documents") or []
                             for l in d.get("links") or []).most_common(5)
    r["ver_media"] = Counter(l.get("media_type") for b in sub for d in b.get("versions") or []
                             for l in d.get("links") or []).most_common(5)
    r["subject_ex"] = Counter(s for b in sub for s in b.get("subject") or []).most_common(5)
    r["abstract_ex"] = next((a.get("abstract", "")[:220] for b in sub for a in b.get("abstracts") or []), "")
    r["avg_actions"] = round(sum(len(b.get("actions") or []) for b in sub) / n, 1)
    r["actions_classified"] = round(100 * sum(1 for b in sub for a in b.get("actions") or [] if a.get("classification"))
                                    / max(1, sum(len(b.get("actions") or []) for b in sub)))
    titles = [b.get("title") or "" for b in sub]
    r["avg_title_len"] = round(sum(map(len, titles)) / n)
    r["title_ex"] = random.Random(st).sample(titles, min(3, n))
    r["sessions"] = Counter(b.get("legislative_session") for b in sub).most_common(3)
    return r


def main():
    os.makedirs(WORK, exist_ok=True)
    results = []
    with ThreadPoolExecutor(8) as ex:
        for st, total, bills in ex.map(lambda s: _safe(s), STATES):
            r = analyze(st, total, bills)
            results.append(r)
            print(st, total, len(bills), r.get("substantive"), file=sys.stderr, flush=True)
    results.sort(key=lambda r: r["state"])
    json.dump(results, open(os.path.dirname(WORK) + "/results.json", "w"), indent=1, default=str)


def _safe(st):
    try:
        return load_state(st)
    except Exception as e:
        print(st, "ERROR", e, file=sys.stderr)
        return st, -1, []


if __name__ == "__main__":
    main()
