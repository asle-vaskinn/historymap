# Historical Map Data Pipeline - Comprehensive Design

## Overview

A multi-stage pipeline that ingests, aligns, extracts, and merges historical geographic data from multiple sources into a unified temporal dataset.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DATA SOURCES (Stage 0)                               │
├─────────────┬─────────────┬─────────────┬─────────────┬─────────────────────┤
│ Kartverket  │ SEFRAK      │ OSM         │ Historical  │ Aerial Photos       │
│ WMS/Archive │ Registry    │ Current     │ Maps (new)  │ (Norge i bilder)    │
└──────┬──────┴──────┬──────┴──────┬──────┴──────┬──────┴──────────┬──────────┘
       │             │             │             │                 │
       ▼             ▼             ▼             ▼                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      INGESTION & NORMALIZATION (Stage 1)                     │
│  • Download/fetch raw data                                                   │
│  • Convert to common format (GeoJSON)                                        │
│  • Normalize coordinate systems (EPSG:4326)                                  │
│  • Extract metadata (dates, sources, confidence)                             │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      GEOREFERENCING (Stage 2)                                │
│  • Already georeferenced → validate & pass through                           │
│  • New maps → alignment pipeline (GCPs, transform, verify)                   │
│  • Quality scoring (RMS error, coverage)                                     │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      FEATURE EXTRACTION (Stage 3)                            │
│  • ML building detection (U-Net)                                             │
│  • Vectorization (raster → polygon)                                          │
│  • Feature classification (building, road, water)                            │
│  • Confidence scoring                                                        │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      TEMPORAL MATCHING (Stage 4)                             │
│  • Cross-reference features across time periods                              │
│  • Match buildings: SEFRAK ↔ OSM ↔ ML-extracted                             │
│  • Establish temporal chains (same building across maps)                     │
│  • Detect: construction, demolition, modification                            │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      MERGE & RECONCILIATION (Stage 5)                        │
│  • Resolve conflicts (which source wins?)                                    │
│  • Combine attributes from multiple sources                                  │
│  • Calculate confidence scores                                               │
│  • Generate unified features with temporal attributes                        │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      OUTPUT GENERATION (Stage 6)                             │
│  • Generate PMTiles for web display                                          │
│  • Export GeoJSON for analysis                                               │
│  • Create source manifests                                                   │
│  • Quality reports                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Stage 0: Data Sources

### Primary Sources

| Source | Type | Temporal Range | Data Type | Update Freq |
|--------|------|----------------|-----------|-------------|
| **Kartverket WMS** | Georeferenced maps | 1700-1960 | Raster | Static |
| **Kartverket Archive** | Raw historical maps | 1700-1970 | Raster | Static |
| **SEFRAK** | Building registry | pre-1900 | Point/Polygon | Yearly |
| **OSM** | Current buildings | 2007-now | Polygon | Daily |
| **Norge i bilder** | Aerial photos | 1935-now | Ortho raster | Yearly |
| **Trondheim Byarkiv** | City maps | 1868-1979 | Raster | Static |
| **Matrikkelen** | Property data | 1980-now | Point | Daily |

### Source Priority (for conflict resolution)

1. **SEFRAK** - Official heritage registry, authoritative for pre-1900 dates
2. **FKB-Bygning** - Kartverket official cadastral geometry (no dates)
3. **Trondheim Kommune** - Municipal building permits with dates
4. **Matrikkelen** - Official property register (linked via bygningsnummer)
5. **Kartverket WMS** - Historical maps (existence evidence)
6. **OSM** - Community data, valuable for user-added dates
7. **ML Extracted** - Derived data, lower confidence

**Key insight**: FKB-Bygning provides authoritative geometry, while SEFRAK/Kommune/OSM provide temporal data. The merge process combines geometry from FKB with dates from other sources.

---

## Stage 1: Ingestion & Normalization

### 1.1 Ingestion Scripts

```
scripts/ingest/
├── ingest_kartverket_wms.py    # Fetch from WMS, cache locally
├── ingest_sefrak.py            # Download SEFRAK GeoJSON
├── ingest_osm.py               # Overpass API query
├── ingest_byarkiv.py           # Process local Flickr downloads
├── ingest_aerial.py            # Norge i bilder integration
└── ingest_matrikkelen.py       # Property data (if accessible)
```

### 1.2 Normalization Rules

