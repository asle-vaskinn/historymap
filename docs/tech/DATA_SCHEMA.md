# Temporal Data Schema

This document defines the temporal data schema for both buildings and roads.

---

# Building Temporal Data Schema

## Problem Statement

We have multiple data sources providing partial temporal information about buildings:

| Source | What it tells us | Certainty |
|--------|-----------------|-----------|
| SEFRAK | Building built in period X | High (registry) |
| OSM start_date | Building built in year Y | Variable |
| ML 1880 detection | Building existed in 1880 | ML confidence |
| ML 1880 non-detection | Building probably post-1880 | Lower confidence |
| Matrikkelen | Official build year | High (official) |
| Aerial photos | Building existed in year Z | High (visual) |

## OSM-Centric Data Model

Modern OSM buildings serve as the **canonical geometry layer**. Date information from other sources is **attached to** OSM buildings rather than creating separate features.

### Data Flow

```
OSM Buildings (polygons)     ──────────────────┐
                                               ▼
SEFRAK (points) ─── match osm_ref/spatial ───► ATTACH dates to OSM
FINN (points)   ─── match osm_ref/spatial ───► ATTACH dates to OSM
MANUAL (polys)  ─── match osm_ref/spatial ───► ATTACH dates to OSM
                                               │
                                               ▼
                              ┌────────────────┴────────────────┐
                              │                                 │
                    MATCHED → buildings_merged.geojson    UNMATCHED → buildings_unmatched.geojson
                    (OSM geometry + best dates)            (historical buildings, no OSM match)
```

### Key Principles

1. **OSM geometry is authoritative** - All matched buildings use OSM polygon geometry
2. **Dates attach to buildings** - Multiple sources can contribute dates to one building
3. **Priority resolves conflicts** - When sources disagree, use date_priority order
4. **Unmatched = potentially demolished** - Historical buildings not in OSM go to separate file

### Fallback Rule

Buildings without any date information are assumed to be modern:
- **Fallback year: 1960**
- Buildings with no `sd` field are shown only when `year >= 1960`
- This prevents undated buildings from appearing in historical views

### Date Inheritance (Multi-Layer Fallback)

Buildings without dates inherit using a three-tier fallback strategy:

| Priority | Method | Radius | Description |
|----------|--------|--------|-------------|
| 1 | **Median** | 2km | Median of all donors within radius (most robust) |
| 2 | **Nearest** | unlimited | Nearest donor at any distance |
| 3 | **1960** | - | Ultimate fallback (should be rare) |

**Parameters:**
- **Median radius:** 2000m (2km)
- **Exclude sources:** SEFRAK (heritage buildings are unusually old outliers)
- **Donor requirements:** Must have `ev: 'h'` or `ev: 'm'` and a valid `sd` date
- **Result evidence:** Inherited dates are marked `ev: 'l'` (low evidence)

**Additional fields for inherited dates:**
```
sd_inherited  : bool       # true = date inherited from neighbor
sd_method     : string     # 'median' | 'nearest' | 'fallback'
sd_donors     : int        # number of donors used (for median method)
sd_dist       : float      # distance in meters to donor (for nearest method)
```

**Rationale:** Buildings in dense areas get the median of nearby dates (more robust than single-point estimate). Isolated buildings fall back to nearest donor. The 1960 fallback is only used when no donors exist at all.

### MANUAL Exception

Researcher-verified MANUAL buildings without OSM match are kept in the main layer with their own geometry (not sent to unmatched file).

## Date Types

Each temporal bound can be one of:

1. **x** (exact) - Known from official records (SEFRAK, Matrikkelen, OSM tag)
2. **n** (not-later-than) - Building detected in historical source → existed by that date
3. **u** (unknown) - No reliable date evidence → show building at all times

**IMPORTANT**: ML non-detection is NOT used as evidence. The ML only detected ~260 of thousands
of buildings that existed in 1880. Non-detection just means "unknown", not "newer".

## Schema (Compact for Vector Tiles)

