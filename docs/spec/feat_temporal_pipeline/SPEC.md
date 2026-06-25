# Pipeline Spec: Year-by-Year Temporal Dataset

## Goal

Produce a map of Trondheim for every year 1850–2025 showing buildings, roads,
water, fields and forest — each feature knowing *when* it existed and *why* we
believe that.

---

## Epistemics: no undated features

Every feature in the dataset came from a dated source. There is no other way
to know it exists. Therefore:

- `sd` (start date) always has an upper bound — the year of the source that
  first recorded the feature.
- `ed` (end date) is `null` for features that still exist today, or bounded
  by the maps where the feature last appeared and first disappeared.
- There are no fallback defaults. A feature without a dated observation is not
  in the dataset.
- Proximity inference never creates a date from nothing — it only tightens a
  range already established by source evidence.

---

## Data model (per feature)

| Field | Type | Description |
|---|---|---|
| `sd` | int | Start date — year of construction / first observation |
| `ed` | int\|null | End date — year demolished, null if still exists |
| `ev` | h\|m\|l | Evidence quality (high / medium / low) |
| `sd_method` | string | How `sd` was determined (see below) |
| `sd_src` | string | Source(s) that determined `sd` |
| `sources` | string[] | All source IDs that contributed to this feature |

**`sd_method` values (in confidence order):**

| Method | Meaning | ev |
|---|---|---|
| `direct` | Construction year from registry (SEFRAK, Matrikkelen) | h |
| `map_window` | Constrained by presence/absence across dated maps | m |
| `aerial_window` | Constrained by aerial photo series | m |
| `proximity` | Range tightened by dated neighbours | l |
| `observation_bound` | Only constraint is year of first source observation | l |

---

## Source catalogue (in pipeline order)

| Source | Year | Feature types | Role |
|---|---|---|---|
| OSM | 2025 | all | Modern baseline geometry — anchor for backward pass |
| SEFRAK | pre-1900 | buildings | Direct construction dates — applied before map pass |
| Matrikkelen | current | buildings | Direct dates where available |
| Kartverket maps | 1865–1960s | all | Existence windows — processed newest → oldest |
| Aerial photos | 1947– | all | Refinement after maps — harder to extract, processed last |
| Municipal archives | varies | all | Supplementary direct dates (ad hoc) |

---

## Pipeline stages

```
[1] INGEST          Pull raw data, no transformation
[2] NORMALIZE       Standardize geometry + schema per source
[3] GEOREF          Align historical imagery to modern coordinates  (human GCPs)
[4] EXTRACT         ML feature extraction from georeferenced imagery
[5] DATE            Assign temporal bounds — ordered by confidence (see below)
[6] MERGE           Spatial conflict resolution + final unified dataset
[7] EXPORT          PMTiles + GeoJSON for viewer
```

Stages 3–4 apply only to raster sources (maps, aerials). All other sources
feed directly into stage 5.

---

## Stage 5: DATE — full algorithm

### 5a. Direct records (SEFRAK, Matrikkelen) — run FIRST

Match registry records to OSM buildings by spatial proximity (≤ 30 m centroid
distance). Assign `sd` directly from the registry field.

```
SEFRAK record: built 1897, matched to OSM building X
→ X.sd = 1897, X.ev = h, X.sd_method = direct, X.sd_src = sefrak:{id}
```

Buildings that receive a direct date skip further date assignment in 5b–5d
unless a map observation is *inconsistent* with the assigned date, in which
case the conflict is flagged for human review.

**Decision mode:** deterministic (spatial match) + human review for conflicts.

---

### 5b. Backward map pass — surviving buildings

Process each Kartverket map series from newest to oldest
(e.g. 1960 → 1930 → 1900 → 1865).

For each OSM building (anchor), attempt spatial match to the extracted
features of each map in order:

```
Match found  → sd ≤ map_year  — keep going back
No match     → sd ∈ (map_year, previous_map_year]  — stop, record window
```

**Example:**
```
OSM building A:
  1960: match → sd ≤ 1960
  1930: match → sd ≤ 1930
  1900: match → sd ≤ 1900
  1865: NO match → sd ∈ (1865, 1900], ev = m, sd_method = map_window
```

The result is an interval, not a single year. The viewer uses `sd ≤ year`
to decide visibility, so the feature appears from the lower bound of the
interval (i.e. the conservative estimate).

**Decision mode:** deterministic spatial match; low-confidence matches
(partial overlap, multiple candidates) → QUEUE for human review.

---

### 5c. Demolished building detection — new features added going backward

