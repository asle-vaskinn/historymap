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
  ed_s      : string    # end_date_source

  # Building metadata (from OSM)
  name      : string
  btype     : string    # building type
```

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
