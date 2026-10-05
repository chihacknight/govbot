#!/usr/bin/env python3
"""Pull each bill's official plain-language summary from the summary document its
own legislature publishes, for the states whose dashboard bills otherwise just
repeat the title under "What this bill is about".

**Why this exists.** For many states govbot's metadata carries no abstract, so the
legislation modal's summary falls back to restating the bill's title. Several of
those legislatures *do* publish a nonpartisan plain-English summary of every bill,
and Open States already links it in each bill's ``documents`` list — it just
wasn't being read. Illinois has its own builder (``build_il_summaries.py``, which
reads the synopsis out of the full text); this one covers the states whose summary
is a separate linked document:

* **mi** — the House Fiscal Agency "Legislative Analysis" (``SUMMARY:``) or the
  Senate Fiscal Agency analysis (``CONTENT``).
* **tn** — the Fiscal Review Committee fiscal note's ``SUMMARY OF BILL:``.
* **id** — the sponsor's ``STATEMENT OF PURPOSE`` (Idaho's official SOP/fiscal note).
* **la** — House Legislative Services' digest: its ``Abstract:`` one-liner, else the
  "Proposed law…"/"New law…" paragraphs (or a resolution's opening paragraph).

**Never the wrong bill.** A summary is kept only when the document's own header
names this bill's number (``mentions_bill``) — Open States occasionally links a
companion/other bill's document (a Tennessee HB linked to a different SB's fiscal
note), and a mismatched summary would be worse than none.

**Output.** One file per state, ``<out-dir>/<state>.json`` =
``{"<billKey>": ["<summary>", "<source document URL>"]}`` (the frontend's
``billKey`` — ``state~session~id``, each part ``encodeURIComponent``-ed). The modal
loads only the opened bill's state file and links the source document. A bill with
no usable summary is cached as ``["", ""]`` so it isn't retried; a *transient*
failure (metadata/document unreachable, poppler missing) is left uncached so it
retries next run — an outage never poisons the backlog.

**Bounded + incremental.** A bill once summarized is cached and never fetched again.
Each run attempts at most ``--cap`` new bills, newest activity first, so the
backlog fills over successive twice-daily deploys and steady state costs only the
day's new bills. The files are carried between deploys by ``actions/cache``.

Pure stdlib (``urllib`` + a ``pdftotext`` shell-out); the extractors are pure
functions tested offline against real documents in
``scripts/__snapshots__/bill_summaries/`` (``test_build_bill_summaries.py``).

Usage:
    python3 scripts/build_bill_summaries.py \
        --data docs/src/dashboard/data.json \
        --out-dir docs/src/dashboard/summaries --cap 2000
"""

import argparse
import concurrent.futures
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from build_il_summaries import pdftotext

# Michigan's legislature site answers 403 to any User-Agent containing "bot" or a
# URL, so this names the project plainly without either (no browser impersonation).
_UA = "chihacknight-civic-data/1.0"

STATES = ("mi", "tn", "id", "la")

# Which linked document holds the summary, in preference order (first match wins).
DOC_PREFS = {
    "mi": [r"summary as introduced", r"summary of introduced bill", r"summary"],
    "tn": [r"^fiscal note\b"],
    "id": [r"statement of purpose"],
    "la": [r"r[ée]sum[ée] digest", r"digest of .*\boriginal\b", r"^digest of\b"],
}

_MIN_LEN = 40
_MAX_LEN = 900


# --------------------------------------------------------------------------- text

def html_to_text(raw):
    """Readable text from an HTML document (block tags become line breaks)."""
    t = re.sub(r"(?is)<(script|style).*?</\1>", "", raw)
    t = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>|</h\d>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    return html.unescape(t).replace("\xa0", " ")


_BULLET_RE = re.compile(r"^(?:--|[•▪●o]\s|-\s|\d{1,2}[.)]\s)")


