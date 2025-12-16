# Trondheim Historical Map - Frontend

Phase 1 implementation of the Trondheim Historical Map project. This is a MapLibre GL JS web application with a time slider for viewing historical map features.

## Files

- **index.html** - Main HTML page with MapLibre map container and UI controls
- **style.css** - Complete styling for map, time slider, and responsive design
- **app.js** - Map initialization, PMTiles integration, and temporal filtering logic

## Features

1. **MapLibre GL JS Integration**
   - Vector tile rendering
   - Smooth zoom and pan
   - Responsive controls

2. **PMTiles Support**
   - Uses protomaps/pmtiles protocol handler
   - Static file serving (no tile server needed)
   - Expected PMTiles path: `../data/trondheim.pmtiles`

3. **Time Slider**
   - Range: 1850-2025
   - Default year: 2020
   - Real-time year display
   - Smooth slider interactions

4. **Temporal Filtering**
   - Features filtered by: `start_date <= selected_year AND (end_date >= selected_year OR end_date is null)`
   - Automatically updates when slider changes
   - Handles missing date attributes gracefully

5. **Styled Layers**
   - Buildings (brown/tan)
   - Roads (grey, categorized by type)
   - Water bodies (blue)
   - Landuse/green spaces (green)
   - Place labels

6. **Responsive Design**
   - Desktop: controls overlay in top-right
   - Mobile: controls at bottom
   - Adapts to screen size

## How to Use

### Option 1: Simple HTTP Server (Recommended)

```bash
# Navigate to the project root
cd /Users/vaskinn/Development/private/historymap

# Start a simple HTTP server (Python 3)
python3 -m http.server 8080

# Or use Node.js
npx http-server -p 8080

# Open in browser
open http://localhost:8080/frontend/
```

### Option 2: Direct File Access

You can also open `index.html` directly in a browser, but you may encounter CORS issues with local files. HTTP server is recommended.

### Option 3: Docker (if you have docker-compose set up)

```bash
docker-compose up frontend
```

## Configuration

Edit `app.js` to modify configuration:

```javascript
const CONFIG = {
    center: [10.39, 63.43],    // Map center (Trondheim coordinates)
    zoom: 12,                   // Initial zoom level
    pmtilesPath: '../data/trondheim.pmtiles',  // Path to PMTiles file
    defaultYear: 2020,          // Default selected year
    minYear: 1850,              // Slider minimum
    maxYear: 2025               // Slider maximum
};
```

## Expected Data Format

The PMTiles file should contain vector tiles with these source layers:

- **building** - Building polygons with optional `start_date` and `end_date` properties
- **transportation** - Road lines with `class` property and temporal attributes
- **water** - Water body polygons with temporal attributes
- **landuse** - Landuse polygons with `class` property and temporal attributes
- **place** - Point features with `name` property for labels

### Temporal Attributes

Features can have these date properties:
- `start_date` (integer): Year when feature first appeared
- `end_date` (integer): Year when feature ceased to exist (optional)

Features without these properties are always visible.

## Browser Requirements

- Modern browser with ES6 support
- WebGL support (for MapLibre GL JS)
- Tested on: Chrome 100+, Firefox 100+, Safari 15+, Edge 100+

## Dependencies (loaded via CDN)

- MapLibre GL JS v4.0.0
- PMTiles v3.0.6

## Next Steps

1. **Generate PMTiles Data**
   - Download OSM data for Trondheim area
   - Convert to PMTiles format with temporal attributes
   - Place at `../data/trondheim.pmtiles`

2. **Test with Sample Data**
   - Create a small test PMTiles file
   - Verify temporal filtering works correctly

3. **Add Historical Data** (Phase 4)
   - Integrate ML-extracted features from historical maps
   - Add proper temporal attributes
   - Regenerate PMTiles

## Troubleshooting

### Map doesn't load
- Check browser console for errors
- Verify PMTiles file exists at correct path
- Ensure you're using an HTTP server (not file://)

### Time slider doesn't filter
- Check that PMTiles has `start_date`/`end_date` properties
- Most OSM data won't have dates initially (expected)
- Historical data will be added in later phases

### CORS errors
- Use an HTTP server instead of opening file directly
- Check that PMTiles file is accessible

## Development

For debugging, the application exposes global state in console:

```javascript
// Access in browser console
HistoricalMap.map           // MapLibre map instance
HistoricalMap.currentYear   // Current selected year
HistoricalMap.updateMapYear(1900)  // Update to specific year
HistoricalMap.CONFIG        // Current configuration
```

## License

Part of the Trondheim Historical Map project.
