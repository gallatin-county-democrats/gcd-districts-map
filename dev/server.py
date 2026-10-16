#!/usr/bin/env python3
"""Local preview of the district map, without WordPress.

    python3 dev/server.py            # http://0.0.0.0:8080
    python3 dev/server.py --port 9000

  /         the map page, exactly as the plugin serves it (assets are read
            fresh from plugin/gcd-district-map/assets on every reload)
  /embed    the map inside an auto-sizing iframe, like the [gcd_district_map]
            shortcode puts it on a WordPress page

With "localLookup": true in the config, address lookups are answered from
tilesets/*.geojson (run scripts/prepare_tilesets.py first) instead of Mapbox
Tilequery, so the results bar and candidates work before anything is uploaded.

Settings come from dev/config.local.json (copy dev/config.example.json).
Candidates are fetched from the Sheet's published CSV on every page load, so
Sheet edits show up on reload; no Publish step here.
"""

import argparse
import csv
import io
import json
import mimetypes
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TILESETS = ROOT / "tilesets"
ASSETS = ROOT / "plugin" / "gcd-district-map" / "assets"
CONFIG = ROOT / "dev" / "config.local.json"
EXAMPLE = ROOT / "dev" / "config.example.json"

# Keep in sync with GCD_DM_MAPBOX_GL_URL / GCD_DM_GEOCODER_URL in gcd-district-map.php.
MAPBOX_GL = "https://api.mapbox.com/mapbox-gl-js/v3.9.0"
GEOCODER = "https://api.mapbox.com/mapbox-gl-js/plugins/mapbox-gl-geocoder/v5.0.3"

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>District lookup map (dev)</title>
<link rel="stylesheet" href="{gl}/mapbox-gl.css">
<link rel="stylesheet" href="{geocoder}/mapbox-gl-geocoder.css">
<link rel="stylesheet" href="/assets/map.css">
<style>
  /* Dev only: frame the map like a page column when opened directly (not inside /embed's iframe). */
  .gcd-dev-standalone #gcd-dm-root {{ max-width: 1000px; margin: 0 auto; padding: 24px 16px; }}
</style>
<script>if (window.top === window) document.documentElement.classList.add('gcd-dev-standalone');</script>
</head>
<body>
<div id="gcd-dm-root"></div>
<script>window.GCD_DM_CONFIG = {config};</script>
<script src="{gl}/mapbox-gl.js"></script>
<script src="{geocoder}/mapbox-gl-geocoder.min.js"></script>
<script src="/assets/candidates.js"></script>
<script src="/assets/map.js"></script>
</body>
</html>
"""

# Mirrors the shortcode output in includes/embed.php, inside a stand-in page.
EMBED = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Embed test (dev)</title>
<style>
  body { margin: 0; font: 17px/1.6 Georgia, serif; background: #eee; }
  main { max-width: 900px; margin: 0 auto; padding: 24px 16px; background: #fff; }
</style>
</head>
<body>
<main>
<h1>Find your districts</h1>
<p>Stand-in for a WordPress page. The map below is in an iframe that resizes to fit, like the shortcode.</p>
<iframe id="gcd-dm-frame-1" class="gcd-dm-frame" src="/" title="District and candidate lookup map" allow="geolocation" style="display:block;width:100%;height:1000px;border:0"></iframe>
<script>(function(f){window.addEventListener("message",function(e){if(e.source===f.contentWindow&&e.data&&e.data.type==="gcd-dm-height"){f.style.height=e.data.height+"px";}});})(document.getElementById("gcd-dm-frame-1"));</script>
<p>Text after the map.</p>
</main>
</body>
</html>
"""


