# Trondheim++ Historical Map System

A system to view maps of Trondheim and surrounding areas across different time periods, using ML-extracted features from historical maps with a time slider interface.

## Project Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        SYSTEM ARCHITECTURE                      │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Frontend: MapLibre GL JS + Time Slider                 │   │
│  │  - Filter features by start_date/end_date               │   │
│  │  - Year selection: 1850 → present                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Tile Server: PMTiles (static) or Martin (dynamic)      │   │
│  │  - Vector tiles with temporal attributes                │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Data: GeoJSON/GeoPackage with date fields              │   │
│  │  - start_date, end_date per feature                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ▲                                  │
│                              │                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  ML Pipeline: Synthetic training → U-Net → Vectorize    │   │
│  │  - Extract features from historical map rasters         │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Scope

**Geographic Area:** Trondheim++ (~3,000 km²)
- Trondheim
- Malvik, Stjørdal, Meråker
- Melhus, Skaun, Klæbu

**Temporal Range:** 1850 - present

**Features to Extract:**
- Buildings
- Roads
- Railways
- Water bodies
- Forests (later phase)

---

## Phase Overview

| Phase | Description | Claude Sessions | Your Time | Output |
|-------|-------------|-----------------|-----------|--------|
| 1 | Infrastructure + Frontend | 2-3 | 2-3 hrs | Working map viewer with time slider |
| 2 | Synthetic Data Pipeline | 2-3 | 4-5 hrs | Training dataset |
| 3 | ML Training | 2-3 | 8-12 hrs | Trained segmentation model |
| 4 | Real Data Integration | 2-3 | 15-20 hrs | Fine-tuned model + extracted vectors |
| 5 | Production | 2-3 | 3-4 hrs | Complete working system |

**Total Estimate:** 10-15 Claude sessions, 30-40 hours your time, 4-8 weekends

---

## Phase 1: Infrastructure + Frontend

### Goal
A working web application showing modern OSM data for Trondheim with a time slider (even if historical data not yet loaded).

### Components
```
project/
├── docker-compose.yml          # All services
├── frontend/
│   ├── index.html              # MapLibre viewer
│   ├── style.css
│   └── app.js                  # Time slider logic
├── data/
│   ├── trondheim.osm.pbf       # OSM extract
│   └── trondheim.pmtiles       # Generated tiles
├── scripts/
│   ├── download_osm.sh         # Get OSM data
│   ├── generate_tiles.sh       # Create PMTiles
│   └── validate_phase1.sh      # Verify setup works
└── README.md
```

### Tech Stack
- **Tiles:** PMTiles (static file, no server needed)
- **Frontend:** MapLibre GL JS
- **Tile Generation:** Planetiler or tippecanoe
- **Hosting:** Local / GitHub Pages / any static host

### Prompt for Claude

```markdown
## Task: Generate Phase 1 - Infrastructure + Frontend

Create a complete, working system for viewing OSM map data of Trondheim, Norway
with a time slider for filtering features by date.

### Requirements

1. **Data Pipeline**
   - Script to download Trondheim area OSM extract from Geofabrik
   - Bounding box: approximately [10.0, 63.3, 10.8, 63.5]
   - Convert to PMTiles format with temporal attributes preserved
   - Include start_date, end_date fields if present in OSM data

2. **Frontend**
   - Single-page MapLibre GL JS application
   - Time slider (range: 1850-2025)
   - Filter displayed features based on selected year
   - Features visible if: start_date <= selected_year AND (end_date >= selected_year OR end_date is null)
   - Default style showing buildings, roads, water, land use
   - Responsive design

3. **Infrastructure**
   - Docker Compose setup for local development
   - Option to run without Docker (just static files)
   - Scripts work on Linux/Mac

4. **Validation**
   - Script that verifies:
     - Data downloaded successfully
     - Tiles generated correctly
     - Frontend loads and displays map
     - Time slider filters features

### Constraints
- Use well-tested, stable library versions
- Extensive error handling and logging
- Comments explaining non-obvious code
- README with step-by-step setup instructions

### Output Structure
Generate all files with complete contents, ready to run.
```

