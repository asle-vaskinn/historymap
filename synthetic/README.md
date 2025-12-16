# Phase 2: Synthetic Data Generation Pipeline

This directory contains the rendering pipeline for converting vector tiles to styled raster images. This is Phase 2 of the Trondheim Historical Map project, which generates synthetic training data for machine learning models.

## Overview

The rendering pipeline converts modern OSM vector data into synthetic "historical map" images by:

1. **Rendering** vector tiles to raster images with historical styling
2. **Applying aging effects** to make maps look old (yellowing, paper texture, etc.)
3. **Creating ground truth masks** for ML training
4. **Generating datasets** with reproducible, deterministic output

## Components

### Core Rendering

- **`render_tiles.py`** - Main rendering script
  - Converts vector tiles (from PMTiles) to styled raster images
  - Supports batch rendering with progress reporting
  - Pure Python implementation using Pillow (works offline)
  - Configurable output size (default 512x512 pixels)

- **`tile_utils.py`** - Utility functions
  - Tile coordinate ↔ geographic coordinate conversions
  - Web Mercator projection helpers
  - Quadkey encoding/decoding
  - Neighboring tile calculations

### Styling

- **`styles/`** - Historical map style definitions
  - `basic_map.json` - Modern base map style
  - `military_1880.json` - 1880s Norwegian military survey style
  - `cadastral_1900.json` - 1900s cadastral/property map style
  - `topographic_1920.json` - 1920s topographic map style

- **`generate_styles.py`** - Style variation generator
  - Creates color variations of base styles
  - Domain randomization for ML training diversity
  - Programmatic style manipulation

### Data Augmentation

- **`age_effects.py`** - Historical aging effects
  - Paper texture overlay
  - Color degradation (yellowing, sepia)
  - Print artifacts (blur, ink spread)
  - Configurable intensity

- **`textures.py`** - Procedural texture generation
  - Paper grain
  - Noise patterns
  - Watermark effects

### Training Data Creation

- **`create_masks.py`** - Ground truth mask generation
  - Converts vector data to segmentation masks
  - Classes: background, building, road, water, forest
  - Pixel-perfect alignment with rendered images

## Installation

### Requirements

Install dependencies:

```bash
pip install -r requirements.txt
```

Key dependencies:
- `Pillow` - Image rendering and manipulation
- `numpy` - Numerical operations
- `pmtiles` - Reading PMTiles archives
- `mapbox-vector-tile` - Decoding vector tiles
- `tqdm` - Progress bars

### Optional Dependencies

For enhanced features:
- `opencv-python` - Advanced aging effects
- `scipy` - Additional image filters

## Usage

### 1. Render a Single Tile

Render one tile to see the output:

```bash
python render_tiles.py \
  --style styles/military_1880.json \
  --tile 10 524 340 \
  --output test_tile.png
```

### 2. Render from PMTiles

Render tiles directly from a PMTiles archive:

```bash
python render_tiles.py \
  --style styles/cadastral_1900.json \
  --pmtiles ../data/trondheim.pmtiles \
  --tile 14 8378 4543 \
  --output cadastral_tile.png
```

### 3. Batch Rendering

Create a file with tile coordinates (`tiles.txt`):

```
# Format: z x y
14 8378 4543
14 8378 4544
14 8379 4543
14 8379 4544
```

Then render all tiles:

```bash
python render_tiles.py \
  --style styles/military_1880.json \
  --pmtiles ../data/trondheim.pmtiles \
  --batch tiles.txt \
  --output-dir output/military/
```

### 4. Parallel Rendering

Use multiple workers for faster batch rendering:

```bash
python render_tiles.py \
  --style styles/topographic_1920.json \
  --batch tiles.txt \
  --output-dir output/topo/ \
  --workers 8
```

### 5. Custom Output Size

Change the output image size:

```bash
python render_tiles.py \
  --style styles/basic_map.json \
  --tile 12 2095 1135 \
  --output large_tile.png \
  --size 1024  # 1024x1024 pixels
```

## Creating Training Datasets

### Generate Style Variations

Create multiple color variations for domain randomization:

```bash
# Generate 10 variations of military style
python generate_styles.py styles/military_1880.json \
  --output-dir styles/variations/military/ \
  --count 10 \
  --variation 0.15

# Generate variations for all styles
for style in styles/*.json; do
  python generate_styles.py "$style" \
    --output-dir "styles/variations/$(basename $style .json)/" \
    --count 5
done
```

### Apply Aging Effects

Add historical aging to rendered tiles:

```bash
python age_effects.py \
  --input output/military/14_8378_4543.png \
  --output aged/14_8378_4543_aged.png \
  --intensity 0.7 \
  --effects yellowing,grain,blur
```