```
Properties:
  bid       : string    # Building ID (OSM ID or synthetic)

  # Start date (when built)
  sd        : int       # start_date - Best estimate year
  sd_t      : string    # start_date_type: 'x'=exact, 'n'=nlt, 'e'=net, 's'=estimated
  sd_c      : float     # start_date_confidence: 0.0-1.0 (omit if exact)
  sd_s      : string    # start_date_source: 'sef'|'osm'|'ml80'|'mat'|'aer'

  # End date (when demolished, null if still exists)
  ed        : int|null  # end_date - Year demolished
  ed_t      : string    # end_date_type
  ed_c      : float     # end_date_confidence
  ed_s      : string    # end_date_source: 'sef'|'osm'|'ml80'|'mat'|'aer'|'repl'

  # Demolition and replacement tracking
  demolished : bool|null    # true = known to be demolished (from SEFRAK status=0)
  repl_by    : string|null  # ID of the building that replaced this one
  repl_of    : string|null  # ID of the building this one replaced

  # Building metadata (from OSM)
  name      : string
  btype     : string    # building type

  # Building lineage (for tracking modifications/replacements)
  pred      : string|null   # predecessor bid (previous building at this location)
  pred_rel  : string|null   # relationship: 'mod' (modified) | 'rep' (replaced)
```

### Building Lineage

When a building changes significantly, we create a new record. The `pred` and `pred_rel` fields track the relationship:

| pred_rel | Meaning | Example |
|----------|---------|---------|
| `mod` | **Modified** - Same building, changed geometry | Building extended, wing added |
| `rep` | **Replaced** - Different building, predecessor demolished | Old house torn down, apartment built |
| `null` | No predecessor or unknown | Original building, or no historical data |

**Visualization hint**:
- Modified: "Built 1880 (extended 1920)" - continuous history
- Replaced: "Built 1920" - new building, previous one is separate history

### Building Replacement Detection

The replacement detection system automatically identifies when demolished buildings have been replaced by new construction at the same location.

#### Detection Logic

**Spatial Matching**: A demolished building and a newer building are considered a replacement pair if:
1. The demolished building's centroid falls within the newer building's polygon
2. The demolished building has a known end date (`ed`)
3. The newer building has a start date (`sd`) later than the demolished building's end date

**Date Inheritance**: When a replacement is detected:
- The old building's `ed` (end date) is set to the new building's `sd` (start date)
- The `ed_s` (end date source) is set to `'repl'` to indicate the date was inherited
- Evidence level is set to `'m'` (medium) for inferred demolition dates

#### Replacement Fields

| Field | Type | Direction | Description |
|-------|------|-----------|-------------|
| `demolished` | bool | Old building | Set to `true` if from SEFRAK with status=0 |
| `repl_by` | string | Old building | ID of the building that replaced this one |
| `repl_of` | string | New building | ID of the building this one replaced |

#### Example: Replacement Pair

```json
// Demolished building (SEFRAK heritage building)
{
  "bid": "sef_12345",
  "sd": 1850, "sd_t": "x", "sd_s": "sef",
  "ed": 1965, "ed_t": "x", "ed_s": "repl",
  "demolished": true,
  "repl_by": "osm_way_789012",
  "ev": "m"
}

// Replacement building (modern OSM building)
{
  "bid": "osm_way_789012",
  "sd": 1965, "sd_t": "x", "sd_s": "mat",
  "ed": null,
  "repl_of": "sef_12345"
}
```

#### End Date Source Values

The `ed_s` field indicates where the end date came from:

| Value | Description | Evidence Level |
|-------|-------------|----------------|
| `sef` | SEFRAK registry (status=0 = demolished) | High |
| `osm` | OSM end_date tag | Medium |
| `mat` | Matrikkelen (official registry) | High |
| `repl` | Inherited from replacement building's start date | Medium |
| `derived` | Inferred from other evidence | Low |

When `ed_s = 'repl'`, the demolition date is not directly known but inferred from when the replacement was built.

## Source Priority & Conflict Resolution

When multiple sources provide dates, resolve using:

