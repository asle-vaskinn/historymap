# Start Phase 3: ML Training Pipeline

Launch parallel workers to build the ML training system.

## Prerequisites
Phase 2 must be complete. Verify: `ls data/synthetic/images/ | head -5`

## Overview  
Phase 3 trains a U-Net segmentation model on synthetic data.

## Parallel Work Streams

Spawn **3 parallel agents**:

### Agent 1: Dataset & Model Architecture
```
Create PyTorch dataset and model.
- ml/dataset.py - load image/mask pairs, augmentations, splits
- ml/model.py - U-Net with ResNet34 encoder (segmentation_models_pytorch)
- Handle: CUDA, Apple MPS, CPU fallback
- 5 output classes
```

### Agent 2: Training Loop & Evaluation
```
Create training and evaluation scripts.
- ml/train.py - mixed precision, scheduler, early stopping, checkpoints
- ml/evaluate.py - IoU per class, accuracy, confusion matrix, visualizations
- ml/config.yaml - hyperparameters
- Support resume from checkpoint
```

### Agent 3: Inference & Vectorization
```
Create inference and post-processing.
- ml/predict.py - run model on images, output masks
- ml/vectorize.py - convert raster masks to GeoJSON polygons
- Polygon simplification
- Batch processing support
```

## Coordination
After agents complete:
1. Run training on synthetic data (will take time)
2. Evaluate on held-out test set
3. Test inference on a sample image
4. Verify vectorization produces valid GeoJSON

## Decision Point
After training, test on ONE real historical map tile.
- IoU > 0.5 → Proceed to Phase 4
- IoU < 0.3 → Improve synthetic styles and retrain
