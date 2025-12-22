# Feature Spec: ML Extraction from Historical Maps

## Overview

ML-based feature extraction uses a U-Net deep learning model to perform semantic segmentation on historical map rasters, extracting building footprints, roads, water bodies, and forested areas. The extracted features are vectorized to GeoJSON polygons with confidence scores.

**Purpose**: Automate extraction of historical geographic features from Kartverket historical maps (1880+) where manual digitization would be prohibitively time-consuming.

**Key Capabilities**:
- Semantic segmentation of 5 feature classes from historical map imagery
- Handles aged/degraded map quality with synthetic training data
- Outputs GeoJSON polygons with ML confidence scores
- Processes full historical map tiles or regions of interest

## Model Architecture

### U-Net with ResNet34 Encoder

```
Input: RGB image (256x256 pixels)
       ↓
Encoder: ResNet34 (pretrained on ImageNet)
  - Conv layers with skip connections
  - Progressive downsampling: 256 → 128 → 64 → 32 → 16
       ↓
Bottleneck: 512 channels at 16x16
       ↓
Decoder: Transposed convolutions with skip connections
  - Progressive upsampling: 16 → 32 → 64 → 128 → 256
  - Concatenates encoder features at each level
       ↓
Output: 5-channel probability map (256x256 pixels)
  - Channel 0: background
  - Channel 1: buildings
  - Channel 2: roads
  - Channel 3: water
  - Channel 4: forest
```

**Architecture Benefits**:
- **Pretrained encoder**: ResNet34 weights from ImageNet provide strong feature extraction
- **Skip connections**: Preserve spatial detail from encoder to decoder
- **Multi-scale features**: Captures both large structures and fine details
- **Efficient**: ~24M parameters, runs on CPU/GPU/Apple Silicon

**Implementation**: `ml/train.py` using `segmentation-models-pytorch` library

## Training Pipeline

### 1. Synthetic Data Generation

**Problem**: Limited annotated historical maps for training.

**Solution**: Generate synthetic training data by aging modern OSM renders.

**Process** (`synthetic/` directory):
1. Render modern OSM vectors with historical map styling
2. Apply aging effects: sepia tones, noise, paper texture, fading
3. Generate corresponding segmentation masks from OSM geometry
4. Output: paired images and masks mimicking historical map appearance

**Data Structure**:
```
data/synthetic/
├── train/
│   ├── images/     # Aged map renders
│   └── masks/      # Ground truth segmentation masks
└── val/            # Validation split (10-20%)
```

### 2. Augmentation

**Applied during training** (via `albumentations`):
- Random rotation (±15°)
- Horizontal/vertical flips
- Brightness/contrast adjustments (±20%)
- Gaussian blur (simulate map degradation)
- Elastic deformations (simulate paper warping)

**Augmentation config**: `ml/config.yaml` → `augmentation` section

### 3. Loss Function

**Dice Loss**: Optimizes overlap between predicted and ground truth masks.

```
Dice Coefficient = 2 * |X ∩ Y| / (|X| + |Y|)
Dice Loss = 1 - Dice Coefficient
```

**Why Dice Loss**:
- Handles class imbalance (e.g., buildings are sparse vs background)
- Directly optimizes segmentation quality (IoU-like metric)
- Smooth gradients for stable training

**Additional**: Class weighting to prioritize buildings (primary feature of interest)

### 4. Training Configuration

**Hyperparameters** (`ml/config.yaml`):
- Optimizer: AdamW (learning rate: 1e-4, weight decay: 1e-5)
- Batch size: 8-16 (depending on GPU memory)
- Epochs: 50-100
- Learning rate schedule: ReduceLROnPlateau (patience: 10)
- Early stopping: Patience 20 epochs on validation loss

**Device Support**:
- CUDA (NVIDIA GPUs)
- MPS (Apple Silicon M1/M2/M3)
- CPU fallback

**Training Command**:
```bash
python ml/train.py --config ml/config.yaml
```

**Outputs**:
- Checkpoints: `models/checkpoints/last_checkpoint.pth`
- Best model: `models/checkpoints/best_model.pth` (lowest val loss)
- Training logs: Loss curves, dice scores per class

## Inference Pipeline

### Input: Historical Map Raster

**Supported formats**: PNG, JPEG, GeoTIFF
**Requirements**: Georeferenced (for coordinate mapping)

### Processing Steps

1. **Tile Input Image** (if large):
   - Split into 256x256 overlapping tiles
   - 10% overlap to avoid edge artifacts
   - Track tile positions for reconstruction

2. **Normalization**:
   - Convert to RGB if grayscale
   - Normalize pixel values to [0, 1]
   - Apply ImageNet mean/std (ResNet34 pretrained)

3. **Model Inference**:
   - Forward pass through U-Net
   - Output: 5-channel probability map per tile
   - Apply softmax to get class probabilities

