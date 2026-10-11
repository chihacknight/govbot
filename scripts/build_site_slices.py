#!/usr/bin/env python3
"""Split the dashboard's all-bills ``data.json`` into the small files each page needs.

**Why.** ``data.json`` holds every tracked bill (~180k, ~75 MB raw / ~10 MB gzipped). The
homepage, Explore Legislation, Illinois Elections and Search used to download and parse all
of it just to show a handful of bills — 5–9 s per page even on a fast machine. Each page now
reads a slice built here at deploy time:

* ``index.json`` — the jurisdiction list + bill counts, the topic list, and the newest
  ``--recent`` bills per jurisdiction (full records). Feeds the homepage's recent bills, the
  legislation map / list / detail card and its "Recent activity" strip.
* ``<state>.json`` — one jurisdiction's full bill records, loaded only when that state's
  catalog (or one of its bills) is opened on Explore Legislation.
* ``il_recent.json`` — Illinois bills with activity in the last ``--il-days`` days, for the
  elections page's Springfield tabs (which show the last 6 months).
* ``search.json`` — a lean search index for ``search.html`` (state, session, id, title,
  sponsors, topic ids), loaded in the background after the page's other results render.

``data.json`` itself is still built and published (pipelines and direct downloaders use it);
no page fetches it any more.

With ``--downloads-dir`` it also writes the **public downloads** behind Explore Legislation's
"Download the data" panel (``build_downloads``): ``bills-<state>.csv`` per jurisdiction,
``govbot-bills-all.csv.zip`` (every bill in one CSV + ``README.txt``), ``README.txt`` (the
column guide, source and CC BY 4.0 credit) and ``manifest.json`` (each file's rows and bytes, for
scripts). The CSVs are for spreadsheets: UTF-8 with a BOM (Excel shows accents), CRLF, lists
joined with "; ", and a cell that starts like a formula (= + - @) gets a leading ' so a
spreadsheet can't run it. The JSON files stay exactly raw. Pure stdlib; offline-tested in
``test_build_site_slices.py``.

Usage:
    python3 scripts/build_site_slices.py --data docs/src/dashboard/data.json \
        --out-dir docs/src/dashboard/bills --downloads-dir docs/src/dashboard/downloads
"""

import argparse
import csv
import datetime as dt
import io
import json
import sys
import urllib.parse
import zipfile
from collections import defaultdict
from pathlib import Path

RECENT_PER_STATE = 3
IL_RECENT_DAYS = 200


def _newest_first(bills):
    return sorted(bills, key=lambda b: (b.get("latest_action") or "", b.get("id") or ""), reverse=True)


def build_slices(data, recent=RECENT_PER_STATE, il_days=IL_RECENT_DAYS, today=None):
    """Return {filename: object} for every slice. Pure — no I/O."""
    bills = data.get("bills") or []
    by_state = defaultdict(list)
    for b in bills:
        by_state[(b.get("state") or "").lower()].append(b)

    tags = data.get("tags") or []
    tag_ids = {t.get("name"): i for i, t in enumerate(tags)}

    index = {
        "generated_at": data.get("generated_at"),
        "source": data.get("source"),
        "states": data.get("states") or [],
        "empty_jurisdictions": data.get("empty_jurisdictions") or [],
        "tags": tags,
        "counts": {code: len(v) for code, v in sorted(by_state.items()) if code},
        "recent": {code: [b for b in _newest_first(v) if b.get("latest_action")][:recent]
                   for code, v in sorted(by_state.items()) if code},
    }
    out = {"index.json": index}
    for code, v in by_state.items():
        if code:
            out[code + ".json"] = {"generated_at": data.get("generated_at"), "state": code, "bills": v}

    today = today or dt.date.today()
    since = (today - dt.timedelta(days=il_days)).isoformat()
    out["il_recent.json"] = {
        "generated_at": data.get("generated_at"),
        "tags": tags,
        "bills": [b for b in by_state.get("il", []) if (b.get("latest_action") or "")[:10] >= since],
    }
    # Rows, not objects, to keep the index small: [state, session, id, title, sponsors, [tag ids]].
    out["search.json"] = {
        "generated_at": data.get("generated_at"),
        "states": data.get("states") or [],
        "tags": [t.get("name") for t in tags],
        "bills": [[b.get("state") or "", b.get("session") or "", b.get("id") or "", b.get("title") or "",
                   ", ".join(b.get("sponsors") or []),
                   [tag_ids[t] for t in (b.get("tags") or []) if t in tag_ids]] for b in bills],
    }
    return out


