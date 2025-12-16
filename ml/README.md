# Phase 3: ML Training and Inference

This directory contains scripts for training segmentation models, running inference on historical maps, and vectorizing the results.

## Directory Structure

```
ml/
├── README.md                 # This file
├── requirements.txt          # Python dependencies
├── predict.py               # Inference script
├── vectorize.py             # Raster to vector conversion
├── validate_phase3.sh       # Validation script
├── dataset.py               # TODO: PyTorch Dataset class
├── model.py                 # TODO: Model architecture
├── train.py                 # TODO: Training loop
├── evaluate.py              # TODO: Evaluation metrics
└── config.yaml              # TODO: Training configuration
```

## Installation

Install dependencies:

```bash
pip install -r requirements.txt
```

This will install:
- PyTorch and TorchVision
- segmentation-models-pytorch (U-Net implementation)
- OpenCV for contour detection
- Shapely and GeoJSON for vectorization
- And other supporting libraries

## GPU/Device Support

The scripts automatically detect and use the best available device:
- **CUDA** (NVIDIA GPUs)
- **MPS** (Apple Silicon M1/M2/M3)
- **CPU** (fallback)

Check device availability:
```bash
python3 -c "import torch; print(f'CUDA: {torch.cuda.is_available()}, MPS: {torch.backends.mps.is_available() if hasattr(torch.backends, \"mps\") else False}')"
```

## Validation

Run the validation script to verify everything is working:

```bash
./validate_phase3.sh
```

This will:
- Check directory structure
- Verify all required files exist
- Check Python dependencies
- Test device availability
- Test model architecture
- Create test images and masks
- Test vectorization

## Usage

### 1. Prediction (Inference)

Run inference on a single image:

```bash
python predict.py \
    --checkpoint models/checkpoints/best_model.pth \
    --input data/historical/map_image.png \
    --output results/predictions/mask.png
```

Process a directory of images:

```bash
python predict.py \
    --checkpoint models/checkpoints/best_model.pth \
    --input-dir data/historical/images/ \
    --output-dir results/predictions/masks/
```

Additional options:

```bash
# Resize images to specific size (e.g., 256x256)
python predict.py --checkpoint model.pth --input image.png --output mask.png --size 256 256

# Apply confidence threshold
python predict.py --checkpoint model.pth --input image.png --output mask.png --confidence-threshold 0.7

# Save probability maps for each class
python predict.py --checkpoint model.pth --input image.png --output mask.png --save-probabilities

# Force specific device
python predict.py --checkpoint model.pth --input image.png --output mask.png --device cuda
```

### 2. Vectorization

Convert a predicted mask to GeoJSON:

```bash
python vectorize.py \
    --input results/predictions/mask.png \
    --output results/predictions/features.geojson
```

With geo-referencing (if you have coordinate bounds):

```bash
python vectorize.py \
    --input mask.png \
    --output features.geojson \
    --bounds "10.38,63.42,10.42,63.44"
```

Process a directory:

```bash
python vectorize.py \
    --input-dir results/predictions/masks/ \
    --output-dir results/predictions/vectors/ \
    --simplify 1.0
```

Additional options:

```bash
# Control polygon simplification (0 = no simplification, higher = more aggressive)
python vectorize.py --input mask.png --output features.geojson --simplify 2.0

# Set minimum polygon area threshold (smaller polygons are discarded)
python vectorize.py --input mask.png --output features.geojson --min-area 20.0

# Disable merging of adjacent polygons
python vectorize.py --input mask.png --output features.geojson --no-merge
```

### 3. Complete Pipeline Example

```bash
# 1. Run inference
python predict.py \
    --checkpoint models/checkpoints/best_model.pth \
    --input-dir data/kartverket/tiles/ \
    --output-dir results/predictions/masks/

# 2. Vectorize results
python vectorize.py \
    --input-dir results/predictions/masks/ \
    --output-dir results/predictions/vectors/ \
    --simplify 1.0 \
    --min-area 15.0

# 3. Merge GeoJSON files (manual or scripted)
# Use scripts/merge_geojson.py or similar
```

## Output Format

### Predicted Masks

Masks are saved as grayscale PNG images with pixel values representing class IDs:
- `0` = background
- `1` = building
- `2` = road
- `3` = water
- `4` = forest

### GeoJSON Features

Each feature in the output GeoJSON has properties:

```json
{
  "type": "Feature",
  "geometry": {
    "type": "Polygon",
    "coordinates": [...]
  },
  "properties": {
    "class": "building",
    "class_id": 1,
    "feature_id": "building_0",
    "area": 1234.5,
    "color": "#8B4513"
  }
}
```

The FeatureCollection also includes metadata:

```json
{
  "type": "FeatureCollection",
  "features": [...],
  "metadata": {
    "source": "mask.png",
    "bounds": [10.38, 63.42, 10.42, 63.44],
    "feature_count": 150,
    "class_counts": {
      "building": 45,
      "road": 12,
      "water": 8,
      "forest": 85
    }
  }
}
```

## Class Definitions

| Class ID | Name       | Color   | Description              |
|----------|------------|---------|--------------------------|
| 0        | background | -       | Not a feature            |
| 1        | building   | #8B4513 | Buildings and structures |
| 2        | road       | #696969 | Roads and paths          |
| 3        | water      | #4169E1 | Rivers, lakes, sea       |
| 4        | forest     | #228B22 | Forested areas           |

## Troubleshooting

### Issue: Out of memory during inference

Solution: Process smaller images or reduce batch size:
```bash
python predict.py ... --size 256 256
```

### Issue: Polygons too complex

Solution: Increase simplification tolerance:
```bash
python vectorize.py ... --simplify 2.0
```

### Issue: Too many small polygons

Solution: Increase minimum area threshold:
```bash
python vectorize.py ... --min-area 25.0
```

### Issue: CUDA out of memory

Solution: Use CPU instead:
```bash
python predict.py ... --device cpu
```

## Next Steps

After creating predictions and vectors:

1. **Validate results** - Visually inspect in QGIS or similar
2. **Fine-tune model** - If needed, annotate more data and retrain
3. **Merge with other data** - Combine with OSM or other sources
4. **Add temporal attributes** - Add start_date/end_date based on map era
5. **Generate tiles** - Create vector tiles for web display

## TODO: Training Scripts

The following scripts still need to be implemented:

- `dataset.py` - PyTorch Dataset class for loading image/mask pairs
- `model.py` - Model architecture and utilities
- `train.py` - Training loop with checkpointing
- `evaluate.py` - Evaluation metrics and visualization
- `config.yaml` - Training hyperparameters

See Phase 3 of HISTORICAL_MAP_PROJECT_PLAN.md for details.

## References

- [segmentation-models-pytorch](https://github.com/qubvel/segmentation_models.pytorch)
- [PyTorch Documentation](https://pytorch.org/docs/)
- [Shapely Documentation](https://shapely.readthedocs.io/)
- [OpenCV Contours](https://docs.opencv.org/4.x/d4/d73/tutorial_py_contours_begin.html)
