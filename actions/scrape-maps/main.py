#!/usr/bin/env python3
"""Build compact district maps for the Elections Happening in IL page.

Fetches official boundary polygons, keyed to the elections seed's race ids, and
writes a small, pre-projected `docs/src/dashboard/maps.json` the dashboard can
draw as an inline-SVG locator next to each race. There are two coordinate
spaces in one file:

  * "chicago" — a city map (all wards as a light context) for the Chicago-scale
    races: alderperson wards and police-district councils.
  * "illinois" — a statewide silhouette (the IL state outline as context) for
    the General Assembly and congressional races, whose districts span the whole
    state; each district is highlighted on the silhouette so a reader can see
    where in Illinois it sits.

Every district also carries the **Chicago neighborhoods (community areas) it
touches** — computed by sampling a grid inside the district and classifying each
interior point by community area — so the card can name the hoods on that ballot.
A statewide district that never reaches Chicago simply carries an empty list.

Sources (all public, keyless APIs):
  * Wards (2023-)            -> City of Chicago portal p293-wvbd (property: ward)
  * Police Districts         -> City of Chicago portal 24zt-jpfn (property: dist_num)
  * Community areas (77)     -> City of Chicago portal igwz-8jzy (property: community)
  * IL Senate / House (2026) -> Census TIGERweb Legislative layers 1 / 2 (SLDU/SLDL)
  * IL congressional (120th) -> Census TIGERweb Legislative layer 0 (CD120)
  * IL state outline         -> Census TIGERweb State_County layer 0 (States)
CPS board electoral subdistrict (1A-10B) boundaries are not published as a usable
polygon layer by any authority, so those races carry no polygon (the page
degrades gracefully) — geometry is never invented.

Design (see CLAUDE.md):
  * Python standard library only. Fail-soft: any fetch/parse error yields an
    empty layer, never a crash; the deploy keeps the committed maps.json when the
    fresh run produced nothing.
  * Geometry is simplified (Douglas-Peucker) and projected to a shared integer
    viewbox at build time, so the browser just draws SVG paths — no mapping
    library, no runtime projection, offline-friendly.
  * Pure helpers (rdp, project_ring, to_path, neighborhood overlap, id mappers)
    are unit-tested offline (--self-test).

Usage:
    python3 actions/scrape-maps/main.py --output docs/src/dashboard/maps.json
    python3 actions/scrape-maps/main.py --self-test        # offline geometry tests
"""

import argparse
import json
import math
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
SEED_PATH = HERE.parent / "scrape-elections" / "elections_seed.json"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
FETCH_TIMEOUT = 90

# City of Chicago Data Portal (Socrata geospatial export -> GeoJSON)
PORTAL = "https://data.cityofchicago.org/api/geospatial/{}?method=export&format=GeoJSON"
WARDS_ID = "p293-wvbd"
POLICE_ID = "24zt-jpfn"
COMMAREA_ID = "igwz-8jzy"

# Census TIGERweb ArcGIS REST (keyless GeoJSON query). maxAllowableOffset trims
# vertices server-side (degrees) before our own RDP so payloads stay small.
TIGER_LEG = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Legislative/MapServer/{lyr}/query"
TIGER_SC = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/{lyr}/query"
SLDU_LAYER = 1   # 2026 State Legislative Districts - Upper (IL Senate)
SLDL_LAYER = 2   # 2026 State Legislative Districts - Lower (IL House)
CD_LAYER = 0     # 120th Congressional Districts
STATE_LAYER = 0  # States
IL_FIPS = "17"

VIEW_W = 1000          # projected coordinate space width; height set by aspect
SIMPLIFY_EPS = 1.2     # Douglas-Peucker tolerance (chicago space, ~px of 1000)
SIMPLIFY_EPS_IL = 2.2  # looser for the statewide silhouette (whole state in 1000px)
MIN_RING_AREA = 4.0    # drop islands/slivers smaller than this (projected units^2)

# Server-side simplification tolerances (degrees) — TIGERweb trims vertices with
# maxAllowableOffset before our own RDP, so payloads stay small.
SIMPLIFY_EPS_IL_DEG = 0.0015   # statewide districts
STATE_SIMPLIFY_DEG = 0.004     # the state outline (coarser is fine)

