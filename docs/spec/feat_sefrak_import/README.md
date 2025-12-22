# Feature Spec: SEFRAK Data Import

## Overview

Import and integrate data from the Norwegian SEFRAK (Sekretariatet for registrering av faste kulturminner i Norge) registry to enrich building data with historical construction dates and cultural heritage information. SEFRAK provides authoritative construction dates for pre-1900 buildings across Norway.

## Data Source

**Source**: SEFRAK Registry (Riksantikvaren - Directorate for Cultural Heritage)
- **Coverage**: Cultural heritage buildings, primarily pre-1900 structures
- **License**: Public sector information (free to use)
- **Format**: CSV/JSON export via API
- **Key Fields**: Building ID, coordinates, construction date, building type, heritage status
- **Geographic Scope**: National (Norway), subset filtered to Trondheim area

## Import Process

### 1. Download
```bash
python scripts/download_sefrak.py --area trondheim --output data/sefrak/raw/
```

Downloads SEFRAK records for specified geographic area via API or bulk export.

### 2. Parse and Normalize
```bash
python scripts/convert_sefrak.py --input data/sefrak/raw/ --output data/sefrak/buildings.geojson
```

Converts raw SEFRAK data to standardized GeoJSON format:
- Extract coordinates (convert from UTM33 if needed)
- Parse construction dates (handle ranges, circa dates, uncertainty)
- Normalize building types to common taxonomy
- Extract heritage status and protection level

### 3. Quality Control
- Validate coordinates fall within expected bounds
- Flag records with missing/invalid dates
- Check for duplicate entries
- Log parsing errors and warnings

## Matching Strategy

### Spatial Matching to OSM Buildings

SEFRAK records are point locations that must be matched to OSM building polygons:

1. **Buffer Match**: Find OSM building containing or nearest to SEFRAK point (within 20m threshold)
2. **Disambiguation**: If multiple OSM buildings within threshold, prefer:
   - Building polygon containing the point
   - Closest centroid distance
   - Similar building type/use
3. **Confidence Scoring**:
   - `high`: Point inside polygon, building type matches
   - `medium`: Within 5m, type compatible
   - `low`: Within 20m, type mismatch or multiple candidates

### Match Script
```bash
python scripts/merge_sefrak_osm.py \
  --sefrak data/sefrak/buildings.geojson \
  --osm data/osm/buildings.geojson \
  --output data/merged/buildings_with_sefrak.geojson
```

## Output Schema

Merged GeoJSON features include SEFRAK-derived attributes:

```json
{
  "type": "Feature",
  "geometry": { "type": "Polygon", "coordinates": [...] },
  "properties": {
    "osm_id": "way/123456",
    "start_date": 1850,
    "end_date": null,
    "source": "sefrak",
    "sefrak_id": "16-1234",
    "sefrak_match_confidence": "high",
    "building_type": "residential",
    "heritage_status": "protected",
    "construction_date_raw": "ca. 1850",
    "construction_date_uncertainty": "circa"
  }
}
```

**Key Fields**:
- `start_date`: Normalized construction year (integer)
- `source`: Always "sefrak" for SEFRAK-derived dates
- `sefrak_id`: Original SEFRAK registry ID for traceability
- `sefrak_match_confidence`: Spatial match quality (high/medium/low)
- `building_type`: Normalized type (residential, church, farm, industrial, etc.)
- `heritage_status`: Protection level (protected, listed, surveyed)
- `construction_date_raw`: Original date string from SEFRAK
- `construction_date_uncertainty`: Date quality flag (exact, circa, range, before, after)

## Dependencies

**Depends On**:
- `feat_osm_baseline`: Requires OSM building polygons for spatial matching

**Enables**:
- `feat_ml_extraction`: Provides training data with known construction dates
- `feat_time_slider`: Historical buildings with authoritative dates

## Implementation Files

- `scripts/download_sefrak.py` - API client for SEFRAK data download
- `scripts/convert_sefrak.py` - Parse and normalize SEFRAK records to GeoJSON
- `scripts/merge_sefrak_osm.py` - Spatial matching to OSM buildings
- `scripts/normalize_dates.py` - Date parsing utilities (handles ranges, circa, etc.)

## Status Checklist

- [x] Download script (`download_sefrak.py`)
- [x] Conversion script (`convert_sefrak.py`)
- [x] Date normalization utilities (`normalize_dates.py`)
- [x] OSM matching script (`merge_sefrak_osm.py`)
- [x] Schema validation
- [x] Match confidence scoring
- [ ] Integration tests
- [ ] Coverage analysis (% of SEFRAK records successfully matched)
- [ ] Documentation of date parsing edge cases
- [ ] Quality metrics (match confidence distribution)

## Known Limitations

1. **Point-to-Polygon Ambiguity**: SEFRAK records are points, not building footprints. Matching relies on spatial proximity which may be imprecise in dense urban areas.

2. **Demolished Buildings**: SEFRAK may include demolished buildings. No demolition dates are provided, so `end_date` remains null unless cross-referenced with other sources.

3. **Date Uncertainty**: Construction dates may be approximate (circa, ranges, "before 1850"). The `construction_date_uncertainty` field preserves this information but `start_date` normalizes to single year (typically midpoint of range or circa date as-is).

4. **Coverage Gaps**: SEFRAK focuses on cultural heritage buildings. Ordinary residential/commercial buildings from the same era may not be registered.

5. **Coordinate Accuracy**: Historical building locations may have coordinate errors or refer to demolished/relocated structures.

## Future Enhancements

- **Rematch Tool**: UI for manually reviewing and correcting low-confidence matches
- **Demolition Cross-Reference**: Integrate with municipal demolition permits or historical records
- **Extended Attributes**: Import additional SEFRAK metadata (architect, materials, photos)
- **Temporal Validation**: Flag anachronisms (e.g., SEFRAK date contradicts OSM construction date)
