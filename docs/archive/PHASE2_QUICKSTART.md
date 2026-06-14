# Phase 2 Quick Start Guide

## Installation

```bash
cd /Users/vaskinn/Development/private/historymap/synthetic
pip install -r requirements.txt
```

## Validation

```bash
# Run validation (generates 10 test samples)
./validate_phase2.sh
```

## Generate Dataset

```bash
# Basic: 1000 samples in Trondheim area
python generate_dataset.py --count 1000 --output ../data/synthetic

# Advanced: Custom parameters
python generate_dataset.py \
  --count 1000 \
  --bbox 10.38,63.42,10.42,63.44 \
  --zoom 15 \
  --styles military_1880 cadastral_1900 topographic_1920 \
  --aging-min 0.4 \
  --aging-max 0.8 \
  --seed 42 \
  --output ../data/synthetic
```

## Files Created

- **`create_masks.py`** - Generate segmentation masks
- **`generate_dataset.py`** - Main dataset pipeline
- **`validate_phase2.sh`** - Validation script
- **`PHASE2_README.md`** - Full documentation

## Output Structure

```
data/synthetic/
├── images/           # Aged historical map images
├── masks/            # Segmentation masks (5 classes)
└── metadata.json     # Sample metadata
```

## Classes

- 0: background
- 1: building
- 2: road
- 3: water
- 4: forest/vegetation

## Next Steps

1. Run `./validate_phase2.sh`
2. Review test samples
3. Generate full dataset
4. Proceed to Phase 3 (ML Training)

## Documentation

- Full guide: `synthetic/PHASE2_README.md`
- Completion summary: `PHASE2_COMPLETION_SUMMARY.md`
- Project plan: `HISTORICAL_MAP_PROJECT_PLAN.md`