### Date Priority Order for Construction Year (`sd`)

Sources that provide exact construction years are prioritized by reliability:

| Priority | Source | Resolution | Notes |
|----------|--------|------------|-------|
| 0 | **MANUAL** | Exact year | Researcher verified, citations |
| 1 | **FINN** | Exact year | Property listings, generally reliable |
| 2 | **SEFRAK** | 10-year ranges | Midpoint used (e.g., 1840-1850 → 1845) |
| 3 | **OSM start_date** | Exact year | Community-sourced, variable quality |
| 10+ | **ML detection** | NLT bound | Existence evidence only |

**Conflict Resolution Rule:** When multiple sources have `sd` for the same building, use the value from the source with the lowest priority number (highest priority).

### Legacy Priority Order (for reference):
1. **Matrikkelen** - Official building registry (exact dates)
2. **SEFRAK** - Historical building registry (exact/period dates)
3. **OSM start_date** - Community-sourced (exact dates)
4. **ML detection (older map)** - Establishes upper bound (nlt)
5. **ML non-detection (older map)** - Establishes lower bound (net)
6. **Assumed/estimated** - Default fallback

### Conflict Resolution Rules:

```python
def resolve_start_date(sources):
    """
    sources: list of (year, type, confidence, source_name)
    Returns: (year, type, confidence, source)
    """

    # 1. Prefer exact dates from official sources
    exact = [s for s in sources if s.type == 'exact']
    if exact:
        # Use highest priority source
        return max(exact, key=lambda s: SOURCE_PRIORITY[s.source])

    # 2. Use NLT dates if available (building detected in old map)
    nlt = [s for s in sources if s.type == 'nlt']
    if nlt:
        # Use oldest NLT date (earliest we know it existed)
        oldest_nlt = min(nlt, key=lambda s: s.year)

        # Check for NET constraints (building not in even older map)
        net = [s for s in sources if s.type == 'net']
        if net:
            newest_net = max(net, key=lambda s: s.year)
            if newest_net.year < oldest_nlt.year:
                # We can narrow: between NET and NLT
                return estimate_between(newest_net.year, oldest_nlt.year)

        return oldest_nlt

    # 3. Use NET dates if that's all we have
    net = [s for s in sources if s.type == 'net']
    if net:
        newest_net = max(net, key=lambda s: s.year)
        return (newest_net.year + 10, 'est', 0.5, 'derived')

    # 4. Default estimate
    return (1950, 'est', 0.3, 'default')
```

## Storage Format

### Raw Evidence Table (for processing)
Each piece of evidence stored separately:

```
building_evidence:
  building_id   : string (OSM ID)
  source        : string ('sefrak', 'osm', 'ml_1880', 'matrikkelen')
  date_type     : string ('start', 'end')
  bound_type    : string ('exact', 'nlt', 'net', 'est')
  year          : int
  confidence    : float
  geometry      : polygon (only for non-OSM sources)
```

### Consolidated Output (for visualization)
One record per building with resolved dates:

```
buildings_consolidated:
  bid           : string
  geometry      : polygon
  sd, sd_t, sd_c, sd_s  : resolved start date
  ed, ed_t, ed_c, ed_s  : resolved end date
  name, btype   : metadata
```

## File Formats

1. **Raw evidence**: `evidence/*.geojson` - One file per source
2. **Consolidated**: `buildings.pmtiles` - Single vector tile set
3. **Metadata**: `sources.json` - Source descriptions and priorities

## Example Records

### Building with exact SEFRAK date:
```json
{
  "bid": "osm_123456",
  "sd": 1820, "sd_t": "x", "sd_s": "sef",
  "ed": null,
  "name": "Stiftsgården",
  "btype": "historic"
}
```

### Building with ML-detected bound:
```json
{
  "bid": "osm_789012",
  "sd": 1880, "sd_t": "n", "sd_c": 0.8, "sd_s": "ml80",
  "ed": null,
  "btype": "residential"
}
```

