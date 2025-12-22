#!/usr/bin/env python3
"""
Extract features from a historical map image using the trained ML model.

This script:
1. Tiles the input image into ML-compatible chunks
2. Runs segmentation on each tile
3. Stitches predictions back together
4. Optionally outputs a colorized visualization

Usage:
    python extract_from_map.py --input map.jpg --checkpoint best_model.pth --output predictions/
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Tuple, Optional

import numpy as np
from PIL import Image
import torch
import torch.nn.functional as F
from tqdm import tqdm

# Add ml directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'ml'))

try:
    import segmentation_models_pytorch as smp
except ImportError:
    print("ERROR: segmentation_models_pytorch required. Install with: pip install segmentation-models-pytorch")
    sys.exit(1)

from model import UNet, get_model


# Class colors for visualization (RGB)
CLASS_COLORS = {
    0: (240, 235, 224),  # background - light tan
    1: (212, 163, 115),  # building - brown/tan
    2: (139, 119, 101),  # road - gray-brown
    3: (74, 144, 226),   # water - blue
    4: (76, 153, 0),     # forest - green
}

CLASS_NAMES = ['background', 'building', 'road', 'water', 'forest']


def get_device() -> torch.device:
    """Detect best available device."""
    if torch.cuda.is_available():
        device = torch.device("cuda")
        print(f"Using CUDA: {torch.cuda.get_device_name(0)}")
    elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
        device = torch.device("mps")
        print("Using Apple MPS")
    else:
        device = torch.device("cpu")
        print("Using CPU")
    return device


def load_model(checkpoint_path: str, device: torch.device, num_classes: int = 5) -> torch.nn.Module:
    """Load trained segmentation model."""
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)

    # Get encoder from checkpoint config if available
    encoder = "resnet34"  # default
    if isinstance(checkpoint, dict) and 'config' in checkpoint:
        config = checkpoint['config']
        if isinstance(config, dict) and 'model' in config:
            encoder = config['model'].get('encoder', encoder)
        elif isinstance(config, dict) and 'encoder' in config:
            encoder = config.get('encoder', encoder)
    print(f"Using encoder: {encoder}")

    # Use the same UNet wrapper class that was used during training
    model = UNet(
        encoder=encoder,
        encoder_weights=None,  # We'll load our trained weights
        classes=num_classes,
    )

    if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
        model.load_state_dict(checkpoint['model_state_dict'])
        print(f"Loaded checkpoint from epoch {checkpoint.get('epoch', 'unknown')}")
        if 'best_metric' in checkpoint:
            print(f"Model best IoU: {checkpoint['best_metric']:.4f}")
    else:
        model.load_state_dict(checkpoint)

    model = model.to(device)
    model.eval()
    return model


def tile_image(image: np.ndarray, tile_size: int = 512, overlap: int = 64) -> Tuple[list, list, Tuple[int, int]]:
    """
    Tile an image into overlapping chunks.

    Returns:
        tiles: List of tile arrays
        positions: List of (x, y) positions for each tile
        padded_size: Size of padded image (h, w)
    """
    h, w = image.shape[:2]
    step = tile_size - overlap

    # Calculate padded size
    pad_h = ((h - overlap) // step + 1) * step + overlap
    pad_w = ((w - overlap) // step + 1) * step + overlap

    # Pad image
    if len(image.shape) == 3:
        padded = np.zeros((pad_h, pad_w, image.shape[2]), dtype=image.dtype)
    else:
        padded = np.zeros((pad_h, pad_w), dtype=image.dtype)
    padded[:h, :w] = image

    tiles = []
    positions = []

    for y in range(0, pad_h - overlap, step):
        for x in range(0, pad_w - overlap, step):
            tile = padded[y:y+tile_size, x:x+tile_size]
            tiles.append(tile)
            positions.append((x, y))

    return tiles, positions, (pad_h, pad_w)


def stitch_predictions(predictions: list, positions: list, padded_size: Tuple[int, int],
                       original_size: Tuple[int, int], tile_size: int = 512, overlap: int = 64) -> np.ndarray:
    """
    Stitch tile predictions back together using weighted blending in overlap regions.
    """
    h, w = padded_size
    orig_h, orig_w = original_size

    # Create output array and weight accumulator
    output = np.zeros((h, w), dtype=np.float32)
    weights = np.zeros((h, w), dtype=np.float32)

    # Create blending weight mask (linear ramp at edges)
    weight_mask = np.ones((tile_size, tile_size), dtype=np.float32)
    ramp = np.linspace(0, 1, overlap)

    # Apply ramp to edges
    for i in range(overlap):
        weight_mask[i, :] *= ramp[i]
        weight_mask[-(i+1), :] *= ramp[i]
        weight_mask[:, i] *= ramp[i]
        weight_mask[:, -(i+1)] *= ramp[i]

    # Accumulate predictions
    for pred, (x, y) in zip(predictions, positions):
        output[y:y+tile_size, x:x+tile_size] += pred * weight_mask
        weights[y:y+tile_size, x:x+tile_size] += weight_mask

    # Normalize by weights
    output = np.divide(output, weights, where=weights > 0)

    # Crop to original size and convert to int
    return output[:orig_h, :orig_w].astype(np.uint8)


def predict_tile(model: torch.nn.Module, tile: np.ndarray, device: torch.device) -> np.ndarray:
    """Run prediction on a single tile."""
    # Normalize to [0, 1]
    tile_float = tile.astype(np.float32) / 255.0

    # Convert to tensor (H, W, C) -> (1, C, H, W)
    tile_tensor = torch.from_numpy(tile_float).permute(2, 0, 1).unsqueeze(0)
    tile_tensor = tile_tensor.to(device)

    with torch.no_grad():
        logits = model(tile_tensor)
        pred = torch.argmax(logits, dim=1).squeeze(0)

    return pred.cpu().numpy().astype(np.uint8)


def colorize_mask(mask: np.ndarray) -> np.ndarray:
    """Convert class mask to RGB visualization."""
    h, w = mask.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)

    for class_id, color in CLASS_COLORS.items():
        rgb[mask == class_id] = color

    return rgb


def main():
    parser = argparse.ArgumentParser(description='Extract features from historical map')
    parser.add_argument('--input', '-i', required=True, help='Input map image')
    parser.add_argument('--checkpoint', '-c', required=True, help='Model checkpoint path')
    parser.add_argument('--output', '-o', required=True, help='Output directory')
    parser.add_argument('--tile-size', type=int, default=512, help='Tile size (default: 512)')
    parser.add_argument('--overlap', type=int, default=64, help='Tile overlap (default: 64)')
    parser.add_argument('--num-classes', type=int, default=5, help='Number of classes (default: 5)')
    args = parser.parse_args()

    # Setup
    device = get_device()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load model
    print(f"Loading model from {args.checkpoint}...")
    model = load_model(args.checkpoint, device, args.num_classes)

    # Load image
    print(f"Loading image from {args.input}...")
    image = np.array(Image.open(args.input).convert('RGB'))
    print(f"Image size: {image.shape[1]}x{image.shape[0]}")

    # Tile image
    print(f"Tiling image (tile_size={args.tile_size}, overlap={args.overlap})...")
    tiles, positions, padded_size = tile_image(image, args.tile_size, args.overlap)
    print(f"Created {len(tiles)} tiles")

    # Run predictions
    print("Running predictions...")
    predictions = []
    for tile in tqdm(tiles, desc="Predicting"):
        pred = predict_tile(model, tile, device)
        predictions.append(pred.astype(np.float32))  # Float for blending

    # Stitch predictions
    print("Stitching predictions...")
    original_size = (image.shape[0], image.shape[1])
    mask = stitch_predictions(predictions, positions, padded_size, original_size,
                              args.tile_size, args.overlap)

    # Save outputs
    input_name = Path(args.input).stem

    # Raw mask (grayscale, values 0-4)
    mask_path = output_dir / f"{input_name}_mask.png"
    Image.fromarray(mask, mode='L').save(mask_path)
    print(f"Saved mask to {mask_path}")

    # Colorized visualization
    color_path = output_dir / f"{input_name}_colorized.png"
    colorized = colorize_mask(mask)
    Image.fromarray(colorized).save(color_path)
    print(f"Saved colorized mask to {color_path}")

    # Overlay on original
    overlay_path = output_dir / f"{input_name}_overlay.png"
    overlay = (image * 0.5 + colorized * 0.5).astype(np.uint8)
    Image.fromarray(overlay).save(overlay_path)
    print(f"Saved overlay to {overlay_path}")

    # Print class statistics
    print("\nClass distribution:")
    unique, counts = np.unique(mask, return_counts=True)
    total = mask.size
    for class_id, count in zip(unique, counts):
        pct = count / total * 100
        print(f"  {CLASS_NAMES[class_id]:12s}: {pct:5.1f}% ({count:,} pixels)")

    print("\nDone!")


if __name__ == '__main__':
    main()
