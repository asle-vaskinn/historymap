# Methodology - Trondheim Historical Map

This document explains the technical approach, machine learning pipeline, and data processing methodology used to create the Trondheim Historical Map.

## Overview

The Trondheim Historical Map project uses a multi-phase approach combining modern vector data, synthetic training data generation, machine learning, and historical map processing to create an interactive temporal map visualization.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        COMPLETE PIPELINE                        │
│                                                                 │
│  Modern Data (OSM)                                             │
│         │                                                       │
│         ├─────────▶ Synthetic Data Pipeline                    │
│         │           - Historical style rendering               │
│         │           - Aging effects                            │
│         │           - Ground truth masks                       │
│         │                  │                                    │
│         │                  ▼                                    │
│         │           Training Dataset                           │
│         │                  │                                    │
│         │                  ▼                                    │
│         │           ML Model (U-Net)                           │
│         │           - Training on synthetic data               │
│         │           - Fine-tuning on real annotations          │
│         │                  │                                    │
│         │                  ▼                                    │
│         │           Trained Segmentation Model                 │
│         │                  │                                    │
│         ▼                  ▼                                    │
│  Historical Maps ────▶ Feature Extraction                      │
│  (Kartverket)          - Building detection                    │
│                        - Road detection                        │
│                        - Vectorization                         │
│                             │                                   │
│                             ▼                                   │
│                     Extracted Features                         │
│                             │                                   │
│                             ├──────────┐                        │
│                             ▼          ▼                        │
│                      Modern Data + Historical Data             │
│                             │                                   │
│                             ▼                                   │
│                      PMTiles Generation                        │
│                             │                                   │
│                             ▼                                   │
│                     Interactive Web Map                        │
└─────────────────────────────────────────────────────────────────┘
```

## Phase 1: Infrastructure and Frontend

### Objective
Create a working web application with time-based filtering capabilities.

### Components

**Frontend**
- **Technology**: MapLibre GL JS
- **Features**: Interactive map with time slider
- **Rendering**: Client-side vector tile rendering
- **Filtering**: Dynamic feature filtering based on temporal attributes

**Data Format**
- **PMTiles**: Single-file vector tile archive
- **Attributes**: `start_date`, `end_date` for temporal filtering
- **Source**: OpenStreetMap data for Trondheim region

**Server**
- **Technology**: Nginx (or static file hosting)
- **Configuration**: Optimized for PMTiles delivery with range request support
- **CORS**: Enabled for development and cross-origin access

### Key Decisions
- PMTiles over traditional tile servers for simplicity and zero server-side processing
- MapLibre GL JS for open-source, performant client-side rendering
- Vector tiles over raster for scalability and styling flexibility

## Phase 2: Synthetic Data Pipeline

### Objective
Generate realistic-looking historical map images from modern vector data for ML training.

### The Domain Gap Problem

Training a machine learning model to extract features from historical maps faces a challenge: we have limited labeled historical data. The solution is **domain randomization** through synthetic data generation.

### Synthetic Data Generation Process

#### 1. Historical Style Creation

**Approach**: LLM-assisted MapLibre style generation

Historical maps have distinct cartographic styles depending on:
- Time period (1880s, 1900s, 1920s, etc.)
- Map type (military survey, cadastral, topographic)
- Printing technology (lithography, engraving, modern printing)

**Process**:
1. Research historical map characteristics
2. Generate MapLibre GL style JSON mimicking these characteristics
3. Define color palettes, line weights, symbols for each era
4. Create multiple style variations for diversity

**Styles Created**:
- Military Survey (1880s): Gray-blue tones, heavy line work
- Cadastral Maps (1900s): Black and white, precise building outlines
- Topographic Maps (1920s): Brown contours, green forests, blue water

#### 2. Map Rendering

**Technology**: MapLibre GL Native or static rendering
**Input**: Modern OSM vector data
**Output**: Styled raster image (256×256 or 512×512 pixels)

**Process**:
1. Select a geographic tile area
2. Apply historical style
3. Render to image
4. Ensure reproducibility (same input → same output)

#### 3. Aging Effects

Real historical maps have degradation that synthetic renders lack. We apply:

**Paper Aging**:
- Yellowing (sepia tone shift)
- Color fading (reduced saturation)
- Paper texture overlay (grain, fiber patterns)

**Print Artifacts**:
- Slight blur (old printing techniques)
- Ink spread (bleeding at edges)
- Registration errors (color layer misalignment)

**Damage Simulation**:
- Noise and grain
- Optional: fold lines, stains, tears (light application)

**Implementation**:
- Pillow (PIL) for image manipulation
- Procedural texture generation
- Configurable intensity (0.0 = pristine, 1.0 = heavily aged)

#### 4. Ground Truth Mask Generation

For supervised learning, we need pixel-perfect masks showing what's in each image.

**Classes**:
- 0: Background
- 1: Buildings
- 2: Roads
- 3: Water
- 4: Forest (optional, later phase)

**Process**:
1. Same tile area as image
2. Rasterize vector features by class
3. Generate class-colored mask
4. Ensure exact alignment with rendered image

**Quality Assurance**:
- Visual inspection of image/mask pairs
- Verify class distribution
- Check for alignment errors

### Dataset Characteristics

**Size**: 1,000+ training pairs minimum
**Diversity**:
- Multiple geographic locations (urban, suburban, rural)
- Multiple historical styles (5+ different styles)
- Multiple aging intensities (light to heavy)
- Random augmentations (rotation, flip, brightness)

**Augmentation** (applied during training):
- Horizontal/vertical flips
- Random rotation (±15°)
- Brightness/contrast adjustment
- Color jitter

## Phase 3: Machine Learning Training

### Objective
Train a segmentation model that can identify buildings, roads, and other features in historical map images.

### Model Architecture

**U-Net with ResNet34 Encoder**

```
Input Image (256×256×3 RGB)
        ↓
