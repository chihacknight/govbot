#!/usr/bin/env python3
"""Extract each Illinois bill's plain-language synopsis and write the summaries
the dashboard shows as "What this bill is about".

**Why this exists.** Illinois is the one jurisdiction whose dashboard bills read
badly: the stored ``title`` is the ILGA cryptic short-code ("$DFPR-TECH",
"URBAN PROBLEMS-TECH") and govbot's metadata carries *no* abstract, so the
plain-English synopsis — which the General Assembly publishes on every bill's
page and in its full text ("SYNOPSIS AS INTRODUCED: …") — is missing from the
site. Other states already ship a readable ``title``, so this is IL-only.

**What it does.** For each Illinois bill it reads the bill's *full text* (the
PDF linked in that bill's ``metadata.json``, extracted with ``pdftotext`` — the
same poppler tool the elections BOE step already uses), pulls out the
``SYNOPSIS AS INTRODUCED`` section, drops the leading run of bare statute
citations ("New Act", "30 ILCS 105/5.10 new") that reads as noise, and keeps the
prose. The result is written to ``il_summaries.json`` as
``{"il~<session>~<id>": "<synopsis>"}`` — the same ``state~session~id`` key the
frontend's ``billKey`` builds — which the legislation modal prefers over "no
summary available", and the elections page's Illinois cards show as a one-liner.

**Bounded + incremental.** A bill's "as introduced" synopsis never changes, so a
bill once summarized is cached and never fetched again. Each run summarizes at
most ``--cap`` *new* bills, so the ~12.8k IL backlog backfills over successive
twice-daily deploys and steady state costs only the day's new bills. The cache is
carried between deploys by ``actions/cache`` (see deploy-docs.yml).

**Fail-soft everywhere.** A missing PDF link, an unreachable download, ``pdftotext``
absent, or an unparseable document simply leaves that bill unsummarized — never a
crash, never a wrong summary. Pure-stdlib (``urllib`` + a ``pdftotext`` shell-out,
no third-party deps); the parser is a pure function tested offline against real
extracted IL bill text in ``scripts/__snapshots__/il_fulltext/``.

Usage:
    python3 scripts/build_il_summaries.py \
        --data docs/src/dashboard/data.json \
        --cache docs/src/dashboard/il_summaries.json \
        --out docs/src/dashboard/il_summaries.json \
        --cap 1500
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

_UA = "govbot-il-summaries (+https://github.com/chihacknight/govbot)"

# The ILGA synopsis label; the useful prose follows it. Some documents repeat it
# ("SYNOPSIS AS INTRODUCED" then a later "HOUSE AMENDMENT" synopsis) — we take the
# first, which is the bill as introduced.
_SYN_RE = re.compile(r"SYNOPSIS\s+AS\s+INTRODUCED\s*:?\s*", re.IGNORECASE)

# The synopsis ends where the drafting footer / bill body begins. ILGA full text
# closes the synopsis with the "*LRB…*" legislative-reference stamp, then the
# enacting text ("AN ACT concerning…", "A BILL FOR…"). Cut at the first of these.
_SYN_END_RE = re.compile(
    r"\n\s*\*?LRB\d"
    r"|(?<![A-Za-z])AN\s+ACT\b"
    r"|(?<![A-Za-z])A\s+BILL\b"
    r"|(?<![A-Za-z])BE\s+IT\s+ENACTED\b",
    re.IGNORECASE)

# Illinois opens its synopsis with a run of statute citations before any prose:
# "New Act30 ILCS 105/5.10 new  Creates the Climate Change Superfund Act." They
# say nothing to a reader, so drop them and keep the prose. (Mirrors the same
# rule in the govbot-social bill_text.py extractor.)
_IL_CITATION_RUN_RE = re.compile(
    r"^(?=\s*(?:New\s+Act|\d*\s*ILCS))"
    r"(?:\s*(?:New\s+Act|\d*\s*ILCS\s+[\d./A-Za-z-]+|new|rep\.|amend(?:s|ed|ment)?|"
    r"from\s+Ch\.\s*[\d.,\s-]*(?:par\.\s*[\d.,\s-]*)?))+\s*",
    re.IGNORECASE)

# A synopsis worth showing has real prose. Guard against returning a bare citation
# run or a scrap.
_MIN_SYNOPSIS_LEN = 24
_MAX_SYNOPSIS_LEN = 900


def extract_synopsis(full_text, max_len=_MAX_SYNOPSIS_LEN):
    """The plain-language synopsis from an Illinois bill's extracted full text, or
    "" when none can be confidently isolated. Pure and offline-testable."""
    if not full_text:
        return ""
    m = _SYN_RE.search(full_text)
    if not m:
        return ""
    rest = full_text[m.end():]
    end = _SYN_END_RE.search(rest)
    syn = rest[:end.start()] if end else rest
    syn = _IL_CITATION_RUN_RE.sub("", syn, count=1)
    syn = re.sub(r"\s+", " ", syn).strip()
    if len(syn) < _MIN_SYNOPSIS_LEN:
        return ""
    if len(syn) > max_len:
        # Trim to the last sentence boundary within the cap so we never cut a word.
        cut = syn[:max_len]
        dot = cut.rfind(". ")
        syn = (cut[:dot + 1] if dot > max_len // 2 else cut.rstrip()) + ""
        if not syn.endswith((".", "!", "?")):
            syn = syn.rstrip(" ,;:") + "…"
    return syn


def il_bills(data):
    """(session, id, url) for every Illinois bill in the dashboard data.json."""
    out = []
    for b in (data.get("bills") or []):
        if (b.get("state") or "").lower() != "il":
            continue
        out.append((b.get("session") or "", b.get("id") or "", b.get("url") or ""))
    return out


def bill_key(session, bill_id):
    # Must equal the frontend's billKey(): "il~" + encodeURIComponent(session) +
    # "~" + encodeURIComponent(id). safe="" matches encodeURIComponent for the
    # alphanumerics IL uses (and would encode a stray "/" the same way).
    return ("il~" + urllib.parse.quote(session, safe="")
            + "~" + urllib.parse.quote(bill_id, safe=""))


def _bill_dir_id(bill_id):
    """The govbot data repos name each bill dir after the identifier with all
    whitespace removed ("HB 10" -> "HB10")."""
    return re.sub(r"\s+", "", str(bill_id or ""))


def govbot_meta_url(session, bill_id, repo_base):
    return (repo_base.rstrip("/") + "/il-legislation/main/country:us/state:il/sessions/"
            + urllib.parse.quote(session) + "/bills/"
            + urllib.parse.quote(_bill_dir_id(bill_id)) + "/metadata.json")


def pdf_link_from_meta(metadata):
    """The bill's full-text PDF URL from its metadata (versions[].links[] with a
    PDF media type or a .pdf URL), or None."""
    for v in (metadata.get("versions") or []):
        for link in (v.get("links") or []):
            url = link.get("url") or ""
            if link.get("media_type") == "application/pdf" or url.lower().endswith(".pdf"):
                return url
    return None


def _default_get_json(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - govbot-data raw
        return json.loads(r.read().decode("utf-8"))


def _default_get_bytes(url, timeout=45):
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - ILGA PDF
        return r.read()


def pdftotext(pdf_bytes):
    """Extract text from PDF bytes via the poppler `pdftotext` tool (shelled out,
    like the elections BOE step), or "" if it isn't available / fails."""
    if not pdf_bytes:
        return ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(pdf_bytes)
            f.flush()
            out = subprocess.run(["pdftotext", "-layout", f.name, "-"],
                                 capture_output=True, timeout=60)
        return out.stdout.decode("utf-8", "replace") if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def summarize_one(session, bill_id, get_json, get_bytes, pdf_text, repo_base):
    """The synopsis for one IL bill. Returns the synopsis string on success, ``""``
    when the bill *definitively* has none (its metadata carries no PDF link, or the
    extracted text has no synopsis), or ``None`` on a *transient* failure (metadata
    or PDF unreachable, or the text extractor produced nothing — usually poppler
    missing). The caller caches "" (don't retry) but not None (retry next run), so a
    transient outage never poisons the backlog. Every fetcher is injectable so the
    build stays offline-testable."""
    try:
        meta = get_json(govbot_meta_url(session, bill_id, repo_base))
    except Exception as exc:  # noqa: BLE001 - transient: retry next run
        print(f"warning: metadata fetch failed for {bill_id}: {exc}", file=sys.stderr)
        return None
    pdf_url = pdf_link_from_meta(meta) if isinstance(meta, dict) else None
    if not pdf_url:
        return ""  # definitively no full-text PDF to read a synopsis from
    try:
        pdf = get_bytes(pdf_url)
    except Exception as exc:  # noqa: BLE001 - transient: retry next run
        print(f"warning: PDF fetch failed for {bill_id} <{pdf_url}>: {exc}", file=sys.stderr)
        return None
    text = pdf_text(pdf)
    if not text:
        return None  # transient: empty extraction usually means poppler unavailable
    return extract_synopsis(text)


