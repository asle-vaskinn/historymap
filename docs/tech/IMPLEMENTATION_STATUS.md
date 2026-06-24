# Implementation Status & Loose Ends

**Regenerated:** 2026-06-14, verified against the current code and `data/export/`.

> The previous version of this file (Dec 2025) is preserved in git history. It described the
> pipeline as non-functional ("no normalizers", "can't run", "PMTiles not integrated") and
> referenced the repo's old path (`Development/private/historymap`). All of that is **obsolete** —
> the pipeline runs end to end today. This rewrite keeps only what is still true.

When a doc entry and the code disagree, **trust the code and flag the doc**.

---

## What works (verified)

- **Pipeline runs end to end.** `scripts/normalize/` has normalizers for ~13 sources
  (osm, osm_roads, sefrak, finn, fkb, kulturminner, byantikvaren, nvdb, manual, ml, ml_roads,
  ml_water, water); `scripts/ingest/` has matching ingestors; `scripts/merge/` and
  `scripts/export/` produce merged + exported output.
- **Export is populated.** `data/export/` holds real artifacts: `buildings.geojson` (~30 MB),
  `buildings.pmtiles`, `buildings_temporal.pmtiles`, `trondheim.pmtiles`, `water.{geojson,pmtiles}`,
  `manifest.json`, and a raster `tiles/` pyramid.
- **PMTiles is the default** serving format (tippecanoe via `scripts/export/export_pmtiles.py`),
  with `manifest.json` hash-based cache busting and nginx range-request config.
- **Backend is live** — FastAPI (`backend/app.py`) with ~34 `/api` endpoints and a sequential
  job queue (`backend/jobs.py`).

---

## Genuine loose ends

### ML training incomplete
- `models/checkpoints/best_model.pth` exists (5-class U-Net). The `checkpoints_1904/` and
  `checkpoints_1937/` dirs are **empty** — those fine-tunes were never trained to completion.
- **Water model** (`ml/config_water.yaml`) trains to **low IoU** from class imbalance — the
  water ML branch is paused (see [`../todo/current_work.md`](../todo/current_work.md)).
- There is no single "run the trained model over all historical maps and emit GeoJSON"
  one-shot script — inference is run manually via `ml/predict.py` + `ml/vectorize.py`.

### Data sources not yet wired
- Some sources are marked disabled in `data/merged/merge_config.json` (e.g. Matrikkelen,
  Trondheim kommune — "API integration pending"). Verify the `enabled` flags before assuming a
  source contributes to the merge.

### Known duplication / fragility
- **Affine/TPS transform math is duplicated** between `frontend/source_manager.html` and
  `frontend/feature_extraction.js` — a fix in one usually belongs in both. Flag it, don't
  silently fix one (see `CLAUDE.md` gotcha #6 and `AGENTS.md` §4).
- **Backend jobs are in-memory only** — a backend restart loses job history (disk artifacts
  survive). Acceptable for a single-user tool; don't rely on job history persisting.
- **Shapely is optional** in merge — without it, spatial matching silently degrades to bbox
  matching.

### Doc drift to reconcile
- Specs/docs that still reference the old `source_viewer.*` or `dataprep.*` names
  (e.g. `docs/spec/feat_source_viewer/`) — the live tools are `feature_extraction.*` and
  `source_manager.html`, with the old ones in `frontend/legacy/`.

---

## Frontend intentional behaviors (not bugs)

- Undated **buildings** appear from **1960**; undated **roads** from **2000** — deliberate
  fallbacks. Don't "fix" without checking `docs/spec/feat_temporal_pipeline/`.
- Roads before 1900 are evidence-gated (`ev == 'h'` only).
- **Type A** sources (sef/mat/tk/man/finn/osm) are timeline-filtered; **Type B** ML snapshots
  (kv1880/kv1904/air1947) are all-or-nothing per `snapshotFilter`. Test both paths after
  touching filter logic.

---

## How to re-verify this file

```bash
ls scripts/normalize/ scripts/ingest/ scripts/export/   # confirm modules exist
ls data/export/                                          # confirm artifacts exist
PYTHONPATH=scripts python3 scripts/pipeline.py --list    # source + stage status
ls models/checkpoints/ models/checkpoints_1904/ models/checkpoints_1937/   # ML state
```
