#!/usr/bin/env python3
"""Build the committed Chicago map asset for the elections dashboard.

Fetches the two authoritative boundary sets from the City of Chicago open-data
portal — the 50 City Council **wards** (dataset p293-wvbd, effective 2023) and
the 77 **community areas** / neighborhoods (dataset igwz-8jzy) — projects both
into ONE shared SVG coordinate space (so ward and neighborhood polygons overlay
exactly), simplifies each ring (Douglas-Peucker), and computes the
neighborhood<->ward correspondence by spatially sampling a dense grid of points
over the city (each point's community area and ward are found by point-in-polygon,
and the co-occurrence is tallied). Writes docs/src/dashboard/assets/chicago-map.json.

Pure stdlib (json/urllib/math) — no third-party geo deps, matching the repo's
"shell out / stdlib only" rule. Fail-soft: on a portal outage the committed
asset is left in place.

Usage:
    python3 scripts/build_chicago_map.py            # fetch + build + write asset
    python3 scripts/build_chicago_map.py --self-test  # offline geometry unit tests
"""
import json
import math
import os
import sys
import urllib.request

PORTAL = "https://data.cityofchicago.org/resource"
WARDS_URL = PORTAL + "/p293-wvbd.geojson?$limit=100"
AREAS_URL = PORTAL + "/igwz-8jzy.geojson?$limit=100"
OUT = os.path.join(os.path.dirname(__file__), "..", "docs", "src", "dashboard",
                   "assets", "chicago-map.json")

VIEW_W = 1000.0          # target SVG width; height derived from the city's aspect
SIMPLIFY_EPS = 0.7       # Douglas-Peucker tolerance in projected (SVG) units
GRID = 260               # sampling grid resolution (GRID x GRID points over bbox)
MIN_COVER = 0.04         # drop a ward/area from a list below this coverage fraction


# ---------- geometry helpers ----------
def _rings(geom):
    """Yield each polygon's OUTER ring as a list of (lon, lat) from a
    Polygon or MultiPolygon GeoJSON geometry."""
    t = geom.get("type")
    if t == "Polygon":
        polys = [geom["coordinates"]]
    elif t == "MultiPolygon":
        polys = geom["coordinates"]
    else:
        return
    for poly in polys:
        if poly:
            yield [(float(x), float(y)) for x, y in poly[0]]


def _perp_dist(p, a, b):
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def simplify(pts, eps):
    """Douglas-Peucker on a ring of (x, y) points."""
    if len(pts) < 3:
        return pts[:]
    dmax, idx = 0.0, 0
    for i in range(1, len(pts) - 1):
        d = _perp_dist(pts[i], pts[0], pts[-1])
        if d > dmax:
            dmax, idx = d, i
    if dmax > eps:
        left = simplify(pts[:idx + 1], eps)
        right = simplify(pts[idx:], eps)
        return left[:-1] + right
    return [pts[0], pts[-1]]


def point_in_ring(x, y, ring):
    """Ray-casting point-in-polygon for a single ring of (x, y)."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > y) != (yj > y)) and \
                (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def bbox(rings):
    xs = [p[0] for r in rings for p in r]
    ys = [p[1] for r in rings for p in r]
    return min(xs), min(ys), max(xs), max(ys)


def centroid(rings):
    """Area-weighted centroid across a shape's rings (label anchor)."""
    cx = cy = area2 = 0.0
    for r in rings:
        for i in range(len(r)):
            x0, y0 = r[i]
            x1, y1 = r[(i + 1) % len(r)]
            cross = x0 * y1 - x1 * y0
            area2 += cross
            cx += (x0 + x1) * cross
            cy += (y0 + y1) * cross
    if abs(area2) < 1e-9:
        # degenerate: fall back to the mean of the biggest ring
        big = max(rings, key=len)
        return (sum(p[0] for p in big) / len(big),
                sum(p[1] for p in big) / len(big))
    return (cx / (3 * area2), cy / (3 * area2))


def path_d(rings):
    """SVG path data for a shape's (already-projected) rings."""
    out = []
    for r in rings:
        if len(r) < 3:
            continue
        out.append("M" + " ".join("%.1f,%.1f" % (x, y) for x, y in r) + "Z")
    return "".join(out)


# ---------- fetch + build ----------
def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "govbot-map/1.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def _load_features(geojson, name_key):
    """[(label, [outer rings in lon/lat]) ...] for each feature."""
    out = []
    for f in geojson.get("features", []):
        label = str(f["properties"].get(name_key, "")).strip()
        rings = list(_rings(f["geometry"]))
        if label and rings:
            out.append((label, rings))
    return out


