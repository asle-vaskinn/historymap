# Current Work

**Status:** Frontend tool consolidation (uncommitted) + picking the project back up
**Last updated:** 2026-06-20

> Read this first on any new task. For the full codebase map see [`AGENTS.md`](../../AGENTS.md);
> for known loose ends see [`../tech/IMPLEMENTATION_STATUS.md`](../tech/IMPLEMENTATION_STATUS.md).

---

## ▶ Active proposal: CI/CD + VPS consolidation (2026-06-20)

Approved direction — set up GitHub Actions CI/deploy by reusing the
`subscribe`/`nextbrain` harness and move the live site onto the shared Hetzner VPS
(`62.238.25.113`) as tenant #3, retiring the dedicated box `77.42.33.192`.

- **Spec:** [`../spec/feat_cicd/SPEC.md`](../spec/feat_cicd/SPEC.md) (AC1–AC10)
- **Plan:** [`../superpowers/plans/2026-06-20-cicd-vps-consolidation.md`](../superpowers/plans/2026-06-20-cicd-vps-consolidation.md)
- **Next:** run `/implement` (start Phase 1 CI — needs no secrets). Phases 2–4 need
  user-only steps: SSH access, GitHub secrets, DNS repoint.

---

## Where things stand

The most recent committed work (`68f36a0`) added the **source manager** with TPS
georeferencing and GCP improvements. On top of that there is a batch of **uncommitted
frontend reorganization** in the working tree — the in-flight task is consolidating the
georeferencing / ML tooling and clearing out superseded editors.

### Uncommitted changes (working tree)

| Change | Meaning |
|--------|---------|
| `source_viewer.{html,js,css}` → `feature_extraction.{html,js,css}` | Renamed the ML / annotation tool to its current name |
| `dataprep.{html,js,css}` → `frontend/legacy/` | Old data-prep tool retired to read-only legacy |
| New `frontend/legacy/{gcp_editor,georef_editor,source_manager_old,water_editor}.html` | Superseded standalone editors archived |
| `frontend/source_manager.html` modified | Current georeferencing tool (TPS + GCP work) |
| `backend/app.py`, `nginx.conf`, `scripts/georef_server.py` modified | Backend/routing adjustments accompanying the above |
| New `docs/tech/TILE_*.md`, `docs/tech/georef_transform_analysis.md`, `scripts/generate_raster_tiles.sh` | Raster tile generation docs + script |

**Current frontend tools (the live set):**
- `index.html` + `app.js` — the map viewer (year slider, layer toggles, inspect/edit modes)
- `source_manager.html` — georeferencing UI (GCP placement, affine preview + TPS warp)
- `feature_extraction.{html,js,css}` — ML pipeline control + annotation drawing
- `frontend/legacy/` — **read-only**, do not edit

### Next steps to resume

1. Decide whether the uncommitted frontend reorg is finished; if so, commit it on a branch
   (per `CLAUDE.md` git workflow — never commit straight to `main`).
2. Verify the renamed `feature_extraction.*` tool still loads and its API calls work
   (`node --check frontend/feature_extraction.js`, then exercise via docker).
3. Confirm `nginx.conf` + `backend/app.py` changes are consistent with the rename.
4. Reconcile any docs still referencing the old `source_viewer.*` / `dataprep.*` names
   (e.g. `docs/spec/feat_source_viewer/`).

---

## Paused: Water Timeline Pipeline

**Status: PAUSED** — ML water extraction blocked on low IoU (class imbalance).

Goal: show coastal change 1700–2025, including land-reclamation areas (Brattøra ~1960–1980,
Nedre Elvehavn ~1970–1990, Ilsvika ~1950–1970).

- **Done:** water integrated into the main pipeline (`--feature-type water`); OSM water
  fetcher (`scripts/ingest/fetch_osm_water.py`); water editor (`scripts/water_editor.py`,
  :5002); `merge_water.py` + `export_water.py`; water layer with temporal filtering on the map.
- **Blocked / TODO:** train a usable water model (`ml/config_water.yaml` — IoU too low),
  run inference on historical maps, vectorize, then manual correction of key reclamation areas.

Schema reminder — water features: `wtype` (river/fjord/lake/canal/harbor), `sd`, `ed`,
`ev` (h/m/l), `nm`, `src` (osm/man/ml). Manual edits land in
`data/sources/manual/water.geojson`; re-run the pipeline to merge + export.

Background: [`../tech/water-pipeline.md`](../tech/water-pipeline.md),
[`../handover/water_pipeline_handover.md`](../handover/water_pipeline_handover.md).

---

## Recently completed (chronological)

- **Source manager + TPS georeferencing** — dual-canvas GCP placement, affine preview +
  TPS final warp, GCP persistence, large-image auto-resize, source-catalog CRUD.
- **Georeferencing alignment to OSM** — IoU matching with TPS/TIN/affine, train/test
  validation (`scripts/align_to_osm.py`), `/api/align` + `/api/alignment-report`.
- **Water editor tooling** — OSM import via Overpass, MapboxDraw polygon editing,
  `/api/water/{add,update,delete}`.
- **Road temporal network** — LSS-Hausdorff road matching, building-based date inference,
  multi-layer fallback (ML → building inference → year-2000 fallback).
- **Building replacement detection** — centroid-containment matching, `repl_by`/`repl_of`,
  `demolished` flag.
- **PMTiles + cache busting** — full PMTiles serving with `manifest.json` hash versioning;
  nginx range-request + immutable-cache config.
- **Timeline UI** — year slider with ◀ ▶ step buttons.

Older per-phase reports are frozen in [`../archive/`](../archive/).