def build(bills, cache, cap, get_json=_default_get_json, get_bytes=_default_get_bytes,
          pdf_text=pdftotext, repo_base="https://raw.githubusercontent.com/govbot-data"):
    """Merge new synopses into ``cache`` (a dict) for up to ``cap`` uncached bills.

    Returns (cache, added, attempted). Only HB/SB-style substantive bills are
    attempted; a bill already in the cache (even with an empty "" — a confirmed
    no-synopsis) is skipped so the backlog only ever moves forward."""
    added = attempted = 0
    for session, bill_id, _url in bills:
        if not session or not bill_id:
            continue
        key = bill_key(session, bill_id)
        if key in cache:
            continue
        if cap is not None and attempted >= cap:
            break
        attempted += 1
        syn = summarize_one(session, bill_id, get_json, get_bytes, pdf_text, repo_base)
        if syn is None:
            continue              # transient failure — leave uncached so it retries next run
        cache[key] = syn          # cache the "" too, so a confirmed no-synopsis isn't retried
        if syn:
            added += 1
    return cache, added, attempted


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", required=True, help="dashboard data.json (source of IL bills)")
    ap.add_argument("--cache", default=None, help="existing il_summaries.json to extend")
    ap.add_argument("--out", required=True, help="output il_summaries.json")
    ap.add_argument("--cap", type=int, default=1500, help="max new bills to summarize this run")
    ap.add_argument("--repo-base", default="https://raw.githubusercontent.com/govbot-data")
    args = ap.parse_args()

    data = json.loads(Path(args.data).read_text())
    cache = {}
    if args.cache and Path(args.cache).exists():
        try:
            cache = json.loads(Path(args.cache).read_text()) or {}
        except (json.JSONDecodeError, OSError) as exc:
            print(f"warning: unreadable cache {args.cache}: {exc}", file=sys.stderr)
    bills = il_bills(data)
    cache, added, attempted = build(bills, cache, args.cap, repo_base=args.repo_base)
    non_empty = sum(1 for v in cache.values() if v)
    Path(args.out).write_text(
        json.dumps(cache, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8")
    print(f"IL summaries: {non_empty} with a synopsis / {len(cache)} known "
          f"({added} new this run, {attempted} attempted) of {len(bills)} IL bills",
          file=sys.stderr)


if __name__ == "__main__":
    main()