```python
NORMALIZED_SCHEMA = {
    "id": "string",              # Unique identifier
    "geometry": "Polygon/Point", # GeoJSON geometry
    "properties": {
        # Temporal
        "start_date": "int",     # Year first appeared (e.g., 1850)
        "end_date": "int|null",  # Year demolished (null = exists)
        "date_confidence": "float", # 0-1 confidence in dates

        # Source
        "source": "string",      # sefrak|osm|kartverket|ml_extracted
        "source_id": "string",   # Original ID in source
        "source_date": "string", # When source data was captured

        # Classification
        "feature_type": "string", # building|road|water|landuse
        "subtype": "string",     # church|residential|industrial|...

        # Matching
        "match_ids": ["string"], # IDs of same feature in other sources
        "match_confidence": "float",

        # Quality
        "geometry_source": "string", # Where geometry came from
        "attribute_sources": {},     # Which source for each attribute
    }
}
```

### 1.3 Coordinate Normalization

All data normalized to **EPSG:4326** (WGS84) for storage.
Transform on-the-fly for:
- UTM zones (EPSG:25832, 25833) for precise calculations
- Web Mercator (EPSG:3857) for display

---

## Stage 2: Georeferencing

### 2.1 Decision Tree

```
Input Map
    │
    ├─→ Has CRS/GeoTIFF? ─→ YES ─→ Validate bounds ─→ Pass through
    │                                    │
    │                                    └─→ Invalid ─→ Re-georeference
    │
    └─→ NO ─→ Check Kartverket WMS
                    │
                    ├─→ Available ─→ Use WMS version
                    │
                    └─→ Not available ─→ Manual georeferencing
                                              │
                                              ▼
                                    ┌─────────────────┐
                                    │ GCP Collection  │
                                    │ (min 4 points)  │
                                    └────────┬────────┘
                                             │
                                    ┌────────▼────────┐
                                    │ Auto-match with │
                                    │ known buildings │
                                    └────────┬────────┘
                                             │
                                    ┌────────▼────────┐
                                    │ Human verify    │
                                    │ (confidence UI) │
                                    └────────┬────────┘
                                             │
                                    ┌────────▼────────┐
                                    │ Transform &     │
                                    │ Quality check   │
                                    └─────────────────┘
```

### 2.2 Quality Metrics

| Metric | Good | Acceptable | Poor |
|--------|------|------------|------|
| RMS Error | <5m | 5-20m | >20m |
| GCP Count | >10 | 6-10 | 4-5 |
| Coverage | All corners + center | Corners | Partial |

---

## Stage 3: Feature Extraction

### 3.1 ML Pipeline

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Georef Map  │ ──▶ │ Tile (512px)│ ──▶ │ U-Net       │ ──▶ │ Mask        │
│ (GeoTIFF)   │     │ with overlap│     │ Inference   │     │ (per class) │
└─────────────┘     └─────────────┘     └─────────────┘     └──────┬──────┘
                                                                   │
┌─────────────┐     ┌─────────────┐     ┌─────────────┐            │
│ GeoJSON     │ ◀── │ Simplify &  │ ◀── │ Vectorize   │ ◀──────────┘
│ Features    │     │ Filter      │     │ (contours)  │
└─────────────┘     └─────────────┘     └─────────────┘
```

### 3.2 Feature Classes

| Class | Color (mask) | Min Area | Simplify |
|-------|--------------|----------|----------|
| Building | Red (1) | 20m² | 1m tolerance |
| Road | Gray (2) | 10m length | 2m tolerance |
| Water | Blue (3) | 50m² | 5m tolerance |
| Forest | Green (4) | 100m² | 10m tolerance |

### 3.3 Confidence Scoring

```python
confidence = (
    model_probability * 0.4 +      # ML confidence
    area_reasonableness * 0.2 +    # Is size reasonable?
    shape_regularity * 0.2 +       # Is shape building-like?
    context_consistency * 0.2      # Does it match surroundings?
)
```

---

## Stage 4: Temporal Matching

### 4.1 Matching Strategy

```
For each extracted feature F from map year Y:

    1. SPATIAL MATCH
       Find candidates within 20m buffer in:
       - SEFRAK (if year < 1900)
       - OSM (if building still exists)
       - Previous/next temporal layer

    2. SHAPE MATCH
       For each candidate C:
       - IoU (Intersection over Union) > 0.5
       - Hausdorff distance < 10m
       - Area ratio 0.5 < F/C < 2.0

    3. TEMPORAL CONSISTENCY
       - If matched to older source: F.start_date = older.start_date
       - If no match in newer source: F.end_date = estimate from next map

    4. CONFIDENCE CALCULATION
       match_confidence = spatial * 0.3 + shape * 0.4 + temporal * 0.3
