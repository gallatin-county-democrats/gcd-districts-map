# Mapbox Studio setup

All map styling lives in one Mapbox Studio style that draws from all five
tilesets. The plugin only turns layers on and off and points each highlight
layer at the visitor's district, so it relies on the layer names below.

## 1. Upload the tilesets

```
python3 scripts/prepare_tilesets.py
```

In Studio → **Tilesets → New tileset → Upload file**, upload each file in
`tilesets/` (one tileset per file, six in all). Note each **Tileset ID**
(`yourname.abc123xy`) and enter it under Settings → District Map in WordPress.

To update a layer later (redistricting, precinct changes), re-export from QGIS,
re-run the script, and use **Replace** on the existing tileset so its ID stays
the same.

## 2. Create the style

Create one style (any template). For each layer: **Add layer** (+ in the Layers
panel), choose the tileset as its source, pick the type (Fill / Line / Symbol),
and rename it. **The name prefix decides which view a layer belongs to:**

| Prefix | Shown when | Suggested layers |
|---|---|---|
| `house-` | "State House" selected (default) | `house-fill` (light, ~15% opacity), `house-outline`, `house-label` (text field: `name`), `house-senate-lines` (senate_districts tileset, heavier line: each Senate district is two House districts) |
| `senate-` | "State Senate" selected | `senate-fill`, `senate-outline`, `senate-label` |
| `congress-` | "Congress" selected | `congress-fill`, `congress-outline`, `congress-label` |
| `precincts-` | Precincts checkbox on | `precincts-outline` (thin, dashed), `precincts-label` (text field: `name`). Set the **zoom range** to start at about 11 (labels about 12) so they appear only when zoomed in |

**Label layers use the `labels` tileset, not the polygon tilesets.** Labeling a
polygon directly repeats the label once per map tile; `labels` has one point
per district, county and precinct, placed well inside it. For each label layer
(`house-label`, `senate-label`, `congress-label`, `precincts-label`):

- Source: the `labels` tileset; type: Symbol
- Filter: `kind` is `house` (or `senate`, `congress`, `precincts`)
- Text field: `name` (HD 69, SD 32, MT-01, 57A, Gallatin), or `label` for the
  long form (House District 69)

The `labels` tileset is for display only; don't enter it in the plugin's
tileset settings.

Layers with any other name are never touched, so they're always visible. Put
shared layers here, such as the Gallatin County outline (the `counties` tileset
filtered to `county` is `Gallatin`).

If your Studio version offers layer groups, a group named exactly `house`,
`senate`, `congress` or `precincts` works the same as the prefix.

### Precinct colors that follow the House districts

Each precinct has `house` (its House district) and `shade` (0-3; neighbors in
the same House district always differ). To tint precincts with their House
district's color:

1. Open `house-fill` → Color → the code view (`</>`), and copy the expression.
2. Paste it into `precincts-fill` → Color, and change `["get", "district"]`
   to `["get", "house"]`.
3. Set `precincts-fill` → Opacity to an expression on `shade`, e.g.
   `["match", ["get", "shade"], 0, 0.35, 1, 0.5, 2, 0.65, 0.8]`.

A thin white `precincts-outline` helps tell precincts apart too.

## 3. Highlight layers

For each prefix, add one layer named `<prefix>highlight`, for example
`house-highlight`, styled however the visitor's district should stand out (a
bold outline works well). Give it a filter that matches nothing, e.g.
`district` is `none`. After a search, the page replaces only that filter:

| Layer | Matches on |
|---|---|
| `house-highlight`, `senate-highlight`, `congress-highlight` | `district` (e.g. `64`) |
| `precincts-highlight` | `id` (e.g. `Gallatin-64B`) |

## 4. Publish and connect

**Publish** the style, then copy its **Style URL** (`mapbox://styles/yourname/...`)
into the plugin settings. Republishing in Studio updates the live map; no
plugin changes needed.

## Token

Create a public (`pk.`) token in Mapbox → Tokens with **URL restrictions** for
the WordPress site. For the local dev server, either add
`http://localhost:8080` to the allowed URLs or use a separate dev token.