### Validation Checklist
- [ ] `docker-compose up` starts successfully
- [ ] Map loads centered on Trondheim
- [ ] Can zoom and pan
- [ ] Time slider visible and draggable
- [ ] Moving slider changes visible features (even if minimal change with current OSM data)
- [ ] No console errors

### Notes
- Most OSM features won't have dates, so slider effect will be minimal initially
- This is intentional - we're building the infrastructure first
- Historical data comes in Phase 4

---

## Phase 2: Synthetic Data Pipeline

### Goal
Generate realistic-looking "historical map" images from modern vector data, paired with ground truth masks for ML training.

### Concept
```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ Modern OSM      │ ──▶ │ Apply historical│ ──▶ │ Synthetic       │
│ vectors         │     │ style + aging   │     │ training image  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                                               │
        │                                               │
        ▼                                               ▼
┌─────────────────┐                             ┌─────────────────┐
│ Rasterized      │                             │ Perfect pair!   │
│ ground truth    │                             │ Image + mask    │
│ mask            │                             │                 │
└─────────────────┘                             └─────────────────┘
```

### Components
```
project/
├── synthetic/
│   ├── styles/
│   │   ├── military_1880.json      # MapLibre style
│   │   ├── cadastral_1900.json
│   │   └── topographic_1920.json
│   ├── generate_styles.py          # LLM-assisted style creation
│   ├── render_tiles.py             # Vector → styled raster
│   ├── age_effects.py              # Paper texture, yellowing, noise
│   ├── create_masks.py             # Vector → segmentation mask
│   ├── generate_dataset.py         # Main pipeline
│   └── validate_phase2.sh
├── data/
│   └── synthetic/
│       ├── images/                 # Training images
│       ├── masks/                  # Ground truth masks
│       └── metadata.json           # Pairing info
```

### Style Generation Approach

Use Claude/LLM to generate MapLibre style JSON that mimics historical cartography:

```python
STYLE_PROMPT = """
Generate a MapLibre GL style JSON that makes a modern map look like a 
{era} Norwegian {map_type} map.

Characteristics for {era}:
- Color palette: {colors}
- Building style: {building_desc}
- Road style: {road_desc}
- Typography: {font_desc}
- Special features: {special}

Output only valid JSON, no explanation.
"""
```

### Aging Effects
```python
def age_map(image, intensity=0.5):
    """Apply realistic aging to synthetic map."""
    # Paper texture overlay
    # Sepia/yellowing color shift
    # Slight blur (old printing)
    # Noise (paper grain)
    # Random ink bleed
    # Optional: fold lines, stains, tears
    return aged_image
```

### Prompt for Claude

```markdown
## Task: Generate Phase 2 - Synthetic Data Pipeline

Create a pipeline to generate synthetic historical map training data from 
modern OSM vector data.

### Requirements

1. **Style System**
   - Generate 3-5 different historical map styles as MapLibre JSON
   - Styles should mimic: 1880s military survey, 1900s cadastral, 1920s topographic
   - Each style defines colors, line widths, patterns for: buildings, roads, water, forest
   - Include helper script to generate more styles via LLM prompt

2. **Rendering Pipeline**
   - Input: OSM vectors for a tile area
   - Render to image using historical style
   - Output: PNG image (256x256 or 512x512)
   - Must be reproducible (same input → same output)

3. **Aging Effects**
   - Paper texture overlay (provide sample or generate procedurally)
   - Color degradation (yellowing, fading)
   - Print artifacts (slight blur, ink spread)
   - Noise and grain
   - Configurable intensity

4. **Mask Generation**
   - Same tile area → segmentation mask
   - Classes: background (0), building (1), road (2), water (3), forest (4)
   - Pixel-perfect alignment with rendered image

5. **Dataset Generation**
   - Generate N training pairs
   - Vary: location, style, aging intensity, random augmentation
   - Save with consistent naming: {tile_id}_{style}_{variant}.png
   - Generate metadata.json linking images to masks

6. **Validation**
   - Script to visualize random samples (image + mask overlay)
   - Check class distribution
   - Verify alignment between image and mask

### Constraints
- Pure Python, minimal dependencies (Pillow, numpy, requests)
- Can use local tile renderer or external service
- Must work offline after initial setup
- Generate 1000 pairs in under 1 hour

### Output
- Complete Python package
- Sample styles included
- Example output images for verification
```

