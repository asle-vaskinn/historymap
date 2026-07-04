# Proposal: Make It a Real Year-by-Year Map of Trondheim

## Status
- [x] Proposed
- [ ] Approved
- [ ] In Development
- [ ] Testing
- [ ] Complete

**Branch:** `feature/year-by-year-improvements`
**Author:** drafted with Claude, 2026-06-14
**Decision format:** every decision below lists 3–4 options; the **recommended** option is
marked ✅ and is the one this proposal adopts.

> **Cross-reference (2026-07-04):** This proposal is **complementary** to
> `docs/spec/feat_temporal_pipeline/SPEC.md`, which is the current approved
> pipeline intent. This PROPOSAL supplies the registry fix-points
> (Matrikkelen/SEFRAK construction dates, `sd`); the SPEC supplies the
> backward map-window algorithm that bounds everything else. Division of
> labour holds across both: registries = construction dates (`sd`),
> historical maps = demolition discovery (`ed`).

---

## Why (the diagnosis)

Measured from `data/export/buildings.geojson` (66,733 buildings):

| Metric | Today |
|--------|-------|
| Buildings with a **real dated** start year (evidence `h`/`m`) | ~5,700 (**8.6%**) |
| Buildings on the **1960 inherited fallback** (evidence `l`) | 60,994 (**91%**) |
| Buildings with a **demolition year** (`ed`) | **7** |
| Geometry source | OSM (61k) — coverage is fine |

The geometry is solved. **The year is the product, and 91% of it is a guess** — and
buildings essentially never disappear (7 demolitions). Every decision below serves one goal:
turn the temporal dimension from estimated into authoritative, and make it the star of the UX.

---

## Decision 1 — What do we fix first?

The single biggest lever for a year-by-year map.

| Option | Pros | Cons |
|--------|------|------|
| A. Authoritative **construction dates** (registry data) | Fixes the 91% problem directly; high-trust dates; reuses existing merge pattern | Needs a new data source + access |
| B. Improve the **ML extraction** (1904/1947 models, water) | Reuses existing investment | Expensive; low-trust dates (`trust_dates:false`); won't move the 91% much |
| C. **UX first** (playback, highlighting) | Quick wins, demos well | Polishes a map that's still 91% guesses — lipstick |
| D. **Demolition (`ed`)** coverage first | Brings the timeline's second half to life | Smaller absolute impact than fixing 91% of starts |

✅ **Recommended: A.** Construction-date coverage is the product. Everything else is
multiplied by getting this right first. (B is demoted — see Decision 6; C and D follow.)

---

## Decision 2 — Which source for construction years?

| Option | Coverage | Trust | Effort |
|--------|----------|-------|--------|
| A. **Matrikkelen** (official property register, `byggeår`) | ~all buildings | High | New ingestor+normalizer + access |
| B. **FKB-Bygning** (Kartverket cadastral) | High | High | Norge digitalt partnership; heavier data |
| C. **OSM `start_date` only** | Tiny (34 today) | High where present | Already wired; community-dependent |
| D. **Keep relying on ML / inheritance** | Status quo | Low | None |

