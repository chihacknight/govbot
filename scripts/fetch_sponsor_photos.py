#!/usr/bin/env python3
"""Vendor sponsor headshots for the bills the dashboard homepage actually shows.

The homepage's "Recent legislative activity" card lists the newest bill per
state and renders each sponsor as a small round photo. Legislator headshots are
public, so this fetches them at deploy time.

**Two public sources, tried in order (a fallback if the first fails):**
  1. **Open States** ``image:`` URL — the canonical headshot, sourced from the
     official legislature site (the same CC0 people repo the name roster uses).
  2. **Wikipedia / Wikimedia Commons** — the page thumbnail, accepted **only
     when Wikipedia confidently describes that person as a legislator from that
     state** (the summary must mention both a legislative role *and* the state
     name; a disambiguation page or a weak match is refused). This guard keeps
     us from ever attaching the wrong face to a real official — when unsure we
     take no photo (the homepage then just doesn't picture that sponsor).

**Deliberately bounded.** We only fetch for the sponsors of the newest bill per
state that the homepage shows (a small cap), not the whole roster. The images
and manifest are *build artifacts*: `.gitignore`d, produced during the Pages
deploy, and published with the site — never committed, so the repo carries no
photo dump.

Output:
  * ``<out-dir>/<state>-<slug(full name)>.<ext>`` — one image per resolved sponsor.
  * ``<manifest>`` — a JSON map ``{"<state>:<full name lower>": "assets/legislators/<file>"}``
    the frontend looks up after it resolves a sponsor to a full name (same
    ``people.json`` matcher legislation.html uses). A sponsor with no entry
    (unresolved name, committee, or no photo from either source) is simply not
    pictured — the homepage shows real photos only, never initials.

Everything is **fail-soft**: a missing people checkout, an unreadable
``data.json``, or a per-image failure skips that piece and never breaks the
deploy.

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
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

_UA = "govbot-photo-vendor (+https://github.com/chihacknight/govbot)"

# State/territory code -> full name, for the Wikipedia correctness guard.
_STATE_NAMES = {
    "al": "Alabama", "ak": "Alaska", "az": "Arizona", "ar": "Arkansas",
    "ca": "California", "co": "Colorado", "ct": "Connecticut", "de": "Delaware",
    "fl": "Florida", "ga": "Georgia", "hi": "Hawaii", "id": "Idaho",
    "il": "Illinois", "in": "Indiana", "ia": "Iowa", "ks": "Kansas",
    "ky": "Kentucky", "la": "Louisiana", "me": "Maine", "md": "Maryland",
    "ma": "Massachusetts", "mi": "Michigan", "mn": "Minnesota", "ms": "Mississippi",
    "mo": "Missouri", "mt": "Montana", "ne": "Nebraska", "nv": "Nevada",
    "nh": "New Hampshire", "nj": "New Jersey", "nm": "New Mexico", "ny": "New York",
    "nc": "North Carolina", "nd": "North Dakota", "oh": "Ohio", "ok": "Oklahoma",
    "or": "Oregon", "pa": "Pennsylvania", "ri": "Rhode Island", "sc": "South Carolina",
    "sd": "South Dakota", "tn": "Tennessee", "tx": "Texas", "ut": "Utah",
    "vt": "Vermont", "va": "Virginia", "wa": "Washington", "wv": "West Virginia",
    "wi": "Wisconsin", "wy": "Wyoming", "dc": "District of Columbia",
    "pr": "Puerto Rico", "gu": "Guam", "vi": "Virgin Islands",
    "as": "American Samoa", "mp": "Northern Mariana Islands",
}

# Words that mark a Wikipedia summary as being about a legislator.
_ROLE_WORDS = (
    "politician", "state representative", "state senator", "state legislator",
    "house of representatives", "state senate", "state assembly", "state house",
    "general assembly", "legislature", "legislator", "assemblymember",
    "assemblyman", "assemblywoman", "delegate", "lawmaker",
)


# ----------------------------------------------------------------------------
# Which bills are "on screen": mirror the homepage's Recent-activity selection
# (newest recorded action first, one bill per state), so we only fetch photos
# for the sponsors the card can actually show, never the whole set.
# ----------------------------------------------------------------------------
def onscreen_bills(bills, per_state=1, max_bills=6):
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


def default_fetch(url, timeout=15, retries=2):
    """GET raw bytes, following redirects, with a couple of retries — an image
    host that blinks (a transient reset/timeout) shouldn't lose the photo."""
    last = None
    for _ in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - https image URLs
                return r.read()
        except Exception as exc:  # noqa: BLE001 - retried, then reported by the caller
            last = exc
    raise last if last else RuntimeError("fetch failed")


