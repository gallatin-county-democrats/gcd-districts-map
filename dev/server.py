#!/usr/bin/env python3
"""Local preview of the district map.

    python3 dev/server.py                # http://0.0.0.0:8080
    python3 dev/server.py --port 9000
    python3 dev/server.py --live-sheet   # candidates straight from the Sheet

Serves site/ as GitHub Pages would, with files read fresh on every reload and
config.js built on the fly, as scripts/build_site.py does for a deploy.

Settings come from site/config.json, with the Mapbox token (and any overrides)
from dev/config.local.json (copy dev/config.example.json). Candidates come
from site/candidates.json (what's published), or with --live-sheet from the
Sheet on every reload, to check edits before running "Publish candidates".

With "localLookup": true in the local config, address lookups are answered from
tilesets/*.geojson (run scripts/prepare_tilesets.py first) instead of Mapbox
Tilequery, so the results bar and candidates work before anything is uploaded.
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
sys.path.insert(0, str(ROOT / "scripts"))
import build_site  # noqa: E402

SITE = build_site.SITE
TILESETS = ROOT / "tilesets"
CONFIG = ROOT / "dev" / "config.local.json"
EXAMPLE = ROOT / "dev" / "config.example.json"

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
    """Same shape as scripts/publish_candidates.js: list of {lowercase header: value}."""
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
        if path == "/config.js":
            return self.send(200, build_site.config_js(self.server.config()), "text/javascript; charset=utf-8")
        if path.startswith("/tilequery/") and LOOKUP:
            lng, lat = path[len("/tilequery/"):].removesuffix(".json").split(",")
            return self.send(200, json.dumps(LOOKUP.query(float(lng), float(lat))), "application/json")
        file = (SITE / (path.lstrip("/") or "index.html")).resolve()
        if file.is_file() and SITE in file.parents and file.name not in build_site.SOURCE_ONLY:
            ctype = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            return self.send(200, file.read_bytes(), ctype)
        self.send(404, "Not found", "text/plain")

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.command, self.path))


class Server(ThreadingHTTPServer):
    live_sheet = False

    def config(self):
        local = load_config()
        token = local.pop("token", "")
        overrides = {k: v for k, v in local.items() if k not in ("localLookup", "sheetUrl")}
        if local.get("localLookup"):
            overrides["tilequeryUrl"] = "/tilequery/{lng},{lat}.json"
        rows = build_site.published_rows()
        if self.live_sheet:
            try:
                rows = fetch_rows(json.loads((SITE / "config.json").read_text())["sheetUrl"])
            except Exception as err:  # keep the map usable without candidates
                print(f"Couldn't fetch the Sheet: {err}", file=sys.stderr)
        return build_site.client_config(token, rows, overrides)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--live-sheet", action="store_true", help="read candidates from the Sheet instead of site/candidates.json")
    args = parser.parse_args()
    global LOOKUP
    if load_config().get("localLookup"):  # also fails fast if the config is missing
        LOOKUP = LocalLookup()
    server = Server(("0.0.0.0", args.port), Handler)
    server.live_sheet = args.live_sheet
    print(f"District map dev server on http://0.0.0.0:{args.port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