### Building with narrowed range (detected in 1880, not in 1840):
```json
{
  "bid": "osm_345678",
  "sd": 1860, "sd_t": "s", "sd_c": 0.6, "sd_s": "derived",
  "sd_min": 1840, "sd_max": 1880,
  "ed": null
}
```

### Demolished building (detected in 1880, not in current OSM):
```json
{
  "bid": "ml_001",
  "sd": 1880, "sd_t": "n", "sd_c": 0.7, "sd_s": "ml80",
  "ed": 1950, "ed_t": "s", "ed_c": 0.4, "ed_s": "derived",
  "btype": "demolished"
}
```

### Modified building (extended in 1920):
```json
// Original building (1880-1920, small footprint)
{
  "bid": "osm_111_v1",
  "sd": 1880, "sd_t": "x", "sd_s": "sef",
  "ed": 1920, "ed_t": "x", "ed_s": "manual",
  "pred": null
}

// Same building after extension (1920-present, larger footprint)
{
  "bid": "osm_111",
  "sd": 1920, "sd_t": "x", "sd_s": "manual",
  "ed": null,
  "pred": "osm_111_v1",
  "pred_rel": "mod"
}
```

### Replaced building (demolished, new construction):
```json
// Old house (demolished 1960)
{
  "bid": "hist_old_house",
  "sd": 1850, "sd_t": "x", "sd_s": "sef",
  "ed": 1960, "ed_t": "x", "ed_s": "manual"
}

// New apartment building (different building)
{
  "bid": "osm_222",
  "sd": 1962, "sd_t": "x", "sd_s": "mat",
  "ed": null,
  "pred": "hist_old_house",
  "pred_rel": "rep"
}
```

## Visualization Rules

When displaying buildings for year Y:

1. **Show building if**: `sd <= Y AND (ed is null OR ed >= Y)`
2. **Color by certainty**:
   - Exact dates (sd_t='x'): Solid color
   - NLT dates (sd_t='n'): Slightly transparent
   - Estimated (sd_t='s'/'e'): More transparent, optional hatching
3. **Show uncertainty indicator** when `sd_c < 0.7`

## Geometry Selection

When merging buildings from multiple sources, geometry is selected in this order:

1. **OSM polygon** - Modern, accurate building footprints (preferred)
2. **MANUAL polygon** - Researcher-drawn geometries
3. **SEFRAK point** - Legacy point-based data
4. **FINN point** - Geocoded address points

**Rule:** Always prefer polygon geometry over point geometry. Use the most recent/accurate source.

## FINN Matching

FINN property listings are matched to existing buildings via:

1. **Primary: `osm_ref` field** - Explicit link to OSM building ID (e.g., `way/143759005`)
2. **Fallback: Spatial matching** - Centroid within 10m AND 50% polygon overlap

When matched, FINN provides the construction date (`sd`) which may override SEFRAK dates per the priority rules above.

## Generated Buildings

Schema for procedurally generated buildings from historical maps:

```
gen       : bool         # true = procedurally generated geometry (not detected/known)
gen_src   : string       # source map used for generation: "kv1880", "kv1904"
gen_zone  : string       # zone ID for grouping (e.g., "zone_001")
gen_conf  : float        # generation confidence based on zone detection quality
```

**Usage**: When historical maps show "buildings exist here" but don't provide accurate footprints, we procedurally generate plausible building polygons using era-appropriate constraints (6-12m wide for 1800s wooden buildings).

**Visualization**: Generated buildings should be styled differently (hatching, transparency) to indicate estimated geometry.

## Building Clusters (Future)

Schema placeholders for grouping adjacent buildings built together:

```
cluster_id  : string|null   # Group ID for adjacent buildings (e.g., "cluster_001")
cluster_sd  : int|null      # Shared/averaged construction date for the cluster
```

**Detection Criteria (not yet implemented):**
- Buildings within 20m of each other
- Construction dates within 5 years
- Applies to all sources

Use cases: Row houses, farm complexes, planned developments.

## Future Extensions

When adding new historical sources (e.g., 1920 aerial photos):

