# Trondheim Historical Map - Frontend

Vanilla JS + MapLibre GL 4 + PMTiles. **No build step** — files are served
as-is by nginx (docker `web` service) at `http://localhost:8080/`.

## Files

| File | Purpose |
|------|---------|
| `index.html` + `app.js` + `style.css` | Main viewer: year slider, temporal filtering (`sd`/`ed`), source filters, "Estimated" toggle for low-evidence (`ev='l'`) buildings (rendered muted) |
| `source_manager.html` | Georeferencing tool: upload historical maps, place GCPs, run georef jobs via `/api/georef/*` |
| `feature_extraction.html` + `.js` + `.css` | ML/annotation tool: inspect sources, annotate, drive ML train/verify via `/api/` (formerly `source_viewer.*`) |
| `about.html` | Static about page |
| `1880_overlay.html` | Standalone 1880-map overlay demo |
| `test_source_filter.html` | Test harness for source-filter logic |

## Data paths

`CONFIG` in `app.js` uses paths **relative** to the frontend root
(e.g. `data/trondheim.pmtiles`, `data/buildings_temporal.pmtiles`,
`data/roads_temporal.geojson`, `data/manifest.json`,
`data/sources_manifest.json`) — nginx maps `/data/` to the repo `data/`
directory. The backend API is reached at `/api/` (nginx proxies to the
FastAPI container on :5000).

## Development

```bash
docker compose up -d     # full stack at http://localhost:8080
make serve               # frontend-only (npx serve — NOT python http.server,
                         # PMTiles need HTTP Range support)
```

After editing any `.js` file, run `node --check frontend/app.js` (and any
other edited file) before committing.

See `AGENTS.md` §4 for filter logic details (Type A timeline-filtered sources
vs Type B all-or-nothing ML snapshots, MapLibre legacy filter syntax).
