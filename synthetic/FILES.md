# Phase 2 Rendering Pipeline - File Reference

Complete reference for all files in the synthetic data generation pipeline.

## Core Rendering Files

### `render_tiles.py` ⭐ MAIN ENTRY POINT
**Purpose**: Convert vector tiles to styled raster images

**Key Features**:
- Render single tiles or batches
- Read from PMTiles archives
- Apply MapLibre GL styles
- Multi-threaded batch processing
- Pure Python (Pillow-based) rendering

**Usage**:
```bash
# Single tile
python render_tiles.py --style styles/basic_map.json --tile 14 8378 4543 --output tile.png

# Batch with PMTiles
python render_tiles.py --style styles/military_1880.json --pmtiles data.pmtiles --batch tiles.txt --output-dir out/
```

**API**:
```python
from render_tiles import TileRenderer, RenderConfig

config = RenderConfig(tile_size=512)
renderer = TileRenderer('styles/military_1880.json', config)
img = renderer.render_tile(14, 8378, 4543, pmtiles_path='data.pmtiles')
img.save('output.png')
```

---

### `tile_utils.py`
**Purpose**: Utility functions for tile coordinate conversions

**Key Functions**:
- `TileCoordinates.tile_to_bbox(z, x, y)` - Get lat/lon bounds
- `TileCoordinates.lonlat_to_tile(lon, lat, z)` - Convert coords to tile
- `TileCoordinates.get_tile_center(z, x, y)` - Get tile center
- `tile_to_quadkey(z, x, y)` - Convert to quadkey string
- `get_neighboring_tiles(z, x, y)` - Get adjacent tiles

**Usage**:
```python
from tile_utils import TileCoordinates

# Trondheim center
lon, lat = 10.4, 63.43
x, y = TileCoordinates.lonlat_to_tile(lon, lat, 14)
bbox = TileCoordinates.tile_to_bbox(14, x, y)
```

---

## Style Files

### `styles/basic_map.json`
**Purpose**: Modern base map style for reference/testing

**Characteristics**:
- Clean, contemporary color palette
- Clear feature distinction
- Good for testing rendering pipeline

---

### `styles/military_1880.json`
**Purpose**: 1880s Norwegian military survey map style

