# Data Pipeline Architecture

## Design Principles

1. **Source Isolation**: Each data source has its own pipeline, directory, and schema
2. **Explicit Merging**: Sources are never mixed accidentally - merging requires explicit configuration
3. **Provenance Tracking**: Every building and road record traces back to its original source
4. **Reproducibility**: Any output can be regenerated from raw inputs
5. **Feature Type Separation**: Buildings and roads are processed through parallel pipelines

## Directory Structure

```
data/
├── sources/                    # RAW SOURCE DATA (read-only after ingestion)
│   ├── sefrak/
│   │   ├── raw/               # Original downloaded data
│   │   ├── normalized/        # Schema-normalized GeoJSON
│   │   └── manifest.json      # Source metadata & version
│   │
│   ├── trondheim_kommune/
│   │   ├── raw/
│   │   ├── normalized/
│   │   └── manifest.json
│   │
│   ├── osm/
│   │   ├── raw/               # OSM extract (.pbf or .geojson)
│   │   ├── normalized/
│   │   └── manifest.json
│   │
│   ├── matrikkelen/
│   │   ├── raw/
│   │   ├── normalized/
│   │   └── manifest.json
│   │
│   └── ml_detected/
│       ├── kartverket_1880/
│       │   ├── raw/           # Model output (masks)
│       │   ├── buildings/     # Vectorized buildings
│       │   ├── roads/         # Vectorized roads
│       │   └── manifest.json
│       ├── kartverket_1904/
│       │   ├── raw/
│       │   ├── buildings/
│       │   ├── roads/
│       │   └── manifest.json
│       └── aerial_1947/
│           ├── raw/
│           ├── buildings/
│           ├── roads/
│           └── manifest.json
│
├── merged/                     # MERGED DATASETS (explicit combinations)
│   ├── merge_config.json      # Defines which sources to merge & rules
│   ├── buildings_merged.geojson
│   ├── roads_merged.geojson   # Merged roads (ML sources only)
│   └── merge_report.json      # Stats per source, conflicts resolved
│
└── export/                     # FRONTEND-READY OUTPUT
    ├── buildings.geojson      # Buildings for development
    ├── buildings.pmtiles      # Buildings for production
    ├── roads_temporal.geojson # Roads for development
    ├── roads_temporal.pmtiles # Roads for production
    └── export_config.json     # Which merged dataset, filters applied
```

## Pipeline Stages

```
┌─────────────────────────────────────────────────────────────────────┐
│                         STAGE 1: INGEST                             │
│   Each source has dedicated ingestion script                        │
│   Output: data/sources/{source}/raw/                                │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       STAGE 2: NORMALIZE                            │
│   Convert to common schema, validate, add source metadata           │
│   Output: data/sources/{source}/normalized/                         │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        STAGE 3: MERGE                               │
│   Combine sources according to merge_config.json                    │
│   Resolve conflicts, match buildings across sources                 │
│   Output: data/merged/                                              │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        STAGE 4: EXPORT                              │
│   Apply filters, optimize for frontend                              │
│   Output: data/export/                                              │
└─────────────────────────────────────────────────────────────────────┘
```

## Source Manifest Schema

Each source directory contains a `manifest.json`:

```json
{
  "source_id": "sefrak",
  "source_name": "SEFRAK Cultural Heritage Registry",
  "version": "2024-01-15",
  "ingested_at": "2024-01-20T10:30:00Z",
  "ingestion_script": "scripts/ingest/sefrak.py",
  "raw_files": ["sefrak_trondheim.csv"],
  "normalized_file": "buildings.geojson",
  "record_count": 2847,
  "schema_version": "1.0",
  "coverage": {
    "temporal": {"min_year": 1650, "max_year": 1900},
    "spatial": "Trondheim municipality"
  },
  "evidence_strength": "high",
  "notes": "Downloaded from Riksantikvaren open data portal"
}
```

## Normalized Building Schema

All building sources normalize to this schema before merging:

```json
{
  "type": "Feature",
  "properties": {
    "_src": "sefrak",              // REQUIRED: Source ID (never modified)
    "_src_id": "SEFRAK-12345",     // REQUIRED: ID within source
    "_ingested": "2024-01-20",     // REQUIRED: When ingested

    "sd": 1850,                    // Start date (year)
    "ed": null,                    // End date (demolished)
    "ev": "h",                     // Evidence strength
    "bt": "residential",           // Building type
    "nm": "Stiftsgården",          // Name (optional)

    "_raw": {}                     // Original properties preserved
  },
  "geometry": { ... }
}
```

## Normalized Road Schema

Roads from ML detection normalize to this schema:

