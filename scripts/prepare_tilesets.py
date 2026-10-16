#!/usr/bin/env python3
"""Turn the raw QGIS exports in data/ into clean GeoJSON files ready to upload
to Mapbox Studio as tilesets (one tileset per file).

Usage:  python3 scripts/prepare_tilesets.py
Output: tilesets/*.geojson

Every feature gets a "kind" (counties, precincts, house, senate, congress) so
the map can tell which layer an address-lookup result came from, a short
"name" for map labels (HD 69, SD 32, MT-01, 57A, Gallatin), and a longer
"label" (House District 69, ...).

Precincts also get a "shade" (0-3), chosen so that neighboring precincts in
the same House district never share one. The style can color precincts by
their House district and vary opacity by shade.

Also writes tilesets/labels.geojson: one point per feature, placed at the spot
inside it farthest from its edges, so map labels show once per district
instead of once per map tile. Each output
file keeps only the attributes the map needs, with consistent
names and unpadded district numbers, and coordinates rounded to 6 decimals
(~10 cm). Requires only the Python standard library.

Inputs must already be in WGS84 (EPSG:4326 / CRS84) -- in QGIS use
Export > Save Features As, CRS = EPSG:4326.
"""

import heapq
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "tilesets"

PRECISION = 6


def ordinal(n):
    n = int(n)
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def unpad(value):
    """'078' -> '78', 'HD078' -> '78'."""
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return str(int(digits))


def county_props(p):
    name = p["NAME"].strip().title().replace(" And ", " and ").replace("Mccone", "McCone")
    return {"kind": "counties", "county": name, "fips": p["FIPS"], "name": name, "label": f"{name} County"}


def house_props(p):
    d = unpad(p["Name"])  # 'HD078'
    return {"kind": "house", "district": d, "name": f"HD {d}", "label": f"House District {d}"}


def senate_props(p):
    d = unpad(p["District"])
    return {"kind": "senate", "district": d, "name": f"SD {d}", "label": f"Senate District {d}"}


def congress_props(p):
    d = unpad(p["DistrictNu"])
    return {"kind": "congress", "district": d, "name": f"MT-{int(d):02d}", "label": f"Montana's {ordinal(d)} Congressional District"}


def precinct_props(p):
    county = p["COUNTY"].strip().title()
    name = p["NAME"].strip()
    return {
        "kind": "precincts",
        "id": f"{county}-{name}",  # precinct names repeat across counties (e.g. 57A)
        "precinct": name,
        "county": county,
        "house": unpad(p["HOUSE"]),
        "senate": unpad(p["SENATE"]),
        "name": name.title() if name.lower().startswith("precinct") else name,
        "label": f"Precinct {name}" if not name.lower().startswith("precinct") else name.title(),
    }


# output name -> (input file, attribute mapper, expected unique key)
LAYERS = {
    "counties": ("montana_counties.geojson", county_props, "county"),
    "house_districts": ("gallatin_county_house_districts.geojson", house_props, "district"),
    "senate_districts": ("gallatin_county_senate_districts.geojson", senate_props, "district"),
    "congressional_districts": ("montana_us_congressional_districts.geojson", congress_props, "district"),
    "precincts": ("gallatin_county_precints.geojson", precinct_props, "id"),
}


def round_coords(coords):
    if isinstance(coords[0], (int, float)):
        return [round(c, PRECISION) for c in coords[:2]]
    return [round_coords(c) for c in coords]


def ring_area(ring):
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:]))) / 2