### Create Ground Truth Masks

Generate segmentation masks for ML training:

```bash
python create_masks.py \
  --pmtiles ../data/trondheim.pmtiles \
  --tile 14 8378 4543 \
  --output masks/14_8378_4543_mask.png \
  --classes building,road,water,forest
```

## Tile Coordinate Reference

### Trondheim Area Tiles

At zoom level 14, Trondheim center is approximately:
- Tile: `14/8378/4543`
- Center: 63.43°N, 10.40°E

Useful zoom levels:
- **Zoom 10** - Regional view (524, 340)
- **Zoom 12** - City overview (2095, 1135)
- **Zoom 14** - District detail (8378, 4543)
- **Zoom 16** - Street level (33512, 18172)

### Finding Tile Coordinates

Use the Python utilities:

```python
from tile_utils import TileCoordinates

# Convert lon/lat to tile coordinates
lon, lat = 10.4, 63.43  # Trondheim
z = 14
x, y = TileCoordinates.lonlat_to_tile(lon, lat, z)
print(f"Tile: {z}/{x}/{y}")

# Get bounding box for a tile
bbox = TileCoordinates.tile_to_bbox(14, 8378, 4543)
print(f"BBox: {bbox}")  # (min_lon, min_lat, max_lon, max_lat)
```