def paragraphs(text):
    """Split extracted text into paragraphs: blank lines separate paragraphs, a
    bullet line ("--", "•", "1.") starts a new item, wrapped lines are rejoined."""
    out, cur = [], []
    for line in text.splitlines():
        s = re.sub(r"[ \t]+", " ", line).strip()
        if not s:
            if cur:
                out.append(" ".join(cur)); cur = []
            continue
        if _BULLET_RE.match(s) and cur:
            out.append(" ".join(cur)); cur = []
        cur.append(s)
    if cur:
        out.append(" ".join(cur))
    return out


def _clip(paras, max_len=_MAX_LEN):
    """Join paragraphs (bullets on their own line) and trim on a sentence boundary."""
    lines = []
    for p in paras:
        p = re.sub(r"^(?:--|[•▪●o]|-)\s*", "• ", p) if _BULLET_RE.match(p) else p
        p = re.sub(r"(?<=[a-z.,;)])\s\d{1,2}$", "", p)      # stray footnote marker ("Allegiance. 1")
        lines.append(p)
    s = "\n".join(lines).strip()
    if len(s) <= max_len:
        return s
    cut = s[:max_len]
    end = max(cut.rfind(". "), cut.rfind(".\n"))
    if end > max_len // 2:
        return cut[:end + 1]
    return cut.rstrip(" ,;:\n") + "…"


def _section(text, start_re, end_re):
    """The text between the first ``start_re`` match and the next ``end_re``."""
    m = re.search(start_re, text, re.M)
    if not m:
        return ""
    rest = text[m.end():]
    e = re.search(end_re, rest, re.M)
    return rest[:e.start()] if e else rest


def _done(paras):
    paras = [p for p in paras if p]
    s = _clip(paras)
    return s if len(s) >= _MIN_LEN else ""


# ------------------------------------------------------------- state extractors

_MI_END = (r"^\s*(?:MCL\s|Legislative Analyst|FISCAL IMPACT|PREVIOUS LEGISLATION|BACKGROUND"
           r"|BRIEF DISCUSSION|ARGUMENTS|POSITIONS|SUPPORTING ARGUMENT|OPPOSING ARGUMENT"
           r"|Fiscal Analyst|This analysis was prepared)")


def extract_mi(text, title=""):
    """Michigan HFA ("SUMMARY:") or SFA ("CONTENT") analysis → its summary prose."""
    sec = _section(text, r"^\s*SUMMARY:?\s*$|^\s*SUMMARY:", _MI_END)
    if not sec:
        sec = _section(text, r"^\s*CONTENT\s*$", _MI_END)
    return _done(paragraphs(sec)[:6])


def extract_tn(text, title=""):
    """Tennessee fiscal note → the "SUMMARY OF BILL:" paragraph."""
    sec = _section(text, r"SUMMARY OF (?:ORIGINAL )?BILL:\s*",
                   r"^\s*(?:ESTIMATED )?FISCAL IMPACT|^\s*IMPACT TO COMMERCE|^\s*SUMMARY OF AMENDMENT")
    return _done(paragraphs(sec)[:3])


def extract_id(text, title=""):
    """Idaho Statement of Purpose → its prose (drops the "RS12345 / H0001" line)."""
    sec = _section(text, r"STATEMENT OF PURPOSE\s*$", r"^\s*FISCAL NOTE\s*$|^\s*DISCLAIMER:")
    # The routing-slip line ("RS33713 / H0963") sometimes wraps into the prose paragraph.
    paras = [re.sub(r"^RS\s?\d+\S*(?:\s*/\s*\S+)?\s*", "", p) for p in paragraphs(sec)]
    return _done(paras[:3])


_LA_STOP = re.compile(r"^\(?(?:Adds|Amends|Repeals|Enacts)\b.*R\.S\.|^Summary of |^Effective\b"
                      r"|^Committee Amendments|^House Floor Amendments|^Senate Committee Amendments")
_LA_LAW = re.compile(r"^(?:Proposed|New) law\b")


def _words(s):
    return set(re.findall(r"[a-z0-9]+", (s or "").lower()))


