# Gallatin County Democrats district map

An address lookup map for the Gallatin County Democrats, published at
https://map.gallatindemocrats.com. It shows a voter's county, precinct, State
House and Senate districts, and congressional district, plus the Democratic
candidates on their ballot.

- **Boundaries:** QGIS exports → `scripts/prepare_tilesets.py` → Mapbox
  tilesets. Address lookup uses Mapbox Tilequery.
- **Styling:** a Mapbox Studio style. See [docs/mapbox-studio-setup.md](docs/mapbox-studio-setup.md).
- **Candidates:** a Google Sheet, published as CSV. The **Publish candidates**
  GitHub Action copies it into `site/candidates.json`.
- **Site:** static files in `site/`, deployed to GitHub Pages by the
  **Deploy site** Action on every push to `main`.

## Updating candidates

1. Edit the Sheet.
2. On GitHub: **Actions → Publish candidates → Run workflow**, keep **preview**,
   and run. Open the finished run: its summary lists what changed since the last
   publish, any problems by Sheet row, and everyone who will be on the map.
3. If it looks right, run it again with **publish**. The map updates a minute or
   two later. (GitHub Pages caches pages for up to 10 minutes, so a reload may
   briefly show the old list.)

To undo a publish, revert its "Publish candidates from the Sheet" commit on
`main`; that redeploys the previous list.

## Candidate Sheet columns

Only these columns are published. Any other column (notes, contact details)
is ignored and never leaves the Sheet.

| Column | Notes |
|---|---|
| `office` | Shown on the card, e.g. "State House" |
| `race_type` | `us_senate`, `us_house`, `mt_senate`, `mt_house`, or anything starting with `county_` (countywide). Other values are flagged and not shown |
| `district` | Number for House, Senate and U.S. House (`64`, `MT-01`). For county races, a number is shown as a residency district (commissioners); otherwise ignored |
| `candidate` | Name as it should appear (and, for write-ins, as voters should write it) |
| `website` | Full `https://` link |
| `photo_url` | A file name from `site/photos/` (e.g. `chris-pope.jpg`), or a full `https://` link. No photo, or one that fails to load, shows initials |
| `order` | Optional sort order within the level (federal, legislature, county) |
| `next_election_year` | Equal to `electionYear` in `site/config.json` means on the ballot; anything else means current official |
| `write_in` | `TRUE` for write-in candidates; shows the write-in callout |

## Candidate photos

Photos live in `site/photos/`, named like `first-last.jpg`. To add one:
crop it square, resize to about 256×256 px, save as JPEG, then on GitHub open
`site/photos/` → **Add file → Upload files** and commit to `main`. Put the file
name in the Sheet's `photo_url` column and run **Publish candidates**. The
preview warns if a file name in the Sheet doesn't match a file in `site/photos/`.

## Settings

`site/config.json` holds the style URL, tileset IDs, Sheet link, election
year, map bounds and text. Edit it on GitHub and commit to `main` to redeploy.
Everything in it is public (browsers see it anyway).

The Mapbox token is **not** in the repo. It's the `MAPBOX_TOKEN` Actions secret
(Settings → Secrets and variables → Actions) and is added at build time. It's a
public `pk.` token, so it does end up in the published page; what keeps it
from being used elsewhere is its URL restriction in Mapbox (see
[docs/mapbox-studio-setup.md](docs/mapbox-studio-setup.md#token)). To rotate it,
create a new token in Mapbox, update the secret, run **Deploy site**, then
delete the old token.

## One-time GitHub setup

1. **Settings → Pages → Source:** GitHub Actions.
2. **Settings → Secrets and variables → Actions → New repository secret:**
   `MAPBOX_TOKEN`.
3. **Custom domain:** add a DNS `CNAME` record for `map` pointing to
   `gallatin-county-democrats.github.io`, then enter `map.gallatindemocrats.com`
   under **Settings → Pages → Custom domain** and tick **Enforce HTTPS** once
   it's offered. Verify the domain under the organization's **Settings → Pages**
   so nobody else can claim it.

## Common tasks

```
python3 scripts/prepare_tilesets.py          # data/*.geojson → tilesets/*.geojson for Mapbox upload
node scripts/publish_candidates.js           # preview the Sheet locally (add --write to save)
MAPBOX_TOKEN=pk.... python3 scripts/build_site.py   # → _site/, as deployed
python3 dev/server.py                        # local preview on :8080 (see below)
```

The raw QGIS exports in `data/` aren't in the repo; get them from a maintainer
to rebuild tilesets.

## Local preview

`dev/server.py` serves `site/` as GitHub Pages would, reading files fresh on
every reload.

1. `cp dev/config.example.json dev/config.local.json` and add a Mapbox token.
   This file is git-ignored; keep it that way.
2. `python3 dev/server.py` (add `--live-sheet` to see unpublished Sheet edits)
3. From the sandbox host: `sbx ports gcd-mapbox-districts --publish 8080:8080`,
   then open http://localhost:8080.

With `"localLookup": true` (the default in the example config), lookups are
answered from `tilesets/*.geojson` instead of Mapbox.