```

### 4.2 Temporal Chain Example

```
Building B-1234:
├── 1868 map: detected at (10.395, 63.428), conf=0.7
├── 1909 map: detected at (10.395, 63.428), conf=0.85
├── SEFRAK: registered, built 1856, id=1662-5-23
├── 1936 map: detected at (10.395, 63.428), conf=0.9
├── 1979 map: NOT detected → demolished between 1936-1979
└── OSM: NOT present → confirmed demolished

Result:
{
    "start_date": 1856,      # From SEFRAK
    "end_date": 1960,        # Estimated midpoint
    "date_confidence": 0.8,
    "sources": ["sefrak", "map_1868", "map_1909", "map_1936"]
}
```

---

## Stage 5: Merge & Reconciliation

### 5.1 Conflict Resolution Rules

| Conflict Type | Resolution |
|---------------|------------|
| Geometry differs | Use highest-confidence source, store alternatives |
| Date differs | SEFRAK > Matrikkelen > Map inference |
| Classification differs | Official registry > OSM > ML |
| Feature exists in one source only | Include with lower confidence |

### 5.2 Attribute Inheritance

```python
def merge_feature(sources: List[Feature]) -> Feature:
    merged = Feature()

    # Geometry: highest confidence
    merged.geometry = max(sources, key=lambda s: s.geometry_confidence).geometry

    # Start date: earliest reliable source
    for source in ['sefrak', 'matrikkelen', 'map_oldest']:
        if source in sources and sources[source].start_date:
            merged.start_date = sources[source].start_date
            break

    # End date: latest observation where missing
    if all(s.end_date is None for s in sources if s.source != 'osm'):
        if 'osm' not in sources:
            merged.end_date = estimate_from_maps(sources)

    # Store provenance
    merged.attribute_sources = {
        'geometry': best_geometry_source,
        'start_date': date_source,
        'end_date': end_date_source,
    }

    return merged
```

### 5.3 Quality Tiers

| Tier | Criteria | Example |
|------|----------|---------|
| **Gold** | SEFRAK + OSM + multiple maps | Historic church, well documented |
| **Silver** | 2+ sources agree | Building in SEFRAK and 2 maps |
| **Bronze** | Single authoritative source | SEFRAK only, no map confirmation |
| **Inferred** | ML-extracted only | Building seen on map, no registry |

---

## Stage 6: Output Generation

### 6.1 Output Formats

```
data/output/
├── pmtiles/
│   ├── trondheim_historical.pmtiles  # All features, optimized for web
│   └── trondheim_by_era/
│       ├── 1850-1900.pmtiles
│       ├── 1900-1950.pmtiles
│       └── 1950-2000.pmtiles
├── geojson/
│   ├── buildings_all.geojson
│   ├── buildings_demolished.geojson
│   └── by_source/
│       ├── sefrak.geojson
│       ├── osm.geojson
│       └── ml_extracted.geojson
├── reports/
│   ├── quality_report.json
│   ├── coverage_by_year.json
│   └── source_statistics.json
└── manifest.json
```

### 6.2 PMTiles Layer Structure

```
Layers:
├── buildings
│   ├── properties: start_date, end_date, source, confidence, subtype
│   └── filter: ["all", ["<=", "start_date", $year], ["any", ["!", "end_date"], [">=", "end_date", $year]]]
├── buildings_demolished
│   └── filter: ["has", "end_date"]
├── roads
├── water
└── historical_overlay (raster tiles from maps)
```

---

## Pipeline Execution

### Daily/Incremental

```bash
# Update OSM data
python scripts/pipeline.py --stage ingest --source osm

# Re-run matching for affected areas
python scripts/pipeline.py --stage match --incremental

# Regenerate tiles
python scripts/pipeline.py --stage output --format pmtiles
```

### Full Rebuild

```bash
# Complete pipeline
python scripts/pipeline.py --full \
    --sources kartverket,sefrak,osm,byarkiv \
    --area trondheim \
    --output data/output/
```

### New Map Integration

```bash
# Add new historical map
python scripts/pipeline.py --add-map \
    --input new_map.jpg \
    --year 1920 \
    --source "private_collection" \
    --georef-mode interactive
