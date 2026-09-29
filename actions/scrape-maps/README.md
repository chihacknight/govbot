# scrape-maps — district locator maps

Builds `docs/src/dashboard/maps.json`, the compact geometry the **Elections
Happening in IL** page draws as an inline-SVG locator next to each race — the
district highlighted (and gently pulsing) inside a light basemap, plus the
**Chicago neighborhoods** and the **Illinois counties** that district touches
(the non-Chicago "hoods"). There are two coordinate spaces in one file:

* **`chicago`** — a city map (all wards as a light context) for the Chicago-scale
  races: alderperson wards, police-district councils and CPS board subdistricts;
  citywide offices tint all of Chicago.
* **`illinois`** — a statewide silhouette (the IL state outline as context) for
  the General Assembly and congressional races, whose districts span the whole
  state; each district is highlighted on the silhouette so a reader can see where
  in Illinois it sits.

## Sources (public, keyless APIs)

| Layer | Source | Key property | Maps to | Space |
|---|---|---|---|---|
| Wards (2023–) | Chicago portal `p293-wvbd` | `ward` | `chicago-alderperson-ward-NN` | chicago |
| Police Districts | Chicago portal `24zt-jpfn` | `dist_num` | `chicago-police-district-council-NNN` | chicago |
| Community areas (77) | Chicago portal `igwz-8jzy` | `community` | *(neighborhood overlap)* | — |
| IL Senate (2026) | Census TIGERweb Legislative layer 1 (SLDU) | `SLDU` | `il-senate-NN` | illinois |
| IL House (2026) | Census TIGERweb Legislative layer 2 (SLDL) | `SLDL` | `il-house-NNN` | illinois |
| U.S. House (120th) | Census TIGERweb Legislative layer 0 (CD120) | `CD120` | `us-house-il-NN` | illinois |
| IL state outline | Census TIGERweb State_County layer 0 | `STATE=17` | *(illinois context)* | illinois |
| IL counties (102) | Census TIGERweb State_County layer 1 | `NAME` | *(county overlap)* | — |
| CPS board subdistricts (1A–10B) | Chalkbeat 2026 CPS board map (`districts-20-centroids.geojson`) | `sub` | `cps-board-member-Nx` | chicago |

No government authority publishes the CPS board **subdistrict** (1A–10B) polygons
as a GIS layer, so the one non-government source is **Chalkbeat**, which digitized
the official 2026 map for its election explorer and serves the 20 subdistrict
polygons as public GeoJSON. It's used only because it's the sole published
geometry for these districts; geometry is still never invented (a fetch failure
just leaves those races map-less).

## How it works

Each space's basemap defines the projection and light **context** base. Every
seed race id is keyed to its district geometry, which is:

1. **projected** once, at build time, to a shared integer viewbox
   (equirectangular, longitude compressed by cos(latitude) so it isn't
   stretched) — the browser just draws SVG paths, no mapping library;
2. **simplified** with Ramer–Douglas–Peucker (TIGERweb also trims vertices
   server-side via `maxAllowableOffset`) and rounded to integers, so the whole
   file stays ~150 KB, not megabytes;
3. tagged with the **neighborhoods** it touches — computed by sampling a grid
   inside the district (clipped to Chicago) and classifying each interior point
   by community area; a statewide district that never reaches Chicago carries an
   empty list;
4. tagged with the **counties** it covers (the non-Chicago "hoods") — the same
   grid-sampling over the district's own bbox (not clipped to Chicago), so a
   downstate district still names its counties and a Chicago-area district
   carries both lists.

Output shape:

```
{
  view:{w,h}, context:[path…],            // chicago space
  il_view:{w,h}, il_context:[path…],      // illinois space
  districts:{ <race_id>: { kind, label, space, paths:[…], neighborhoods:[…], counties:[…] } }
}
```

Fail-soft: any fetch/parse error yields no basemap and **leaves the committed
`maps.json` in place** (the deploy never blanks the maps).

## Usage

```bash
python3 actions/scrape-maps/main.py --output docs/src/dashboard/maps.json
python3 actions/scrape-maps/main.py --self-test    # offline geometry tests (no network)
```

The pure helpers (`rdp`, `ring_area`, `make_projector`, `to_path`,
`point_in_rings`, `district_neighborhoods`, `district_counties`, the id mappers,
`build`) are unit-tested offline via `--self-test`.