def label_point(geom):
    """Pole of inaccessibility (Mapbox's polylabel) of the largest polygon part."""
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    poly = max(polys, key=lambda p: ring_area(p[0]))
    # Work in roughly equal-distance units, on a thinned outline: label
    # placement doesn't need every vertex, and it keeps this fast.
    kx = math.cos(math.radians(sum(y for _, y in poly[0]) / len(poly[0])))
    rings = []
    for ring in poly:
        step = max(1, len(ring) // 400)
        pts = [(x * kx, y) for x, y in ring[::step][:-1]] + [(ring[0][0] * kx, ring[0][1])]
        if len(pts) >= 4:
            rings.append(pts)
    if not rings:
        x, y = poly[0][0]
        return [x, y]

    def dist(x, y):  # signed distance to the outline, positive inside
        inside, best = False, float("inf")
        for ring in rings:
            for (ax, ay), (bx, by) in zip(ring, ring[1:]):
                if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
                    inside = not inside
                dx, dy = bx - ax, by - ay
                t = 0 if dx == dy == 0 else max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
                best = min(best, (x - ax - t * dx) ** 2 + (y - ay - t * dy) ** 2)
        return math.sqrt(best) * (1 if inside else -1)

    xs, ys = [p[0] for p in rings[0]], [p[1] for p in rings[0]]
    minx, miny, maxx, maxy = min(xs), min(ys), max(xs), max(ys)
    size = min(maxx - minx, maxy - miny)
    precision = max(maxx - minx, maxy - miny) / 200
    best = ((minx + maxx) / 2, (miny + maxy) / 2)
    best_d = dist(*best)
    if size == 0:
        return [best[0] / kx, best[1]]

    heap = []

    def push(x, y, h):
        d = dist(x, y)
        heapq.heappush(heap, (-(d + h * math.sqrt(2)), x, y, h, d))

    h = size / 2
    x = minx
    while x < maxx:
        y = miny
        while y < maxy:
            push(x + h, y + h, h)
            y += size
        x += size
    while heap:
        neg_max, x, y, h, d = heapq.heappop(heap)
        if d > best_d:
            best, best_d = (x, y), d
        if -neg_max - best_d <= precision:
            continue
        h /= 2
        for sx in (-h, h):
            for sy in (-h, h):
                push(x + sx, y + sy, h)
    return [round(best[0] / kx, PRECISION), round(best[1], PRECISION)]


def add_precinct_shades(features, shades=4):
    """Give each precinct a shade that differs from its neighbors in the same House district."""
    def vertices(geom):
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        return {(round(x, 5), round(y, 5)) for poly in polys for ring in poly for x, y in ring}

    verts = [vertices(f["geometry"]) for f in features]
    groups = {}
    for i, f in enumerate(features):
        p = f["properties"]
        groups.setdefault((p["county"], p["house"]), []).append(i)

    for members in groups.values():
        # Precincts from one source share boundary vertices; two shared points = a shared edge.
        neighbors = {i: {j for j in members if j != i and len(verts[i] & verts[j]) >= 2} for i in members}
        for i in sorted(members, key=lambda i: (-len(neighbors[i]), features[i]["properties"]["name"])):
            used = {features[j]["properties"].get("shade") for j in neighbors[i]}
            features[i]["properties"]["shade"] = next((s for s in range(shades) if s not in used), 0)


def check_lonlat(coords, path):
    if isinstance(coords[0], (int, float)):
        lon, lat = coords[:2]
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            sys.exit(f"{path}: coordinate {coords} is not lon/lat -- re-export from QGIS as EPSG:4326")
        return
    for c in coords:
        check_lonlat(c, path)


def main():
    OUT.mkdir(exist_ok=True)
    labels = []
    for out_name, (src, mapper, key) in LAYERS.items():
        path = DATA / src
        if not path.exists():
            sys.exit(f"Missing input: {path}")
        raw = json.loads(path.read_text())

        features, seen = [], set()
        for f in raw["features"]:
            geom = f.get("geometry")
            if not geom or geom["type"] not in ("Polygon", "MultiPolygon"):
                sys.exit(f"{src}: expected polygon geometry, got {geom and geom['type']}")
            check_lonlat(geom["coordinates"], src)
            props = mapper(f["properties"])
            if props[key] in seen:
                sys.exit(f"{src}: duplicate {key} {props[key]!r}")
            seen.add(props[key])
            features.append({
                "type": "Feature",
                "properties": props,
                "geometry": {"type": geom["type"], "coordinates": round_coords(geom["coordinates"])},
            })

        if out_name == "precincts":
            add_precinct_shades(features)
        write(OUT / f"{out_name}.geojson", features)

        for f in features:
            props = {k: f["properties"][k] for k in ("kind", "name", "label")}
            labels.append({"type": "Feature", "properties": props,
                           "geometry": {"type": "Point", "coordinates": label_point(f["geometry"])}})

    write(OUT / "labels.geojson", labels)


def write(dest, features):
    dest.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")))
    size_kb = dest.stat().st_size / 1024
    print(f"{dest.relative_to(ROOT)}: {len(features)} features, {size_kb:,.0f} KB")


if __name__ == "__main__":
    main()
