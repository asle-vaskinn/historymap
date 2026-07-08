# Current Work

**Status:** Repo cleanup + spec alignment landed; next up is real dating coverage
**Last updated:** 2026-07-04

> Read this first on any new task. For the full codebase map see [`AGENTS.md`](../../AGENTS.md);
> for known loose ends see [`../tech/IMPLEMENTATION_STATUS.md`](../tech/IMPLEMENTATION_STATUS.md).

---

## ▶ 2026-07-04: Cleanup + temporal-spec alignment (committed on `feature/year-by-year-improvements`)

One commit per change so any step can be reverted individually (`git log --oneline`):

1. **Dead code removed (~32k lines):** `production/` (pre-CI/CD deploy path), the unwired
   `scripts/extract|db|generate` packages + `config_schema.py`/`pipeline_state.py`, ~25
   superseded one-off scripts, the phase-4 annotation toolkit, the dead editor servers
   (`water_editor.py` :5002, `georef_server.py` :8082, `gcp_editor.py`) and `frontend/legacy/`.
   All recoverable from git history.
2. **Single backend:** the Flask :5001 manual-edit API was folded into the FastAPI backend
   (`GET/POST /api/manual`, `POST /api/rebuild`); `app.js` now calls them through nginx
   — the "building-year save Load failed" bug class is gone. Only port 8080 is exposed.
3. **No fallback years (spec alignment):** the 1960/2000 frontend fallbacks were removed per
   [`../spec/feat_temporal_pipeline/SPEC.md`](../spec/feat_temporal_pipeline/SPEC.md).
   Undated and low-evidence (`ev='l'`) features render **muted** and follow the new
   **Estimated** toggle in the viewer (feat_year_by_year Decision 5C).
4. **Self-contained export:** `data/export/` now contains everything the frontend needs
   (`roads_temporal.geojson` — the pipeline previously wrote it under a name nothing used —
   `sources_manifest.json`, `manifest.json`); root `data/` live files are symlinks into it,
   so `sync_data.sh` ships a complete site. Legacy root artifacts moved to
   `data/archive/legacy_root/` (see its README).
5. **Docs reconciled:** SPEC.md carries a "current intent" banner; the fallback-era docs
   (PIPELINE_DESIGN, PRODUCT_SPEC, DATA_PIPELINE_ARCHITECTURE, methodology, DATA_SCHEMA)
   are marked legacy-record; stale QUICKSTART/user_guide archived; backend/frontend READMEs
   rewritten.
6. **Verified:** pytest 39/39, `test_frontend.js` 24/24, `test_pipeline_e2e.py` green
   (it had been failing — see below), docker smoke on all endpoints + PMTiles range requests.

### ⚠ Honest-data reality discovered during verification

A full `rebuild.sh` had not been run since January. Running it revealed the old
"100 % dated" exports were only achievable via fallbacks baked into data:

- **Buildings:** the current pipeline produces ~2.3 % genuinely dated buildings
  (SEFRAK matches). The old export's 60,994 `ev='l'` buildings carried an inherited
  sd=1960. The 1960-inheritance path no longer exists in the pipeline.
- **Roads:** 47 of 36,730 roads have a real `sd`. The old `roads_temporal.geojson`
  (10,000 roads, "100 % dated") had the year-2000 fallback baked in — archived as
  `data/archive/legacy_root/roads_temporal_fallbackbaked.geojson`.

The viewer handles this honestly (undated = muted + toggle; `validate_export.py` now
reports missing `sd` as a *coverage gap* warning, not an error). **Dating coverage is
now the explicit product gap, not something fallbacks paper over.**

---

## Next steps (the year-by-year plan)

Per [`../spec/feat_temporal_pipeline/SPEC.md`](../spec/feat_temporal_pipeline/SPEC.md) +
[`../spec/feat_year_by_year/PROPOSAL.md`](../spec/feat_year_by_year/PROPOSAL.md).

**2026-07-04 finding:** Matrikkelen does **not** contain byggeår at all (Kartverket:
[byggeår-siden](https://www.kartverket.no/en/property/mine-eiendommer/bygning-og-bruksenheter/byggear-for-bygninger-og-bruksenheter));
brukstillatelse/ferdigattest dates exist only from 2009. The registry lever therefore
shrinks, and **the backward map/aerial pass is the primary dating engine** — which is
exactly what SPEC.md was designed for:

1. **Backward map pass on existing extracted sources** (SPEC.md §5b–5c): kv1880,
   kv1904 and air1947 are already georeferenced + ML-extracted
   (`data/sources/ml_detected/`). Match OSM anchors newest → oldest for `map_window`
   intervals and demolished-building discovery. Also populate `sd_method`/`sd_src`
   in the export (currently dropped by the export stage).
2. **Registry supplements (quick wins):** Byantikvaren kulturminnekart — ~5,000
   Trondheim buildings *with byggeår* (classes A/B/C; a `byantikvaren` ingest module
   already exists — check whether it captures byggeår); post-2009 matrikkel
   brukstillatelse/ferdigattest for new construction and bygningsstatus "revet" for `ed`.
3. **Densify the timeline:** georeference more Kartverket sheets and the Norge i
   bilder aerial epochs (Trondheim has many: 1947, 1950s, 60s, 70s, 80s, 90s …) —
   every added epoch tightens the `sd`/`ed` windows by roughly a decade. Aerials are
   processed after maps per SPEC.md §5d (harder extraction, refinement only).
4. **UX:** animated playback + URL year state (`?year=1965`) once dates move.
5. **CI/CD remaining user-only steps:** GitHub secrets, Environments, DNS, provision —
   see [`../tech/DEPLOYMENT.md`](../tech/DEPLOYMENT.md) §First-time setup.

---

## Paused: Water Timeline Pipeline

**Status: PAUSED** — ML water extraction blocked on low IoU (class imbalance).

Goal: coastal change 1700–2025 incl. land reclamation (Brattøra ~1960–1980,
Nedre Elvehavn ~1970–1990, Ilsvika ~1950–1970). Done: water in main pipeline,
OSM fetcher, `/api/water/*` endpoints, temporal water layer. TODO: usable water
model (`ml/config_water.yaml`), inference on historical maps, manual correction
of reclamation areas. Background: [`../tech/water-pipeline.md`](../tech/water-pipeline.md),
[`../handover/water_pipeline_handover.md`](../handover/water_pipeline_handover.md).

---

## Recently completed (chronological)

- **2026-07-04 cleanup + spec alignment** (this page, above).
- **CI/CD harness** (`test.yml`, deploy workflows, VPS scripts) — implemented; user-side
  setup steps remain (see DEPLOYMENT.md).
- **Source manager + TPS georeferencing**, **alignment to OSM**, **road temporal network**,
  **building replacement detection**, **PMTiles + cache busting**, **timeline UI** —
  see [`../archive/`](../archive/) for frozen phase reports.
