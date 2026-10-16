#!/usr/bin/env python3
"""Package the WordPress plugin for upload (Plugins → Add New → Upload Plugin).

Usage:  python3 scripts/build_plugin.py
Output: dist/gcd-district-map-<version>.zip
"""

import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugin" / "gcd-district-map"
DIST = ROOT / "dist"


def main():
    main_file = (PLUGIN / "gcd-district-map.php").read_text()
    version = re.search(r"^\s*\*\s*Version:\s*(\S+)", main_file, re.M).group(1)
    DIST.mkdir(exist_ok=True)
    dest = DIST / f"gcd-district-map-{version}.zip"
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(PLUGIN.rglob("*")):
            if path.is_file() and path.name != ".DS_Store":
                # WordPress expects the plugin folder at the top of the zip.
                z.write(path, Path("gcd-district-map") / path.relative_to(PLUGIN))
    print(f"{dest.relative_to(ROOT)} ({dest.stat().st_size / 1024:.0f} KB)")
    print("Bump Version: in gcd-district-map.php (and GCD_DM_VERSION) for each release so browsers fetch the new assets.")


if __name__ == "__main__":
    main()