1. Run ML detection on 1920 photos
2. Add evidence records to `evidence/ml_1920.geojson`
3. Re-run consolidation to update bounds:
   - Buildings in 1920 but not 1880: narrow to 1880-1920
   - Buildings in 1880 and 1920: confirm existence span
   - Buildings not in 1920: potential demolition evidence

---

# Road Temporal Data Schema

## Key Difference from Buildings

Buildings have authoritative sources (SEFRAK, Matrikkelen) providing exact construction dates.
**Roads have no such registry** - all temporal data comes from ML detection across historical maps.

This means:
- Road dates are **bounds**, not exact values
- All road evidence is type `n` (not-later-than) or `e` (not-earlier-than), never `x` (exact)
- Confidence levels are always ML-based

## Data Sources for Roads

| Source | What it tells us | Certainty |
|--------|-----------------|-----------|
| ML 1880 detection | Road existed in 1880 | ML confidence |
| ML 1880 non-detection | Road probably post-1880 | Lower confidence |
| ML 1904 detection | Road existed in 1904 | ML confidence |
| ML 1947 detection | Road existed in 1947 | ML confidence |
| OSM presence | Road exists today | High (current) |
| OSM absence | Road no longer exists | High (current) |

## Date Types for Roads

1. **n** (not-later-than) - Road detected in historical map → existed by that date
2. **e** (not-earlier-than) - Road absent in older map → didn't exist yet
3. **s** (estimated) - Midpoint between bounds when we have both

**Note:** Unlike buildings, roads never have type `x` (exact) since no registry provides exact dates.

## Schema (Compact for Vector Tiles)

```
Properties:
  rid       : string    # Road ID (OSM way ID or ML-generated)

  # Start date (when road first appeared)
  sd        : int       # start_date - Best estimate year
  sd_t      : string    # start_date_type: 'n'=nlt, 'e'=net, 's'=estimated
  sd_c      : float     # start_date_confidence: 0.0-1.0
  sd_s      : string    # start_date_source: 'ml80'|'ml04'|'ml47'|'derived'

  # End date (when road was removed, null if still exists)
  ed        : int|null  # end_date - Year removed
  ed_t      : string    # end_date_type
  ed_c      : float     # end_date_confidence
  ed_s      : string    # end_date_source

  # Road metadata
  rt        : string    # road_type from OSM (primary, secondary, etc.)
  nm        : string    # road name (if matched to OSM)
  mlc       : float     # ML confidence for detection
  ml_src    : string    # Which map: kv1880, kv1904, air1947
```

## Temporal Inference Rules

### Single Map Detection

| Scenario | Inference |
|----------|-----------|
| Detected in 1880 map | `sd <= 1880`, `sd_t = 'n'` |
| Detected in 1904 map | `sd <= 1904`, `sd_t = 'n'` |
| Detected in 1947 map | `sd <= 1947`, `sd_t = 'n'` |

### Multi-Map Detection

| Scenario | Inference |
|----------|-----------|
| In 1880 AND 1904 | `sd <= 1880`, higher confidence |
| In 1904 but NOT 1880 | `sd ∈ (1880, 1904]`, `sd_t = 's'`, `sd = 1892` (midpoint) |
| In 1947 but NOT 1904 | `sd ∈ (1904, 1947]`, `sd_t = 's'`, `sd = 1925` (midpoint) |

### Demolition/Removal Detection

| Scenario | Inference |
|----------|-----------|
| In 1880/1904 but NOT OSM | `ed <= 2024`, road removed |
| In 1904 but NOT 1947 | `ed ∈ (1904, 1947]`, `ed_t = 's'` |

## Evidence Levels for Roads

| Level | Code | Criteria |
|-------|------|----------|
| High | `h` | Detected in 2+ historical maps with avg confidence > 0.8 |
| Medium | `m` | Detected in 1 map OR confidence 0.5-0.8 |
| Low | `l` | OSM only (no historical detection) |

## Example Records