SITE = "https://chihacknight.github.io/govbot/"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
CREDIT = "Govbot (Chi Hack Night), https://chihacknight.github.io/govbot/"
CSV_COLUMNS = ["Jurisdiction", "Jurisdiction name", "Session", "Bill", "Title", "Chamber",
               "Last action date", "Last action", "Sponsors", "Topics", "Official link", "Govbot link"]
ALL_CSV = "govbot-bills-all.csv"


def bill_key(b):
    """The state~session~id key behind legislation.html#bill= (same as GB.billKey in
    docs/src/dashboard/assets/govbot-utils.js: each part URI-encoded like encodeURIComponent)."""
    q = lambda v: urllib.parse.quote(str(v or ""), safe="!'()*-._~")
    return q(b.get("state")) + "~" + q(b.get("session")) + "~" + q(b.get("id"))


def _cell(v):
    """One spreadsheet-safe cell: a text that starts like a formula gets a leading ' (so
    Excel/Sheets show it instead of running it — "CSV injection")."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def _csv_bytes(bills, names):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(CSV_COLUMNS)
    for b in bills:
        code = (b.get("state") or "").lower()
        w.writerow([_cell(x) for x in (
            code, names.get(code, code.upper()), b.get("session"), b.get("id"), b.get("title"),
            b.get("chamber"), b.get("latest_action"), b.get("latest_action_desc"),
            "; ".join(b.get("sponsors") or []), "; ".join(b.get("tags") or []), b.get("url"),
            SITE + "dashboard/legislation.html#bill=" + bill_key(b))])
    return buf.getvalue().encode("utf-8-sig")


def _readme(data, total):
    cols = "\n".join("  " + line for line in [
        "Jurisdiction       two/three-letter code (usa = U.S. Congress)",
        "Jurisdiction name  the state, territory or federal government",
        "Session            the legislative session the bill belongs to",
        "Bill               the bill's number as the legislature writes it",
        "Title              the bill's official title",
        "Chamber            lower (House/Assembly), upper (Senate) or legislature (one chamber)",
        "Last action date   date of the latest recorded action (YYYY-MM-DD), blank if none",
        "Last action        what that action was",
        "Sponsors           sponsors and co-sponsors as the legislature lists them, separated by \"; \"",
        "Topics             Govbot's topic tags (AI-assigned), separated by \"; \"",
        "Official link      the bill on the legislature's own site",
        "Govbot link        the bill on Govbot's Explore Legislation page",
    ])
    return (
        "Govbot bill data\n================\n\n"
        f"{total:,} bills, as of {data.get('generated_at') or 'unknown'}.\n"
        f"Source: public government records gathered by the Open States scrapers ({data.get('source') or ''}),\n"
        "tagged by Govbot and refreshed twice a day. Explore it at " + SITE + "dashboard/legislation.html\n\n"
        "License: CC BY 4.0 (" + LICENSE_URL + ").\n"
        "You may share and adapt this data for any purpose, including commercially, as long as you\n"
        "credit: " + CREDIT + "\n\n"
        "Files\n-----\n"
        "  govbot-bills-all.csv.zip  every bill in one CSV (opens in Excel, Google Sheets, Numbers)\n"
        "  bills-<code>.csv          one jurisdiction's bills\n"
        "  manifest.json             every file with its rows and size, for scripts\n"
        "  ../data.json              every bill as JSON; ../bills/<code>.json one jurisdiction as JSON\n"
        "  Full per-bill records (all actions, votes, versions): the govbot-data/<code>-legislation\n"
        "  git repos on GitHub, or `govbot clone all` (see " + SITE + "about.html).\n\n"
        "Columns\n-------\n" + cols + "\n\n"
        "Note: in the CSV files a cell that starts with = + - or @ has a ' added in front so a\n"
        "spreadsheet shows it as text instead of running it as a formula. The JSON files are unchanged.\n"
    )


def build_downloads(data):
    """Return {filename: bytes} for the public downloads. Pure — no I/O."""
    names = {(s.get("code") or "").lower(): s.get("name") or "" for s in data.get("states") or []}
    order = lambda b: ((b.get("state") or "").lower(), str(b.get("session") or ""), str(b.get("id") or ""))
    bills = sorted(data.get("bills") or [], key=order)
    by_state = defaultdict(list)
    for b in bills:
        by_state[(b.get("state") or "").lower()].append(b)
    readme = _readme(data, len(bills)).encode("utf-8")
    out, files = {}, []
    for code in sorted(c for c in by_state if c):
        name = f"bills-{code}.csv"
        out[name] = _csv_bytes(by_state[code], names)
        files.append({"file": name, "jurisdiction": code, "name": names.get(code, code.upper()),
                      "rows": len(by_state[code]), "bytes": len(out[name])})
    # The zip carries a fixed timestamp (the data's own date) so the same data gives the same file.
    stamp = (data.get("generated_at") or "1980-01-01T00:00:00")[:19]
    when = tuple(int(x) for x in stamp.replace("T", "-").replace(":", "-").split("-")[:6])
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
        for fname, payload in ((ALL_CSV, _csv_bytes(bills, names)), ("README.txt", readme)):
            info = zipfile.ZipInfo(fname, date_time=max(when, (1980, 1, 1, 0, 0, 0)))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, payload)
    out[ALL_CSV + ".zip"] = zbuf.getvalue()
    out["README.txt"] = readme
    out["manifest.json"] = (json.dumps({
        "generated_at": data.get("generated_at"), "source": data.get("source"),
        "license": "CC BY 4.0", "license_url": LICENSE_URL, "credit": CREDIT,
        "columns": CSV_COLUMNS, "total_rows": len(bills),
        "all": {"file": ALL_CSV + ".zip", "rows": len(bills), "bytes": len(out[ALL_CSV + ".zip"])},
        "jurisdictions": files,
        "json": {"all": "../data.json", "per_jurisdiction": "../bills/<code>.json"},
    }, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", required=True, help="the dashboard's all-bills data.json")
    ap.add_argument("--out-dir", required=True, help="directory for the slices (replaced)")
    ap.add_argument("--recent", type=int, default=RECENT_PER_STATE)
    ap.add_argument("--il-days", type=int, default=IL_RECENT_DAYS)
    ap.add_argument("--downloads-dir", default=None,
                    help="also write the public CSV/zip downloads here (replaced)")
    args = ap.parse_args()

    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    slices = build_slices(data, recent=args.recent, il_days=args.il_days)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.json"):          # a jurisdiction that dropped out leaves no stale file
        if old.name not in slices:
            old.unlink()
    for name, obj in slices.items():
        (out / name).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n",
                                encoding="utf-8")
    total = sum((out / n).stat().st_size for n in slices)
    print(f"site slices: {len(slices)} files, {total / 1e6:.1f} MB raw "
          f"(index {(out / 'index.json').stat().st_size / 1e3:.0f} KB)", file=sys.stderr)

    if args.downloads_dir:
        files = build_downloads(data)
        dl = Path(args.downloads_dir)
        dl.mkdir(parents=True, exist_ok=True)
        for old in dl.iterdir():            # a jurisdiction that dropped out leaves no stale file
            if old.is_file() and old.name not in files:
                old.unlink()
        for name, payload in files.items():
            (dl / name).write_bytes(payload)
        print(f"downloads: {len(files)} files, {sum(map(len, files.values())) / 1e6:.1f} MB "
              f"(all-bills zip {len(files[ALL_CSV + '.zip']) / 1e6:.1f} MB)", file=sys.stderr)


if __name__ == "__main__":
    main()
