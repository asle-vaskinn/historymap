# Feature Spec: OSM Baseline Import

## Overview

Import OpenStreetMap data as the modern baseline for all features in the Trondheim Historical Map. This provides the "Find" baseline (current state) that other data sources (SEFRAK, ML extraction) will enrich with historical information.

## Data Source

**OpenStreetMap (OSM)** via:
- **Overpass API**: For targeted queries (recommended for development)
- **Planet extracts**: For bulk downloads (Geofabrik Norway extract)

**License**: ODbL (Open Database License)

## Feature Types

Extract the following feature types within Trondheim bounding box:

### 1. Buildings
- OSM tags: `building=*`
- Attributes: `building` type, `name`, `addr:*`, `start_date`, `building:levels`

### 2. Roads
- OSM tags: `highway=*` (exclude `footway`, `path`, `steps`)
- Attributes: `highway` type, `name`, `surface`, `lanes`

### 3. Water
- OSM tags: `natural=water`, `waterway=*`
- Attributes: `water` type, `name`, `waterway` type

### 4. Forest/Landuse
- OSM tags: `landuse=forest`, `natural=wood`
- Attributes: `landuse` type, `natural` type, `name`

## Import Process

### 1. Define Bounding Box
```python
# Trondheim city center + surrounding areas
TRONDHEIM_BBOX = {
    "south": 63.35,
    "west": 10.25,
    "north": 63.50,
    "east": 10.65
}
```

### 2. Download via Overpass API
```bash
# Query for each feature type
curl -X POST "https://overpass-api.de/api/interpreter" \
  --data "[bbox:63.35,10.25,63.50,10.65];(way[building];);out geom;" \
  > buildings.osm
```

### 3. Convert to GeoJSON
```bash
# Using osmtogeojson or ogr2ogr
osmtogeojson buildings.osm > buildings.geojson
```

### 4. Filter and Normalize
- Remove features outside exact bbox (Overpass bbox is inclusive)
- Convert OSM tags to normalized schema (see below)
- Add temporal attributes: `start_date=2025`, `end_date=null`, `source=osm`

## Schema

Normalized GeoJSON properties for each feature type:

### Buildings
```json
{
  "id": "osm-way-12345",
  "feature_type": "building",
  "building_type": "residential",
  "name": "Building Name",
  "start_date": 2025,
  "end_date": null,
  "source": "osm",
  "confidence": 1.0,
  "osm_id": "way/12345",
  "osm_tags": {
    "building": "residential",
    "building:levels": "3"
  }
}
```

### Roads
```json
{
  "id": "osm-way-67890",
  "feature_type": "road",
  "road_type": "primary",
  "name": "Kongens gate",
  "start_date": 2025,
  "end_date": null,
  "source": "osm",
  "confidence": 1.0,
  "osm_id": "way/67890",
  "osm_tags": {
    "highway": "primary",
    "surface": "asphalt"
  }
}
```

### Water
```json
{
  "id": "osm-way-11111",
  "feature_type": "water",
  "water_type": "river",
  "name": "Nidelva",
  "start_date": 1700,
  "end_date": null,
  "source": "osm",
  "confidence": 1.0,
  "osm_id": "way/11111",
  "osm_tags": {
    "waterway": "river"
  }
}
```

### Forest/Landuse
```json
{
  "id": "osm-way-22222",
  "feature_type": "landuse",
  "landuse_type": "forest",
  "name": "Bymarka",
  "start_date": 1700,
  "end_date": null,
  "source": "osm",
  "confidence": 1.0,
  "osm_id": "way/22222",
  "osm_tags": {
    "landuse": "forest"
  }
}
```

## Role in Pipeline

1. **Baseline ("Find")**: OSM provides the current state of all features
2. **Enrichment Target**: Other sources add historical context:
   - SEFRAK: Adds accurate `start_date` for historic buildings
   - ML Extraction: Adds demolished buildings (`end_date < 2025`)
3. **Spatial Reference**: OSM geometries used for matching/merging with other sources
4. **Completeness**: OSM is most complete for modern features, less so for historical

## Implementation Plan

### Scripts
- `scripts/download_osm.py`: Download OSM data via Overpass API
- `scripts/normalize/normalize_osm.py`: Convert OSM tags to normalized schema
- `scripts/ingest/ingest_osm.py`: Import into main GeoJSON/PMTiles pipeline

### Output
- `data/sources/osm_buildings.geojson`
- `data/sources/osm_roads.geojson`
- `data/sources/osm_water.geojson`
- `data/sources/osm_landuse.geojson`

### Configuration
```yaml
# config/osm_import.yaml
bbox:
  south: 63.35
  west: 10.25
  north: 63.50
  east: 10.65

feature_types:
  - buildings
  - roads
  - water
  - landuse

overpass_url: "https://overpass-api.de/api/interpreter"
```

## Dependencies

**None** - This is the starting point of the data pipeline.

**Depends on this**:
- `feat_sefrak_enrichment`: Enriches OSM buildings with SEFRAK dates
- `feat_ml_extraction`: Adds historical buildings not in OSM
- `feat_merge_sources`: Merges all sources into unified dataset

## Status

- [ ] Define Trondheim bounding box
- [ ] Implement Overpass API download script
- [ ] Implement OSM to normalized GeoJSON converter
- [ ] Test download for each feature type
- [ ] Validate schema compliance
- [ ] Document OSM attribution requirements
- [ ] Integrate into main pipeline (`scripts/pipeline.py`)
- [ ] Add validation tests
- [ ] Update QUICKSTART.md with OSM import instructions