4. **Post-Processing**:
   - Stitch tiles back together (average overlapping regions)
   - Apply confidence threshold (default: 0.5)
   - Morphological operations: remove small noise, fill holes

5. **Output Raster Mask**:
   - Single-channel image: pixel values = class IDs (0-4)
   - Confidence map: separate channel with per-pixel probabilities

**Inference Command**:
```bash
python ml/predict.py \
  --checkpoint models/checkpoints/best_model.pth \
  --input data/kartverket/historical_map.png \
  --output results/segmentation_mask.png \
  --confidence-threshold 0.5
```

**Performance**: ~0.5s per 256x256 tile on M2 MacBook Pro

## Vectorization

### Raster Mask → GeoJSON Polygons

**Process** (`ml/vectorize.py`):

1. **Connected Component Analysis**:
   - Group contiguous pixels of same class into blobs
   - Filter by minimum area (e.g., 10 sq meters for buildings)

2. **Contour Extraction**:
   - Extract boundaries using `cv2.findContours` or `rasterio.features.shapes`
   - Simplify contours with Douglas-Peucker (tolerance: 0.5m)

3. **Coordinate Transformation**:
   - Map pixel coordinates to geographic coordinates (WGS84)
   - Use GeoTIFF geotransform or manual georeferencing metadata

4. **Polygon Simplification**:
   - Remove self-intersections
   - Merge overlapping polygons (buildings touching)
   - Snap to grid (0.1m precision)

5. **Attribute Assignment**:
   - Calculate mean confidence from probability map per polygon
   - Assign feature class (building, road, water, forest)
   - Add source metadata

**Vectorization Command**:
```bash
python ml/vectorize.py \
  --input results/segmentation_mask.png \
  --confidence results/confidence_map.png \
  --geotransform results/geotransform.txt \
  --output data/ml_extracted/buildings_1880.geojson \
  --min-area 10 \
  --class building
```

## Confidence Scoring

### Per-Pixel Confidence

**During inference**: Softmax output gives probability distribution over 5 classes.

```python
confidence_pixel = max(softmax_probabilities)
```

### Per-Polygon Confidence

**Aggregation methods**:
1. **Mean confidence**: Average of all pixel confidences within polygon
2. **Min confidence**: Lowest pixel confidence (conservative estimate)
3. **Weighted mean**: Weight by distance from polygon boundary

**Default**: Mean confidence (balances conservatism and informativeness)

**Confidence Attributes**:
- `mlc`: Mean confidence score (0.0 - 1.0)
- `mlc_min`: Minimum pixel confidence in polygon
- `mlc_std`: Standard deviation of pixel confidences (uncertainty measure)

### Confidence Thresholds

**Filtering low-confidence extractions**:
- `mlc >= 0.7`: High confidence (use directly)
- `0.5 <= mlc < 0.7`: Medium confidence (flag for review)
- `mlc < 0.5`: Low confidence (discard or manual verification)

**Usage in frontend**: Filter layer by confidence slider

## Output Schema

### GeoJSON Feature Properties

```json
{
  "type": "Feature",
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[lon1, lat1], [lon2, lat2], ...]]
  },
  "properties": {
    "ml_src": "kartverket_1880",        // Source historical map
    "mlc": 0.87,                         // Mean confidence score
    "mlc_min": 0.72,                     // Minimum confidence
    "mlc_std": 0.08,                     // Confidence std dev
    "class": "building",                 // Feature class
    "area_sqm": 245.3,                   // Polygon area
    "extraction_date": "2025-01-15",     // When ML was run
    "model_version": "v1.2"              // Model checkpoint ID
  }
}
```

### Integration with Temporal Schema

ML-extracted features can be merged with temporal data:

```json
{
  "ml_src": "kartverket_1880",
  "mlc": 0.87,
  "start_date": 1880,          // Inferred from source map date
  "end_date": null,            // Unknown if still exists
  "source": "ml_extracted",    // Data provenance
  "confidence": 0.87           // Alias for mlc
}
```

## Building Verification Workflow

### Purpose

Verify if known buildings (from OSM/SEFRAK) existed in historical maps. This "verification" workflow differs from "discovery" - instead of finding new buildings, we confirm that existing buildings were present at specific historical dates.

### Pipeline Overview

```
┌─────────────────────────────────────────────────────────────┐
│  STEP 1: PREPARE MAP                                        │
│  Input: Historical map (PNG/TIFF)                          │
│  ↓ Check if GeoTIFF → use existing georef                  │
│  ↓ Otherwise → apply GCPs from JSON file                   │
│  Output: Georeferenced GeoTIFF                             │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  STEP 2: ML EXTRACTION                                      │
│  Input: Georeferenced map                                   │
│  ↓ predict.py → segmentation mask                          │
│  ↓ vectorize.py → GeoJSON with confidence                  │
│  Output: ML buildings with mlc, mlc_min, mlc_std           │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  STEP 3: VERIFY BUILDINGS                                   │
│  Input: ML buildings + known buildings (OSM/SEFRAK)        │
│  ↓ Spatial matching (bbox filter → centroid check)         │
│  ↓ Calculate combined confidence                           │
│  Output: Updated buildings_temporal.geojson                │
└─────────────────────────────────────────────────────────────┘
```