### Validation Checklist
- [ ] Can generate at least 3 distinct historical styles
- [ ] Rendered maps look plausibly "old" (human judgment)
- [ ] Masks align perfectly with images
- [ ] All 5 classes represented in masks
- [ ] Can generate 1000 pairs without errors
- [ ] Sample visualization script works

### Notes
- Quality of synthetic data directly impacts ML training
- Err on side of MORE variety in styles/aging
- Domain randomization helps model generalize

---

## Phase 3: ML Training

### Goal
Train a U-Net segmentation model on synthetic data that can extract features from map images.

### Architecture
```
Input image (256x256x3)
       │
       ▼
┌─────────────────────────────────┐
│     Encoder (ResNet34)          │
│     - Pretrained on ImageNet    │
│     - Feature extraction        │
└─────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────┐
│     Decoder (U-Net style)       │
│     - Upsampling                │
│     - Skip connections          │
└─────────────────────────────────┘
       │
       ▼
Output mask (256x256x5)
  - Channel per class
```

### Components
```
project/
├── ml/
│   ├── dataset.py              # PyTorch Dataset class
│   ├── model.py                # U-Net architecture
│   ├── train.py                # Training loop
│   ├── evaluate.py             # Metrics, visualization
│   ├── predict.py              # Run inference on new images
│   ├── vectorize.py            # Raster mask → vector polygons
│   ├── config.yaml             # Hyperparameters
│   └── validate_phase3.sh
├── models/
│   └── checkpoints/            # Saved model weights
├── results/
│   ├── training_logs/
│   └── predictions/
```

### Training Configuration
```yaml
# config.yaml
model:
  encoder: resnet34
  pretrained: true
  classes: 5  # background, building, road, water, forest

training:
  epochs: 50
  batch_size: 16
  learning_rate: 0.001
  optimizer: adam
  loss: dice  # or cross_entropy, focal

data:
  train_split: 0.8
  val_split: 0.1
  test_split: 0.1
  augmentation: true

augmentation:
  horizontal_flip: true
  vertical_flip: true
  rotation: 15
  brightness: 0.2
  contrast: 0.2
```

### Prompt for Claude

```markdown
## Task: Generate Phase 3 - ML Training Pipeline

Create a complete PyTorch training pipeline for map segmentation.

### Requirements

1. **Dataset Class**
   - Load image/mask pairs from Phase 2 output
   - Apply augmentations (flip, rotate, color jitter)
   - Proper train/val/test split
   - Handle class imbalance

2. **Model**
   - U-Net with ResNet34 encoder (use segmentation_models_pytorch)
   - Pretrained encoder weights
   - 5 output classes

3. **Training Loop**
   - Mixed precision training (faster on modern GPUs)
   - Learning rate scheduler (reduce on plateau)
   - Early stopping
   - Save best model checkpoint
   - TensorBoard or wandb logging (optional)
   - Progress bar with metrics

4. **Evaluation**
   - IoU (Intersection over Union) per class
   - Overall accuracy
   - Confusion matrix
   - Visual comparison: input → prediction → ground truth

5. **Inference Script**
   - Load trained model
   - Process single image or directory
   - Output predicted mask as PNG
   - Include confidence threshold option

6. **Vectorization**
   - Convert raster mask to vector polygons
   - Simplify polygons (reduce point count)
   - Output as GeoJSON
   - Include feature class as property

### Constraints
- Must work on: CUDA GPU, Apple MPS, CPU (fallback)
- Clear requirements.txt with pinned versions
- Training should complete in <4 hours on RTX 3060

### Output
- Complete training pipeline
- Example inference script
- Vectorization script
- Requirements.txt
```

### Expected Training Metrics