┌───────────────────┐
│   Encoder         │  ResNet34 backbone
│   (downsampling)  │  - Pretrained on ImageNet
│   64 → 512 ch     │  - Feature extraction
└───────────────────┘
        ↓
┌───────────────────┐
│   Bottleneck      │  Feature processing
└───────────────────┘
        ↓
┌───────────────────┐
│   Decoder         │  U-Net style decoder
│   (upsampling)    │  - Skip connections from encoder
│   512 → 64 ch     │  - Gradual resolution recovery
└───────────────────┘
        ↓
Output Mask (256×256×5)
- 5 channels (one per class)
```

**Why U-Net?**
- Proven architecture for image segmentation
- Skip connections preserve spatial detail
- Works well with limited training data

**Why ResNet34 Encoder?**
- Pretrained weights transfer low-level features (edges, textures)
- Residual connections prevent vanishing gradients
- Good balance of capacity vs. speed

### Training Configuration

**Hyperparameters**:
- **Batch size**: 16
- **Learning rate**: 0.001 (with scheduler)
- **Optimizer**: Adam
- **Epochs**: 50 (with early stopping)
- **Loss function**: Dice loss (better for imbalanced classes)

**Data Split**:
- Training: 80%
- Validation: 10%
- Test: 10%

**Augmentation** (during training):
- Random horizontal flip
- Random vertical flip
- Random rotation (±15°)
- Brightness adjustment (±20%)
- Contrast adjustment (±20%)

**Training Process**:
1. Load pretrained ResNet34 encoder
2. Initialize decoder randomly
3. Train on synthetic data
4. Monitor validation metrics
5. Save best model checkpoint
6. Apply learning rate decay on plateau

### Evaluation Metrics

**Primary Metric: Intersection over Union (IoU)**

IoU = (Area of Overlap) / (Area of Union)

Per-class IoU:
- Building IoU
- Road IoU
- Water IoU
- Mean IoU (average across classes)

**Secondary Metrics**:
- Pixel accuracy
- Precision and recall per class
- F1 score

**Expected Performance on Synthetic Data**:
- Building IoU: 0.60-0.75
- Road IoU: 0.50-0.70
- Water IoU: 0.75-0.90
- Mean IoU: 0.60-0.75

### Transfer to Real Data

Synthetic training provides a foundation, but real historical maps differ. We address this with **fine-tuning**.

## Phase 4: Real Data Integration

### Objective
Apply the model to actual historical maps from Kartverket, with fine-tuning to improve accuracy.

### Data Acquisition

**Source**: Kartverket (Norwegian Mapping Authority)
- Historical map archive at https://kartkatalog.geonorge.no/
- Coverage: Trondheim region, 1850-2000s
- Formats: GeoTIFF, JPEG2000

**Map Types**:
- Amtskart (county maps) 1826-1916
- Topographic maps (various eras)
- Cadastral maps (property boundaries)

**Licensing**:
- Maps >100 years old: Public domain
- Maps <100 years old: CC BY 4.0

### Georeferencing

Historical maps often lack proper coordinate systems or have slight misalignments.

**Process**:
1. Identify control points (landmarks still existing)
2. Use GDAL/rasterio for georeferencing
3. Transform to WGS84 or UTM Zone 33N
4. Output as GeoTIFF with embedded CRS

**Quality Control**:
- Visual inspection against modern satellite imagery
- Check alignment at multiple zoom levels
- Accept some imperfection (historical maps weren't perfectly accurate)

### Tiling

Large historical maps are split into training-size tiles.

**Process**:
1. Cut georeferenced map into 256×256 pixel tiles
2. Maintain geographic coordinates for each tile
3. Skip tiles that are mostly empty or border artifacts
4. Save metadata (tile ID, coordinates, source map, year)

### Manual Annotation

To fine-tune the model, we need some manually labeled real historical map tiles.

**Target**: 30-50 annotated tiles (10-20 hours of work)

**Tool**: QGIS, Label Studio, or custom annotation helper

**Process**:
1. Select diverse tiles (different years, locations, feature densities)
2. Model provides initial prediction (saves time)
3. Human annotator corrects prediction
4. Export as mask matching tile size
5. Verify alignment

**Priority Features**:
1. Buildings (clearest, most valuable)
2. Roads (medium difficulty)
3. Water bodies (usually easy)

### Fine-Tuning

**Process**:
1. Load pretrained model from Phase 3
2. Use much lower learning rate (0.0001)
3. Train on manually annotated real tiles
4. More aggressive augmentation (to generalize from small dataset)
5. Monitor performance on holdout real tiles

**Expected Improvement**:
- Building IoU: 0.75-0.85 (+0.10-0.15)
- Road IoU: 0.65-0.80 (+0.10-0.15)
- Mean IoU: 0.70-0.85

### Batch Processing

Once fine-tuned, process all historical map tiles.

**Pipeline**:
1. Load fine-tuned model
2. For each historical map tile:
   - Run inference
   - Get probability map for each class
   - Apply threshold (e.g., 0.5 confidence)
   - Generate segmentation mask
3. Vectorize masks (raster to vector conversion)
4. Simplify polygons (reduce point count)
5. Add metadata (source map, year, confidence)
6. Merge into GeoJSON per era

**Vectorization**:
- Technology: `rasterio.features.shapes()` or OpenCV contours
- Simplification: Douglas-Peucker algorithm
- Minimum area threshold (filter tiny artifacts)

**Output**:
- `trondheim_1880.geojson`
- `trondheim_1900.geojson`
- `trondheim_1920.geojson`
- etc.

## Phase 5: Production Integration

### Data Merging

Combine modern OSM data with extracted historical features.

**Challenges**:
- Same building exists in multiple eras
- Overlapping features need deduplication
- Inconsistent geometries between sources

**Strategy**:
1. Load all GeoJSON files (modern + historical)
2. Spatial matching of overlapping features
3. Assign date ranges:
   - Historical feature exists 1900-1950 → `start_date: 1900, end_date: 1950`
   - Modern feature with no history → `start_date: null, end_date: null`
4. Handle conflicts (same location, different geometries)
   - Prefer modern data for geometry
   - Keep historical dates
5. Output unified GeoJSON

**Schema**:
```json
{
  "type": "Feature",
  "geometry": {...},
  "properties": {
    "feature_type": "building",
    "start_date": 1900,
    "end_date": 1950,
    "source": "kartverket_1900",
    "confidence": 0.85,
    "osm_id": "...",
    "name": "..."
  }
}
```

### PMTiles Generation

Convert merged GeoJSON to PMTiles for web delivery.

**Tool**: Tippecanoe or Planetiler

**Configuration**:
- Zoom levels: 6-14 (region overview to street detail)
- Simplification: Aggressive at low zoom, minimal at high zoom
- Attributes: Include temporal and metadata fields
- Tile size limit: 500KB per tile

**Command Example**:
```bash
tippecanoe -o trondheim_historical.pmtiles \
  --minimum-zoom=6 \
  --maximum-zoom=14 \
  --drop-densest-as-needed \
  --extend-zooms-if-still-dropping \
  trondheim_merged.geojson
