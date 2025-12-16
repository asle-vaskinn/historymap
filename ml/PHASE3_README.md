# Phase 3: ML Training - Complete Implementation

This directory contains the complete implementation of Phase 3 of the Trondheim Historical Map project, including training loop, evaluation scripts, and all required infrastructure.

## Overview

Phase 3 provides a complete PyTorch-based training pipeline for semantic segmentation of historical maps. The system uses U-Net architecture with pretrained encoders (ResNet34 by default) to segment maps into 5 classes: background, building, road, water, and forest.

## File Structure

```
ml/
├── PHASE3_README.md          # This file
├── README.md                  # General ML pipeline documentation
├── requirements.txt           # Python dependencies
│
├── config.yaml                # Training configuration (COMPLETE)
├── losses.py                  # Custom loss functions (COMPLETE)
├── dataset.py                 # PyTorch Dataset class (COMPLETE)
├── model.py                   # U-Net model architecture (COMPLETE)
├── train.py                   # Training script (COMPLETE)
├── evaluate.py                # Evaluation script (COMPLETE)
│
├── predict.py                 # Inference on new images
├── vectorize.py               # Convert masks to GeoJSON
├── utils.py                   # Utility functions
└── validate_phase3.sh         # Validation script
```

## Features Implemented

### 1. Training Script (train.py)

**All Required Features:**
- ✅ Load config from YAML file
- ✅ Mixed precision training (torch.cuda.amp)
- ✅ Learning rate scheduler (ReduceLROnPlateau)
- ✅ Early stopping (patience configurable)
- ✅ Save best model checkpoint by validation IoU
- ✅ Progress bar with current metrics (tqdm)
- ✅ Logging to console and file
- ✅ Resume from checkpoint support

**CLI Usage:**
```bash
python train.py --config config.yaml
python train.py --config config.yaml --resume checkpoint.pth
```

### 2. Evaluation Script (evaluate.py)

**All Required Features:**
- ✅ IoU (Intersection over Union) per class
- ✅ Mean IoU across classes
- ✅ Overall pixel accuracy
- ✅ Confusion matrix generation
- ✅ Visual comparison: input → prediction → ground truth
- ✅ Save evaluation report

**CLI Usage:**
```bash
python evaluate.py --checkpoint best_model.pth --data ../data/synthetic
python evaluate.py --checkpoint best_model.pth --data ../data/synthetic --visualize
```

### 3. Configuration File (config.yaml)

**Complete configuration includes:**
- Model settings (encoder, pretrained weights, classes)
- Training hyperparameters (epochs, batch size, learning rate, optimizer)
- Loss function selection (dice, ce, focal, combined)
- Learning rate scheduler settings
- Early stopping configuration
- Mixed precision training toggle
- Gradient clipping
- Data splits and augmentation
- Paths for data, checkpoints, and logs
- Logging configuration
- Metrics to compute
- Class names

### 4. Custom Loss Functions (losses.py)

**Implemented losses:**
- **Dice Loss**: Good for imbalanced classes, focuses on overlap
- **Focal Loss**: Reduces weight of easy examples, focuses on hard negatives
- **Combined Loss**: Dice + Cross Entropy for balanced training
- **Factory function**: `get_loss_function()` for easy instantiation

## Installation

1. Install dependencies:
```bash
cd ml
pip install -r requirements.txt
```

2. Verify installation:
```bash
./validate_phase3.sh
```

## Quick Start

### 1. Prepare Your Data

The training pipeline supports two directory structures:

**Structure A: Flat (images and masks together)**
```
data/synthetic/
├── images/
│   ├── img_001.png
│   ├── img_002.png
│   └── ...
└── masks/
    ├── img_001.png
    ├── img_002.png
    └── ...
```

**Structure B: Pre-split (train/val/test)**
```
data/synthetic/
├── train/
│   ├── images/
│   └── masks/
├── val/
│   ├── images/
│   └── masks/
└── test/
    ├── images/
    └── masks/
```

The training script automatically detects which structure you're using.

### 2. Configure Training

Edit `config.yaml` to adjust:
- Model architecture (`encoder: resnet34`)
- Training parameters (`batch_size`, `learning_rate`, etc.)
- Data paths (`data_dir: ../data/synthetic`)
- Loss function (`loss: dice`)

### 3. Start Training

```bash
# Train from scratch
python train.py --config config.yaml

# Resume from checkpoint
python train.py --config config.yaml --resume ../models/checkpoints/last_checkpoint.pth
```

### 4. Monitor Training

During training, you'll see:
- Real-time progress bars (tqdm)
- Loss and metrics for each epoch
- Automatic learning rate adjustments
- Best model checkpoints saved

Logs are saved to: `../results/training_logs/training.log`

### 5. Evaluate Model

```bash
# Evaluate on test set
python evaluate.py \
    --checkpoint ../models/checkpoints/best_model.pth \
    --data ../data/synthetic \
    --split test

# With visualizations
python evaluate.py \
    --checkpoint ../models/checkpoints/best_model.pth \
    --data ../data/synthetic \
    --split test \
    --visualize \
    --num_vis 10
```

## Configuration Options

### Model Settings

```yaml
model:
  encoder: resnet34          # resnet18, resnet34, resnet50, efficientnet-b0
  pretrained: true           # Use ImageNet pretrained weights
  classes: 5                 # Number of output classes
```

### Training Settings

