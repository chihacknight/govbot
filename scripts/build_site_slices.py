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
no page fetches it any more. Pure stdlib; offline-tested in ``test_build_site_slices.py``.

Usage:
    python3 scripts/build_site_slices.py --data docs/src/dashboard/data.json \
        --out-dir docs/src/dashboard/bills
"""

import argparse
import datetime as dt
import json
import sys
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


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", required=True, help="the dashboard's all-bills data.json")
    ap.add_argument("--out-dir", required=True, help="directory for the slices (replaced)")
    ap.add_argument("--recent", type=int, default=RECENT_PER_STATE)
    ap.add_argument("--il-days", type=int, default=IL_RECENT_DAYS)
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


if __name__ == "__main__":
    main()