```json
{
  "type": "Feature",
  "properties": {
    "_src": "ml_kv1880",           // REQUIRED: Source ID (always ml_*)
    "_src_id": "road-001",         // REQUIRED: ID within source
    "_ingested": "2024-01-20",     // REQUIRED: When ingested

    "sd": 1880,                    // Start date (earliest detection)
    "sd_t": "n",                   // Start date type: n=nlt, e=net, s=estimated
    "sd_c": 0.85,                  // Start date confidence (0-1)
    "ed": null,                    // End date (if removed)
    "ed_t": null,                  // End date type
    "ed_c": null,                  // End date confidence
    "ev": "m",                     // Evidence strength
    "rt": null,                    // Road type (populated during OSM matching)
    "nm": null,                    // Road name (populated during OSM matching)
    "mlc": 0.85,                   // ML confidence

    "_raw": {}                     // Original ML output preserved
  },
  "geometry": { ... }             // LineString geometry
}
```

**Key Differences from Buildings:**
- `_src` is always `ml_*` (no registry sources for roads)
- `sd_t` field tracks date type (buildings from registries have exact dates)
- Geometry is LineString, not Polygon
- `rt` and `nm` populated during OSM matching (post-merge)

## Merge Configuration

`data/merged/merge_config.json` controls how sources are combined:

```json
{
  "version": "1.0",
  "created": "2024-01-20",
  "description": "Production merge for Trondheim historical map",

  "sources": {
    "sefrak": {
      "enabled": true,
      "path": "../sources/sefrak/normalized/buildings.geojson",
      "priority": 1,
      "trust_dates": true
    },
    "trondheim_kommune": {
      "enabled": true,
      "path": "../sources/trondheim_kommune/normalized/buildings.geojson",
      "priority": 2,
      "trust_dates": true
    },
    "ml_kartverket_1880": {
      "enabled": true,
      "path": "../sources/ml_detected/kartverket_1880/normalized/buildings.geojson",
      "priority": 3,
      "trust_dates": false,
      "date_represents": "not_later_than"
    },
    "osm": {
      "enabled": true,
      "path": "../sources/osm/normalized/buildings.geojson",
      "priority": 10,
      "trust_dates": "if_explicit"
    }
  },

  "matching": {
    "method": "spatial_overlap",
    "overlap_threshold": 0.5,
    "centroid_max_distance_m": 10
  },

  "conflict_resolution": {
    "date_conflict": "prefer_higher_priority",
    "geometry_conflict": "prefer_higher_priority",
    "merge_evidence": true
  },

  "output": {
    "include_source_breakdown": true,
    "preserve_all_sources": true
  }
}
```

### Road Merge Configuration

Roads have a separate, simpler merge config since they only come from ML sources:

```json
{
  "version": "1.0",
  "feature_type": "road",
  "description": "Road merge from ML detections",

  "sources": {
    "ml_kartverket_1880": {
      "enabled": true,
      "path": "../sources/ml_detected/kartverket_1880/roads/roads.geojson",
      "map_year": 1880
    },
    "ml_kartverket_1904": {
      "enabled": true,
      "path": "../sources/ml_detected/kartverket_1904/roads/roads.geojson",
      "map_year": 1904
    },
    "ml_aerial_1947": {
      "enabled": true,
      "path": "../sources/ml_detected/aerial_1947/roads/roads.geojson",
      "map_year": 1947
    }
  },

  "matching": {
    "method": "centerline_buffer",
    "buffer_m": 5,
    "angle_tolerance_deg": 15,
    "min_overlap_ratio": 0.6
  },

  "temporal_inference": {
    "method": "presence_bounds",
    "rules": [
      {"detected_in": [1880], "sd": 1880, "sd_t": "n"},
      {"detected_in": [1904], "not_in": [1880], "sd": 1892, "sd_t": "s"},
      {"detected_in": [1947], "not_in": [1880, 1904], "sd": 1925, "sd_t": "s"},
      {"detected_in": [1880, 1904], "sd": 1880, "sd_t": "n", "confidence_boost": 0.2}
    ]
  },

  "osm_matching": {
    "enabled": true,
    "osm_roads_path": "../sources/osm/normalized/roads.geojson",
    "inherit_fields": ["nm", "rt"],
    "match_threshold": 0.6
  }
}
```