class LocalLookup:
    """Point-in-polygon over the prepared GeoJSON, answering like Mapbox Tilequery."""

    def __init__(self):
        self.features = []
        for path in sorted(TILESETS.glob("*.geojson")):
            for f in json.loads(path.read_text())["features"]:
                g = f["geometry"]
                if g["type"] not in ("Polygon", "MultiPolygon"):  # e.g. labels.geojson points
                    continue
                polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
                xs = [p[0] for poly in polys for p in poly[0]]
                ys = [p[1] for poly in polys for p in poly[0]]
                self.features.append((f["properties"], polys, (min(xs), min(ys), max(xs), max(ys))))
        if not self.features:
            sys.exit("localLookup needs tilesets/*.geojson: run python3 scripts/prepare_tilesets.py")

    @staticmethod
    def in_ring(x, y, ring):
        inside = False
        j = len(ring) - 1
        for i in range(len(ring)):
            xi, yi = ring[i][:2]
            xj, yj = ring[j][:2]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                inside = not inside
            j = i
        return inside

    def query(self, x, y):
        hits = []
        for props, polys, (x0, y0, x1, y1) in self.features:
            if not (x0 <= x <= x1 and y0 <= y <= y1):
                continue
            if any(self.in_ring(x, y, poly[0]) and not any(self.in_ring(x, y, h) for h in poly[1:]) for poly in polys):
                hits.append({"type": "Feature", "properties": props, "geometry": {"type": "Point", "coordinates": [x, y]}})
        return {"type": "FeatureCollection", "features": hits}


LOOKUP = None


def load_config():
    if not CONFIG.exists():
        sys.exit(f"Missing {CONFIG.relative_to(ROOT)}: copy {EXAMPLE.relative_to(ROOT)} and fill in your Mapbox token.")
    return json.loads(CONFIG.read_text())


def fetch_rows(url):
    """Same shape as gcd_dm_parse_csv(): list of {lowercase header: value}."""
    with urllib.request.urlopen(url, timeout=20) as res:
        text = res.read().decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    header = [h.strip().lower() for h in next(reader)]
    rows = [{h: (cells[i].strip() if i < len(cells) else "") for i, h in enumerate(header) if h} for cells in reader]
    while rows and not "".join(rows[-1].values()):
        rows.pop()
    return rows


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, content_type):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            return self.map_page()
        if path.startswith("/tilequery/") and LOOKUP:
            lng, lat = path[len("/tilequery/"):].removesuffix(".json").split(",")
            return self.send(200, json.dumps(LOOKUP.query(float(lng), float(lat))), "application/json")
        if path == "/embed":
            return self.send(200, EMBED, "text/html; charset=utf-8")
        if path.startswith("/assets/"):
            file = (ASSETS / path[len("/assets/"):]).resolve()
            if file.is_file() and ASSETS in file.parents:
                ctype = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
                return self.send(200, file.read_bytes(), ctype)
        self.send(404, "Not found", "text/plain")

    def map_page(self):
        config = load_config()
        sheet_url = config.pop("sheetUrl", "")
        if config.pop("localLookup", False):
            config["tilequeryUrl"] = "/tilequery/{lng},{lat}.json"
        rows = []
        if sheet_url:
            try:
                rows = fetch_rows(sheet_url)
            except Exception as err:  # keep the map usable without candidates
                print(f"Couldn't fetch the Sheet: {err}", file=sys.stderr)
        config["candidates"] = {"rows": rows}
        # Same escaping as wp_json_encode(..., JSON_HEX_TAG | JSON_HEX_AMP).
        payload = json.dumps(config).replace("<", "\\u003C").replace(">", "\\u003E").replace("&", "\\u0026")
        self.send(200, PAGE.format(gl=MAPBOX_GL, geocoder=GEOCODER, config=payload), "text/html; charset=utf-8")

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.command, self.path))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    global LOOKUP
    if load_config().get("localLookup"):  # also fails fast if the config is missing
        LOOKUP = LocalLookup()
    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(f"District map dev server on http://0.0.0.0:{args.port}/  (embed test: /embed)")
    server.serve_forever()


if __name__ == "__main__":
    main()