Features found in historical map extraction that have **no OSM match** are
candidates for demolished buildings. Process map series newest → oldest:

```
Feature F in map year X, no OSM match, absent from all newer maps processed
→ ed ∈ (X, next_newer_map_year]
→ continue going back to find sd

Feature F also found in map year X-Δ
→ sd ≤ X-Δ, still searching
```

**Example:**
```
Extracted feature F, no OSM match:
  1960: absent
  1930: absent
  1900: present → ed ∈ (1900, 1930]
  1865: present → sd ≤ 1865
→ demolished building: sd ≤ 1865, ed ∈ (1900, 1930], ev = m
```

Demolished buildings are **added as new features** to the dataset as they are
discovered going backward. They are distinct from OSM features.

**Decision mode:** spatial matching deterministic; unmatched features below
a size/confidence threshold → QUEUE for human review before adding to dataset.

---

### 5d. Aerial photo pass — refinement only

After the full map pass, process aerial photo series (newest → oldest) against
the same buildings. Aerials narrow existing windows — they never set `sd` from
scratch.

**Why maps before aerials:**
- Maps have explicit drawn feature boundaries — ML extraction is cleaner.
- Aerials require interpreting raw pixels — higher ML uncertainty.
- Pre-1960 aerials have poorer georeferencing accuracy.

**Decision mode:** same as map pass, but higher QUEUE threshold due to lower
baseline confidence.

---

### 5e. Proximity inference — remaining observation-bound buildings

For buildings with only `observation_bound` (seen in OSM only, not found in
any historical map), use spatial proximity to tighten the range.

Cluster spatially adjacent buildings with similar characteristics. Use dated
members of the cluster to infer a probable era for undated members. The
inferred range cannot exceed the observation bound already set.

```
Building B: sd ≤ 2025 (observation_bound only)
Cluster neighbours: sd ∈ (1895, 1910] × 4, sd ∈ (1900, 1920] × 2
→ B.sd ≈ 1900–1910, ev = l, sd_method = proximity
```

**Decision mode:** LLM proposes era per cluster with reasoning; human
approves/rejects in batch via review queue.

---

## Decision modes per step

| Step | Deterministic | LLM | Human |
|---|---|---|---|
| SEFRAK spatial match | ≤ 30 m rule | — | Ambiguous matches |
| GCP placement | — | Suggest candidates | **Place GCPs** (unavoidable) |
| ML feature extraction | U-Net inference | Read map labels/text | Review output quality |
| Backward map matching | Overlap threshold | — | Partial/ambiguous matches |
| Demolished detection | No-OSM-match rule | — | Below-threshold features |
| Aerial refinement | Overlap threshold | — | Uncertain matches |
| Proximity inference | Cluster formation | Era assignment + reasoning | Batch approve/reject |
| Date conflict | Detect contradiction | Propose resolution | Final decision |

**Three pipeline states per item:**

| State | Meaning |
|---|---|
| `ACCEPT` | Deterministic rule matched cleanly — proceed |
| `QUEUE` | Uncertain — human spot-check before committing |
| `BLOCK` | Contradictory evidence — must resolve before pipeline continues |

---

## Stage 6: MERGE

Combine surviving buildings (OSM + date evidence) with demolished buildings
(discovered during backward pass). Resolve conflicts where the same real-world
feature was contributed by multiple sources with different geometries or dates.

**Conflict resolution priority:**
1. Direct record (SEFRAK, Matrikkelen) always wins on `sd`
2. Tightest consistent map window wins over wider window
3. Higher `ev` wins over lower `ev`
4. Remaining conflicts → BLOCK for human review

---

## Viewer query

The year slider applies a single filter:

```sql
sd <= selected_year AND (ed IS NULL OR ed > selected_year)
```

The pipeline never stores per-year snapshots. All temporal logic lives in
`sd` and `ed` on each feature.

---

## Acceptance criteria

- [ ] Every feature has `sd`, `ev`, `sd_method`, `sd_src` populated
- [ ] No feature has `sd_method = default` (forbidden — use `observation_bound`)
- [ ] SEFRAK-matched buildings have `ev = h` and `sd_method = direct`
- [ ] All map-window features carry both bounds of the interval in `sd_src`
- [ ] Demolished buildings have non-null `ed`
- [ ] QUEUE items are visible in the review UI before export runs
- [ ] BLOCK items halt the pipeline until resolved
- [ ] Pipeline is re-runnable from any stage without corrupting earlier output
- [ ] Each stage produces a versioned output artifact (no in-place mutation)
