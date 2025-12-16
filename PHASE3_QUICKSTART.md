# Phase 3 Quick Start Guide

## Installation

```bash
cd ml/
pip install -r requirements.txt
```

## Validation

```bash
./validate_phase3.sh
```

Expected: All checks pass ✅

## Usage Examples

### 1. Single Image Prediction

```bash
python predict.py \
  --checkpoint ../models/checkpoints/best_model.pth \
  --input ../data/historical/map.png \
  --output ../results/predictions/mask.png
```

### 2. Batch Prediction

```bash
python predict.py \
  --checkpoint ../models/checkpoints/best_model.pth \
  --input-dir ../data/kartverket/tiles/ \
  --output-dir ../results/predictions/masks/
```

### 3. Prediction with Options

```bash
python predict.py \
  --checkpoint ../models/checkpoints/best_model.pth \
  --input image.png \
  --output mask.png \
  --size 512 512 \
  --confidence-threshold 0.7 \
  --save-probabilities
```

### 4. Simple Vectorization

```bash
python vectorize.py \
  --input ../results/predictions/mask.png \
  --output ../results/predictions/features.geojson
```

### 5. Vectorization with Geo-referencing

```bash
python vectorize.py \
  --input mask.png \
  --output features.geojson \
  --bounds "10.38,63.42,10.42,63.44" \
  --simplify 1.0
```

### 6. Batch Vectorization

```bash
python vectorize.py \
  --input-dir ../results/predictions/masks/ \
  --output-dir ../results/predictions/vectors/ \
  --simplify 1.0 \
  --min-area 15.0
```

### 7. Complete Pipeline

```bash
# Step 1: Train (if needed)
python train.py --config config.yaml

# Step 2: Predict
python predict.py \
  --checkpoint ../models/checkpoints/best_model.pth \
  --input-dir ../data/kartverket/tiles/ \
  --output-dir ../results/predictions/masks/

# Step 3: Vectorize
python vectorize.py \
  --input-dir ../results/predictions/masks/ \
  --output-dir ../results/predictions/vectors/ \
  --simplify 1.0

# Step 4: Evaluate
python evaluate.py \
  --checkpoint ../models/checkpoints/best_model.pth \
  --data ../data/synthetic \
  --visualize
```

## Device Selection

Auto-detect (recommended):
```bash
python predict.py --checkpoint model.pth --input image.png --output mask.png
```

Force specific device:
```bash
# GPU
python predict.py ... --device cuda

# Apple Silicon
python predict.py ... --device mps

# CPU
python predict.py ... --device cpu
```

## Class IDs

- 0 = background
- 1 = building
- 2 = road
- 3 = water
- 4 = forest

## Troubleshooting

### Out of Memory
```bash
python predict.py ... --size 256 256
```

### Too Many Polygons
```bash
python vectorize.py ... --min-area 25.0 --simplify 2.0
```

### CUDA Errors
```bash
python predict.py ... --device cpu
```

## Next Steps

1. Run validation script
2. Train model on synthetic data (Phase 2)
3. Test inference on sample images
4. Vectorize predictions
5. Inspect results in QGIS
6. Proceed to Phase 4 (Real data integration)

## Help

```bash
python predict.py --help
python vectorize.py --help
python train.py --help
python evaluate.py --help
```

## File Locations

- Models: `../models/checkpoints/`
- Predictions: `../results/predictions/`
- Logs: `../results/training_logs/`
- Config: `config.yaml`

## Documentation

See `README.md` for detailed documentation.
See `PHASE3_COMPLETION_SUMMARY.md` for full feature list.
