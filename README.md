# Gallatin County Democrats district map

An address lookup map for the Gallatin County Democrats WordPress site. It
shows a voter's county, precinct, State House and Senate districts, and
congressional district, plus the Democratic candidates on their ballot.

- **Boundaries:** QGIS exports in `data/` → `scripts/prepare_tilesets.py` →
  Mapbox tilesets. Address lookup uses Mapbox Tilequery.
- **Styling:** a Mapbox Studio style. See [docs/mapbox-studio-setup.md](docs/mapbox-studio-setup.md).
- **Candidates:** a Google Sheet, published as CSV, synced and published from
  Settings → District Map in WordPress.
- **Delivery:** the WordPress plugin in `plugin/gcd-district-map`. The
  `[gcd_district_map]` shortcode embeds the map in an auto-sizing iframe.

## Candidate Sheet columns

| Column | Notes |
|---|---|
| `office` | Shown on the card, e.g. "State House" |
| `race_type` | `us_senate`, `us_house`, `mt_senate`, `mt_house`, or anything starting with `county_` (countywide). Other values are flagged and not shown |
| `district` | Number for House, Senate and U.S. House (`64`, `MT-01`). For county races, a number is shown as a residency district (commissioners); otherwise ignored |
| `candidate` | Name as it should appear (and, for write-ins, as voters should write it) |
| `website`, `photo_url` | Full `https://` links. No photo shows initials |
| `order` | Optional sort order within the level (federal, legislature, county) |
| `next_election_year` | Equal to the "current election year" setting means on the ballot; anything else means current official |
| `write_in` | `TRUE` for write-in candidates; shows the write-in callout |

## Common tasks

```
python3 scripts/prepare_tilesets.py   # data/*.geojson → tilesets/*.geojson for Mapbox upload
python3 scripts/build_plugin.py       # → dist/gcd-district-map-<version>.zip
python3 dev/server.py                 # local preview on :8080 (see below)
```

## Local preview

`dev/server.py` serves the map page as the plugin would, reading assets fresh
on every reload and pulling candidates straight from the Sheet. `/embed` shows
it inside an auto-sizing iframe on a stand-in page.

1. `cp dev/config.example.json dev/config.local.json` and add a Mapbox token
   (plus the style URL and tileset IDs once they exist).
2. `python3 dev/server.py`
3. From the sandbox host: `sbx ports gcd-mapbox-districts --publish 8080:8080`,
   then open http://localhost:8080.

With `"localLookup": true` (the default in the example config), lookups are
answered from `tilesets/*.geojson` instead of Mapbox, so results and candidates
work before the tilesets are uploaded.