| Metric | Synthetic Only | After Fine-tuning |
|--------|---------------|-------------------|
| Building IoU | 0.5-0.7 | 0.7-0.85 |
| Road IoU | 0.4-0.6 | 0.6-0.8 |
| Water IoU | 0.7-0.9 | 0.8-0.95 |
| Overall Accuracy | 0.8-0.9 | 0.85-0.95 |

### Validation Checklist
- [ ] Training starts without errors
- [ ] Loss decreases over epochs
- [ ] Validation metrics logged
- [ ] Checkpoint saved
- [ ] Can load checkpoint and resume
- [ ] Inference works on new image
- [ ] Vectorization produces valid GeoJSON
- [ ] Results visually reasonable (human check)

### Decision Point
After training on synthetic data, test on REAL historical map:

```
IF IoU > 0.5 on real map:
    → Proceed to Phase 4 (fine-tuning will improve)
    
IF IoU < 0.3 on real map:
    → Domain gap too large
    → Options:
       A) Improve synthetic styles to match real maps better
       B) Annotate 50+ real tiles manually
       C) Reduce scope (buildings only, not all features)
```

---

## Phase 4: Real Data Integration

### Goal
Download real historical maps from Kartverket, manually annotate a subset, fine-tune the model, and process all available maps.

### Data Sources

**Kartverket Historical Maps:**
- URL: https://www.kartverket.no/en/order-historical-maps
- Download: https://kartkatalog.geonorge.no/
- Types available:
  - Amtskart (county maps) 1826-1916
  - Topographic maps various eras
  - Cadastral maps

**License:**
- Maps >100 years old: Public domain
- Maps <100 years old: CC BY 4.0

### Components
```
project/
├── data/
│   ├── kartverket/
│   │   ├── raw/                # Downloaded map images
│   │   ├── georeferenced/      # Aligned to coordinates
│   │   └── tiles/              # Cut into training tiles
│   ├── annotations/
│   │   ├── images/             # Tiles to annotate
│   │   └── masks/              # Manual annotations
│   └── extracted/
│       └── trondheim_1900.geojson  # Final extracted features
├── scripts/
│   ├── download_kartverket.py
│   ├── georeference.py
│   ├── tile_maps.py
│   ├── annotation_helper.py    # Simple annotation UI
│   └── fine_tune.py
```

### Manual Annotation Strategy

**Tools:** QGIS, Label Studio, or custom simple tool

**Target:** 30-50 annotated tiles (10-20 hours work)

**Process:**
1. Select diverse tiles (city center, suburbs, rural)
2. Trace buildings, roads, water
3. Export as matching PNG masks
4. Verify alignment

### Prompt for Claude

```markdown
## Task: Generate Phase 4 - Real Data Integration

Create scripts to download, process, and annotate real Kartverket historical maps.

### Requirements

1. **Download Script**
   - Fetch historical maps for Trondheim area from Kartverket
   - Handle their API/download format
   - Organize by era/type

2. **Georeferencing**
   - Align historical maps to modern coordinate system
   - Use GDAL/rasterio
   - Output: GeoTIFF with proper CRS

3. **Tiling**
   - Cut large map into training-size tiles (256x256)
   - Maintain geo-coordinates for each tile
   - Skip empty/border tiles

4. **Annotation Helper**
   - Simple tool to assist manual annotation
   - Load historical tile
   - Overlay model prediction as starting point
   - Allow correction
   - Save mask

5. **Fine-tuning Script**
   - Load pretrained model from Phase 3
   - Train on real annotated data
   - Lower learning rate
   - More augmentation
   - Save fine-tuned model

6. **Batch Processing**
   - Run inference on all historical map tiles
   - Vectorize results
   - Merge into single GeoJSON per era
   - Add temporal attributes (start_date from map metadata)

### Constraints
- Handle various Kartverket formats (TIFF, JPEG2000)
- Robust to missing/corrupt files
- Progress tracking for long batch jobs

### Output
- Download and processing scripts
- Annotation helper tool
- Fine-tuning script
- Batch processing pipeline
```

