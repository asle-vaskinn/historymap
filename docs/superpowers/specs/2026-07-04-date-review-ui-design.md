# Design: Map-Dating Review Tool (DATE stage MVP + review UI)

**Date:** 2026-07-04
**Status:** Approved (brainstorm with user; approach A chosen)
**Implements:** `docs/spec/feat_temporal_pipeline/SPEC.md` §5b/5c (backward map pass) — MVP
**First target map:** Trondheim 1936 (byarkiv; warped GeoTIFF exists)

## Purpose

The backward map pass needs a human in the loop: deterministic matching handles clean
cases, but partial overlaps, multi-candidate matches, demolished-building candidates and
date conflicts need review. This design adds the missing **editor entry point** for that
workflow: a focused localhost review tool, plus the DATE-stage matcher that feeds it.

Explicitly out of scope: georeferencing (stays in `source_manager.html`), ML extraction
control (stays in `feature_extraction.html`), public viewer changes.

**Prerequisite (not part of this build, done first as data work):** an actual extraction
for the target map — run `ml/predict.py` + `ml/vectorize.py` on the warped
`trondheim_1936` GeoTIFF and align with `scripts/align_to_osm.py`, producing
`data/sources/ml_detected/trondheim_1936/buildings_aligned.geojson`. The current
ml_detected entries for kv1880/kv1904/air1947 are 1–3-feature test stubs; only
ortofoto1937 (85 buildings) is real. The tool can be smoke-tested against ortofoto1937
while the 1936 extraction is produced.

## Decisions made with the user

| Decision | Choice |
|---|---|
| Tool scope | Focused review tool (new page), not a workflow cockpit, not a viewer mode |
| Review flow | Card queue sidebar + map pane; keyboard-driven triage |
| Auto-accept | Clean matches auto-ACCEPT; humans review QUEUE only (auto-accepts browsable/overturnable) |
| Architecture | A: precomputed queue artifacts + thin API + new vanilla page |

## Architecture

```
scripts/date/match_map.py            # NEW pipeline stage (SPEC §5b/5c MVP)
  inputs:
    data/sources/ml_detected/<map>/buildings_aligned.geojson   # extracted footprints
    data/sources/osm/normalized/buildings.geojson              # anchors
    data/merged/buildings_merged.geojson                       # existing date evidence (for conflict detection)
    data/sources/map_review/<map>/decisions.json               # human overrides (optional)
  outputs (data/sources/map_review/<map>/):
    matches.json    # auto-ACCEPT items
    queue.json      # items needing human review
    report.json     # counts, thresholds, dropped items, run timestamp

scripts/normalize/normalize_map_review.py    # NEW, standard BaseNormalizer
  # matches.json + accepted decisions → normalized date evidence:
  #   sd ≤ map_year, ev=m, sd_method=map_window, sd_src=<map_id>
  # accepted demolished candidates → new features with ed windows
  # → consumed by the existing merge stage like any other source

backend/app.py                                # 3 NEW endpoints
  GET  /api/review/{map_id}            # queue + progress + report summary
  POST /api/review/{map_id}/decision   # {item_id, action: accept|reject|demolished|skip, note?}
  POST /api/review/{map_id}/rerun      # job-queue run of match_map.py

frontend/date_review.html + date_review.js (+ css)   # NEW focused page
  # vanilla MapLibre, no build step (house pattern)
```

**Re-run safety:** the matcher recomputes everything, but `decisions.json` always wins —
human decisions are never overwritten. Deleting `matches.json`/`queue.json` and re-running
is always safe. This keeps the pipeline deterministic and re-runnable (SPEC acceptance
criterion).

## Matcher rules (deterministic, no ML)

**Epistemics:** extracted 1936 polygons are *occupancy evidence*, not geometry —
"built mass stood approximately here." The OSM footprint stays the permanent anchor;
identity is assumed by continuity (same building unless evidence otherwise). A match
contributes only the temporal bound; the extracted polygon is discarded afterwards,
except for demolished candidates where it becomes the (approximate) geometry of a
feature with no modern counterpart.