```yaml
training:
  epochs: 50                 # Maximum number of epochs
  batch_size: 16             # Batch size (adjust based on GPU memory)
  learning_rate: 0.001       # Initial learning rate
  optimizer: adam            # adam, sgd, adamw
  loss: dice                 # dice, ce, focal, combined
  mixed_precision: true      # Faster training on modern GPUs
  grad_clip: 1.0             # Gradient clipping value
```

### Data Settings

```yaml
data:
  train_split: 0.8           # 80% for training
  val_split: 0.1             # 10% for validation
  test_split: 0.1            # 10% for testing
  image_size: 512            # Training image size

  augmentation:
    enabled: true
    horizontal_flip: 0.5     # 50% probability
    vertical_flip: 0.5
    rotation: 15             # ±15 degrees
    brightness: 0.2
    contrast: 0.2
```

## Output

### Checkpoints

Saved to: `../models/checkpoints/`

- `best_model.pth` - Best model by validation IoU
- `last_checkpoint.pth` - Most recent checkpoint
- `checkpoint_epoch_N.pth` - Periodic checkpoints

Each checkpoint contains:
- Model weights
- Optimizer state
- Scheduler state
- Training epoch
- Best metric value
- Full configuration

### Training Logs

Saved to: `../results/training_logs/`

- `training.log` - Detailed training log with all metrics

### Evaluation Results

Saved to: `../results/evaluation/`

- `evaluation_report_{split}.json` - JSON report with all metrics
- `confusion_matrix_{split}.png` - Confusion matrix visualization
- `visualizations/predictions.png` - Sample predictions

## Expected Performance

Based on Phase 3 project plan:

| Metric | Synthetic Only | After Fine-tuning |
|--------|---------------|-------------------|
| Building IoU | 0.5-0.7 | 0.7-0.85 |
| Road IoU | 0.4-0.6 | 0.6-0.8 |
| Water IoU | 0.7-0.9 | 0.8-0.95 |
| Overall Accuracy | 0.8-0.9 | 0.85-0.95 |

## Device Support

The training pipeline automatically detects and uses:
- **CUDA** (NVIDIA GPUs) - Full mixed precision support
- **MPS** (Apple Silicon M1/M2/M3) - Native acceleration
- **CPU** - Fallback (slower but works)

Check your device:
```bash
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}, MPS: {torch.backends.mps.is_available() if hasattr(torch.backends, \"mps\") else False}')"
```

## Troubleshooting

### Out of Memory

Reduce batch size in `config.yaml`:
```yaml
training:
  batch_size: 8  # or 4
```

### Training Too Slow

- Enable mixed precision (if not already):
  ```yaml
  training:
    mixed_precision: true
  ```
- Reduce image size:
  ```yaml
  data:
    image_size: 256
  ```
- Use fewer data workers:
  ```yaml
  data:
    num_workers: 2
  ```

### Loss Not Decreasing

- Try different loss function:
  ```yaml
  training:
    loss: combined  # instead of dice
  ```
- Adjust learning rate:
  ```yaml
  training:
    learning_rate: 0.0001  # lower
  ```
- Check data quality and class distribution

### Model Overfitting

- Enable more augmentation
- Reduce model capacity (use resnet18 instead of resnet34)
- Increase early stopping patience

## Advanced Usage

### Custom Loss Weights

For combined loss, you can adjust weights in code:

```python
from losses import CombinedLoss

criterion = CombinedLoss(dice_weight=0.6, ce_weight=0.4)
```

### Class Weights for Imbalance

Add to `config.yaml`:
```yaml
data:
  class_weights: [1.0, 2.0, 1.5, 1.0, 1.0]  # [bg, building, road, water, forest]
```

### Different Architectures

Edit `model.py` to use:
- `UNetPlusPlus` - Nested U-Net with better skip connections
- `FPN` - Feature Pyramid Network for multi-scale features

## Next Steps

After training:

1. **Evaluate Results**
   ```bash
   python evaluate.py --checkpoint best_model.pth --data ../data/synthetic --visualize
   ```

2. **Test on Real Historical Map**
   ```bash
   python predict.py --checkpoint best_model.pth --input historical_map.png --output prediction.png
   ```

3. **Decision Point** (from project plan):
   - If IoU > 0.5 on real map → Proceed to Phase 4 (fine-tuning)
   - If IoU < 0.3 on real map → Improve synthetic styles or increase manual annotation

4. **Vectorize Results**
   ```bash
   python vectorize.py --input prediction.png --output features.geojson
   ```

5. **Proceed to Phase 4** - Fine-tuning on real Kartverket data

## References

- Project Plan: `/HISTORICAL_MAP_PROJECT_PLAN.md`
- Model Architecture: `segmentation_models_pytorch` library
- Loss Functions: Custom implementations in `losses.py`
- Dataset: Custom PyTorch Dataset in `dataset.py`

## Support

For issues or questions:
1. Check this README
2. Review training logs in `../results/training_logs/`
3. Consult the main project plan
4. Review the validation script output

## Status

**Phase 3: COMPLETE** ✅

All required components implemented and ready for training:
- ✅ Training loop with all features
- ✅ Evaluation metrics and visualization
- ✅ Configuration system
- ✅ Custom loss functions
- ✅ Model architecture
- ✅ Dataset handling
- ✅ Checkpoint management
- ✅ Logging and monitoring
- ✅ Device compatibility (CUDA/MPS/CPU)
