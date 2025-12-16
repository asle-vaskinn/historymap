# Installation Guide - Phase 3

## Prerequisites

- Python 3.8 or higher
- pip package manager
- (Optional) CUDA-compatible GPU for faster training
- (Optional) Apple Silicon (M1/M2/M3) for MPS acceleration

## Step 1: Install Dependencies

```bash
cd /Users/vaskinn/Development/private/historymap/ml
pip install -r requirements.txt
```

This will install:
- PyTorch and TorchVision (ML framework)
- segmentation-models-pytorch (U-Net implementation)
- opencv-python (for contour detection)
- rasterio, shapely, geojson (for vectorization)
- albumentations (for data augmentation)
- tqdm, PyYAML, scikit-learn, matplotlib (utilities)

## Step 2: Verify Installation

Run the validation script:

```bash
./validate_phase3.sh
```

This will:
1. Check all files exist
2. Verify Python dependencies
3. Test device availability (CUDA/MPS/CPU)
4. Create test images
5. Run inference and vectorization tests

Expected output: All checks pass ✅

## Step 3: Test Scripts

Test predict.py:
```bash
python predict.py --help
```

Test vectorize.py:
```bash
python vectorize.py --help
```

## GPU/Device Setup

### NVIDIA GPU (CUDA)

PyTorch will automatically detect CUDA. Verify with:
```bash
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
```

### Apple Silicon (MPS)

PyTorch will automatically detect MPS. Verify with:
```bash
python -c "import torch; print(f'MPS available: {torch.backends.mps.is_available()}')"
```

### CPU Only

No additional setup needed. PyTorch will use CPU by default.

## Troubleshooting

### Issue: pip install fails for torch

Try installing PyTorch separately first:
```bash
# For CUDA (check pytorch.org for your CUDA version)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# For CPU/MPS
pip install torch torchvision
```

### Issue: opencv-python installation fails

Try:
```bash
pip install opencv-python-headless
```

### Issue: GDAL/rasterio installation fails

On macOS:
```bash
brew install gdal
pip install rasterio
```

On Ubuntu/Debian:
```bash
sudo apt-get install gdal-bin libgdal-dev
pip install rasterio
```

## Next Steps

After successful installation:

1. Run validation: `./validate_phase3.sh`
2. Review documentation: `cat README.md`
3. Try quick start examples: `cat PHASE3_QUICKSTART.md`
4. Train a model: `python train.py --config config.yaml`

## System Requirements

### Minimum
- 8GB RAM
- 10GB free disk space
- CPU: Any modern processor
- OS: macOS, Linux, Windows

### Recommended for Training
- 16GB+ RAM
- NVIDIA GPU with 6GB+ VRAM or Apple Silicon M1/M2/M3
- 50GB+ free disk space (for datasets)
- SSD for faster data loading

### Recommended for Inference
- 8GB RAM
- Any GPU or Apple Silicon
- CPU fallback is acceptable for small batches