Or use online tools:
- [geojson.io](http://geojson.io/) - Visual tile explorer
- [Mercantile CLI](https://github.com/mapbox/mercantile) - `mercantile tile 10.4 63.43 14`

## Architecture

### Rendering Pipeline

```
┌─────────────────────────────────────────────────────────┐
│                  Input: PMTiles File                    │
│                  + Style JSON                           │
│                  + Tile Coordinates (z/x/y)             │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│  1. Read Vector Tile Data                              │
│     - Decode MVT (Mapbox Vector Tile)                  │
│     - Extract features by layer                        │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│  2. Apply Style                                         │
│     - Parse MapLibre GL JSON                           │
│     - Match features to style layers                   │
│     - Evaluate zoom-based properties                   │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│  3. Render Geometry                                     │
│     - Project coordinates to pixel space               │
│     - Draw polygons (buildings, water, landuse)        │
│     - Draw lines (roads, railways)                     │
│     - Draw points (POIs)                               │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│  4. Post-Processing (Optional)                          │
│     - Apply aging effects                              │
│     - Add paper texture                                │
│     - Color grading                                    │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│              Output: PNG Image (512x512)                │
└─────────────────────────────────────────────────────────┘
```

### Rendering Backends

The system supports multiple rendering backends (in order of preference):

1. **Pillow Renderer** (Primary)
   - Pure Python, works offline
   - No external dependencies beyond Pillow
   - Good quality for training data
   - ~100-200 tiles/second

2. **MapLibre Native** (Optional, not yet implemented)
   - C++ native rendering
   - Higher quality, faster
   - Requires compilation from source
   - ~1000+ tiles/second

3. **Static API** (Fallback, not yet implemented)
   - External rendering service
   - Requires network connection
   - Rate limited
   - Use only for testing

## Configuration

### RenderConfig Options

Customize rendering in code:

```python
from render_tiles import RenderConfig, TileRenderer

config = RenderConfig(
    tile_size=512,                                    # Output size
    background_color=(242, 239, 233, 255),           # Light beige RGBA
    antialias=True,                                  # Smooth edges
    line_quality=4,                                  # Supersampling factor
    compression='PNG',                               # Output format
    compression_level=6                              # 0-9 (0=fast, 9=small)
)

renderer = TileRenderer('styles/military_1880.json', config)
img = renderer.render_tile(14, 8378, 4543, pmtiles_path='../data/trondheim.pmtiles')
img.save('output.png')
```

## Reproducibility

The rendering pipeline is deterministic:
- Same input → Same output
- No random seeds needed for basic rendering
- Color variations use seeded random generators
- Aging effects are reproducible with fixed seeds

This ensures training datasets can be regenerated exactly.

## Performance

### Benchmarks

On a modern CPU (Apple M1):
- Single tile rendering: ~5-20ms (Pillow backend)
- Batch rendering (8 workers): ~100-200 tiles/second
- 1000 tiles: ~5-10 minutes

Bottlenecks:
- PMTiles I/O: ~2-5ms per tile
- Vector tile decoding: ~3-8ms
- Rendering: ~5-10ms
- PNG encoding: ~2-5ms

### Optimization Tips

1. **Use batch rendering** with multiple workers
2. **Keep PMTiles files on SSD** for faster I/O
3. **Reduce output size** for faster rendering (256px vs 512px)
4. **Lower PNG compression** level for speed (level 3-4 vs 6)
5. **Simplify styles** - fewer layers = faster rendering

## Troubleshooting

### Common Issues

**Q: `ModuleNotFoundError: No module named 'pmtiles'`**

A: Install dependencies: `pip install pmtiles`

**Q: `No tile data for z=X, x=Y, y=Z`**

A: The PMTiles file might not contain that tile. Check zoom levels and bounds.

**Q: Rendered tiles are blank/white**

A: Check that:
- Style JSON references correct source layers
- PMTiles contains data for that area
- Source-layer names match between style and data

**Q: Colors don't match style**

A: Verify:
- Color values in style JSON are valid hex/rgb
- Zoom-based expressions are properly formatted
- Opacity values are between 0-1

**Q: Rendering is slow**

A: Try:
- Increase `--workers` count
- Reduce `--size` (e.g., 256 instead of 512)
- Use lower PNG compression level
- Profile with `--verbose` flag

### Debugging

Enable verbose logging:

```bash
python render_tiles.py \
  --style styles/basic_map.json \
  --tile 14 8378 4543 \
  --output test.png \
  --verbose
```

Test coordinate conversion:

```bash
python tile_utils.py
```

## Examples

### Example 1: Generate Training Dataset

Complete workflow to generate 100 training image/mask pairs:

```bash
# 1. Create tile list for Trondheim city center (zoom 14)
cat > tiles_trondheim.txt << EOF
14 8377 4542
14 8377 4543
14 8378 4542
14 8378 4543
14 8379 4542
14 8379 4543
EOF

# 2. Render with military style
python render_tiles.py \
  --style styles/military_1880.json \
  --pmtiles ../data/trondheim.pmtiles \
  --batch tiles_trondheim.txt \
  --output-dir dataset/images/military/ \
  --workers 4

# 3. Create matching ground truth masks
python create_masks.py \
  --pmtiles ../data/trondheim.pmtiles \
  --batch tiles_trondheim.txt \
  --output-dir dataset/masks/ \
  --workers 4

# 4. Apply aging effects
python age_effects.py \
  --input-dir dataset/images/military/ \
  --output-dir dataset/images/military_aged/ \
  --intensity 0.5 \
  --batch
```

### Example 2: Compare Different Styles

Render the same tile with all three historical styles:

```bash
TILE="14 8378 4543"
PMTILES="../data/trondheim.pmtiles"

for style in styles/military_1880.json styles/cadastral_1900.json styles/topographic_1920.json; do
  name=$(basename $style .json)
  python render_tiles.py \
    --style "$style" \
    --pmtiles "$PMTILES" \
    --tile $TILE \
    --output "comparison_${name}.png"
done
```

### Example 3: Large Area Coverage

Generate tiles for entire Trondheim municipality:

```python
# generate_tile_list.py
from tile_utils import TileCoordinates

# Trondheim bounding box
min_lon, min_lat = 10.0, 63.3
max_lon, max_lat = 10.8, 63.5
zoom = 14

# Calculate tile range
min_x, min_y = TileCoordinates.lonlat_to_tile(min_lon, max_lat, zoom)
max_x, max_y = TileCoordinates.lonlat_to_tile(max_lon, min_lat, zoom)

# Write tile list
with open('tiles_all_trondheim.txt', 'w') as f:
    for x in range(min_x, max_x + 1):
        for y in range(min_y, max_y + 1):
            f.write(f"{zoom} {x} {y}\n")

print(f"Generated {(max_x-min_x+1) * (max_y-min_y+1)} tiles")
```

Then render:

```bash
python render_tiles.py \
  --style styles/topographic_1920.json \
  --pmtiles ../data/trondheim.pmtiles \
  --batch tiles_all_trondheim.txt \
  --output-dir output/trondheim_full/ \
  --workers 8
```

## Next Steps

After generating synthetic data:

1. **Phase 3: ML Training**
   - Use rendered images + masks for U-Net training
   - See `../ml/README.md` for training pipeline

2. **Quality Check**
   - Visually inspect sample tiles
   - Verify image/mask alignment
   - Check class distribution in masks

3. **Domain Randomization**
   - Generate more style variations
   - Vary aging intensity
   - Add noise and augmentation

## Related Documentation

- [Project Plan](../HISTORICAL_MAP_PROJECT_PLAN.md) - Full project overview
- [Styles README](styles/README.md) - Historical style details
- [Tile Utils](tile_utils.py) - API documentation (see docstrings)
- [MapLibre Style Spec](https://maplibre.org/maplibre-style-spec/) - Official style format

## License

MIT License - See project root for details.

Map data © OpenStreetMap contributors (ODbL).
