# Water Pipeline Handover

> **Note (2026-07-04):** The `source_viewer.*` tool referenced throughout this
> document has been renamed — it is now `frontend/feature_extraction.html` /
> `feature_extraction.js`. Line-number references below apply to the old file
> and are approximate in the renamed tool.

**Date:** 2026-01-01
**From:** Claude (pipeline/ML work)
**To:** Claude (source_viewer work)

## Summary

Water pipeline infrastructure is complete. Manual tracing via source_viewer is the recommended approach for historical water features (filled harbors, changed shorelines).

## What's Built

### Pipeline Scripts (all working)

| Script | Purpose | Status |
|--------|---------|--------|
| `scripts/ingest/fetch_osm_water.py` | Fetch current OSM water | ✅ Working |
| `scripts/normalize/normalize_water.py` | Normalize OSM water | ✅ Working |
| `scripts/merge/merge_water.py` | Merge OSM + manual + ML | ✅ Working |
| `scripts/export/export_water.py` | Export to GeoJSON/PMTiles | ✅ Working |
| `scripts/ingest/ingest_ml_water.py` | Ingest ML water (placeholder) | ✅ Working |
| `scripts/normalize/normalize_ml_water.py` | Normalize ML water | ✅ Working |

### Run Water Pipeline

```bash
# Full pipeline
PYTHONPATH=scripts python3 scripts/pipeline.py --stage all --feature-type water

# Individual steps
PYTHONPATH=scripts python3 scripts/ingest/fetch_osm_water.py
PYTHONPATH=scripts python3 scripts/normalize/normalize_water.py
PYTHONPATH=scripts python3 scripts/merge/merge_water.py
PYTHONPATH=scripts python3 scripts/export/export_water.py
```

### Data Locations

```
data/
├── sources/
│   ├── osm/
│   │   ├── raw/water.geojson          # Raw OSM water (41 features)
│   │   └── normalized/water.geojson   # Normalized
│   ├── manual/
│   │   └── normalized/water.geojson   # Manual annotations (target)
│   └── ml_water/
│       └── normalized/water.geojson   # ML detections (empty placeholder)
├── merged/
│   └── water_merged.geojson           # Merged output
└── export/
    ├── water.geojson                  # Frontend-ready GeoJSON
    └── water.pmtiles                  # Vector tiles
```

## Water Schema

```javascript
{
  "type": "Feature",
  "properties": {
    "wtype": "fjord",        // river, fjord, lake, canal, harbor, pond, stream
    "nm": "Trondheimsfjorden", // Name (optional)
    "sd": 1700,              // Start date - when water existed from
    "ed": 1965,              // End date - when filled (null if still exists)
    "ev": "m",               // Evidence: h=high, m=medium, l=low
    "src": "man",            // Source: osm, man, ml
    "_src": "manual",        // Internal source ID
    "_src_id": "man_001"     // Internal feature ID
  },
  "geometry": { /* Polygon */ }
}
```

## What Needs Source_Viewer Work

### 1. Manual Water Tracing Workflow

The source_viewer already has water drawing tools. Key areas to trace:

| Area | Fill Period | Priority | Notes |
|------|-------------|----------|-------|
| Brattøra | 1960-1980 | HIGH | Railway yard, largest fill |
| Nedre Elvehavn | 1970-1990 | HIGH | Now Solsiden district |
| Ilsvika | 1950-1970 | MEDIUM | Industrial area |
| Ravnkloa south | 1920-1940 | MEDIUM | Fish market expansion |
| Skansen area | 1900-1920 | LOW | Fortress area |

### 2. Workflow UX

1. User selects historical WMS year as backdrop
2. User sees current OSM water overlay (what exists now)
3. User draws polygon where water USED TO exist but is now filled
4. User sets properties:
   - `wtype`: Usually "fjord" or "harbor" for fill areas
   - `sd`: Start date (use earliest map showing water, or 1700 default)
   - `ed`: End date (year when filled, from map comparison)
   - `ev`: "m" for manual tracing
5. Save to `data/sources/manual/water.geojson`

### 3. Existing Water Editor Code

- `frontend/source_viewer.js` lines 1320-1604: Water drawing/editing
- `frontend/data_prep/water.js`: Modular water editing (473 lines)
- `backend/app.py` lines 475-597: Water API endpoints
  - `POST /api/water/add`
  - `PUT /api/water/update/<id>`
  - `DELETE /api/water/delete/<id>`

### 4. WMS Sources for Reference

```javascript
// Historical maps for tracing
const WMS_SOURCES = {
  '1880': 'https://wms.geonorge.no/skwms1/wms.historiskekart?layers=amt1',
  '1937': 'https://kart.trondheim.kommune.no/geoserver/Raster/wms?layers=ortofoto1937',
  '1947': 'https://kart.trondheim.kommune.no/geoserver/Raster/wms?layers=ortofoto1947',
  '1964': 'https://kart.trondheim.kommune.no/geoserver/Raster/wms?layers=ortofoto1964',
  '2006': 'https://kart.trondheim.kommune.no/geoserver/Raster/wms?layers=ortofoto2006',
};
```

## ML Approach (Abandoned for Now)

Color-based detection doesn't work because:
- 1880/1904 Amtskart: Sepia-toned (water is brown, not blue)
- 1937+ Aerial photos: Grayscale/color photos (no distinct water color)

ML training was attempted but struggled with class imbalance (5% water pixels).
Scripts exist but are not the recommended approach:
- `scripts/ml/bootstrap_water_training.py`
- `scripts/ml/extract_water_color.py`
- `ml/config_water.yaml`

## Integration with Main Map

Water layer should display with temporal filtering:

```javascript
// Filter expression for year Y
['all',
  ['<=', ['get', 'sd'], currentYear],  // Existed by this year
  ['any',
    ['!', ['has', 'ed']],               // Still exists (no end date)
    ['>', ['get', 'ed'], currentYear]   // Or end date is after current year
  ]
]
```

## Next Steps for Source_Viewer

1. [ ] Verify water drawing tools work with current backend
2. [ ] Add "Water Tracing Mode" with appropriate WMS backdrop
3. [ ] Pre-load OSM water as reference layer
4. [ ] Add date picker for sd/ed fields
5. [ ] Trace priority fill areas (start with Brattøra)
6. [ ] Test full pipeline: manual edit → merge → export → display

## Questions?

Check `docs/todo/current_work.md` for overall project status.
Run `/status` or `/doctor` for project health.