### Road detected in 1880 map:
```json
{
  "rid": "ml-road-001",
  "sd": 1880, "sd_t": "n", "sd_c": 0.85, "sd_s": "ml80",
  "ed": null,
  "ev": "m",
  "ml_src": "kv1880",
  "mlc": 0.85,
  "rt": "secondary",
  "nm": null
}
```

### Road detected in 1904 but not 1880:
```json
{
  "rid": "ml-road-002",
  "sd": 1892, "sd_t": "s", "sd_c": 0.7, "sd_s": "derived",
  "ed": null,
  "ev": "m",
  "ml_src": "kv1904",
  "mlc": 0.78,
  "rt": "tertiary",
  "nm": null
}
```

### Road matched to OSM with name:
```json
{
  "rid": "osm-way-123456",
  "sd": 1880, "sd_t": "n", "sd_c": 0.9, "sd_s": "ml80",
  "ed": null,
  "ev": "h",
  "ml_src": "kv1880",
  "mlc": 0.92,
  "rt": "primary",
  "nm": "Kongens gate"
}
```

### Historical road no longer exists:
```json
{
  "rid": "ml-road-003",
  "sd": 1880, "sd_t": "n", "sd_c": 0.75, "sd_s": "ml80",
  "ed": 1970, "ed_t": "s", "ed_c": 0.5, "ed_s": "derived",
  "ev": "m",
  "ml_src": "kv1880",
  "mlc": 0.75,
  "rt": "residential",
  "nm": null
}
```

## Visualization Rules for Roads

When displaying roads for year Y:

1. **Show road if**: `sd <= Y AND (ed is null OR ed >= Y)`
2. **Color by era**:
   - Pre-1880 (sd_t='n', sd=1880): Dark slate
   - 1880-1904 (sd_t='s'): Slate gray
   - 1904-1947 (sd_t='s'): Gray
   - Post-1947/Modern: Light gray
3. **Line style by certainty**:
   - High confidence (ev='h'): Solid line
   - Medium confidence (ev='m'): Slightly transparent
   - Low confidence (ev='l'): Dashed line
4. **Show uncertainty indicator** when `sd_c < 0.6`

## OSM Matching for Roads

Roads detected by ML are matched to OSM ways to inherit names and types:

1. Buffer ML road centerline by 5m
2. Find OSM ways that intersect buffer
3. Score by:
   - Length overlap (0-1)
   - Angle similarity (0-1)
   - Distance from centerline
4. Match if combined score > 0.6
5. Inherit `nm` (name) and `rt` (road type) from best match

Unmatched ML roads get `nm: null` and `rt: "unknown"`.

---

## Road Properties

Road segments use segment-based tracking (split at intersections).

### Core Fields

| Field | Type | Description |
|-------|------|-------------|
| `src` | string | Source: osm, ml, man |
| `sd` | int | Start date (construction year) |
| `ed` | int/null | End date (removal/replacement year) |
| `ev` | string | Evidence: h (high), m (medium), l (low) |
| `change` | string | Change type relative to modern OSM |
| `width` | float | Estimated width in meters |
| `name` | string | Road name (from OSM) |

### Change Types

| Value | Description |
|-------|-------------|
| `same` | Unchanged geometry |
| `widened` | Same centerline, increased width |
| `rerouted` | Partial geometry change |
| `replaced` | Completely new alignment |
| `removed` | No longer exists in OSM |
| `new` | Didn't exist historically |

### Date Inference Fields

| Field | Type | Description |
|-------|------|-------------|
| `sd_method` | string | How date was inferred: ml, building, bounded, fallback |
| `sd_buildings` | int | Number of nearby buildings used for inference |
| `sd_offset` | int | Years subtracted from building date (typically -2) |

### Date Inference Logic

Roads are dated using this fallback chain:
1. **ML detection**: If road visible in dated historical map
2. **Building-based**: Earliest nearby building date minus 2 years
3. **Bounded**: Map era (1880, 1904, 1947) for ML roads
4. **Fallback**: 1960

The building-based method uses the insight that local roads are typically built 1-2 years before the houses they serve.
