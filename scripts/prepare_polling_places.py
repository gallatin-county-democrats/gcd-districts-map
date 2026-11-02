#!/usr/bin/env python3
"""Turn the Elections Office polling place list into site/polling_places.json.

Usage:  MAPBOX_TOKEN=pk.... python3 scripts/prepare_polling_places.py [data/gallatin_polling_places.csv]
Output: site/polling_places.json, which the map uses to show each precinct's
polling place and pin it on the map.

The CSV needs the columns Precinct, Polling Place, Address and City (other
columns are ignored). Each distinct place is geocoded once with the Mapbox
Geocoding API. Places already in site/polling_places.json keep their saved
coordinates, so a pin moved by hand stays put; delete a place's entry (or the
whole file) to geocode it again.

Prints a check: every geocoded place with its match, precincts on the map with
no polling place, and precincts in the CSV that aren't on the map.
"""

import csv
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = ROOT / "data" / "gallatin_polling_places.csv"
OUT = ROOT / "site" / "polling_places.json"
PRECINCTS = ROOT / "tilesets" / "precincts.geojson"
CONFIG = ROOT / "site" / "config.json"


def geocode(token, address, city, bounds):
    # "Bozeman/Four Corners" -> "Bozeman"
    query = f"{address}, {city.split('/')[0].strip()}, MT"
    params = {
        "q": query,
        "access_token": token,
        "limit": 1,
        "country": "us",
        "bbox": ",".join(str(v) for v in bounds),
    }
    url = "https://api.mapbox.com/search/geocode/v6/forward?" + urllib.parse.urlencode(params)
    # The public token is URL-restricted; send the site as the referrer.
    req = urllib.request.Request(url, headers={"Referer": "https://map.gallatindemocrats.com/"})
    with urllib.request.urlopen(req, timeout=20) as res:
        features = json.load(res)["features"]
    if not features:
        sys.exit(f"No geocoding match for {query!r}; add its coordinates to {OUT.relative_to(ROOT)} by hand.")
    f = features[0]
    lng, lat = f["geometry"]["coordinates"]
    confidence = f["properties"].get("match_code", {}).get("confidence", "?")
    return [round(lng, 6), round(lat, 6)], f["properties"].get("full_address", ""), confidence


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CSV
    with src.open(newline="", encoding="utf-8-sig") as fh:
        rows = [{k.strip(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(fh)]

    config = json.loads(CONFIG.read_text())
    home = config["homeCounty"]
    saved = {}
    if OUT.exists():
        for place in json.loads(OUT.read_text())["places"]:
            saved[(place["name"], place["address"], place["city"])] = place["coordinates"]

    token = os.environ.get("MAPBOX_TOKEN", "").strip()
    places = {}
    for row in rows:
        if not row.get("Precinct"):
            continue
        key = (row["Polling Place"], row["Address"], row["City"])
        if key not in places:
            places[key] = {"name": key[0], "address": key[1], "city": key[2], "coordinates": None, "precincts": []}
        places[key]["precincts"].append(row["Precinct"].upper())

    for key, place in places.items():
        if key in saved:
            place["coordinates"] = saved[key]
            print(f"  kept      {place['name']}: {saved[key]}")
            continue
        if not token.startswith("pk."):
            sys.exit("Set MAPBOX_TOKEN to the Mapbox public (pk.) token to geocode new polling places.")
        place["coordinates"], match, confidence = geocode(token, place["address"], place["city"], config["bounds"])
        print(f"  geocoded  {place['name']}: {place['address']} -> {match} {place['coordinates']} ({confidence} confidence)")

    listed = {p for place in places.values() for p in place["precincts"]}
    if PRECINCTS.exists():
        on_map = {f["properties"]["precinct"] for f in json.loads(PRECINCTS.read_text())["features"]
                  if f["properties"].get("county") == home}
        if on_map - listed:
            print(f"Precincts on the map with no polling place: {', '.join(sorted(on_map - listed))}")
        if listed - on_map:
            print(f"Precincts in the CSV that aren't on the map: {', '.join(sorted(listed - on_map))}")

    out = {"county": home, "places": sorted(places.values(), key=lambda p: p["name"])}
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(f"Wrote {OUT.relative_to(ROOT)}: {len(places)} polling places for {len(listed)} precincts.")


if __name__ == "__main__":
    main()
