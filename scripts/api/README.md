# Manual Edits API

Flask API server for managing manual building edits.

## Installation

Flask and flask-cors are required but not in the main requirements.txt. Install them separately:

```bash
pip install flask flask-cors
```

## Running the Server

```bash
python scripts/api/server.py
```

The server will start on `http://localhost:5001`.

## Endpoints

### GET /api/manual
Returns all manual edits as a GeoJSON FeatureCollection.

**Example:**
```bash
curl http://localhost:5001/api/manual
```

**Response:**
```json
{
  "type": "FeatureCollection",
  "features": [...]
}
```

### POST /api/manual
Adds or updates a manual building edit.

**Request body:**
```json
{
  "osm_id": "way/12345",
  "geometry": {
    "type": "Polygon",
    "coordinates": [[...]]
  },
  "sd": 1850,
  "ed": null,
  "note": "Corrected construction date based on historical records"
}
```

**Example:**
```bash
curl -X POST http://localhost:5001/api/manual \
  -H "Content-Type: application/json" \
  -d '{
    "osm_id": "way/12345",
    "geometry": {"type": "Point", "coordinates": [10.4, 63.4]},
    "sd": 1850,
    "ed": null,
    "note": "Test edit"
  }'
```

**Response:**
```json
{
  "type": "Feature",
  "geometry": {...},
  "properties": {
    "osm_id": "way/12345",
    "sd": 1850,
    "ed": null,
    "src": "manual",
    "ev": "h",
    "note": "Corrected construction date...",
    "edited_at": "2025-12-22T12:34:56Z"
  }
}
```

### POST /api/rebuild
Triggers the data pipeline to rebuild merged data and PMTiles.

**Steps executed:**
1. Normalize manual source
2. Merge all sources
3. Export to GeoJSON and PMTiles

**Example:**
```bash
curl -X POST http://localhost:5001/api/rebuild
```

**Response (success):**
```json
{
  "status": "success",
  "message": "Pipeline rebuilt successfully"
}
```

**Response (error):**
```json
{
  "error": "Error message",
  "stderr": "...",
  "stdout": "..."
}
```

### GET /api/health
Health check endpoint.

**Example:**
```bash
curl http://localhost:5001/api/health
```

**Response:**
```json
{
  "status": "healthy",
  "edits_path": "/path/to/edits.json",
  "edits_exist": true
}
```

## Data Storage

Manual edits are stored in:
```
data/sources/manual/raw/edits.json
```

Each edit becomes a GeoJSON feature with properties:
- `osm_id` - OpenStreetMap ID (e.g., "way/12345")
- `sd` - Start date (construction year)
- `ed` - End date (demolition year, null if still standing)
- `src` - Always "manual"
- `ev` - Evidence level, always "h" (high) for manual edits
- `note` - Explanation for the edit
- `edited_at` - ISO timestamp of when the edit was made

## Integration with Pipeline

When you add edits via the API, they're saved to `edits.json`. To integrate them into the main dataset:

1. **Automatic:** Use the `/api/rebuild` endpoint (recommended)
2. **Manual:** Run the pipeline commands:
   ```bash
   # Normalize manual edits
   PYTHONPATH=scripts python scripts/pipeline.py --stage normalize --sources manual

   # Merge with other sources
   PYTHONPATH=scripts python scripts/pipeline.py --stage merge

   # Export to frontend
   PYTHONPATH=scripts python scripts/pipeline.py --stage export
   ```

## CORS

CORS is enabled for all origins to allow frontend access from any domain.

## Notes

- Updates to existing `osm_id` will replace the previous edit
- The server runs in debug mode by default (disable in production)
- No authentication is implemented (add if deploying publicly)
- Timeouts are set to prevent long-running operations from blocking
