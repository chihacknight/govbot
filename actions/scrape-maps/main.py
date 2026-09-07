#!/usr/bin/env python3
"""Build compact district maps for the Elections Happening in IL page.

Fetches official boundary polygons from the City of Chicago Data Portal, keyed
to the elections seed's race ids, and writes a small, pre-projected
`docs/src/dashboard/maps.json` the dashboard can draw as an inline-SVG locator
next to each race (a ward, a police district, or the whole city for citywide
offices).

Sources (public-domain, City of Chicago Data Portal):
  * Wards (2023-)          -> p293-wvbd   (property: ward)
  * Police Districts       -> 24zt-jpfn   (property: dist_num)
CPS board subdistrict (1A-10B) boundaries are not published as a single portal
layer, so those races carry no polygon yet — the page degrades gracefully.

Design (see CLAUDE.md):
  * Python standard library only. Fail-soft: any fetch/parse error yields an
    empty layer, never a crash; the deploy keeps the committed maps.json when the
    fresh run produced nothing.
  * The geometry is simplified (Douglas-Peucker) and projected to a shared
    integer viewbox at build time, so the browser just draws SVG paths — no
    mapping library, no runtime projection, offline-friendly.
  * Pure helpers (rdp, project_ring, to_path) are unit-tested offline.

Usage:
    python3 actions/scrape-maps/main.py --output docs/src/dashboard/maps.json
    python3 actions/scrape-maps/main.py --self-test        # offline geometry tests
"""

import argparse
import json
import math
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
SEED_PATH = HERE.parent / "scrape-elections" / "elections_seed.json"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
FETCH_TIMEOUT = 45
PORTAL = "https://data.cityofchicago.org/api/geospatial/{}?method=export&format=GeoJSON"

WARDS_ID = "p293-wvbd"
POLICE_ID = "24zt-jpfn"

VIEW_W = 1000          # projected coordinate space width; height set by aspect
SIMPLIFY_EPS = 1.2     # Douglas-Peucker tolerance in projected units (~px of 1000)
MIN_RING_AREA = 4.0    # drop islands/slivers smaller than this (projected units^2)


# --------------------------------------------------------------------------- #
# network
# --------------------------------------------------------------------------- #
def fetch_geojson(dataset_id):
    url = PORTAL.format(dataset_id)
    req = urllib.request.Request(url, headers={"user-agent": UA, "accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as err:  # network / TLS / parse — non-fatal
        print(f"warning: fetch failed {url}: {err}", file=sys.stderr)
        return None


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
    the city isn't stretched. Returns (project(lon,lat)->(x,y), width, height)."""
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


def feature_paths(geom, project):
    out = []
    for ring in _iter_rings(geom):
        s = project_ring(ring, project)
        if s:
            out.append(to_path(s))
    return out


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #
def _seed_race_ids():
    try:
        seed = json.loads(SEED_PATH.read_text())
        return {r["id"] for r in seed.get("races", [])}
    except (OSError, json.JSONDecodeError):
        return set()


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


def build(wards_geo, police_geo, now):
    """Assemble maps.json from the ward + police GeoJSON documents. The ward
    layer defines the projection + the light 'context' base (all wards); each
    ward and police district is keyed to its race id."""
    wards = (wards_geo or {}).get("features", [])
    if not wards:
        return None  # no basemap -> nothing to draw; keep committed maps.json
    valid = _seed_race_ids()
    bbox = bbox_of(wards)
    project, w, h = make_projector(bbox)

    context = []
    districts = {}

    for f in wards:
        paths = feature_paths(f.get("geometry"), project)
        context.extend(paths)
        rid = _ward_race_id(f.get("properties", {}))
        if rid and (not valid or rid in valid) and paths:
            districts[rid] = {"kind": "ward",
                              "label": "Ward " + str(int(f["properties"].get("ward") or f["properties"].get("ward_id"))),
                              "paths": paths}

    for f in (police_geo or {}).get("features", []):
        rid = _police_race_id(f.get("properties", {}))
        if not rid or (valid and rid not in valid):
            continue
        paths = feature_paths(f.get("geometry"), project)
        if paths:
            num = int(f["properties"].get("dist_num"))
            districts[rid] = {"kind": "police_district",
                              "label": f"Police District {num:03d}", "paths": paths}

    return {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "City of Chicago Data Portal (wards p293-wvbd, police 24zt-jpfn)",
        "view": {"w": round(w), "h": round(h)},
        "context": context,
        "districts": districts,
    }


# --------------------------------------------------------------------------- #
# offline self-test (no network)
# --------------------------------------------------------------------------- #
def self_test():
    import unittest

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

        def test_build_maps_from_synthetic(self):
            square = {"type": "Polygon", "coordinates": [[[-87.7, 41.8], [-87.6, 41.8],
                                                          [-87.6, 41.9], [-87.7, 41.9], [-87.7, 41.8]]]}
            wards = {"features": [{"properties": {"ward": "1"}, "geometry": square}]}
            police = {"features": [{"properties": {"dist_num": "14"}, "geometry": square}]}
            doc = build(wards, police, datetime(2026, 9, 7, tzinfo=timezone.utc))
            self.assertIn("chicago-alderperson-ward-01", doc["districts"])
            self.assertIn("chicago-police-district-council-014", doc["districts"])
            self.assertTrue(doc["context"])
            self.assertTrue(doc["districts"]["chicago-alderperson-ward-01"]["paths"][0].startswith("M"))

        def test_to_path_closed(self):
            self.assertTrue(to_path([(0, 0), (10, 0), (10, 10)]).endswith("Z"))

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
    doc = build(wards, police, now)
    if not doc:
        print("::warning::no basemap fetched; not writing maps.json", file=sys.stderr)
        return 0
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, separators=(",", ":")) + "\n")
    print(f"wrote {len(doc['districts'])} district maps ({len(doc['context'])} "
          f"context rings) to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