✅ ~~**Recommended: A — Matrikkelen.**~~ **INVALIDATED 2026-07-04:** Kartverket confirms
byggeår is *not registered in Matrikkelen at all* — for any building, open or restricted
access ([kartverket.no/…/byggear-for-bygninger-og-bruksenheter](https://www.kartverket.no/en/property/mine-eiendommer/bygning-og-bruksenheter/byggear-for-bygninger-og-bruksenheter)).
The nearest proxies (midlertidig brukstillatelse / ferdigattest dates) exist only from
2009 onward — useful for dating *new* construction and for `ed` via bygningsstatus
"revet", but not for historical coverage.

**Revised recommendation:** the backward map/aerial pass
(`feat_temporal_pipeline/SPEC.md` §5b–5d) becomes the *primary* dating engine, with
registry supplements: Byantikvaren kulturminnekart (~5,000 Trondheim buildings with
byggeår), SEFRAK (already ingested), OSM `start_date`, and post-2009 matrikkel status
dates. Expected coverage comes from map/aerial windows (`ev=m`), not registry `ev=h`.

---

## Decision 3 — How do we access Matrikkelen data?

> ⚠️ Verify current access terms before committing — Norwegian open-data terms for the
> matrikkel have been changing. A `docs/matrikkelen_application.md` (gitignored) suggests an
> access application is already in progress.

| Option | Mechanism | Pros | Cons |
|--------|-----------|------|------|
| A. **Geonorge bulk download** ("Matrikkelen – Bygningspunkt", GML/GeoPackage) | One-off / periodic file | Fits the offline batch pipeline; no live API in the hot path; easy to re-run | Snapshot, not live; may need membership |
| B. **Matrikkel API** (SOAP/REST, live) | Per-query | Always current | Heavyweight; partner agreement; awkward for bulk |
| C. **Kommune / municipal open data** | Local export | May be openly licensed | Partial; format varies |
| D. **Third-party / commercial provider** | Hosted | Easy | Cost; licensing constraints |

✅ **Recommended: A — Geonorge bulk download** of the building-point dataset. It matches
the project's existing "ingest a file → normalize → merge" architecture (`BaseIngestor` /
`BaseNormalizer`), keeps the pipeline offline and reproducible, and a yearly refresh is
plenty for a historical map. Fall back to C if access to A is blocked short-term.

---

## Decision 4 — How do we attach matrikkel dates to OSM building polygons?

Matrikkelen building points must be joined to the OSM polygons that carry geometry.

| Option | Method | Pros | Cons |
|--------|--------|------|------|
| A. **Official building-number join** (`bygningsnummer` ↔ OSM `ref:bygningsnr`) | Exact key | Precise; no false matches | Only works where OSM has the ref tag |
| B. **Point-in-polygon** (matrikkel point inside OSM footprint) | Spatial containment | High coverage; simple | Ambiguous for adjacent/stacked buildings |
| C. **Nearest within N metres** | Distance | Catches missing footprints | False matches in dense areas |
| D. **Hybrid: A → B → C fallback** | Layered | Best of all; precise where possible, broad where not | Slightly more code |

✅ **Recommended: D — hybrid.** Try the exact building-number key first (this mirrors the
existing `osm_ref` matching already used for the FINN source), fall back to point-in-polygon,
then nearest-within-threshold. Record which method matched in `sd_method` so trust is auditable.

---

## Decision 5 — What about buildings still undated after Matrikkelen?

A residual set will remain (new builds, unmatched). Today they silently appear at 1960.

| Option | Behaviour | Pros | Cons |
|--------|-----------|------|------|
| A. **Keep silent 1960 fallback** | As-is | No work | The map lies — undated looks dated |
| B. **Hide undated buildings** | Only show dated | Honest | Map looks empty for sparse years |
| C. **Visually distinguish** (faded/hatched) + "show estimated" toggle | Render undated differently | Honest *and* complete; user controls | Small frontend change |
| D. **Per-building "unknown" neutral style always on** | Always greyed | Honest | No way to hide the noise |

✅ **Recommended: C.** Undated/low-evidence buildings render muted (e.g. reduced opacity or
hatch) with a toggle to hide them. The map stops implying false precision while staying full.
This is a small `app.js` change reusing the existing `ev`/`sd_method` fields.

> **Shipped 2026-07-04:** Option C is implemented — the silent frontend
> 1960/2000 fallback was removed, and `ev='l'` buildings render muted with an
> "Estimated" toggle.

---

## Decision 6 — Demolition (`ed`) strategy

The timeline's second half (buildings disappearing) barely exists (7 records).

| Option | Source of demolitions | Pros | Cons |
|--------|-----------------------|------|------|
| A. **Registries only** (Byantikvaren demolition years) | Official | High trust | Heritage buildings only |
| B. **Historical-map diff** (drawn on 1880/1904 map, absent in OSM today → demolished) | ML/footprint comparison | The *unique* value of the old maps | Needs the ML/georef branch working |
| C. **Replacement inference** (new building over old footprint ⇒ old demolished) | Already implemented | Free; already in pipeline | Only catches replaced, not cleared, sites |
| D. **Manual** via source_manager/edit mode | Researcher | Accurate | Doesn't scale |

✅ **Recommended: A + C now, B later.** Use Byantikvaren demolition dates and the existing
replacement-detection immediately; **reframe the ML/historical-map work as a demolition-
discovery engine** (B) rather than a construction-date source. Clean division of labour:
**registers = construction (`sd`), historical maps = demolition (`ed`).**

---

## Decision 7 — The headline UX upgrade

Once dates are real, make the time dimension compelling.

| Option | What | Pros | Cons |
|--------|------|------|------|
| A. **Animated playback** (play button sweeps years, fade in/out) | Motion | The defining feature of a year-by-year map; reuses `updateLayerFilters(year)` | Needs opacity transitions |
| B. **"What changed this year" highlight** | Pulse new/demolished | Narrative; cheap | Less wow alone |
| C. **URL deep-link state** (`?year=1965`) | Shareable | Trivial; high value | Not a "feature" by itself |
| D. **Side-by-side year compare** | Dual map | Powerful for analysis | Heaviest to build |

✅ **Recommended: A first, then C, then B.** Animated playback is the single most compelling
addition and the data plumbing already exists. URL state is nearly free. Highlighting layers
on top. Defer D.

---

## Decision 8 — Rollout mechanics

| Option | Approach | Pros | Cons |
|--------|----------|------|------|
| A. **Incremental source add** (enable Matrikkelen in `merge_config`, re-export) | Follows existing pattern | Low risk; reversible via config | — |
| B. **Big-bang re-architecture** | Rebuild merge | "Clean" | Risky; unnecessary |
| C. **Parallel dataset** (separate export, A/B) | Side-by-side | Safe comparison | Duplicate plumbing |

✅ **Recommended: A.** Add Matrikkelen as one more source in the established
ingest→normalize→merge→export flow, gated by its `enabled` flag, and re-export. Validate with
the coverage script before/after (rerun the query in `IMPLEMENTATION_STATUS.md`).

---

## Recommended end-to-end plan (the adopted path)

1. **Data:** Geonorge bulk download → `scripts/ingest/matrikkelen.py` + `normalize_matrikkelen.py`
   → enable in `merge_config.json` → hybrid join (Decision 4) → re-export.
   *Success metric: dated coverage 8.6% → ≥80%.*
2. **Honesty:** mute/toggle undated buildings (Decision 5).
3. **UX:** animated playback + URL state (Decision 7).
4. **Demolitions:** Byantikvaren `ed` + replacement inference now; repoint ML at demolition
   discovery later (Decision 6).

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Matrikkelen access blocked/licensing | Medium | High | Pursue Geonorge download + the in-progress application; fall back to kommune data |
| Join produces wrong matches | Medium | Medium | Exact-key-first hybrid; record `sd_method`; spot-check via provenance UI |
| Re-export regressions | Low | Medium | Incremental flag; before/after coverage check; keep ML sources unchanged |

## References

- `AGENTS.md` §6 (pipeline), §8 (schema), §4 (frontend filters)
- `data/merged/merge_config.json` (Matrikkelen entry, currently `enabled:false`)
- `docs/tech/IMPLEMENTATION_STATUS.md` (coverage re-verification query)
- `docs/spec/feat_temporal_pipeline/`, `docs/spec/feat_timeline_ui/`
- `docs/matrikkelen_application.md` (access application, gitignored)

## Changelog

### 2026-06-14
- Created proposal on branch `feature/year-by-year-improvements`.
