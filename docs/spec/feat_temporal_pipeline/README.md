# Feature: Temporal Data Extraction

Build a temporal dataset of features (buildings, roads, nature) by combining multiple sources.

## Operations

Two fundamental operations for building temporal knowledge:

### 1. Find New Objects

Discover objects and add them to the dataset.

```
Source → Extract objects → Add to dataset with temporal bounds
```

A source is "good for finding" if it contains objects not yet in the dataset.

### 2. Verify Existence Across Time

Confirm when known objects existed (or didn't exist).

```
Known object + Source → Check presence → Refine temporal bounds
```

A source is "good for verifying" if it provides point-in-time snapshots.

## Sources

A **source** provides information about features at a specific time or time range.

### Source Properties

| Property | Description |
|----------|-------------|
| `time_point` | When this source represents (year or range) |
| `feature_types` | What it contains (buildings, roads, etc.) |
| `find_strength` | How good for discovering new objects (high/medium/low) |
| `verify_strength` | How good for temporal verification (high/medium/low) |
| `extraction_method` | How to get data (registry, ML, manual, etc.) |

### Source Catalog

#### Modern Baseline

| Source | Time | Features | Find | Verify | Notes |
|--------|------|----------|------|--------|-------|
| OSM | current | all | **primary** | - | Start here - current state of all features |

#### Registries (Temporal Enrichment)

| Source | Time | Features | Find | Verify | Notes |
|--------|------|----------|------|--------|-------|
| SEFRAK | pre-1900 | buildings | - | high | Adds construction dates to OSM buildings |
| Matrikkelen | current | buildings | - | medium | Property registry, may have dates |

#### Historical Maps (ML-extractable)

| Source | Time | Features | Find | Verify | Notes |
|--------|------|----------|------|--------|-------|
| Kartverket 1880 | ~1880 | all | medium | high | Topographic map |
| Kartverket 1904 | ~1904 | all | medium | high | Topographic map |
| Aerial 1947 | 1947 | all | medium | high | Post-war aerial |
| Aerial 1964 | 1964 | all | low | high | Later aerial |

#### Future Sources (Examples)

| Source | Time | Features | Find | Verify | Notes |
|--------|------|----------|------|--------|-------|
| Road Registry | varies | roads | high | low | If one exists for Norway |
| Insurance Maps | 1890s | buildings | high | high | Detailed building footprints |
| Municipal Archives | varies | all | medium | medium | Historical records |

## Typical Workflow

```
1. FIND: Start with modern baseline
   OSM → all current buildings, roads, nature
   (These exist today, but we don't know when they were built)

2. VERIFY: Enrich with registry data
   SEFRAK → matches OSM buildings, adds construction dates
   Matrikkelen → adds additional date information

3. FIND+VERIFY: Process historical maps (ML)
   Kartverket 1880 →
     - VERIFY: confirms OSM/SEFRAK buildings existed in 1880
     - FIND: discovers demolished buildings not in OSM

4. VERIFY: Chain additional historical sources
   Kartverket 1904 → refines temporal bounds
   Aerial 1947 → detects demolitions between 1904-1947
```

## Operations by Feature Type

### Buildings

| Source | Find | Verify |
|--------|------|--------|
| OSM | Current footprints (baseline) | - |
| SEFRAK | - | Adds construction dates to OSM buildings |
| Matrikkelen | - | Additional date information |
| ML (historical maps) | Demolished buildings | Confirm existence at map date |

### Roads

| Source | Find | Verify |
|--------|------|--------|
| OSM | Current road network | - |
| ML (any historical map) | Historical roads | Confirm existence at map date |
| (No SEFRAK equivalent) | - | - |

### Nature (Water, Forest)

| Source | Find | Verify |
|--------|------|--------|
| OSM | Current state | - |
| ML (any historical map) | Historical extent | Changes over time |

## Temporal Bound Inference

When combining sources, infer temporal bounds:

| Scenario | Inference |
|----------|-----------|
| Found in SEFRAK (built 1875) | `start_date = 1875` (authoritative) |
| Found in 1880 map, not in OSM | `start_date ≤ 1880`, `end_date < present` |
| Found in 1880, not in 1904 | `end_date` between 1880-1904 |
| Found in OSM, not in 1880 map | `start_date > 1880` (or missed by ML) |
| Found in 1880 and 1904, not in 1947 | `end_date` between 1904-1947 |

## Evidence Strength

Evidence level based on source combination:

| Combination | Evidence |
|-------------|----------|
| Registry + ML verification | High |
| Multiple ML sources agree | High |
| Single ML source | Medium |
| OSM only (no historical) | Low |

## Extraction Methods

How data is extracted from sources:

| Method | Sources | Output |
|--------|---------|--------|
| Direct import | SEFRAK, Matrikkelen, OSM | GeoJSON with attributes |
| ML segmentation | Historical maps | Raster mask → vectorized polygons |
| Manual annotation | Any | Ground truth for training/validation |

## Implementation Details

See the following technical documentation for implementation:

- **Data Schema**: `/docs/tech/DATA_SCHEMA.md` - Detailed schema for temporal attributes
- **Pipeline Architecture**: `/docs/tech/DATA_PIPELINE_ARCHITECTURE.md` - Full pipeline implementation
- **Methodology**: `/docs/tech/methodology.md` - ML and data processing methodology

## Early Implementation Notes

The initial pipeline implementation (Phase 1-4) included:

1. **SEFRAK Download** - GML files from Geonorge API
2. **SEFRAK Conversion** - Parse GML, extract temporal data (construction decades)
3. **OSM Fetch** - Overpass API for building polygons
4. **Spatial Matching** - SEFRAK points → OSM polygons (within 30m)
5. **PMTiles Generation** - Tippecanoe for vector tiles

**Initial Results:**
- SEFRAK matched: 2,786 buildings (1700-1900)
- OSM with dates: 51 buildings
- Assumed modern: 41,526 buildings (no date → assumed 1950+)

**Output Files (historical):**
- `data/sefrak/sefrak_trondheim.geojson` - SEFRAK points
- `data/buildings_temporal.geojson` - OSM + SEFRAK merged
- `data/buildings_temporal.pmtiles` - Vector tiles

## Status

- [x] SEFRAK import pipeline
- [x] OSM import pipeline
- [x] ML extraction (U-Net trained)
- [x] Vectorization
- [x] Multi-source temporal inference (merge pipeline)
- [ ] Road-specific sources (if available)
