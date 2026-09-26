#!/usr/bin/env python3
"""Vendor sponsor headshots for the bills the dashboard homepage actually shows.

The homepage's "Recent legislative activity" card lists the newest bill per
state and renders each sponsor as a small round photo. Legislator headshots are
public, so this fetches them at deploy time.

**Three public sources, tried in order (each a fallback if the last found none):**
  1. **Open States** ``image:`` URL — the canonical headshot, sourced from the
     official legislature site (the same CC0 people repo the name roster uses).
  2. **Wikipedia** — the article page thumbnail, accepted **only when Wikipedia
     confidently describes that person as a legislator from that state** (the
     summary must mention both a legislative role *and* the state name; a
     disambiguation page or a weak match is refused). Two guarded lookups: the
     exact ``Full_Name`` page, then Wikipedia's search API for the name + state.
  3. **Wikimedia Commons search** — a real keyless image-search API (``list=search``
     over the File namespace), for the many legislators who have a Commons portrait
     but no Wikipedia *article*. A hit is kept **only when the file's own metadata
     (title, description, categories) carries the person's name *and* a
     state/legislature signal** — the same "never attach the wrong face" gate.

This is the TOS-safe form of "search the web for the photo": every source is a
documented public API, never a scrape of a search engine's result page. When no
source clears its confidence gate we take **no photo** (the homepage then just
doesn't picture that sponsor — it never falls back to initials).

**Deliberately bounded.** We only fetch for the sponsors of the newest bill per
state that the homepage shows (a small cap), not the whole roster — including the
newest **federal** ("usa") bill, whose Congress members carry reliable CC0 photos.
The images
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
import html
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

# Distinctly-federal role phrases — used to confirm a Wikipedia page is about a
# member of the U.S. Congress (federal bills carry no state to cross-check).
_FED_WORDS = (
    "united states representative", "u.s. representative", "us representative",
    "united states senator", "u.s. senator", "us senator",
    "member of congress", "congressman", "congresswoman", "congressperson",
    "united states congress",
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
    # Includes federal (`data/us`) too — those Congress bills DO appear on the
    # homepage (as "USA") and their members carry reliable CC0 headshots. The
    # people repo dir is "us"; `data.json` labels federal bills "usa", so we alias.
    for state_dir in sorted(p for p in data_dir.glob("*") if p.is_dir()):
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
            if state_dir.name == "us":
                index["usa"] = fam   # data.json's federal state code
    return index


def is_federal(state):
    return (state or "").lower() in ("us", "usa")


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


def is_image_bytes(data):
    """True if ``data`` starts with a known raster-image magic number (JPEG, PNG,
    GIF, WebP, BMP). Legislature/CMS image URLs often 200 with an HTML error or
    login page instead of the photo; that HTML must be rejected so we fall through
    to the next source rather than writing a broken 'photo'."""
    if not data or len(data) < 12:
        return False
    if data[:3] == b"\xff\xd8\xff":                       # JPEG
        return True
    if data[:8] == b"\x89PNG\r\n\x1a\n":                  # PNG
        return True
    if data[:6] in (b"GIF87a", b"GIF89a"):               # GIF
        return True
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":    # WebP
        return True
    if data[:2] == b"BM":                                # BMP
        return True
    return False


def default_fetch(url, timeout=15, retries=2):
    """GET raw image bytes, following redirects, with a couple of retries — an
    image host that blinks (a transient reset/timeout) shouldn't lose the photo.

    Hardened for the hotlink-averse legislature/CMS hosts that serve most Open
    States ``image:`` URLs: send a same-origin ``Referer`` and an image ``Accept``
    (many hosts 403 a bare programmatic GET but serve one that looks like an
    <img> load), and reject a non-image body (an HTML block/login page returned
    with a 200) so the caller falls through to the next source."""
    parts = urllib.parse.urlsplit(url)
    referer = "{}://{}/".format(parts.scheme, parts.netloc) if parts.netloc else None
    headers = {
        "User-Agent": _UA,
        "Accept": "image/avif,image/webp,image/png,image/jpeg,image/*,*/*;q=0.8",
    }
    if referer:
        headers["Referer"] = referer
    last = None
    for _ in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - https image URLs
                data = r.read()
            if not is_image_bytes(data):
                raise ValueError("response was not an image (likely an HTML error/block page)")
            return data
        except Exception as exc:  # noqa: BLE001 - retried, then reported by the caller
            last = exc
    raise last if last else RuntimeError("fetch failed")


def _default_get_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - Wikipedia REST API
        return json.loads(r.read().decode("utf-8"))


def _wiki_summary(get_json, title, timeout):
    """Fetch one page summary dict (or None on any failure)."""
    slug = urllib.parse.quote(str(title).strip().replace(" ", "_"))
    try:
        data = get_json("https://en.wikipedia.org/api/rest_v1/page/summary/" + slug, timeout)
    except Exception as exc:  # noqa: BLE001 - no page / network error -> no summary
        print(f"warning: wiki lookup failed for {title}: {exc}", file=sys.stderr)
        return None
    return data if isinstance(data, dict) else None


def _wiki_thumb_if_confident(state, full, data):
    """A thumbnail URL from a summary dict, but only when it confidently describes
    ``full`` as a legislator from ``state``: not a disambiguation page, the
    person's surname appears (so a search hit for a different subject is rejected),
    and — federal: a congressional role phrase; state: a legislative role *and*
    the state name. Otherwise None."""
    if not isinstance(data, dict) or data.get("type") == "disambiguation":
        return None
    thumb = ((data.get("thumbnail") or {}).get("source")) or None
    if not thumb:
        return None
    title = (data.get("title") or "").lower()
    blob = ((data.get("description") or "") + " " + (data.get("extract") or "")).lower()
    # The page must actually be about this person: their surname has to appear in
    # the title or the summary text (guards a search result about someone else).
    parts = str(full).strip().split()
    surname = parts[-1].lower() if parts else ""
    if surname and surname not in title and surname not in blob:
        return None
    # Federal: there's no state to cross-check, so require a distinctly-federal
    # congressional role phrase instead (Congress members are notable, so a
    # full-name page match is reliable).
    if is_federal(state):
        return thumb if any(w in blob for w in _FED_WORDS) else None
    state_name = _STATE_NAMES.get((state or "").lower(), "")
    is_legislator = any(w in blob for w in _ROLE_WORDS)
    right_place = bool(state_name) and state_name.lower() in blob
    return thumb if (is_legislator and right_place) else None


def wiki_thumbnail(state, full, get_json=_default_get_json, timeout=15, search=True):
    """A Wikimedia thumbnail URL for ``full`` — but only when Wikipedia's page
    summary confidently describes them as a legislator from ``state`` (see
    ``_wiki_thumb_if_confident``). Otherwise None: we would rather show no photo
    than risk attaching the wrong person's face.

    Two lookups, each guarded the same way: (1) the exact ``Full_Name`` page, then
    (2) — since many legislators' pages are disambiguated titles like
    "Jane Roe (politician)" that the exact lookup misses — Wikipedia's own search
    API (``rest.php/v1/search/page``, not screen-scraping) for the name plus the
    state and a legislature/congress hint, guarding each of the top hits. This is
    the "search by name + state" step: it finds the right page the way a person
    googling the sponsor would, then applies the same confidence gate so a
    namesake is still rejected. ``get_json`` is injectable for tests."""
    data = _wiki_summary(get_json, full, timeout)
    thumb = _wiki_thumb_if_confident(state, full, data) if data else None
    if thumb or not search:
        return thumb

    hint = "congress" if is_federal(state) else "state legislature"
    state_name = _STATE_NAMES.get((state or "").lower(), "")
    query = " ".join(x for x in (str(full).strip(), state_name, hint) if x)
    url = ("https://en.wikipedia.org/w/rest.php/v1/search/page?limit=5&q="
           + urllib.parse.quote(query))
    try:
        res = get_json(url, timeout)
    except Exception as exc:  # noqa: BLE001 - search unavailable -> no fallback photo
        print(f"warning: wiki search failed for {full}: {exc}", file=sys.stderr)
        return None
    pages = res.get("pages") if isinstance(res, dict) else None
    for pg in (pages or [])[:5]:
        title = (pg.get("key") or pg.get("title")) if isinstance(pg, dict) else None
        if not title:
            continue
        cand = _wiki_summary(get_json, title, timeout)
        thumb = _wiki_thumb_if_confident(state, full, cand) if cand else None
        if thumb:
            return thumb
    return None


_TAG_RE = re.compile(r"<[^>]+>")
_IMG_EXT_RE = re.compile(r"\.(jpe?g|png|webp|gif)$", re.I)
_RASTER_MIMES = ("image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif")


def _strip_html(s):
    """Plain text from a Commons extmetadata value (HTML-unescaped, tags removed)."""
    return _TAG_RE.sub(" ", html.unescape(str(s or ""))).strip()


def _commons_search_url(query):
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": query, "gsrnamespace": "6", "gsrlimit": "8",
        "prop": "imageinfo", "iiprop": "url|extmetadata|mime", "iiurlwidth": "400",
    }
    return "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)


def commons_thumbnail(state, full, get_json=_default_get_json, timeout=15):
    """A Wikimedia Commons image thumbnail for ``full``, found via the Commons
    **search API** (``list=search`` over the File namespace — a real keyless image
    search, not a scrape of a search engine's result page). This reaches the many
    state legislators who have a Commons portrait but no Wikipedia *article*, which
    ``wiki_thumbnail`` can't see.

    A candidate file is kept **only when its own metadata confidently ties it to
    this person and their legislature**: both name tokens (given + surname) appear
    in the file's title/description/categories, *and* — federal: a congressional
    role phrase; state: the state name or a legislative role word. Otherwise None,
    so a same-named file for a different subject is never attached. ``get_json`` is
    injectable for tests."""
    parts = str(full).strip().split()
    if len(parts) < 2:
        return None  # need a given + surname to gate on; a lone token is too risky
    given, surname = parts[0].lower(), parts[-1].lower()
    state_name = _STATE_NAMES.get((state or "").lower(), "")
    hint = "congress" if is_federal(state) else "legislature"
    query = " ".join(x for x in (str(full).strip(), state_name, hint) if x)
    try:
        res = get_json(_commons_search_url(query), timeout)
    except Exception as exc:  # noqa: BLE001 - search unavailable -> no fallback photo
        print(f"warning: commons search failed for {full}: {exc}", file=sys.stderr)
        return None
    pages = ((res.get("query") or {}).get("pages")) if isinstance(res, dict) else None
    if not isinstance(pages, dict):
        return None
    # Preserve the search ranking (the API keys pages by id, but carries 'index').
    ordered = sorted(
        (p for p in pages.values() if isinstance(p, dict)),
        key=lambda p: p.get("index", 1_000_000))
    for pg in ordered:
        title = str(pg.get("title") or "")
        ii = pg.get("imageinfo")
        info = ii[0] if isinstance(ii, list) and ii and isinstance(ii[0], dict) else None
        if not info:
            continue
        mime = str(info.get("mime") or "").lower()
        if mime:
            if mime not in _RASTER_MIMES:
                continue  # not a raster photo (an SVG signature, a PDF, a video)
        elif not _IMG_EXT_RE.search(title):
            continue
        ex = info.get("extmetadata") if isinstance(info.get("extmetadata"), dict) else {}

        def _meta(key):
            v = ex.get(key)
            return _strip_html(v.get("value")) if isinstance(v, dict) else ""
        blob = " ".join([title, _meta("ImageDescription"),
                         _meta("Categories"), _meta("ObjectName")]).lower()
        if surname not in blob or given not in blob:
            continue  # not confidently this person
        if is_federal(state):
            ok = any(w in blob for w in _FED_WORDS)
        else:
            ok = (bool(state_name) and state_name.lower() in blob) \
                or any(w in blob for w in _ROLE_WORDS)
        if not ok:
            continue  # no legislature/state signal -> don't risk the wrong face
        thumb = info.get("thumburl") or info.get("url")
        if thumb:
            return thumb
    return None


def resolve_photo(state, full, os_image, fetch, wiki, max_bytes, commons=None):
    """Try each public source in turn and return (bytes, source_url) or
    (None, None): (1) the Open States image, (2) a confidently-matched Wikipedia
    thumbnail, then (3) a confidently-matched Wikimedia Commons search hit. A
    failure of one method falls through to the next. ``commons`` is optional (and
    injectable) so callers/tests that don't want the Commons step can omit it."""
    candidates = []
    if os_image:
        candidates.append(os_image)
    turl = wiki(state, full)
    if turl:
        candidates.append(turl)
    if commons is not None:
        curl = commons(state, full)
        if curl:
            candidates.append(curl)
    for url in candidates:
        try:
            data = fetch(url)
        except Exception as exc:  # noqa: BLE001 - try the next source
            print(f"warning: fetch failed for {full} <{url}>: {exc}", file=sys.stderr)
            continue
        if data and is_image_bytes(data) and len(data) <= max_bytes:
            return data, url
        if data and not is_image_bytes(data):
            print(f"warning: {full} <{url}> was not an image; skipping", file=sys.stderr)
    return None, None


def vendor(bills, index, out_dir, manifest_path, fetch=default_fetch,
           wiki=wiki_thumbnail, commons=commons_thumbnail,
           per_state=1, max_bills=6, max_bytes=3_000_000):
    """Download photos for the on-screen sponsors and write the manifest.

    Returns (downloaded, wanted). ``fetch``, ``wiki`` and ``commons`` are
    injectable so tests stay offline.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Every resolved sponsor is a candidate — even one with no Open States image,
    # since the Wikipedia / Commons fallbacks may still have a photo for them.
    wanted = {}
    for b in onscreen_bills(bills, per_state, max_bills):
        st = b.get("state") or ""
        for name in (b.get("sponsors") or []):
            m = match(st, name, index)
            if not m:
                continue  # unresolved (e.g. a committee) — no photo, not pictured
            _given, full, image = m
            # The manifest key must equal what the frontend's photoFor() looks up:
            # state bills resolve the sponsor to the people.json roster full name,
            # but federal ("usa") has no people.json roster, so the frontend keys by
            # the RAW sponsor name — mirror that so the lookup hits.
            key_name = name if is_federal(st) else full
            wanted.setdefault(img_key(st, key_name), (st, full, image or ""))

    manifest, got = {}, 0
    for key, (st, full, os_image) in sorted(wanted.items()):
        data, src = resolve_photo(st, full, os_image, fetch, wiki, max_bytes, commons=commons)
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