- Candidate pairing via spatial index (shapely STRtree).
- **Primary score = per-anchor coverage**: fraction of the OSM footprint covered by the
  union of extracted 1936 built-mass. Drawn maps merge row houses into single block
  blobs, so one extracted feature may support MANY anchors (many-to-one is expected,
  not an error). Symmetric IoU is the secondary signal: high coverage + low IoU with a
  single small blob suggests "same plot, different building" (replacement) → QUEUE.
- `coverage ≥ 0.5` (and no replacement signal) → auto-ACCEPT.
- `0.15 ≤ coverage < 0.5`, or replacement signal → QUEUE.
- `coverage < 0.15` → no match: the anchor is unconstrained by this map — with a newer
  matched observation this becomes `sd ∈ (1936, newer]` (absence is evidence too, where
  extraction quality is trusted).
- Extracted feature with no OSM match, area ≥ 30 m² → QUEUE as *demolished candidate*;
  below 30 m² → dropped but counted in `report.json` (no silent truncation).
- OSM building with no extracted match → unconstrained by this map (report counts only).
  Interval bounds (`sd ∈ (older_map, newer_map]`) activate when a second map is matched;
  `match_map.py` takes `--map-year` and writes bounds so no redesign is needed then.
- Conflict (map match contradicts an existing higher-evidence date, e.g. registry
  `sd=1950` vs match implying `sd ≤ 1936`) → QUEUE with `type: conflict`, sorted first.
  Full BLOCK semantics (halting export) deferred until the review loop has proven itself;
  `report.json` makes conflicts visible.

## Queue item shape (synthetic example)

```json
{
  "item_id": "t1936_q_00042",
  "type": "low_overlap | multi_candidate | demolished | conflict",
  "map_id": "trondheim_1936",
  "map_year": 1936,
  "extracted": { "geometry": "<GeoJSON>", "mlc": 0.87, "area_m2": 142.0 },
  "candidates": [ { "osm_id": "way/123", "iou": 0.31, "centroid_dist_m": 6.2 } ],
  "context": { "existing_sd": null, "existing_sd_src": null }
}
```

Decision record: `{ "item_id", "action", "chosen_osm_id?", "note?", "decided_at" }` —
appended to `decisions.json`; latest decision per item wins (undo = re-decide).

## UI

- **Sidebar:** card queue sorted by uncertainty (conflicts first), progress bar
  (`reviewed/queued`, auto-accept count), filter by item type.
- **Card:** side-by-side thumbnail (historical raster crop vs OSM situation), score,
  queue reason, candidate chooser when multiple.
- **Map pane:** three toggleable layers — historical raster (warped map, served as in
  the viewer's inspect mode), extracted footprint (orange fill), OSM anchors (blue
  outline). Clicking a card zooms to the item.
- **Keyboard:** `a` accept, `r` reject, `d` demolished, `s` skip, arrows navigate.
- Optimistic UI: decision applies instantly, POST in background; failed POST re-flags
  the card with a visible error.

## Error handling

- Endpoints 404 with clear detail for unknown `map_id`; decision POSTs validate
  `item_id` against the current queue.
- All artifact writes are atomic (write temp + rename) so a crash cannot corrupt
  `decisions.json`.
- Page shows a banner with the exact command to run when queue artifacts are missing.

## Testing

- `tests/test_date/` pytest units on synthetic fixtures: clean match, partial overlap,
  multi-candidate, demolished candidate, sub-threshold drop, conflict, decision override
  on re-run.
- FastAPI TestClient tests for the three endpoints.
- `node --check` + `scripts/test_frontend.js` conventions for the page.
- E2E: run `match_map.py` on the real 1936 extraction → review a handful of items →
  normalize + merge → assert dated buildings appear in `data/export/buildings.geojson`.

## Milestone definition of done

Trondheim 1936 matched; QUEUE reviewed; merge/export produces buildings with
`sd ≤ 1936`, `ev=m`, `sd_method=map_window`, `sd_src=trondheim_1936`; the viewer shows
them solid (not muted) for years ≥ 1936; demolished acceptances appear with `ed` windows.
