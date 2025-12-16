# Phase 4: Real Data Integration

This directory contains scripts for fine-tuning the model on real historical map annotations and batch extracting features.

## Overview

Phase 4 integrates real historical maps from Kartverket into the ML pipeline:

1. **Fine-tuning**: Take the pretrained model from Phase 3 (trained on synthetic data) and fine-tune it on manually annotated real historical map tiles
2. **Batch Extraction**: Process all historical map tiles with the fine-tuned model to extract building, road, water, and forest features
3. **Vectorization**: Convert raster masks to vector GeoJSON with temporal attributes for the frontend time slider

## Directory Structure

```
data/
├── kartverket/
│   ├── raw/              # Downloaded historical maps from Kartverket
│   ├── georeferenced/    # Georeferenced maps (aligned to modern coordinates)
│   └── tiles/            # Tiles cut from georeferenced maps (256x256 or 512x512)
├── annotations/
│   ├── images/           # Sample tiles to annotate (30-50 recommended)
│   └── masks/            # Manual annotations (class masks)
└── extracted/
    └── trondheim_{era}.geojson  # Final extracted features per era
```

## Scripts

### 1. fine_tune.py

Fine-tunes the pretrained model on real annotated data.

**Features:**
- Load pretrained model from Phase 3
- Load real annotated data from `data/annotations/`
- Fine-tuning with lower learning rate (1e-4 or 1e-5)
- Fewer epochs (10-20)
- More aggressive augmentation
- Optional encoder freezing initially, then unfreezing
- Compare metrics before/after fine-tuning

**Usage:**

```bash
# Basic fine-tuning
python fine_tune.py \
  --pretrained ../models/checkpoints/best_model.pth \
  --annotations ../data/annotations/ \
  --output ../models/checkpoints/finetuned_model.pth \
  --epochs 20 \
  --lr 1e-4

# With encoder freezing (recommended for small datasets)
python fine_tune.py \
  --pretrained ../models/checkpoints/best_model.pth \
  --annotations ../data/annotations/ \
  --output ../models/checkpoints/finetuned_model.pth \
  --epochs 20 \
  --lr 1e-4 \
  --freeze-encoder \
  --unfreeze-at-epoch 5

# Lower learning rate for more careful fine-tuning
python fine_tune.py \
  --pretrained ../models/checkpoints/best_model.pth \
  --annotations ../data/annotations/ \
  --output ../models/checkpoints/finetuned_model.pth \
  --epochs 30 \
  --lr 1e-5
```

**Arguments:**

- `--pretrained`: Path to pretrained model checkpoint from Phase 3 (required)
- `--annotations`: Path to annotations directory with `images/` and `masks/` subdirs (required)
- `--output`: Path to save fine-tuned model checkpoint (required)
- `--epochs`: Number of fine-tuning epochs (default: 20)
- `--lr`: Learning rate (default: 1e-4)
- `--batch-size`: Batch size (default: 8)
- `--freeze-encoder`: Freeze encoder initially (only train decoder)
- `--unfreeze-at-epoch`: Epoch at which to unfreeze encoder if frozen
- `--device`: Device to use: auto, cuda, mps, cpu (default: auto)
- `--num-workers`: Number of data loading workers (default: 4)
- `--grad-clip`: Gradient clipping value (default: 1.0)
- `--early-stopping-patience`: Early stopping patience in epochs (default: 10)

**Output:**

- Fine-tuned model checkpoint saved to specified path
- Training logs in `{output_dir}/fine_tuning_logs/`
- Metrics comparison: pretrained vs fine-tuned on real data

### 2. batch_extract.py

Processes all historical map tiles and extracts features to GeoJSON.

**Features:**
- Load fine-tuned model
- Process all tiles in `data/kartverket/tiles/`
- Run inference with progress bar
- Vectorize each mask to GeoJSON polygons
- Merge all GeoJSON files per era/map series
- Add temporal attributes (`start_date`, `end_date`)
- Output: `data/extracted/trondheim_{era}.geojson`

**Usage:**

```bash
# Basic batch extraction
python batch_extract.py \
  --model ../models/checkpoints/finetuned_model.pth \
  --tiles ../data/kartverket/tiles/ \
  --output ../data/extracted/

# With confidence threshold and simplification
python batch_extract.py \
  --model ../models/checkpoints/finetuned_model.pth \
  --tiles ../data/kartverket/tiles/ \
  --output ../data/extracted/ \
  --confidence-threshold 0.7 \
  --simplify 2.0 \
  --min-area 20.0

# Group by year instead of era
python batch_extract.py \
  --model ../models/checkpoints/finetuned_model.pth \
  --tiles ../data/kartverket/tiles/ \
  --output ../data/extracted/ \
  --group-by year
```