### GCP File Format

Ground Control Points are stored in `data/kartverket/gcps/{map_name}.gcp.json`:

```json
{
  "version": "1.0",
  "map_id": "trondheim_1880",
  "map_date": 1880,
  "crs": "EPSG:4326",
  "source_file": "raw/trondheim_amt1.png",
  "gcps": [
    {
      "id": "GCP1",
      "pixel_x": 1234,
      "pixel_y": 567,
      "geo_x": 10.395,
      "geo_y": 63.430,
      "description": "Nidaros Cathedral"
    }
  ]
}
```

### Combined Confidence Calculation

```python
combined_confidence = 0.4 * ml_confidence
                    + 0.3 * overlap_score
                    + 0.2 * area_ratio
                    + 0.1 * centroid_score

# Quality thresholds:
# >= 0.7: high quality
# >= 0.5: medium quality
# < 0.5: low quality
```

### Verification Schema

Buildings are updated with `_verification` metadata:

```json
{
  "properties": {
    "sd": 1880,
    "ev": "h",
    "src": "ml",
    "_verification": {
      "maps_checked": [1880, 1900],
      "detections": [
        {
          "map_date": 1880,
          "map_id": "kartverket_1880",
          "combined_score": 0.85,
          "quality": "high"
        }
      ],
      "verified": true,
      "verified_date": 1880
    }
  }
}
```

### Verification Command

```bash
python scripts/verify_buildings.py \
  --map data/kartverket/raw/1880.png \
  --gcps data/kartverket/gcps/1880.gcp.json \
  --buildings data/buildings_temporal.geojson \
  --output data/buildings_verified.geojson \
  --model models/checkpoints/best_model.pth
```

## Dependencies

**None** - This is a leaf feature in the dependency graph.

**Enables**:
- `feat_temporal_data`: ML extractions provide historical features with dates
- `feat_data_merge`: ML features merged with OSM and SEFRAK
- `feat_source_attribution`: ML source tracking for provenance

## Implementation Reference

**Key Files**:
- `ml/train.py` - Training script with configuration loading
- `ml/predict.py` - Inference script for generating segmentation masks
- `ml/vectorize.py` - Raster-to-vector conversion
- `ml/config.yaml` - Training hyperparameters and paths
- `synthetic/render_aged.py` - Synthetic training data generation
- `synthetic/generate_masks.py` - Ground truth mask creation

**Verification Pipeline**:
- `scripts/verify_buildings.py` - End-to-end verification pipeline
- `scripts/georeference_map.py` - Unified georeferencing (GCP or passthrough)
- `scripts/compare_buildings.py` - Building matching with confidence scoring
- `data/kartverket/gcps/` - GCP files for historical maps

**Model Checkpoints**:
- `models/checkpoints/best_model.pth` - Production model
- `models/checkpoints/last_checkpoint.pth` - Resume training

**Data Directories**:
- `data/synthetic/train/` - Training data (images + masks)
- `data/kartverket/` - Historical map rasters
- `data/ml_extracted/` - Vectorized extraction outputs

## Status

- [x] U-Net architecture implemented with ResNet34 encoder
- [x] Synthetic data generation pipeline (aging effects, masks)
- [x] Training pipeline with Dice loss and augmentation
- [x] Multi-device support (CUDA, MPS, CPU)
- [x] Inference script with tiling for large images
- [x] Vectorization with confidence scoring
- [x] GeoJSON output with ml_src and mlc attributes
- [x] Building verification pipeline with combined confidence
- [x] GCP-based georeferencing support
- [x] Evidence tracking per building
- [ ] Fine-tuning on real Kartverket annotations (in progress)
- [ ] Batch processing for full map sheets
- [ ] Confidence calibration and validation metrics
- [ ] Model versioning and reproducibility tracking
- [ ] Integration tests with temporal data pipeline

## Performance Metrics

**Training** (on synthetic data):
- Dice score: ~0.82 (buildings), ~0.75 (roads), ~0.88 (water)
- Training time: ~4 hours (50 epochs, Apple M2 Max)

**Inference**:
- Throughput: ~0.5s per 256x256 tile (M2 MacBook Pro)
- Memory: ~2GB GPU/unified memory

**Vectorization**:
- Processing: ~10s per 1000 polygons
- Output size: ~500KB GeoJSON per map sheet

## Future Enhancements

1. **Multi-temporal extraction**: Track building changes across multiple historical maps
2. **Uncertainty quantification**: Bayesian neural networks for epistemic uncertainty
3. **Active learning**: Prioritize ambiguous regions for manual annotation
4. **Transfer learning**: Fine-tune on other historical map sources (military, cadastral)
5. **3D reconstruction**: Extract building heights from map shadows/perspective