```

---

## File Structure

```
historymap/
├── scripts/
│   ├── pipeline.py              # Main orchestrator
│   ├── ingest/                  # Stage 1
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── kartverket.py
│   │   ├── sefrak.py
│   │   ├── osm.py
│   │   └── byarkiv.py
│   ├── georef/                  # Stage 2
│   │   ├── __init__.py
│   │   ├── validator.py
│   │   ├── gcp_matcher.py
│   │   └── transformer.py
│   ├── extract/                 # Stage 3
│   │   ├── __init__.py
│   │   ├── ml_inference.py
│   │   └── vectorizer.py
│   ├── match/                   # Stage 4
│   │   ├── __init__.py
│   │   ├── spatial.py
│   │   ├── temporal.py
│   │   └── chains.py
│   ├── merge/                   # Stage 5
│   │   ├── __init__.py
│   │   ├── resolver.py
│   │   └── confidence.py
│   └── export/                  # Stage 6
│       ├── __init__.py
│       ├── pmtiles.py
│       ├── geojson.py
│       └── reports.py
├── data/
│   ├── sources/                 # Raw ingested data
│   │   ├── kartverket/
│   │   ├── sefrak/
│   │   ├── osm/
│   │   └── byarkiv/
│   ├── georeferenced/           # Stage 2 output
│   ├── extracted/               # Stage 3 output
│   ├── matched/                 # Stage 4 output
│   ├── merged/                  # Stage 5 output
│   └── output/                  # Stage 6 output (final)
├── models/                      # ML models
└── docs/
    └── spec/
        └── PIPELINE_DESIGN.md   # This document
```

---

## Implementation Status

### Completed Components

| Component | Path | Status |
|-----------|------|--------|
| **Ingest Base** | `scripts/ingest/base.py` | ✅ BaseIngestor class |
| **OSM Ingest** | `scripts/ingest/osm.py` | ✅ Overpass API download |
| **FKB Ingest** | `scripts/ingest/fkb_bygning.py` | ✅ WFS download |
| **Normalize Base** | `scripts/normalize/base.py` | ✅ Schema + BaseNormalizer |
| **SEFRAK Normalize** | `scripts/normalize/normalize_sefrak.py` | ✅ UTM→WGS84, building types |
| **OSM Normalize** | `scripts/normalize/normalize_osm.py` | ✅ Date extraction |
| **FKB Normalize** | `scripts/normalize/normalize_fkb.py` | ✅ SOSI type mapping |
| **ML Normalize** | `scripts/normalize/normalize_ml.py` | ✅ Confidence mapping |
| **Merge Engine** | `scripts/merge/merge_sources.py` | ✅ Spatial index, replacement detection |
| **Merge Config** | `data/merged/merge_config.json` | ✅ JSON Schema validated |
| **GeoJSON Export** | `scripts/export/export_geojson.py` | ✅ |
| **PMTiles Export** | `scripts/export/export_pmtiles.py` | ✅ |
| **Quality Reports** | `scripts/merge/merge_sources.py` | ✅ Integrated |

### Data Status

| Source | Ingested | Normalized | Count | Notes |
|--------|----------|------------|-------|-------|
| SEFRAK | ✅ | ✅ | 1,894 | Pre-1900 with dates |
| FKB-Bygning | 🔄 | 🔄 | ~20,000+ | Official geometry, no dates |
| OSM | ✅ | ✅ | ~15,000+ | Community data, some dates |
| ML Kartverket 1880 | ✅ | Partial | Variable | Existence evidence |
| Trondheim Kommune | ❌ | ❌ | Pending | Building permits |
| Matrikkelen | ❌ | ❌ | API pending | Links to FKB |
| Norge i bilder | ❌ | ❌ | Auth required | Aerial photos |

### Normalized Schema (Compact)

```python
# Property names are shortened for tile efficiency
{
    '_src': 'sefrak',      # Source identifier
    '_src_id': '1234',     # Source-specific ID
    '_ingested': '2024-01', # Ingestion date
    'sd': 1856,            # Start date (year built)
    'ed': 1960,            # End date (demolished, null=exists)
    'ev': 'h',             # Evidence: h=high, m=medium, l=low
    'bt': 'residential',   # Building type
    'nm': 'Gamle huset',   # Name
    '_raw': {...}          # Original properties preserved
}
```

### Merge Configuration

Located at `data/merged/merge_config.json` with JSON Schema validation.

Key settings:
- **Overlap threshold**: 0.5 (50% overlap = match)
- **Replacement detection**: Era-based rules
  - Pre-1900: Requires high evidence to hide
  - 1900-1950: Requires medium evidence
  - Post-1950: Any evidence sufficient
- **Source priorities**: SEFRAK (1) > OSM (100) > ML (10+)

---

## Next Steps

1. **Add Trondheim Kommune data** - Municipality has building permits/dates
2. **Test Kartverket WMS** - Check available georeferenced maps
3. **Improve ML model** - Fine-tune on more historical map styles
4. **Add pipeline orchestrator** - `pipeline.py` with stage management
5. **Add Norge i bilder** - Requires authentication handling
