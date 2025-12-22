# PMTiles Quick Start Guide

Quick reference for using the PMTiles export functionality.

## Prerequisites

Install tippecanoe:

```bash
# macOS
brew install tippecanoe

# Verify
tippecanoe --version
```

## Basic Usage

### 1. Export via Pipeline (Recommended)

```bash
# Export GeoJSON + PMTiles automatically
python scripts/pipeline.py --stage export

# Or run full pipeline
python scripts/pipeline.py --stage all
```

### 2. Export PMTiles Manually

```bash
# Requires GeoJSON already exported
python scripts/export/export_pmtiles.py

# Custom paths
python scripts/export/export_pmtiles.py \
  -i data/export/buildings.geojson \
  -o data/export/buildings.pmtiles
```

### 3. Skip PMTiles Generation

```bash
# Export GeoJSON only
python scripts/pipeline.py --stage export --no-pmtiles
```

## Common Options

```bash
# Adjust zoom levels
python scripts/export/export_pmtiles.py --min-zoom 8 --max-zoom 18

# Force overwrite
python scripts/export/export_pmtiles.py --force

# Quiet mode (no progress)
python scripts/export/export_pmtiles.py --quiet

# With metadata
python scripts/export/export_pmtiles.py \
  --name "My Buildings" \
  --description "Historical building footprints" \
  --attribution "© Data sources"
```

## Output Files

After export, you'll have:

```
data/export/
├── buildings.geojson          # Frontend-ready GeoJSON
├── buildings.geojson.meta.json  # GeoJSON metadata
├── buildings.pmtiles          # Vector tiles archive
└── buildings.pmtiles.meta.json  # PMTiles metadata
```

## Testing

```bash
# Run test suite
python scripts/export/test_pmtiles.py

# Should see:
# ✓ tippecanoe is available
# ✓ PMTiles file created successfully
# ✓ All tests passed!
```

## Frontend Integration

### HTML Setup

```html
<!DOCTYPE html>
<html>
<head>
  <script src="https://unpkg.com/maplibre-gl@latest/dist/maplibre-gl.js"></script>
  <script src="https://unpkg.com/pmtiles@latest/dist/index.js"></script>
  <link href="https://unpkg.com/maplibre-gl@latest/dist/maplibre-gl.css" rel="stylesheet" />
</head>
<body>
  <div id="map" style="width: 100%; height: 100vh;"></div>
</body>
</html>
```

### JavaScript

```javascript
// Register PMTiles protocol
let protocol = new pmtiles.Protocol();
maplibregl.addProtocol('pmtiles', protocol.tile);

// Create map
const map = new maplibregl.Map({
  container: 'map',
  style: 'https://demotiles.maplibre.org/style.json',
  center: [10.39, 63.43], // Trondheim
  zoom: 13
});

map.on('load', () => {
  // Add PMTiles source
  map.addSource('buildings', {
    type: 'vector',
    url: 'pmtiles://./buildings.pmtiles'
  });

  // Add building layer
  map.addLayer({
    id: 'buildings',
    type: 'fill',
    source: 'buildings',
    'source-layer': 'buildings',
    paint: {
      'fill-color': '#888',
      'fill-opacity': 0.8
    }
  });
});
```

### Temporal Filtering

```javascript
// Show buildings for a specific year
function filterByYear(year) {
  map.setFilter('buildings', [
    'all',
    ['<=', ['get', 'sd'], year],
    ['any',
      ['>=', ['get', 'ed'], year],
      ['!', ['has', 'ed']]
    ]
  ]);
}

// Add year slider
const slider = document.getElementById('year-slider');
slider.addEventListener('input', (e) => {
  const year = parseInt(e.target.value);
  filterByYear(year);
});
```

## Hosting

### Local Testing

```bash
# Python HTTP server (has range request support)
cd data/export
python -m http.server 8000

# Open: http://localhost:8000
```

### GitHub Pages

```bash
# 1. Copy PMTiles to docs/ folder
cp data/export/buildings.pmtiles docs/

# 2. Update HTML to load from relative path
# url: 'pmtiles://./buildings.pmtiles'

# 3. Commit and push
git add docs/buildings.pmtiles
git commit -m "Add PMTiles data"
git push

# 4. Enable GitHub Pages in repo settings
# Pages will be at: https://{username}.github.io/{repo}/
```

### S3/Cloudflare R2

```bash
# Upload with public read access
aws s3 cp data/export/buildings.pmtiles \
  s3://my-bucket/buildings.pmtiles \
  --acl public-read \
  --content-type application/x-protobuf

# Update CORS policy to allow range requests
# Then use: pmtiles://https://bucket.s3.region.amazonaws.com/buildings.pmtiles
```

## Troubleshooting

### "tippecanoe not found"

```bash
# Install tippecanoe
brew install tippecanoe

# Or use Docker
docker run -v $(pwd):/data felt/tippecanoe \
  -o /data/buildings.pmtiles \
  --force \
  /data/buildings.geojson
```

### "Output file exists"

```bash
# Use --force flag
python scripts/export/export_pmtiles.py --force

# Or delete old file
rm data/export/buildings.pmtiles
```

### PMTiles not loading in browser

1. Check browser console for errors
2. Verify server supports HTTP Range requests:
   ```bash
   curl -I -H "Range: bytes=0-100" http://localhost:8000/buildings.pmtiles
   # Should see: HTTP/1.0 206 Partial Content
   ```
3. Check CORS headers if loading from different domain
4. Verify PMTiles protocol is registered before map.addSource()

### Large file size

```bash
# Reduce zoom levels (fewer detail levels)
python scripts/export/export_pmtiles.py --max-zoom 14

# Or filter data before export
# (fewer features = smaller file)
```

## Tips

1. **Test locally first**: Use Python HTTP server for quick testing
2. **Check file size**: ~25-35 MB for 100k buildings is normal
3. **Use CDN**: PMTiles work great with Cloudflare or CloudFront
4. **Enable caching**: Set long cache headers (immutable data)
5. **Monitor requests**: Check browser network tab for tile loads

## Help

```bash
# Script help
python scripts/export/export_pmtiles.py --help

# Pipeline help
python scripts/pipeline.py --help

# Run tests
python scripts/export/test_pmtiles.py
```

## More Information

- Full documentation: `scripts/export/README.md`
- Implementation details: `PMTILES_IMPLEMENTATION.md`
- PMTiles spec: https://github.com/protomaps/PMTiles
- Tippecanoe docs: https://github.com/felt/tippecanoe
