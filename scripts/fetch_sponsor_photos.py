#!/usr/bin/env python3
"""Vendor sponsor headshots for the bills the dashboard homepage actually shows.

The homepage's "Recent legislative activity" card lists the newest bill per
state and renders each sponsor as a small avatar. Legislator headshots are
public (the Open States people repo ships an ``image:`` URL per person, sourced
from the official legislature sites), so this makes the avatars real photos
instead of monograms.

**Deliberately bounded.** We only fetch photos for the sponsors of the newest
few bills per state — a small candidate pool for the homepage strip, not the
whole roster. The homepage shows one bill per state and picks, per state, the
newest bill it has photos for, so every avatar on screen is a real face and
never an initials monogram; the extra depth here is just so that when a state's
very newest bill is committee-sponsored (no photo), the next one can supply the
faces. The downloaded images and the manifest are *build artifacts*:
`.gitignore`d, produced during the Pages deploy, and published with the site.
They are never committed, so the repo carries no photo dump.

Output:
  * ``<out-dir>/<state>-<slug(full name)>.<ext>`` — one image per resolved sponsor.
  * ``<manifest>`` — a JSON map ``{"<state>:<full name lower>": "assets/legislators/<file>"}``
    the frontend looks up after it resolves a sponsor to a full name (same
    ``people.json`` matcher legislation.html uses), falling back to a monogram
    when a sponsor has no entry (an unresolved name, a committee, a failed
    download).

Everything is **fail-soft**: a missing people checkout, an unreadable
``data.json``, or a per-image download error skips that piece and never breaks
the deploy (the frontend just shows monograms). The image source of truth is
the same public-domain (CC0) Open States people repo the name roster uses.

Usage:
    python3 scripts/fetch_sponsor_photos.py \
        --data docs/src/dashboard/data.json \
        --people-dir /tmp/openstates-people \
        --out-dir docs/src/dashboard/assets/legislators \
        --manifest docs/src/dashboard/legislator_images.json
"""

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

import yaml


# ----------------------------------------------------------------------------
# Which bills are "on screen": mirror the homepage's Recent-activity selection
# (newest recorded action first, one bill per state) with a little headroom, so
# every sponsor the card can show has a photo but we never fetch the whole set.
# ----------------------------------------------------------------------------
def onscreen_bills(bills, per_state=3, max_bills=30):
    dated = [b for b in bills if b.get("latest_action")]
    pool = sorted(dated or bills,
                  key=lambda b: str(b.get("latest_action") or ""), reverse=True)
    seen, out = {}, []
    for b in pool:
        st = b.get("state") or ""
        if seen.get(st, 0) >= per_state:
            continue
        seen[st] = seen.get(st, 0) + 1
        out.append(b)
        if len(out) >= max_bills:
            break
    return out


# ----------------------------------------------------------------------------
# Open States people index: {state: {family_lower: [(given, full, image_url)]}}
# ----------------------------------------------------------------------------
def build_index(people_dir):
    data_dir = Path(people_dir) / "data"
    index = {}
    # Federal (data/us) sponsors already arrive with full names and aren't shown
    # in the per-state card; skip to stay lean, matching build_people_roster.
    for state_dir in sorted(p for p in data_dir.glob("*") if p.is_dir() and p.name != "us"):
        leg = state_dir / "legislature"
        if not leg.is_dir():
            continue
        fam = {}
        for yml in sorted(leg.glob("*.yml")):
            try:
                doc = yaml.safe_load(yml.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001 - one bad file mustn't stop the build
                print(f"warning: could not parse {yml}: {exc}", file=sys.stderr)
                continue
            if not isinstance(doc, dict):
                continue
            full = (doc.get("name") or "").strip()
            family = (doc.get("family_name") or "").strip()
            given = (doc.get("given_name") or "").strip()
            image = (doc.get("image") or "").strip()
            if not full or not family:
                continue
            fam.setdefault(family.lower(), []).append((given, full, image))
        if fam:
            index[state_dir.name] = fam
    return index


# Resolve a sponsor to exactly one legislator, or None — the same rules as
# legislation.html's matchLeg (surname-only, "Surname, F", or "First Last",
# disambiguated by first initial). We never guess an ambiguous surname, so the
# keys stay in lockstep with what the frontend resolves.
def match(state, name, index):
    roster = index.get(state)
    if not name or not roster:
        return None
    raw = str(name).strip()
    family, first = raw, ""
    if "," in raw:
        family, _, rest = raw.partition(",")
        family = family.strip()
        first = re.sub(r"[^A-Za-z]", "", rest)
    elif re.search(r"\s", raw):
        parts = raw.split()
        first, family = parts[0], parts[-1]
    cands = roster.get(family.lower())
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0]
    if first:
        fi = first[0].lower()
        hits = [c for c in cands if (c[0] or "").strip()[:1].lower() == fi]
        if len(hits) == 1:
            return hits[0]
    return None  # several share the surname — don't guess