def build(wards_geo, areas_geo):
    wards = _load_features(wards_geo, "ward")
    areas = _load_features(areas_geo, "community")
    if not wards or not areas:
        raise SystemExit("empty ward/area geometry")

    # One projection for BOTH sets so they overlay exactly. Equirectangular with
    # a cos(lat0) x-correction; y flipped so north is up in SVG.
    all_pts = [p for _, rings in (wards + areas) for r in rings for p in r]
    lon0 = sum(p[0] for p in all_pts) / len(all_pts)
    lat0 = sum(p[1] for p in all_pts) / len(all_pts)
    k = math.cos(math.radians(lat0))

    def proj(lon, lat):
        return ((lon - lon0) * k, -(lat - lat0))

    def project(feats):
        out = []
        for label, rings in feats:
            out.append((label, [[proj(lon, lat) for lon, lat in r] for r in rings]))
        return out

    pw = project(wards)
    pa = project(areas)

    # Normalize to the target viewBox (shared extents).
    everything = [p for _, rings in (pw + pa) for r in rings for p in r]
    minx = min(p[0] for p in everything)
    miny = min(p[1] for p in everything)
    maxx = max(p[0] for p in everything)
    maxy = max(p[1] for p in everything)
    span = maxx - minx
    scale = (VIEW_W - 16) / span
    ox = 8 - minx * scale
    oy = 8 - miny * scale

    def norm(feats):
        out = []
        for label, rings in feats:
            out.append((label, [[(x * scale + ox, y * scale + oy) for x, y in r]
                                for r in rings]))
        return out

    pw = norm(pw)
    pa = norm(pa)
    view_h = (maxy - miny) * scale + 16

    # --- neighborhood <-> ward overlap by grid sampling (on normalized coords) ---
    ward_bb = [(lbl, rings, bbox(rings)) for lbl, rings in pw]
    area_bb = [(lbl, rings, bbox(rings)) for lbl, rings in pa]

    def locate(x, y, table):
        for lbl, rings, bb in table:
            if bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3]:
                if any(point_in_ring(x, y, r) for r in rings):
                    return lbl
        return None

    co = {}          # (area, ward) -> hits
    ward_tot = {}    # ward -> hits
    area_tot = {}    # area -> hits
    step_x = (maxx - minx) * scale / GRID
    step_y = (maxy - miny) * scale / GRID
    y = 8.0
    for _iy in range(GRID + 1):
        x = 8.0
        for _ix in range(GRID + 1):
            a = locate(x, y, area_bb)
            if a is not None:
                w = locate(x, y, ward_bb)
                if w is not None:
                    co[(a, w)] = co.get((a, w), 0) + 1
                    ward_tot[w] = ward_tot.get(w, 0) + 1
                    area_tot[a] = area_tot.get(a, 0) + 1
            x += step_x
        y += step_y

    def ranked_for_area(a):
        rows = [(w, n) for (aa, w), n in co.items() if aa == a]
        tot = area_tot.get(a, 0) or 1
        rows = [(w, n / tot) for w, n in rows if n / tot >= MIN_COVER]
        rows.sort(key=lambda t: -t[1])
        return [w for w, _ in rows]

    def ranked_for_ward(w):
        rows = [(a, n) for (a, ww), n in co.items() if ww == w]
        tot = ward_tot.get(w, 0) or 1
        rows = [(a, n / tot) for a, n in rows if n / tot >= MIN_COVER]
        rows.sort(key=lambda t: -t[1])
        return [a for a, _ in rows]

    # --- emit ---
    def emit(feats, extra):
        out = []
        for label, rings in feats:
            simp = [simplify(r, SIMPLIFY_EPS) for r in rings]
            simp = [r for r in simp if len(r) >= 3]
            cx, cy = centroid(simp or rings)
            row = {"d": path_d(simp), "cx": round(cx, 1), "cy": round(cy, 1)}
            row.update(extra(label))
            out.append(row)
        return out

    ward_rows = emit(pw, lambda w: {"ward": w, "areas": ranked_for_ward(w)})
    ward_rows.sort(key=lambda r: int(r["ward"]))
    # attach the community-area number to each area for stable ordering
    num_by_name = {str(f["properties"].get("community", "")).strip():
                   str(f["properties"].get("area_numbe", "")).strip()
                   for f in areas_geo.get("features", [])}
    area_rows = emit(pa, lambda a: {"name": a, "num": num_by_name.get(a, ""),
                                    "wards": ranked_for_area(a)})
    area_rows.sort(key=lambda r: r["name"])

    return {
        "generated_by": "scripts/build_chicago_map.py",
        "source": "City of Chicago open data (p293-wvbd wards; igwz-8jzy community areas)",
        "viewBox": "0 0 %d %d" % (round(VIEW_W), round(view_h)),
        "wards": ward_rows,
        "areas": area_rows,
    }


def _self_test():
    sq = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert point_in_ring(5, 5, sq) and not point_in_ring(15, 5, sq)
    assert simplify([(0, 0), (5, 0.1), (10, 0)], 1.0) == [(0, 0), (10, 0)]
    cx, cy = centroid([sq])
    assert abs(cx - 5) < 1e-6 and abs(cy - 5) < 1e-6
    d = path_d([sq])
    assert d.startswith("M0.0,0.0") and d.endswith("Z")
    print("self-test OK")


def main():
    if "--self-test" in sys.argv:
        _self_test()
        return
    try:
        wards_geo = _fetch(WARDS_URL)
        areas_geo = _fetch(AREAS_URL)
    except Exception as e:  # fail-soft
        print("fetch failed (%s) — leaving committed asset in place" % e)
        return
    data = build(wards_geo, areas_geo)
    with open(OUT, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    print("wrote %s — %d wards, %d areas, viewBox %s"
          % (OUT, len(data["wards"]), len(data["areas"]), data["viewBox"]))


if __name__ == "__main__":
    main()