def _default_get_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - Wikipedia REST API
        return json.loads(r.read().decode("utf-8"))


def wiki_thumbnail(state, full, get_json=_default_get_json, timeout=15):
    """A Wikimedia thumbnail URL for ``full`` — but only when Wikipedia's page
    summary confidently describes them as a legislator from ``state`` (its text
    mentions both a legislative role *and* the state name, and it isn't a
    disambiguation page). Otherwise None: we would rather show no photo than risk
    attaching the wrong person's face. ``get_json`` is injectable for tests."""
    title = urllib.parse.quote(str(full).strip().replace(" ", "_"))
    try:
        data = get_json("https://en.wikipedia.org/api/rest_v1/page/summary/" + title, timeout)
    except Exception as exc:  # noqa: BLE001 - no page / network error -> no fallback photo
        print(f"warning: wiki lookup failed for {full}: {exc}", file=sys.stderr)
        return None
    if not isinstance(data, dict) or data.get("type") == "disambiguation":
        return None
    blob = ((data.get("description") or "") + " " + (data.get("extract") or "")).lower()
    state_name = _STATE_NAMES.get((state or "").lower(), "")
    is_legislator = any(w in blob for w in _ROLE_WORDS)
    right_place = bool(state_name) and state_name.lower() in blob
    if not (is_legislator and right_place):
        return None
    return ((data.get("thumbnail") or {}).get("source")) or None


def resolve_photo(state, full, os_image, fetch, wiki, max_bytes):
    """Try each public source in turn and return (bytes, source_url) or
    (None, None): (1) the Open States image, then (2) a confidently-matched
    Wikipedia thumbnail. A failure of one method falls through to the next."""
    candidates = []
    if os_image:
        candidates.append(os_image)
    turl = wiki(state, full)
    if turl:
        candidates.append(turl)
    for url in candidates:
        try:
            data = fetch(url)
        except Exception as exc:  # noqa: BLE001 - try the next source
            print(f"warning: fetch failed for {full} <{url}>: {exc}", file=sys.stderr)
            continue
        if data and len(data) <= max_bytes:
            return data, url
    return None, None


def vendor(bills, index, out_dir, manifest_path, fetch=default_fetch,
           wiki=wiki_thumbnail, per_state=1, max_bills=6, max_bytes=3_000_000):
    """Download photos for the on-screen sponsors and write the manifest.

    Returns (downloaded, wanted). ``fetch`` and ``wiki`` are injectable so tests
    stay offline.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Every resolved sponsor is a candidate — even one with no Open States image,
    # since the Wikipedia fallback may still have a photo for them.
    wanted = {}
    for b in onscreen_bills(bills, per_state, max_bills):
        st = b.get("state") or ""
        for name in (b.get("sponsors") or []):
            m = match(st, name, index)
            if not m:
                continue  # unresolved (e.g. a committee) — no photo, not pictured
            _given, full, image = m
            wanted.setdefault(img_key(st, full), (st, full, image or ""))

    manifest, got = {}, 0
    for key, (st, full, os_image) in sorted(wanted.items()):
        data, src = resolve_photo(st, full, os_image, fetch, wiki, max_bytes)
        if not data:
            continue
        fname = f"{st.lower()}-{_slug(full)}{_ext_for(src)}"
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
    ap.add_argument("--per-state", type=int, default=1)
    ap.add_argument("--max-bills", type=int, default=6)
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