```

### Frontend Updates

Update `frontend/app.js` to show temporal features appropriately.

**Styling**:
- Historical features: Sepia/aged appearance
- Modern features: Contemporary colors
- Opacity based on confidence
- Highlight features on hover with date tooltip

**Time Slider**:
- Smooth transitions when changing year
- Feature fade-in/fade-out animations
- Clear indication of data availability per era

## Accuracy and Limitations

### Model Performance

**Synthetic Data Training**:
- Provides good generalization
- May not capture all map style variations
- Domain gap from synthetic to real

**Fine-Tuned Model**:
- Significantly improved on real historical maps
- Performance varies by map quality, age, and condition

### Expected Accuracy

**High Confidence (>80% accuracy)**:
- Clear buildings in good quality maps
- Major roads
- Large water bodies

**Medium Confidence (60-80% accuracy)**:
- Small buildings
- Minor roads
- Features in degraded maps

**Low Confidence (<60% accuracy)**:
- Very old or damaged maps
- Handwritten labels (not extracted)
- Ambiguous features

### Known Limitations

1. **Temporal Accuracy**:
   - Dates from source map metadata (may be approximate)
   - Building construction/demolition dates may be unknown

2. **Geographic Coverage**:
   - Not all years have available historical maps
   - Some rural areas less documented

3. **Feature Classification**:
   - May misclassify similar-looking features
   - Small features may be missed
   - Complex geometries simplified

4. **Alignment**:
   - Historical maps not perfectly accurate
   - Georeferencing has some error
   - ±5-20m position error typical for old maps

## Validation Approach

### Quantitative Validation
- IoU metrics on annotated test set
- Cross-validation across map eras
- Comparison with modern satellite imagery (for recent maps)

### Qualitative Validation
- Visual inspection of extractions
- Spot-checking against known historical records
- Community feedback and corrections

### Continuous Improvement
- Track reported errors
- Periodic retraining with corrected annotations
- Version control for model checkpoints

## Future Improvements

### Short Term
- More historical map processing
- Additional manual annotations
- Model fine-tuning iterations

### Medium Term
- Forest/vegetation extraction
- Railway detection improvements
- Street name extraction (OCR)

### Long Term
- 3D building reconstruction from shadows
- Height estimation from map symbols
- Historical photo integration
- Crowd-sourced correction interface

## Technical Stack Summary

**Frontend**:
- MapLibre GL JS 3.x
- Vanilla JavaScript
- CSS3

**Data Processing**:
- Python 3.11
- GDAL/rasterio (georeferencing)
- Pillow (image processing)
- NumPy, Pandas

**Machine Learning**:
- PyTorch 2.x
- segmentation_models_pytorch
- Albumentations (augmentation)

**Tile Generation**:
- Tippecanoe or Planetiler
- PMTiles format

**Deployment**:
- Docker + Nginx
- GitHub Pages (static hosting)
- Cloudflare R2 (tile storage)

## References

### Academic Papers
- U-Net: Convolutional Networks for Biomedical Image Segmentation (Ronneberger et al., 2015)
- Deep Residual Learning for Image Recognition (He et al., 2016)
- Sim-to-Real Transfer in Deep Reinforcement Learning (domain randomization concepts)

### Tools and Libraries
- MapLibre GL JS: https://maplibre.org/
- PMTiles: https://protomaps.com/docs/pmtiles
- segmentation_models_pytorch: https://github.com/qubvel/segmentation_models.pytorch
- Tippecanoe: https://github.com/felt/tippecanoe

### Data Sources
- OpenStreetMap: https://www.openstreetmap.org/
- Kartverket: https://www.kartverket.no/
- Geonorge (map catalog): https://kartkatalog.geonorge.no/

---

**Document Version**: 1.0
**Last Updated**: 2025-12-16

For questions about methodology, please refer to the project repository or contact the maintainers.