**Key Differences from Building Merge:**
- No registry sources (SEFRAK, Matrikkelen don't cover roads)
- Temporal inference from map presence/absence instead of source priority
- OSM matching is optional enrichment, not primary source
- Matching uses centerline buffer instead of polygon overlap

## Scripts Structure

```
scripts/
├── ingest/                     # Stage 1: Source-specific ingestion
│   ├── sefrak.py
│   ├── trondheim_kommune.py
│   ├── osm.py
│   ├── matrikkelen.py
│   └── ml_extract.py          # Runs ML model on historical maps
│
├── normalize/                  # Stage 2: Normalize to common schema
│   ├── normalize_sefrak.py
│   ├── normalize_tk.py
│   ├── normalize_osm.py
│   ├── normalize_matrikkelen.py
│   ├── normalize_ml_buildings.py
│   ├── normalize_ml_roads.py   # NEW: Normalize ML-detected roads
│   └── validate_schema.py     # Validates normalized output
│
├── merge/                      # Stage 3: Combine sources
│   ├── merge_buildings.py     # Merge building sources
│   ├── merge_roads.py         # NEW: Merge road sources with temporal inference
│   ├── spatial_matching.py    # Match buildings across sources
│   ├── centerline_matching.py # NEW: Match roads using centerline buffer
│   └── conflict_resolver.py   # Handle conflicting data
│
├── export/                     # Stage 4: Frontend-ready output
│   ├── export_geojson.py
│   ├── export_pmtiles.py
│   └── apply_filters.py
│
└── pipeline.py                 # Orchestrates full pipeline (buildings + roads)
```

**Road-specific scripts:**
- `normalize_ml_roads.py` - Converts ML road masks to LineString GeoJSON
- `merge_roads.py` - Merges roads from multiple maps, infers temporal bounds
- `centerline_matching.py` - Matches roads across maps using centerline buffer method

## Usage Examples

### Run single source pipeline
```bash
# Ingest and normalize SEFRAK only
python scripts/ingest/sefrak.py
python scripts/normalize/normalize_sefrak.py

# Validate output
python scripts/normalize/validate_schema.py data/sources/sefrak/normalized/
```

### Run ML detection on new map
```bash
# Extract buildings AND roads from 1904 map
python scripts/ingest/ml_extract.py \
  --input data/kartverket/1904/ \
  --output data/sources/ml_detected/kartverket_1904/raw/ \
  --model ml/models/segmentation_model.pt

# Normalize buildings
python scripts/normalize/normalize_ml_buildings.py \
  --source kartverket_1904 \
  --map_year 1904

# Normalize roads (NEW)
python scripts/normalize/normalize_ml_roads.py \
  --source kartverket_1904 \
  --map_year 1904
```

### Run road pipeline
```bash
# Merge roads from all ML sources with temporal inference
python scripts/merge/merge_roads.py \
  --config data/merged/road_merge_config.json \
  --output data/merged/roads_merged.geojson

# Export roads for frontend
python scripts/export/export_geojson.py \
  --input data/merged/roads_merged.geojson \
  --output data/export/roads_temporal.geojson \
  --feature_type road
```

### Merge specific sources (explicit)
```bash
# Edit merge_config.json to enable/disable sources, then:
python scripts/merge/merge_sources.py \
  --config data/merged/merge_config.json \
  --output data/merged/buildings_merged.geojson
```

### Full pipeline
```bash
# Run everything according to config
python scripts/pipeline.py --config pipeline_config.json
```

## Safety Guards

### 1. No implicit mixing
- Merge script REQUIRES explicit config file
- Config file must list all sources explicitly
- Disabled sources are skipped, not auto-included

### 2. Source immutability
- Raw data is never modified after ingestion
- Normalized data is regenerated, not edited
- Each run creates new output, doesn't modify in place

### 3. Provenance in output
- Every merged building has `_sources` array listing contributing sources
- Merge report shows exactly what was combined

### 4. Dev vs Prod separation
```json
// merge_config.dev.json - for testing new sources
{
  "sources": {
    "sefrak": {"enabled": true},
    "ml_kartverket_1904": {"enabled": true},  // Testing new ML
    "osm": {"enabled": true}
  }
}

// merge_config.prod.json - validated sources only
{
  "sources": {
    "sefrak": {"enabled": true},
    "osm": {"enabled": true}
    // ml_kartverket_1904 not yet validated
  }
}
```

## Adding a New Source

1. **Create directory structure**
   ```bash
   mkdir -p data/sources/new_source/{raw,normalized}
   ```

2. **Write ingestion script**
   ```bash
   # scripts/ingest/new_source.py
   # Downloads/extracts raw data to data/sources/new_source/raw/
   ```

3. **Write normalization script**
   ```bash
   # scripts/normalize/normalize_new_source.py
   # Converts to common schema, creates manifest.json
   ```

4. **Validate**
   ```bash
   python scripts/normalize/validate_schema.py data/sources/new_source/normalized/
   ```

5. **Add to merge config** (when ready)
   ```json
   // In merge_config.json:
   "new_source": {
     "enabled": true,
     "path": "../sources/new_source/normalized/buildings.geojson",
     "priority": 5
   }
   ```

## Building Replacement Detection

When a new building is constructed on the site of an old building, the old building should be marked as demolished. This happens during the merge stage.

### Replacement Detection Algorithm

```
┌─────────────────────────────────────────────────────────────────────┐
│                    REPLACEMENT DETECTION                            │
│                                                                     │
│  For each building B_old with end_date OR from historical source:  │
│                                                                     │
│    1. Find overlapping buildings from newer sources                 │
│       - Spatial overlap > 50% OR centroid within 10m                │
│                                                                     │
│    2. If B_new exists with start_date > B_old.start_date:          │
│       - Mark B_old.ed = B_new.sd (demolished when new was built)   │
│       - Set B_old.replaced_by = B_new.bid                          │
│                                                                     │
│    3. Evidence requirements for replacement:                        │
│       - B_new must have HIGH evidence of its start_date            │
│       - OR B_old must be absent in map where B_new appears         │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Replacement Rules by Era

| Era | Replacement Rule |
|-----|------------------|
| Pre-1900 | Old building hidden when new building has HIGH evidence start_date |
| 1900-1950 | Old building hidden when new building has MEDIUM+ evidence |
| Post-1950 | Old building hidden when new building exists in modern map |

### Implementation in Merge Config

The actual `data/merged/merge_config.json` format:

```json
{
  "replacement_detection": {
    "enabled": true,
    "overlap_threshold": 0.5,
    "centroid_max_distance_m": 10,
    "rules": [
      {
        "era": "pre_1900",
        "old_building_hidden_when": "new_building_evidence >= high"
      },
      {
        "era": "1900_1950",
        "old_building_hidden_when": "new_building_evidence >= medium"
      },
      {
        "era": "post_1950",
        "old_building_hidden_when": "new_building_exists"
      }
    ]
  }
}
```

**Note**: The `old_building_hidden_when` field is currently a human-readable description. The merge code parses these rules and applies era-based evidence filtering. Output field names (`ed`, `rep_by`, `rep_ev`) are hardcoded in the export stage.

### Replacement Detection Script

```python
# scripts/merge/detect_replacements.py

def detect_replacements(buildings, config):
    """
    Detect when buildings have been replaced by newer ones.

    For each historical building:
    1. Find spatially overlapping modern buildings
    2. Check if modern building has later start_date
    3. Apply era-based evidence rules
    4. Mark old building with end_date and replaced_by
    """
    spatial_index = build_spatial_index(buildings)

    for old in buildings_with_historical_date(buildings):
        candidates = find_overlapping(old, spatial_index, config.overlap_threshold)

        for new in candidates:
            if is_replacement(old, new, config):
                old.properties['ed'] = new.properties.get('sd')
                old.properties['rep_by'] = new.properties['bid']
                old.properties['rep_ev'] = calculate_replacement_evidence(old, new)

    return buildings
```

### Output Schema for Replaced Buildings

```json
{
  "type": "Feature",
  "properties": {
    "bid": "sefrak-1234",
    "sd": 1750,                    // Built in 1750
    "ed": 1965,                    // Demolished in 1965
    "ev": "h",
    "src": "sef",
    "rep_by": "osm-567890",        // Replaced by this building
    "rep_ev": "h"                  // Evidence strength for replacement
  }
}
```

### Frontend Handling

The frontend uses `ed` (end date) to hide replaced buildings:

```javascript
// Building is visible if:
// - year >= sd (after construction)
// - AND (no end date OR year < ed)

filter: [
  'all',
  ['<=', ['get', 'sd'], year],
  ['any',
    ['!', ['has', 'ed']],
    ['>', ['get', 'ed'], year]
  ]
]
```

## Merged Building Schema

After merging, buildings have combined metadata:

```json
{
  "type": "Feature",
  "properties": {
    "bid": "merged-12345",
    "sd": 1850,
    "ev": "h",
    "src": "sef",                  // Primary source
    "src_all": ["sef", "osm"],    // All contributing sources
    "ml_src": null,               // If ML-detected: which map
    "mlc": null,                  // ML confidence

    "_merge_info": {
      "matched_at": "2024-01-20",
      "match_method": "spatial_overlap",
      "match_score": 0.85,
      "sources": {
        "sefrak": {"src_id": "SEFRAK-12345", "sd": 1850},
        "osm": {"src_id": "way/123456", "sd": null}
      }
    }
  },
  "geometry": { ... }
}
```
