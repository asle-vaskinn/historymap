# Archived legacy data artifacts

Moved here 2026-07-04 from `data/` root during repo cleanup. These are
pre-pipeline-era generated artifacts that nothing in the current codebase
references (verified by grep across frontend, backend, scripts, ml).

The canonical data flow is `data/sources/ → data/merged/ → data/export/`
(regenerate with `PYTHONPATH=scripts python3 scripts/pipeline.py`).

| File | What it was |
|------|-------------|
| `buildings_dated.geojson` | Pre-merge dated buildings (superseded by `merged/buildings_merged.geojson`) |
| `buildings_unified.geojson` | Old unified building set |
| `buildings_temporal.geojson` (+ `.meta.json`) | Old temporal export (superseded by `export/buildings.geojson` + PMTiles) |
| `buildings_demolished_since_1880.geojson`, `buildings_demolished_unified.geojson` | Old demolition experiments |
| `roads_dated.geojson` | Old road dating output (superseded by `roads_temporal.geojson` pipeline output) |
| `extracted/` | One-off 1936 ML extraction output |
| `db/` | Abandoned SQLite evidence prototype (the `scripts/db/` code was removed the same day) |
| `CLEANUP_RECOMMENDATIONS.md`, `cleanup.sh` | The Dec-2025 cleanup plan these moves finally executed (in updated form) |

Note: `data/buildings.geojson` and `data/buildings_demolished.geojson` at the
data root are still symlinks to `buildings_v2.geojson` / `buildings_demolished_v2.geojson`,
which were kept in place. Everything here can be deleted outright once the
year-by-year pipeline rework no longer needs them for comparison.