### Validation Checklist
- [ ] Can download at least one historical map series
- [ ] Georeferencing produces correctly aligned output
- [ ] Tiles generated at correct size and location
- [ ] Annotation helper works
- [ ] Fine-tuning improves metrics on real data
- [ ] Batch processing completes without errors
- [ ] Extracted GeoJSON loads in QGIS/frontend

### Notes
- This is the most time-intensive phase (manual annotation)
- Quality of annotation directly impacts final results
- Start with buildings (clearest features) before roads

---

## Phase 5: Production

### Goal
Integrate extracted historical features into the map viewer, deploy for sharing.

### Final Data Flow
```
┌─────────────────┐
│ OSM Current     │──┐
│ (with dates)    │  │    ┌─────────────────┐
└─────────────────┘  │    │                 │
                     ├───▶│  Merged         │───▶ PMTiles ───▶ Frontend
┌─────────────────┐  │    │  GeoJSON        │
│ Extracted 1900  │──┤    │  (all eras)     │
│ features        │  │    └─────────────────┘
└─────────────────┘  │
                     │
┌─────────────────┐  │
│ Extracted 1950  │──┘
│ features        │
└─────────────────┘
```

### Components
```
project/
├── production/
│   ├── merge_data.py           # Combine all sources
│   ├── generate_pmtiles.sh     # Final tile generation
│   ├── deploy.sh               # Deployment script
│   └── Dockerfile              # Production container
├── frontend/
│   └── (updated with historical styles)
├── data/
│   └── final/
│       ├── trondheim_all_eras.geojson
│       └── trondheim_historical.pmtiles
```

### Deployment Options

**Option A: Static Hosting (simplest)**
```
- PMTiles file on GitHub Pages / Cloudflare R2 / S3
- Static HTML/JS frontend
- Cost: $0
```

**Option B: VPS (more control)**
```
- Hetzner CX22: €4/month
- Docker container with everything
- Own domain
```

**Option C: Local Demo**
```
- Run on laptop
- Share via Cloudflare Tunnel (free)
- Good for demos
```

### Prompt for Claude

```markdown
## Task: Generate Phase 5 - Production Integration

Create scripts to merge all data and deploy the complete system.

### Requirements

1. **Data Merging**
   - Combine OSM current data with extracted historical features
   - Handle overlapping features (same building in multiple eras)
   - Ensure consistent schema (start_date, end_date, source)
   - Validate temporal consistency

2. **Final Tile Generation**
   - Generate PMTiles with all eras
   - Optimize for web delivery
   - Include appropriate zoom levels

3. **Frontend Updates**
   - Historical-appropriate styling for old features
   - Era indicator on UI
   - Legend showing data source/confidence
   - About page with methodology

4. **Deployment**
   - Dockerfile for self-contained deployment
   - GitHub Pages deployment script
   - Cloudflare R2 upload script

5. **Documentation**
   - User guide
   - Data sources and methodology
   - Known limitations
   - How to contribute corrections

### Output
- Complete production-ready system
- Multiple deployment options
- Documentation
```

### Validation Checklist
- [ ] All eras visible in viewer
- [ ] Time slider correctly filters features
- [ ] Switching years shows appropriate features appearing/disappearing
- [ ] Performance acceptable (no lag on zoom/pan)
- [ ] Works on mobile
- [ ] Deployed and accessible via URL

---

## Risk Register

| ID | Risk | Likelihood | Impact | Mitigation | Status |
|----|------|------------|--------|------------|--------|
| R1 | Training data takes too long | HIGH | HIGH | Start synthetic pipeline early | |
| R2 | Map alignment issues | HIGH | MED | Build alignment tools, accept imperfection | |
| R3 | Synthetic→Real domain gap | MED | MED | Fine-tuning budget, small real dataset | |
| R4 | Model doesn't generalize | MED | HIGH | Multi-style training, domain randomization | |
| R5 | LLM styles don't match reality | MED | LOW | Human review, reference real maps | |
| R6 | Kartverket access issues | LOW | MED | Download and cache early | |
| R7 | Performance issues | LOW | LOW | PMTiles solves this | |

---

## Decision Points