**Arguments:**

- `--model`: Path to fine-tuned model checkpoint (required)
- `--tiles`: Directory containing tile images (required)
- `--output`: Directory for output GeoJSON files (required)
- `--confidence-threshold`: Minimum confidence for predictions 0-1 (optional)
- `--simplify`: Polygon simplification tolerance (default: 1.0)
- `--min-area`: Minimum polygon area threshold (default: 10.0)
- `--group-by`: How to group output files: era, series, year (default: era)
- `--prefix`: Prefix for output filenames (default: trondheim)

**Tile Naming Convention:**

The script expects tiles to follow this naming pattern:
```
{era}_{series}_{year}_{tile_id}.png
```

Example: `1900_cadastral_1905_tile_123.png`

Alternatively, place a `{tile_name}_metadata.json` file next to each tile with:
```json
{
  "era": "1900",
  "series": "cadastral",
  "year": 1905,
  "tile_id": "tile_123",
  "bounds": [10.38, 63.42, 10.42, 63.44]
}
```

**Output:**

- GeoJSON files per era/series: `data/extracted/trondheim_{era}.geojson`
- Extraction statistics: `data/extracted/extraction_stats.json`
- Logs: `data/extracted/logs/batch_extraction.log`

**GeoJSON Feature Properties:**

Each extracted feature includes:
```json
{
  "class": "building",
  "class_id": 1,
  "feature_id": "tile_123_building_0",
  "area": 450.5,
  "source_tile": "1900_cadastral_1905_tile_123.png",
  "era": "1900",
  "series": "cadastral",
  "year": 1905,
  "start_date": 1905,
  "end_date": 1905,
  "color": "#8B4513"
}
```

### 3. validate_phase4.sh

Validation script to check Phase 4 setup.

**Checks:**
- Directory structure
- Phase 4 scripts exist and are executable
- ML module dependencies
- Kartverket data (raw maps, georeferenced, tiles)
- Manual annotations (images and masks)
- Pretrained model from Phase 3
- Python dependencies
- Script functionality (--help works)
- Extraction output

**Usage:**

```bash
./validate_phase4.sh
```

## Workflow

### Step 1: Download Historical Maps

Visit Kartverket's historical map archive and download maps for the Trondheim area:

- **Kartverket**: https://kartkatalog.geonorge.no/
- **Coverage**: Trondheim and surrounding municipalities
- **Formats**: GeoTIFF, JPEG2000, or TIFF
- **Eras**: 1850-present (various map series)

Place downloaded maps in `data/kartverket/raw/`

### Step 2: Georeference Maps

Use GDAL or QGIS to align historical maps to modern coordinate system (EPSG:4326 or EPSG:25833):

```bash
# Example using GDAL (requires ground control points)
gdal_translate -of GTiff \
  -a_srs EPSG:25833 \
  -gcp pixel_x pixel_y geo_x geo_y \
  data/kartverket/raw/map.tif \
  data/kartverket/georeferenced/map_georef.tif
```

Or use QGIS's Georeferencer tool for manual alignment.

Save georeferenced maps to `data/kartverket/georeferenced/`

### Step 3: Generate Tiles

Cut large maps into training-size tiles (256x256 or 512x512):

```bash
# Example using GDAL
gdal_retile.py \
  -ps 512 512 \
  -targetDir data/kartverket/tiles/ \
  data/kartverket/georeferenced/*.tif
```

Name tiles following the convention: `{era}_{series}_{year}_{tile_id}.png`

### Step 4: Manual Annotation

**Recommended: 30-50 tiles**

1. Select diverse tiles:
   - Urban areas (dense buildings, roads)
   - Suburban areas
   - Rural areas
   - Different map eras/styles

2. Use annotation tool:
   - **QGIS**: Create polygon layers, export as raster
   - **Label Studio**: Image segmentation project
   - **Custom tool**: Use the model's predictions as a starting point

3. Annotation classes:
   - **0**: Background (black)
   - **1**: Building (dark gray, value 1)
   - **2**: Road (mid gray, value 2)
   - **3**: Water (light gray, value 3)
   - **4**: Forest (lighter gray, value 4)

