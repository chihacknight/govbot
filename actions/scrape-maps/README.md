# scrape-maps — Chicago district locator maps

Builds `docs/src/dashboard/maps.json`, the compact geometry the **Elections
Happening in IL** page draws as an inline-SVG locator next to each race (the
ward or police district highlighted inside a light map of the whole city;
citywide offices tint all of Chicago).

## Sources (public domain — City of Chicago Data Portal)

| Layer | Dataset | Key property | Maps to |
|---|---|---|---|
| Wards (2023–) | `p293-wvbd` | `ward` | `chicago-alderperson-ward-NN` |
| Police Districts | `24zt-jpfn` | `dist_num` | `chicago-police-district-council-NNN` |

CPS board **subdistrict** (1A–10B) polygons aren't published as a single portal
layer, so those races carry no polygon yet and the page omits the map for them.

## How it works

The ward layer defines the projection and the light **context** base (all 50
wards). Every ward and police district is keyed to its elections-seed race id.
Geometry is:

1. **projected** once, at build time, to a shared integer viewbox
   (equirectangular, longitude compressed by cos(latitude) so the city isn't
   stretched) — the browser just draws SVG paths, no mapping library;
2. **simplified** with Ramer–Douglas–Peucker and rounded to integers, so the
   whole file is tens of KB, not megabytes;
3. written as `maps.json`: `{ view:{w,h}, context:[path…], districts:{ <race_id>:
   {kind,label,paths:[…]} } }`.

Fail-soft: any fetch/parse error yields no basemap and **leaves the committed
`maps.json` in place** (the deploy never blanks the maps).

## Usage

```bash
python3 actions/scrape-maps/main.py --output docs/src/dashboard/maps.json
python3 actions/scrape-maps/main.py --self-test    # offline geometry tests (no network)
```

The pure geometry helpers (`rdp`, `ring_area`, `make_projector`, `to_path`,
`build`) are unit-tested offline via `--self-test`.