### After Phase 3: Synthetic Training
```
Test model on ONE real historical map tile.

IoU > 0.5 → Continue to Phase 4
IoU 0.3-0.5 → Improve synthetic styles, test again
IoU < 0.3 → Major pivot needed:
            - More manual annotation
            - Reduce feature scope
            - Consider raster-only approach
```

### After Phase 4: Fine-tuning
```
Extraction quality assessment.

>70% usable → Continue to Phase 5
50-70% usable → Build correction UI, plan for human-in-loop
<50% usable → Reduce scope, hybrid approach
```

---

## Resource Estimates

### Compute
| Resource | Amount | Cost |
|----------|--------|------|
| GPU training | 10-20 hours | $10-30 (cloud) or free (Colab) |
| Processing | 3-5 hours | Free (local) |
| Storage | 5-10 GB | Free (local) |
| Hosting | Static files | €0-4/month |

### Time
| Phase | Claude | Your Active Time | Your Passive Time |
|-------|--------|------------------|-------------------|
| 1 | 2-3 hrs | 1-2 hrs | 1 hr |
| 2 | 2-3 hrs | 2-3 hrs | 2 hrs |
| 3 | 2-3 hrs | 2-4 hrs | 6-8 hrs (training) |
| 4 | 2-3 hrs | 12-15 hrs | 3-5 hrs |
| 5 | 1-2 hrs | 2-3 hrs | 1 hr |
| **Total** | **10-15 hrs** | **20-25 hrs** | **15-20 hrs** |

---

## File Structure (Final)

```
trondheim-historical-maps/
├── README.md
├── PLAN.md                     # This file
├── docker-compose.yml
├── requirements.txt
│
├── frontend/
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   └── assets/
│
├── synthetic/
│   ├── styles/
│   ├── generate_styles.py
│   ├── render_tiles.py
│   ├── age_effects.py
│   └── generate_dataset.py
│
├── ml/
│   ├── dataset.py
│   ├── model.py
│   ├── train.py
│   ├── evaluate.py
│   ├── predict.py
│   ├── vectorize.py
│   └── config.yaml
│
├── scripts/
│   ├── download_osm.sh
│   ├── download_kartverket.py
│   ├── generate_tiles.sh
│   ├── georeference.py
│   └── validate_*.sh
│
├── data/
│   ├── osm/
│   ├── kartverket/
│   ├── synthetic/
│   ├── annotations/
│   └── final/
│
├── models/
│   └── checkpoints/
│
├── production/
│   ├── merge_data.py
│   ├── deploy.sh
│   └── Dockerfile
│
└── docs/
    ├── methodology.md
    ├── data_sources.md
    └── user_guide.md
```

---

## Quick Start Commands

```bash
# Clone and setup
git clone <repo>
cd trondheim-historical-maps

# Phase 1: Infrastructure
./scripts/download_osm.sh
./scripts/generate_tiles.sh
docker-compose up frontend
# Open http://localhost:8080

# Phase 2: Synthetic data
python synthetic/generate_dataset.py --count 1000

# Phase 3: Train
python ml/train.py --config ml/config.yaml

# Phase 4: Real data
python scripts/download_kartverket.py
python scripts/fine_tune.py

# Phase 5: Deploy
./production/deploy.sh
```

---

## Prompting Guide for Claude

When starting a new phase, provide Claude with:

1. **This plan document** (or relevant section)
2. **Current state:** What's already built, what works
3. **Specific errors:** If debugging, include full error logs
4. **Constraints:** Your machine specs, available tools

**Example prompt:**
```
I'm working on Phase 2 of my historical map project (see PLAN.md attached).

Phase 1 is complete: I have a working frontend with OSM data and time slider.

Now I need the synthetic data pipeline. Please generate all files for:
- Style generation system
- Rendering pipeline  
- Aging effects
- Dataset generation

My setup:
- Ubuntu 22.04
- Python 3.11
- Have GDAL installed
- Will run training on RTX 3060

Generate complete, working code with error handling.
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2024-XX-XX | Initial plan |

---

## License

This project plan: MIT
Generated map data: Depends on sources (ODbL for OSM derivatives, CC0/CC-BY for Kartverket)