**Characteristics**:
- Muted earth tones (beige/tan background)
- Dark buildings (#3d3530)
- Brown roads (#a89578 to #7a6542)
- Steel blue water (#5f7a8a) with hatching
- Stippled forest patterns

**Best for**: Building and major road extraction

---

### `styles/cadastral_1900.json`
**Purpose**: 1900s cadastral/property map style

**Characteristics**:
- Clean technical appearance
- Light cream background (#faf8f5)
- Cadastral pink buildings (#e6b8b8)
- Simple black roads
- Light blue water
- Emphasized property boundaries

**Best for**: Property boundary and precise building extraction

---

### `styles/topographic_1920.json`
**Purpose**: 1920s topographic map style

**Characteristics**:
- Natural tones with red highways
- Off-white background (#f5f3ed)
- Black outlined buildings
- Red main roads (#c84030), black minor roads
- Blue water (#b8d9e8)
- Light green vegetation

**Best for**: Road classification and terrain features

---

## Data Generation Pipeline

### `generate_dataset.py`
**Purpose**: Complete pipeline to generate training datasets

**Features**:
- Orchestrates entire workflow
- Random tile selection
- Multi-style rendering
- Aging effect application
- Mask generation
- Metadata tracking

**Usage**:
```bash
# Generate 1000 training pairs
python generate_dataset.py --count 1000 --output ../data/synthetic/

# Specific area and styles
python generate_dataset.py \
  --count 500 \
  --bbox 10.3,63.4,10.5,63.5 \
  --zoom 14 \
  --styles military_1880 cadastral_1900
```

**Output Structure**:
```
data/synthetic/
├── images/               # Rendered map images
├── masks/               # Ground truth segmentation masks
└── metadata.json        # Image-mask pairing info
```

---

### `create_masks.py`
**Purpose**: Generate ground truth segmentation masks

**Classes**:
- 0: Background
- 1: Building
- 2: Road
- 3: Water
- 4: Forest/vegetation

**Usage**:
```bash
# Single mask
python create_masks.py \
  --pmtiles data.pmtiles \
  --tile 14 8378 4543 \
  --output mask.png

# Batch processing
python create_masks.py \
  --pmtiles data.pmtiles \
  --batch tiles.txt \
  --output-dir masks/
```

---

### `age_effects.py`
**Purpose**: Apply historical aging effects to rendered images

**Effects**:
- Paper texture overlay
- Yellowing/sepia tone
- Color degradation
- Blur (old printing)
- Grain and noise
- Optional: fold lines, stains

**Usage**:
```bash
# Single image
python age_effects.py \
  --input tile.png \
  --output aged_tile.png \
  --intensity 0.7

# Batch with specific effects
python age_effects.py \
  --input-dir images/ \
  --output-dir aged/ \
  --effects yellowing,grain,blur \
  --intensity 0.5
```

**API**:
```python
from age_effects import apply_aging_effects

img = Image.open('tile.png')
aged_img = apply_aging_effects(img, intensity=0.6, effects=['yellowing', 'grain'])
aged_img.save('aged_tile.png')
```

---

### `textures.py`
**Purpose**: Procedural texture generation for aging effects

**Functions**:
- `generate_paper_texture()` - Realistic paper grain
- `generate_noise()` - Perlin/simplex noise
- `generate_watermark()` - Subtle watermark patterns

**Usage**:
```python
from textures import generate_paper_texture

texture = generate_paper_texture(512, 512, grain_size=3)
```

---

### `generate_styles.py`
**Purpose**: Create color variations of base styles

**Features**:
- Domain randomization
- Programmatic color manipulation
- Preserve style structure
- Seeded random generation (reproducible)

**Usage**:
```bash
# Single variation
python generate_styles.py styles/military_1880.json \
  --output military_var001.json \
  --variation 0.1

# Generate 20 variations
python generate_styles.py styles/military_1880.json \
  --output-dir variations/ \
  --count 20 \
  --variation 0.15
```

---

## Testing and Documentation

### `test_render.py`
**Purpose**: Test suite to verify rendering pipeline

**Tests**:
1. Tile coordinate conversion
2. Basic rendering with synthetic features
3. Multiple historical styles
4. Output file validation

**Usage**:
```bash
python test_render.py
```

**Expected Result**:
- Creates test images (test_*.png)
- Reports pass/fail for each test
- Validates entire rendering pipeline

---

### `example_usage.py`
**Purpose**: Example code showing how to use the API

**Contains**:
- Rendering examples
- Coordinate conversion examples
- Batch processing patterns
- Custom configuration examples

**Usage**:
```bash
python example_usage.py
```

---

### `test_aging.py`
**Purpose**: Test aging effects pipeline

**Usage**:
```bash
python test_aging.py
```

---

## Documentation Files

### `README.md` 📖 COMPREHENSIVE GUIDE
**Purpose**: Complete documentation for the rendering pipeline

**Sections**:
- Installation instructions
- Usage examples
- Architecture overview
- Configuration reference
- Troubleshooting
- Performance optimization
- API documentation

---

### `QUICKSTART.md` 🚀 START HERE
**Purpose**: 5-minute quick start guide

**Content**:
- Installation verification
- First render example
- Common commands cheat sheet
- Troubleshooting basics

---

### `FILES.md` 📋 THIS FILE
**Purpose**: Reference for all files in the pipeline

---

### `README_AGING.md`
**Purpose**: Detailed documentation for aging effects

**Content**:
- Effect descriptions
- Parameter tuning guide
- Example outputs
- Historical accuracy notes

---

### `styles/README.md`
**Purpose**: Documentation for historical map styles

**Content**:
- Style characteristics
- Color palettes
- Historical context
- Usage examples
- Variation generation

---

## Configuration Files

### `requirements.txt`
**Purpose**: Python package dependencies

**Key Packages**:
- `Pillow` - Image rendering and manipulation
- `numpy` - Numerical operations
- `pmtiles` - PMTiles archive reading
- `mapbox-vector-tile` - MVT decoding
- `tqdm` - Progress bars
- `opencv-python` - Advanced image processing (optional)
- `scipy` - Image filters (optional)

**Installation**:
```bash
pip install -r requirements.txt
```

---

## File Size and Line Count Summary

```
Core Rendering:
  render_tiles.py       ~680 lines    Main rendering engine
  tile_utils.py         ~390 lines    Coordinate utilities

Style Generation:
  generate_styles.py    ~400 lines    Style variations
  age_effects.py        ~550 lines    Aging effects
  textures.py           ~420 lines    Texture generation

Data Pipeline:
  generate_dataset.py   ~600 lines    Main dataset generator
  create_masks.py       ~450 lines    Mask generation

Testing:
  test_render.py        ~280 lines    Rendering tests
  test_aging.py         ~350 lines    Aging tests
  example_usage.py      ~200 lines    Usage examples

Documentation:
  README.md             ~800 lines    Comprehensive guide
  QUICKSTART.md         ~280 lines    Quick start
  FILES.md              ~450 lines    This file
  README_AGING.md       ~320 lines    Aging effects guide
  styles/README.md      ~190 lines    Style documentation

Styles:
  basic_map.json        ~135 lines
  military_1880.json    ~115 lines
  cadastral_1900.json   ~180 lines
  topographic_1920.json ~250 lines

Total: ~6,000+ lines of code and documentation
```

---

## Execution Flow

### Simple Rendering Workflow
```
User Command
    ↓
render_tiles.py
    ↓
StyleProcessor (parse JSON)
    ↓
PMTilesReader (load data)
    ↓
PillowRenderer (draw geometries)
    ↓
Output PNG
```

### Complete Dataset Generation Workflow
```
User Command
    ↓
generate_dataset.py
    ↓
┌───────────────┬──────────────────┬──────────────────┐
↓               ↓                  ↓                  ↓
Select Tiles    Load Styles        Initialize Output  Configure Effects
↓               ↓                  ↓                  ↓
└───────────────┴──────────────────┴──────────────────┘
    ↓
For each tile:
    ├─> render_tiles.py (create image)
    ├─> create_masks.py (create mask)
    └─> age_effects.py (age image)
    ↓
Save metadata.json
    ↓
Complete Dataset
```

---

## Dependencies Between Files

```
render_tiles.py
  ├─> tile_utils.py (coordinate conversion)
  └─> styles/*.json (map styling)

generate_dataset.py
  ├─> render_tiles.py (image rendering)
  ├─> create_masks.py (mask generation)
  ├─> age_effects.py (aging)
  └─> textures.py (texture overlays)

age_effects.py
  └─> textures.py (paper texture, noise)

test_render.py
  ├─> render_tiles.py (testing)
  └─> tile_utils.py (testing)

All scripts
  └─> requirements.txt (dependencies)
```

---

## Quick Reference Commands

```bash
# Test everything
python test_render.py

# Render one tile
python render_tiles.py --style styles/basic_map.json --tile 14 8378 4543 -o out.png

# Batch render
python render_tiles.py --style styles/military_1880.json --batch tiles.txt -d output/

# Generate dataset
python generate_dataset.py --count 1000 --output ../data/synthetic/

# Create mask
python create_masks.py --tile 14 8378 4543 --output mask.png

# Apply aging
python age_effects.py --input tile.png --output aged.png --intensity 0.7

# Generate style variation
python generate_styles.py styles/military_1880.json --count 10 -d variations/
```

---

## File Modification History

All files created during Phase 2 setup (2024-12-16):
- Initial rendering pipeline implementation
- Historical map style definitions
- Complete data generation workflow
- Test suites and examples
- Comprehensive documentation

---

## Where to Start

1. **New user?** → Read `QUICKSTART.md`
2. **Want details?** → Read `README.md`
3. **Need API docs?** → Check docstrings in `.py` files
4. **Ready to render?** → Run `python test_render.py` then use `render_tiles.py`
5. **Generate dataset?** → Use `generate_dataset.py`