4. Save:
   - Original tiles → `data/annotations/images/`
   - Masks (single-channel PNG) → `data/annotations/masks/`

**Tips:**
- Start with buildings (easiest to identify)
- Roads can be traced as thin polygons
- Water bodies are usually clear
- Forests may be hardest on old maps

### Step 5: Fine-tune Model

```bash
python scripts/fine_tune.py \
  --pretrained models/checkpoints/best_model.pth \
  --annotations data/annotations/ \
  --output models/checkpoints/finetuned_model.pth \
  --epochs 20 \
  --lr 1e-4 \
  --freeze-encoder \
  --unfreeze-at-epoch 5
```

**Monitor training:**
- Watch for improvement in validation IoU
- Fine-tuned IoU should be > pretrained IoU on real data
- Target: Building IoU > 0.7, Overall IoU > 0.6

**Expected metrics:**

| Metric | Pretrained | Fine-tuned | Target |
|--------|-----------|------------|--------|
| Building IoU | 0.5-0.7 | 0.7-0.85 | > 0.7 |
| Road IoU | 0.4-0.6 | 0.6-0.8 | > 0.6 |
| Water IoU | 0.7-0.9 | 0.8-0.95 | > 0.8 |
| Overall IoU | 0.6-0.8 | 0.7-0.9 | > 0.7 |

### Step 6: Batch Extract Features

```bash
python scripts/batch_extract.py \
  --model models/checkpoints/finetuned_model.pth \
  --tiles data/kartverket/tiles/ \
  --output data/extracted/ \
  --confidence-threshold 0.7 \
  --simplify 2.0
```

**Processing time:**
- ~0.5-2 seconds per tile (GPU)
- ~5-10 seconds per tile (CPU)
- 1000 tiles: ~15-30 minutes (GPU)

### Step 7: Validate Extraction

Load extracted GeoJSON in QGIS to validate:

```bash
# Open in QGIS
qgis data/extracted/trondheim_1900.geojson
```

**Check:**
1. Features align with underlying map
2. Building outlines are accurate
3. Roads follow the map
4. No excessive noise or artifacts
5. Temporal attributes are correct

**Quality metrics:**
- Manual inspection of 50-100 random features
- Calculate IoU on a held-out test set
- Compare with ground truth annotations

## Troubleshooting

### Low IoU after fine-tuning

**Problem**: Fine-tuned model doesn't improve much over pretrained

**Solutions**:
1. Add more annotations (aim for 50+)
2. Ensure annotations are high quality
3. Use lower learning rate (1e-5)
4. Freeze encoder initially
5. More epochs with early stopping

### Poor extraction quality

**Problem**: Extracted features have artifacts or don't match maps

**Solutions**:
1. Adjust confidence threshold (--confidence-threshold 0.7-0.9)
2. Increase minimum area (--min-area 20-50)
3. Fine-tune more (more epochs)
4. Check georeferencing accuracy
5. Ensure tiles are properly aligned

### Out of memory during fine-tuning

**Problem**: CUDA out of memory error

**Solutions**:
1. Reduce batch size (--batch-size 4 or 2)
2. Use smaller image size in config
3. Use CPU instead (--device cpu)
4. Close other applications

### Slow batch extraction

**Problem**: Extraction takes too long

**Solutions**:
1. Use GPU (CUDA or MPS)
2. Increase batch processing (modify script)
3. Reduce image size
4. Use lower resolution tiles

## Integration with Frontend

Extracted GeoJSON files can be:

1. **Converted to PMTiles** for efficient serving
2. **Uploaded to PostGIS** for dynamic tile generation (Martin)
3. **Served directly** as static GeoJSON files

Features include `start_date` and `end_date` properties for the time slider to filter:

```javascript
// Frontend time slider filtering
const visibleFeatures = features.filter(f => {
  const year = timeSlider.value;
  return f.properties.start_date <= year &&
         (f.properties.end_date === null || f.properties.end_date >= year);
});
```

## Next Steps

After Phase 4 completion, proceed to **Phase 5: Production**:

1. Merge extracted historical features with modern OSM data
2. Generate final PMTiles with all eras
3. Update frontend with historical styling
4. Deploy complete system

## References

- [Kartverket Historical Maps](https://kartkatalog.geonorge.no/)
- [GDAL Documentation](https://gdal.org/)
- [QGIS Georeferencer](https://docs.qgis.org/latest/en/docs/user_manual/working_with_raster/georeferencer.html)
- [GeoJSON Specification](https://geojson.org/)