# Neighborhood overlap sampling
GRID_N = 64            # grid points per axis over a district's Chicago overlap
HOOD_MIN_SHARE = 0.04  # keep a community area with >= this share of interior points
HOOD_MIN_COUNT = 3     # ...and at least this many points (drops sliver clips)
HOOD_CAP = 16          # cap the stored list (frontend shows first few + "N more")


# --------------------------------------------------------------------------- #
# network
# --------------------------------------------------------------------------- #
def _fetch(url):
    req = urllib.request.Request(url, headers={"user-agent": UA, "accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as err:  # network / TLS / parse — non-fatal
        print(f"warning: fetch failed {url}: {err}", file=sys.stderr)
        return None


def fetch_geojson(dataset_id):
    return _fetch(PORTAL.format(dataset_id))


def fetch_tiger(base, layer, where, simplify):
    params = [
        "where=" + urllib.parse.quote(where),
        "f=geojson", "outFields=*", "returnGeometry=true",
        "outSR=4326", "geometryPrecision=5",
        "maxAllowableOffset=" + str(simplify),
    ]
    return _fetch(base.format(lyr=layer) + "?" + "&".join(params))


# --------------------------------------------------------------------------- #
# geometry helpers (pure, unit-tested)
# --------------------------------------------------------------------------- #
def _perp_dist(p, a, b):
    """Perpendicular distance from point p to segment a-b."""
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def rdp(points, eps):
    """Ramer-Douglas-Peucker polyline simplification."""
    if len(points) < 3:
        return points[:]
    dmax, idx = 0.0, 0
    for i in range(1, len(points) - 1):
        d = _perp_dist(points[i], points[0], points[-1])
        if d > dmax:
            dmax, idx = d, i
    if dmax > eps:
        left = rdp(points[:idx + 1], eps)
        right = rdp(points[idx:], eps)
        return left[:-1] + right
    return [points[0], points[-1]]


def ring_area(points):
    """Absolute shoelace area of a ring."""
    a = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0


def to_path(ring):
    """SVG path 'M x y L x y ... Z' from integer-rounded points."""
    if not ring:
        return ""
    pts = [f"{round(x)},{round(y)}" for x, y in ring]
    return "M" + " L".join(pts) + "Z"


def point_in_rings(x, y, rings):
    """Even-odd ray cast over every ring (handles multi-piece polygons + holes):
    a point is inside the shape when a rightward ray crosses an odd number of
    edges across all rings combined."""
    inside = False
    for ring in rings:
        n = len(ring)
        j = n - 1
        for i in range(n):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if (yi > y) != (yj > y):
                xint = (xj - xi) * (y - yi) / (yj - yi) + xi
                if x < xint:
                    inside = not inside
            j = i
    return inside


def rings_bbox(rings):
    minx = miny = float("inf")
    maxx = maxy = float("-inf")
    for ring in rings:
        for x, y in ring:
            minx, maxx = min(minx, x), max(maxx, x)
            miny, maxy = min(miny, y), max(maxy, y)
    return (minx, miny, maxx, maxy)


# --------------------------------------------------------------------------- #
# projection
# --------------------------------------------------------------------------- #
def _iter_rings(geom):
    """Yield exterior rings ([[lon,lat],...]) from a Polygon/MultiPolygon."""
    if not geom:
        return
    t = geom.get("type")
    if t == "Polygon":
        for ring in geom.get("coordinates", []):
            yield ring
    elif t == "MultiPolygon":
        for poly in geom.get("coordinates", []):
            for ring in poly:
                yield ring


def geom_rings(geom):
    """All rings of a geometry as a list (lon/lat), for overlap tests."""
    return [ring for ring in _iter_rings(geom)]


def bbox_of(features):
    minx = miny = float("inf")
    maxx = maxy = float("-inf")
    for f in features:
        for ring in _iter_rings(f.get("geometry")):
            for lon, lat in ring:
                minx, maxx = min(minx, lon), max(maxx, lon)
                miny, maxy = min(miny, lat), max(maxy, lat)
    return (minx, miny, maxx, maxy)


def make_projector(bbox, width=VIEW_W):
    """Equirectangular projection from lon/lat into a [0,width] x [0,height] box
    (y flipped for screen), with longitude compressed by cos(mean latitude) so
    the map isn't stretched. Returns (project(lon,lat)->(x,y), width, height)."""
    minx, miny, maxx, maxy = bbox
    mean_lat = math.radians((miny + maxy) / 2.0)
    xscale = math.cos(mean_lat) or 1.0
    span_x = (maxx - minx) * xscale
    span_y = (maxy - miny)
    if span_x <= 0 or span_y <= 0:
        return (lambda lon, lat: (0.0, 0.0)), width, width
    height = width * (span_y / span_x)

    def project(lon, lat):
        x = ((lon - minx) * xscale) / span_x * width
        y = height - ((lat - miny) / span_y * height)
        return (x, y)

    return project, width, height


def project_ring(ring, project, eps=SIMPLIFY_EPS):
    """Project a lon/lat ring to screen space and simplify; None if too small."""
    pts = [project(lon, lat) for lon, lat in ring]
    if len(pts) > 2 and pts[0] != pts[-1]:
        pts.append(pts[0])
    simplified = rdp(pts, eps)
    if len(simplified) < 4 or ring_area(simplified) < MIN_RING_AREA:
        return None
    return simplified


def feature_paths(geom, project, eps=SIMPLIFY_EPS):
    out = []
    for ring in _iter_rings(geom):
        s = project_ring(ring, project, eps)
        if s:
            out.append(to_path(s))
    return out


# --------------------------------------------------------------------------- #
# neighborhoods (Chicago community areas a district touches)
# --------------------------------------------------------------------------- #
def _nice_name(raw):
    """Title-case a community-area name ('NEAR WEST SIDE' -> 'Near West Side'),
    keeping the couple of Chicago-specific casings readable."""
    s = " ".join(w.capitalize() for w in str(raw).split())
    fixes = {"Ohare": "O'Hare", "O'hare": "O'Hare", "Mckinley": "McKinley"}
    return " ".join(fixes.get(w, w) for w in s.split())


def build_ca_index(commarea_geo):
    """[(nice_name, rings_lonlat, bbox), ...] for the 77 community areas."""
    idx = []
    for f in (commarea_geo or {}).get("features", []):
        rings = geom_rings(f.get("geometry"))
        if not rings:
            continue
        name = _nice_name(f.get("properties", {}).get("community") or "")
        if not name:
            continue
        idx.append((name, rings, rings_bbox(rings)))
    return idx


def district_neighborhoods(district_rings, ca_index, chicago_bbox):
    """Community areas a district overlaps, most-covered first. Samples a grid
    over the district's intersection with Chicago and classifies each interior
    point by community area. Returns [] for a district that never reaches the
    city (statewide/downstate)."""
    if not district_rings or not ca_index:
        return []
    dminx, dminy, dmaxx, dmaxy = rings_bbox(district_rings)
    cminx, cminy, cmaxx, cmaxy = chicago_bbox
    # overlap of district bbox with Chicago bbox
    ox0, oy0 = max(dminx, cminx), max(dminy, cminy)
    ox1, oy1 = min(dmaxx, cmaxx), min(dmaxy, cmaxy)
    if ox0 >= ox1 or oy0 >= oy1:
        return []
    counts = {}
    total = 0
    for gx in range(GRID_N):
        x = ox0 + (ox1 - ox0) * (gx + 0.5) / GRID_N
        for gy in range(GRID_N):
            y = oy0 + (oy1 - oy0) * (gy + 0.5) / GRID_N
            if not point_in_rings(x, y, district_rings):
                continue
            for name, rings, (bx0, by0, bx1, by1) in ca_index:
                if x < bx0 or x > bx1 or y < by0 or y > by1:
                    continue
                if point_in_rings(x, y, rings):
                    counts[name] = counts.get(name, 0) + 1
                    total += 1
                    break
    if not total:
        return []
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    keep = [n for n, c in ranked if c >= HOOD_MIN_COUNT and c / total >= HOOD_MIN_SHARE]
    return keep[:HOOD_CAP]


# --------------------------------------------------------------------------- #
# race-id mappers (pure)
# --------------------------------------------------------------------------- #
def _ward_race_id(props):
    raw = props.get("ward") or props.get("ward_id")
    try:
        return f"chicago-alderperson-ward-{int(raw):02d}"
    except (TypeError, ValueError):
        return None


def _police_race_id(props):
    raw = props.get("dist_num") or props.get("district")
    try:
        return f"chicago-police-district-council-{int(raw):03d}"
    except (TypeError, ValueError):
        return None


def _senate_race_id(props):
    raw = props.get("SLDU") or props.get("BASENAME")
    try:
        return f"il-senate-{int(raw):02d}"
    except (TypeError, ValueError):
        return None


def _house_race_id(props):
    raw = props.get("SLDL") or props.get("BASENAME")
    try:
        return f"il-house-{int(raw):03d}"
    except (TypeError, ValueError):
        return None


def _cong_race_id(props):
    raw = props.get("CD120") or props.get("BASENAME")
    try:
        return f"us-house-il-{int(raw):02d}"
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #
def _seed_race_ids():
    try:
        seed = json.loads(SEED_PATH.read_text())
        return {r["id"] for r in seed.get("races", [])}
    except (OSError, json.JSONDecodeError):
        return set()


def _statewide_features(geo, id_fn, label_fn, kind):
    """Yield (race_id, label, kind, rings_lonlat, geom) for a TIGER layer."""
    for f in (geo or {}).get("features", []):
        props = f.get("properties", {})
        rid = id_fn(props)
        if not rid:
            continue
        geom = f.get("geometry")
        rings = geom_rings(geom)
        if not rings:
            continue
        yield rid, label_fn(props), kind, rings, geom


def build(wards_geo, police_geo, commarea_geo, senate_geo, house_geo, cong_geo,
          state_geo, now):
    """Assemble maps.json. Chicago space comes from the ward layer; the Illinois
    space from the state outline. Every kept district is keyed to its race id
    with its space, paths and the Chicago neighborhoods it touches."""
    wards = (wards_geo or {}).get("features", [])
    if not wards:
        return None  # no basemap -> nothing to draw; keep committed maps.json
    valid = _seed_race_ids()

    ca_index = build_ca_index(commarea_geo)
    chicago_bbox = bbox_of((commarea_geo or {}).get("features", []) or wards)

    def hoods(rings):
        return district_neighborhoods(rings, ca_index, chicago_bbox)

    # ---- Chicago space (wards context + ward/police districts) ----
    cproj, cw, ch = make_projector(bbox_of(wards))
    context = []
    districts = {}

    for f in wards:
        paths = feature_paths(f.get("geometry"), cproj)
        context.extend(paths)
        rid = _ward_race_id(f.get("properties", {}))
        if rid and (not valid or rid in valid) and paths:
            num = int(f["properties"].get("ward") or f["properties"].get("ward_id"))
            districts[rid] = {"kind": "ward", "space": "chicago",
                              "label": f"Ward {num}", "paths": paths,
                              "neighborhoods": hoods(geom_rings(f.get("geometry")))}

    for f in (police_geo or {}).get("features", []):
        rid = _police_race_id(f.get("properties", {}))
        if not rid or (valid and rid not in valid):
            continue
        paths = feature_paths(f.get("geometry"), cproj)
        if paths:
            num = int(f["properties"].get("dist_num"))
            districts[rid] = {"kind": "police_district", "space": "chicago",
                              "label": f"Police District {num:03d}", "paths": paths,
                              "neighborhoods": hoods(geom_rings(f.get("geometry")))}

    # ---- Illinois space (state silhouette context + statewide districts) ----
    il_view = None
    il_context = []
    state_feats = (state_geo or {}).get("features", [])
    if state_feats:
        iproj, iw, ih = make_projector(bbox_of(state_feats))
        for f in state_feats:
            il_context.extend(feature_paths(f.get("geometry"), iproj, SIMPLIFY_EPS_IL))
        il_view = {"w": round(iw), "h": round(ih)}

        statewide = [
            (senate_geo, _senate_race_id, lambda p: "Senate District " + str(int(p.get("SLDU") or p.get("BASENAME"))), "il_senate"),
            (house_geo, _house_race_id, lambda p: "House District " + str(int(p.get("SLDL") or p.get("BASENAME"))), "il_house"),
            (cong_geo, _cong_race_id, lambda p: "IL Congressional District " + str(int(p.get("CD120") or p.get("BASENAME"))), "us_house"),
        ]
        for geo, id_fn, label_fn, kind in statewide:
            for rid, label, knd, rings, geom in _statewide_features(geo, id_fn, label_fn, kind):
                if valid and rid not in valid:
                    continue
                paths = feature_paths(geom, iproj, SIMPLIFY_EPS_IL)
                if not paths:
                    continue
                districts[rid] = {"kind": knd, "space": "illinois",
                                  "label": label, "paths": paths,
                                  "neighborhoods": hoods(rings)}

    doc = {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": ("City of Chicago Data Portal (wards p293-wvbd, police 24zt-jpfn, "
                   "community areas igwz-8jzy) + US Census TIGERweb "
                   "(IL SLDU/SLDL/CD, state outline)"),
        "view": {"w": round(cw), "h": round(ch)},
        "context": context,
        "districts": districts,
    }
    if il_view:
        doc["il_view"] = il_view
        doc["il_context"] = il_context
    return doc


# --------------------------------------------------------------------------- #
# offline self-test (no network)
# --------------------------------------------------------------------------- #
def self_test():
    import unittest

    SQUARE = {"type": "Polygon", "coordinates": [[[-87.7, 41.8], [-87.6, 41.8],
                                                  [-87.6, 41.9], [-87.7, 41.9], [-87.7, 41.8]]]}

    class T(unittest.TestCase):
        def test_rdp_collapses_collinear(self):
            pts = [(0, 0), (1, 0.0001), (2, 0), (3, 0)]
            self.assertEqual(rdp(pts, 0.1), [(0, 0), (3, 0)])

        def test_rdp_keeps_corner(self):
            pts = [(0, 0), (1, 5), (2, 0)]
            self.assertEqual(len(rdp(pts, 0.1)), 3)

        def test_area_unit_square(self):
            self.assertAlmostEqual(ring_area([(0, 0), (0, 2), (2, 2), (2, 0)]), 4.0)

        def test_projector_corners(self):
            proj, w, h = make_projector((-1, 41, 1, 42))
            x0, y0 = proj(-1, 41)
            x1, y1 = proj(1, 42)
            self.assertAlmostEqual(x0, 0.0, places=3)
            self.assertAlmostEqual(y0, h, places=3)   # min lat at bottom
            self.assertAlmostEqual(x1, w, places=3)
            self.assertAlmostEqual(y1, 0.0, places=3)  # max lat at top

        def test_to_path_closed(self):
            self.assertTrue(to_path([(0, 0), (10, 0), (10, 10)]).endswith("Z"))

        def test_point_in_rings(self):
            sq = [[(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]]
            self.assertTrue(point_in_rings(5, 5, sq))
            self.assertFalse(point_in_rings(15, 5, sq))

        def test_id_mappers(self):
            self.assertEqual(_senate_race_id({"SLDU": "058"}), "il-senate-58")
            self.assertEqual(_house_race_id({"SLDL": "081"}), "il-house-081")
            self.assertEqual(_cong_race_id({"CD120": "09"}), "us-house-il-09")
            self.assertEqual(_ward_race_id({"ward": "3"}), "chicago-alderperson-ward-03")
            self.assertEqual(_police_race_id({"dist_num": "14"}), "chicago-police-district-council-014")

        def test_nice_name(self):
            self.assertEqual(_nice_name("NEAR WEST SIDE"), "Near West Side")
            self.assertEqual(_nice_name("OHARE"), "O'Hare")
            self.assertEqual(_nice_name("MCKINLEY PARK"), "McKinley Park")

        def test_neighborhoods_overlap(self):
            # Two community areas side by side; a district covering the left one.
            left = [[(-87.7, 41.8), (-87.65, 41.8), (-87.65, 41.9), (-87.7, 41.9), (-87.7, 41.8)]]
            right = [[(-87.65, 41.8), (-87.6, 41.8), (-87.6, 41.9), (-87.65, 41.9), (-87.65, 41.8)]]
            ca_index = [("Left Side", left, rings_bbox(left)), ("Right Side", right, rings_bbox(right))]
            chicago_bbox = (-87.7, 41.8, -87.6, 41.9)
            dist = left  # district == the left CA
            hoods = district_neighborhoods(dist, ca_index, chicago_bbox)
            self.assertEqual(hoods, ["Left Side"])
            # a district far outside Chicago -> no neighborhoods
            far = [[(-90.0, 40.0), (-89.9, 40.0), (-89.9, 40.1), (-90.0, 40.1), (-90.0, 40.0)]]
            self.assertEqual(district_neighborhoods(far, ca_index, chicago_bbox), [])

        def test_build_maps_from_synthetic(self):
            wards = {"features": [{"properties": {"ward": "1"}, "geometry": SQUARE}]}
            police = {"features": [{"properties": {"dist_num": "14"}, "geometry": SQUARE}]}
            commarea = {"features": [{"properties": {"community": "TEST AREA"}, "geometry": SQUARE}]}
            # a synthetic IL outline + one senate district inside it
            il = {"type": "Polygon", "coordinates": [[[-91.5, 37.0], [-87.5, 37.0],
                                                      [-87.5, 42.5], [-91.5, 42.5], [-91.5, 37.0]]]}
            state = {"features": [{"properties": {"STATE": "17"}, "geometry": il}]}
            senate = {"features": [{"properties": {"SLDU": "020", "BASENAME": "20"}, "geometry": SQUARE}]}
            doc = build(wards, police, commarea, senate, None, None, state,
                        datetime(2026, 9, 7, tzinfo=timezone.utc))
            self.assertIn("chicago-alderperson-ward-01", doc["districts"])
            self.assertIn("chicago-police-district-council-014", doc["districts"])
            self.assertIn("il-senate-20", doc["districts"])
            self.assertEqual(doc["districts"]["il-senate-20"]["space"], "illinois")
            self.assertIn("il_context", doc)
            self.assertTrue(doc["context"])
            self.assertTrue(doc["districts"]["chicago-alderperson-ward-01"]["paths"][0].startswith("M"))
            # ward overlaps the sole community area
            self.assertEqual(doc["districts"]["chicago-alderperson-ward-01"]["neighborhoods"], ["Test Area"])

    suite = unittest.TestLoader().loadTestsFromTestCase(T)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--output", "-o", default="docs/src/dashboard/maps.json")
    ap.add_argument("--now", default=None, help="Override generated_at (ISO) for deterministic output")
    ap.add_argument("--self-test", action="store_true", help="Run offline geometry tests and exit")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    now = (datetime.strptime(args.now, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
           if args.now else datetime.now(timezone.utc))

    wards = fetch_geojson(WARDS_ID)
    police = fetch_geojson(POLICE_ID)
    commarea = fetch_geojson(COMMAREA_ID)
    senate = fetch_tiger(TIGER_LEG, SLDU_LAYER, f"STATE='{IL_FIPS}'", SIMPLIFY_EPS_IL_DEG)
    house = fetch_tiger(TIGER_LEG, SLDL_LAYER, f"STATE='{IL_FIPS}'", SIMPLIFY_EPS_IL_DEG)
    cong = fetch_tiger(TIGER_LEG, CD_LAYER, f"STATE='{IL_FIPS}'", SIMPLIFY_EPS_IL_DEG)
    state = fetch_tiger(TIGER_SC, STATE_LAYER, f"STATE='{IL_FIPS}'", STATE_SIMPLIFY_DEG)

    doc = build(wards, police, commarea, senate, house, cong, state, now)
    if not doc:
        print("::warning::no basemap fetched; not writing maps.json", file=sys.stderr)
        return 0
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, separators=(",", ":")) + "\n")
    il_n = sum(1 for d in doc["districts"].values() if d.get("space") == "illinois")
    print(f"wrote {len(doc['districts'])} district maps "
          f"({len(doc['context'])} chicago rings, {len(doc.get('il_context', []))} il rings, "
          f"{il_n} statewide) to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
