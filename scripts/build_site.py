#!/usr/bin/env python3
"""Build the static site for GitHub Pages.

Usage:  MAPBOX_TOKEN=pk.... python3 scripts/build_site.py
Output: _site/

Copies site/ and writes _site/config.js from site/config.json, the published
candidates (site/candidates.json) and the Mapbox token. The token comes from
the environment (a GitHub Actions secret), so it is never committed; it is a
public token, so restrict it to the site's URL in Mapbox.

Asset links in index.html get a ?v=<content hash> so browsers pick up changes
despite GitHub Pages' 10-minute cache.
"""

import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
OUT = ROOT / "_site"

# Read by the build, not copied into _site as-is.
SOURCE_ONLY = {"config.json", "candidates.json"}


def client_config(token, rows, overrides=None):
    """Everything map.js reads from window.GCD_DM_CONFIG."""
    config = json.loads((SITE / "config.json").read_text())
    config.pop("sheetUrl", None)  # only used by scripts/publish_candidates.js
    config.update(overrides or {})
    config["token"] = token
    config["candidates"] = {"rows": rows}
    return config


def published_rows():
    path = SITE / "candidates.json"
    return json.loads(path.read_text()) if path.exists() else []


def config_js(config):
    # Escape <, > and & so nothing in the Sheet can close the <script> early.
    payload = json.dumps(config, ensure_ascii=False)
    payload = payload.replace("<", "\\u003C").replace(">", "\\u003E").replace("&", "\\u0026")
    return f"window.GCD_DM_CONFIG = {payload};\n"


def version_links(html, out_dir):
    def add_version(m):
        file = out_dir / m.group(2)
        digest = hashlib.sha256(file.read_bytes()).hexdigest()[:10]
        return f'{m.group(1)}="{m.group(2)}?v={digest}"'

    return re.sub(r'\b(src|href)="((?:assets/[^"?]+|config\.js))"', add_version, html)


def main():
    token = os.environ.get("MAPBOX_TOKEN", "").strip()
    if not token.startswith("pk."):
        sys.exit("Set MAPBOX_TOKEN to the Mapbox public (pk.) token. Never use a secret (sk.) token here.")

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(SITE, OUT, ignore=lambda d, names: [n for n in names if n in SOURCE_ONLY or n == ".DS_Store"])

    rows = published_rows()
    (OUT / "config.js").write_text(config_js(client_config(token, rows)))
    index = OUT / "index.html"
    index.write_text(version_links(index.read_text(), OUT))
    print(f"_site/ built with {len(rows)} candidate rows")


if __name__ == "__main__":
    main()