def similar(a, b, threshold=0.75):
    """True when ``a`` mostly restates ``b`` (share of a's words found in b)."""
    wa, wb = _words(a), _words(b)
    return bool(wa) and len(wa & wb) / len(wa) >= threshold


def extract_la(text, title=""):
    """Louisiana digest → the "Abstract:" line (unless it just restates the title),
    else the "Proposed/New law" paragraphs, else (a resolution) the first paragraph
    after the session header line."""
    ab = _done(paragraphs(_section(text, r"^\s*Abstract:\s*", r"^\s*$"))[:1])
    if ab and not similar(ab, title):
        return ab
    paras = paragraphs(text)
    body = []
    for i, p in enumerate(paras):
        if re.search(r"\b(?:Regular|Extraordinary|First|Second) (?:Extraordinary )?Session\b", p):
            body = paras[i + 1:]
            break
    out = []
    for p in body:
        if _LA_STOP.match(p):
            break
        out.append(p)
    # A "…composed as follows:" lead-in loses its list once paragraphs are picked, so skip it.
    law = [p for p in out if _LA_LAW.match(p) and not p.rstrip().endswith(":")]
    return _done(law[:3]) or ab or _done(out[:1])


EXTRACTORS = {"mi": extract_mi, "tn": extract_tn, "id": extract_id, "la": extract_la}


# ------------------------------------------------------------------ bill checks

def mentions_bill(text, bill_id, head_chars=1500):
    """True when the document's header names this bill ("H.B. 4301", "House Bill
    4301", "HB 492", "RS33705 / H0921", "HB 2000 - SB 2318") — the guard against a
    record that links some other bill's document."""
    m = re.match(r"\s*([A-Za-z])[A-Za-z. ]*?(\d+)", str(bill_id or ""))
    if not m:
        return False
    letter, num = m.group(1), str(int(m.group(2)))
    pat = r"\b%s[^\n]{0,30}?(?<!\d)0*%s(?!\d)" % (re.escape(letter), num)
    return re.search(pat, text[:head_chars], re.I) is not None


def pick_document(state, meta):
    """(note, url) of the bill's summary document, or None. Prefers HTML over PDF."""
    docs = [d for d in (meta.get("documents") or []) if isinstance(d, dict)]
    for pref in DOC_PREFS.get(state, []):
        for d in docs:
            if re.search(pref, d.get("note") or "", re.I):
                links = [l for l in (d.get("links") or []) if l.get("url")]
                if not links:
                    continue
                html_l = [l for l in links if (l.get("media_type") or "").startswith("text/html")]
                return d.get("note") or "", (html_l or links)[0]["url"]
    return None


# ------------------------------------------------------------------- keys/urls

def bill_key(state, session, bill_id):
    # Must equal the frontend's billKey(): encodeURIComponent of each part.
    q = lambda s: urllib.parse.quote(str(s or ""), safe="!'()*")
    return q(state) + "~" + q(session) + "~" + q(bill_id)


def govbot_meta_url(state, session, bill_id, repo_base):
    return (repo_base.rstrip("/") + "/" + state + "-legislation/main/country:us/state:" + state
            + "/sessions/" + urllib.parse.quote(session) + "/bills/"
            + urllib.parse.quote(re.sub(r"\s+", "", str(bill_id or ""))) + "/metadata.json")


def _get(url, timeout=45):
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - public legislature docs
        return r.read()


def default_fetch_json(url):
    return json.loads(_get(url, timeout=25).decode("utf-8"))


def default_fetch_text(url):
    """Text of a summary document (PDF via pdftotext, else HTML), "" if unreadable."""
    raw = _get(url)
    if raw[:4] == b"%PDF":
        return pdftotext(raw)
    return html_to_text(raw.decode("utf-8", "replace"))


# ------------------------------------------------------------------------ build