def img_key(state, full):
    return (state or "").lower() + ":" + str(full).strip().lower()


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-") or "x"


def _ext_for(url):
    m = re.search(r"\.(jpg|jpeg|png|webp|gif)(?:\?|#|$)", url, re.I)
    return "." + (m.group(1).lower() if m else "jpg").replace("jpeg", "jpg")


def default_fetch(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "govbot-photo-vendor"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - https image URLs
        return r.read()


def vendor(bills, index, out_dir, manifest_path, fetch=default_fetch,
           per_state=3, max_bills=30, max_bytes=3_000_000):
    """Download photos for the on-screen sponsors and write the manifest.

    Returns (downloaded, wanted). ``fetch`` is injectable so tests stay offline.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Collect the distinct sponsors that have a resolvable photo URL.
    wanted = {}
    for b in onscreen_bills(bills, per_state, max_bills):
        st = b.get("state") or ""
        for name in (b.get("sponsors") or []):
            m = match(st, name, index)
            if not m:
                continue
            _given, full, image = m
            if not image:
                continue
            wanted.setdefault(img_key(st, full), (st, full, image))

    manifest, got = {}, 0
    for key, (st, full, image) in sorted(wanted.items()):
        try:
            data = fetch(image)
        except Exception as exc:  # noqa: BLE001 - a bad image just falls back to a monogram
            print(f"warning: fetch failed for {full} <{image}>: {exc}", file=sys.stderr)
            continue
        if not data or len(data) > max_bytes:
            continue
        fname = f"{st.lower()}-{_slug(full)}{_ext_for(image)}"
        (out_dir / fname).write_bytes(data)
        manifest[key] = f"assets/legislators/{fname}"
        got += 1

    Path(manifest_path).write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8")
    return got, len(wanted)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="dashboard data.json (the bills)")
    ap.add_argument("--people-dir", required=True,
                    help="checkout of github.com/openstates/people (for image URLs)")
    ap.add_argument("--out-dir", required=True, help="where to write the images")
    ap.add_argument("--manifest", required=True, help="where to write the JSON manifest")
    ap.add_argument("--per-state", type=int, default=3)
    ap.add_argument("--max-bills", type=int, default=30)
    args = ap.parse_args(argv)

    try:
        bills = (json.loads(Path(args.data).read_text(encoding="utf-8")) or {}).get("bills", [])
    except Exception as exc:  # noqa: BLE001 - fail-soft: no data, no photos, no crash
        print(f"warning: could not read {args.data}: {exc}; skipping photo vendor", file=sys.stderr)
        return 0
    index = build_index(args.people_dir)
    if not index:
        print("warning: no Open States people index; skipping photo vendor", file=sys.stderr)
        return 0

    got, wanted = vendor(bills, index, args.out_dir, args.manifest,
                         per_state=args.per_state, max_bills=args.max_bills)
    print(f"vendored {got}/{wanted} sponsor photos -> {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