def summarize_one(state, session, bill_id, fetch_json, fetch_text, repo_base, title=""):
    """[summary, url] for one bill; ["", ""] when it definitively has none (no
    summary document, or one that names another bill / yields no prose); None on a
    transient failure (retry next run)."""
    try:
        meta = fetch_json(govbot_meta_url(state, session, bill_id, repo_base))
    except Exception as exc:  # noqa: BLE001 - transient
        print(f"warning: metadata fetch failed for {state} {bill_id}: {exc}", file=sys.stderr)
        return None
    doc = pick_document(state, meta) if isinstance(meta, dict) else None
    if not doc:
        return ["", ""]
    _note, url = doc
    try:
        text = fetch_text(url)
    except Exception as exc:  # noqa: BLE001 - transient
        print(f"warning: document fetch failed for {state} {bill_id} <{url}>: {exc}", file=sys.stderr)
        return None
    if not text or not text.strip():
        return None   # usually poppler missing — transient
    if not mentions_bill(text, bill_id):
        return ["", ""]
    s = EXTRACTORS[state](text, title)
    return [s, url] if s else ["", ""]


def candidates(data, states, cache):
    """(state, session, id, title) of every uncached bill in ``states``, newest activity first."""
    bills = [b for b in (data.get("bills") or []) if (b.get("state") or "") in states
             and b.get("session") and b.get("id")]
    bills.sort(key=lambda b: b.get("latest_action") or "", reverse=True)
    per = {}
    for b in bills:
        st = b["state"]
        if bill_key(st, b["session"], b["id"]) not in cache.get(st, {}):
            per.setdefault(st, []).append((st, b["session"], b["id"], b.get("title") or ""))
    # Round-robin across states so one busy state can't use up the whole cap.
    out, queues = [], [per[s] for s in sorted(per)]
    i = 0
    while any(queues):
        q = queues[i % len(queues)]
        if q:
            out.append(q.pop(0))
        i += 1
    return out


def build(data, cache, cap, states=STATES, fetch_json=default_fetch_json,
          fetch_text=default_fetch_text, repo_base="https://raw.githubusercontent.com/govbot-data",
          workers=6):
    """Fill ``cache`` ({state: {billKey: [summary, url]}}) for up to ``cap`` new bills.
    Returns (cache, added, attempted)."""
    for st in states:
        cache.setdefault(st, {})
    todo = candidates(data, set(states), cache)
    if cap is not None:
        todo = todo[:cap]

    def one(item):
        st, session, bid, title = item
        return item, summarize_one(st, session, bid, fetch_json, fetch_text, repo_base, title)

    added = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        for (st, session, bid, _title), res in ex.map(one, todo):
            if res is None:
                continue
            cache[st][bill_key(st, session, bid)] = res
            added += 1 if res[0] else 0
    return cache, added, len(todo)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", required=True, help="dashboard data.json")
    ap.add_argument("--out-dir", required=True, help="directory of <state>.json files (read as cache, rewritten)")
    ap.add_argument("--states", default=",".join(STATES))
    ap.add_argument("--cap", type=int, default=2000, help="max new bills to attempt this run")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--repo-base", default="https://raw.githubusercontent.com/govbot-data")
    args = ap.parse_args()

    states = [s for s in args.states.split(",") if s in EXTRACTORS]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = {}
    for st in states:
        f = out_dir / f"{st}.json"
        if f.exists():
            try:
                cache[st] = json.loads(f.read_text()) or {}
            except (json.JSONDecodeError, OSError) as exc:
                print(f"warning: unreadable cache {f}: {exc}", file=sys.stderr)
    data = json.loads(Path(args.data).read_text())
    cache, added, attempted = build(data, cache, args.cap, states=states,
                                    repo_base=args.repo_base, workers=args.workers)
    for st in states:
        (out_dir / f"{st}.json").write_text(
            json.dumps(cache[st], ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8")
        have = sum(1 for v in cache[st].values() if v and v[0])
        print(f"{st}: {have} summaries / {len(cache[st])} known", file=sys.stderr)
    print(f"bill summaries: {added} new this run ({attempted} attempted)", file=sys.stderr)


if __name__ == "__main__":
    main()
