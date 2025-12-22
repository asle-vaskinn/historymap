#!/usr/bin/env python3
"""
Inference script for map segmentation model.
Runs prediction on new images and outputs segmentation masks.

Usage:
    python predict.py --checkpoint best_model.pth --input image.png --output mask.png
    python predict.py --checkpoint best_model.pth --input-dir images/ --output-dir masks/
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional, Tuple, List

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from tqdm import tqdm
import segmentation_models_pytorch as smp


def get_device() -> torch.device:
    """Detect and return the best available device (CUDA, MPS, or CPU)."""
    if torch.cuda.is_available():
        device = torch.device("cuda")
        print(f"Using CUDA device: {torch.cuda.get_device_name(0)}")
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
        print("Using Apple MPS (Metal Performance Shaders)")
    else:
        device = torch.device("cpu")
        print("Using CPU")
    return device


def load_model(checkpoint_path: str, device: torch.device, num_classes: int = 5, encoder_name: str = None) -> torch.nn.Module:
    """
    Load trained segmentation model from checkpoint.

    Args:
        checkpoint_path: Path to model checkpoint (.pth file)
        device: Device to load model on
        num_classes: Number of output classes (default: 5 for background, building, road, water, forest)
        encoder_name: Encoder architecture (default: auto-detect from checkpoint)

    Returns:
        Loaded model in eval mode
    """
    if not os.path.exists(checkpoint_path):
        raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")

    # Load checkpoint first to detect config
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)

    # Auto-detect encoder from checkpoint config if not specified
    if encoder_name is None:
        if isinstance(checkpoint, dict) and 'config' in checkpoint:
            encoder_name = checkpoint['config'].get('model', {}).get('encoder', 'resnet34')
            num_classes = checkpoint['config'].get('model', {}).get('classes', num_classes)
            print(f"Auto-detected encoder: {encoder_name}, classes: {num_classes}")
        else:
            encoder_name = "resnet34"  # Default fallback

    # Initialize model architecture (must match training)
    model = smp.Unet(
        encoder_name=encoder_name,
        encoder_weights=None,  # We'll load our trained weights
        in_channels=3,
        classes=num_classes,
    )

    # Handle different checkpoint formats
    if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
        state_dict = checkpoint['model_state_dict']

        # Handle state dicts saved with "model." prefix (e.g., from PyTorch Lightning)
        if any(k.startswith('model.') for k in state_dict.keys()):
            state_dict = {k.replace('model.', ''): v for k, v in state_dict.items()}

        model.load_state_dict(state_dict)
        print(f"Loaded checkpoint from epoch {checkpoint.get('epoch', 'unknown')}")
        if 'val_iou' in checkpoint:
            print(f"Model validation IoU: {checkpoint['val_iou']:.4f}")
    else:
        state_dict = checkpoint
        # Handle state dicts saved with "model." prefix
        if any(k.startswith('model.') for k in state_dict.keys()):
            state_dict = {k.replace('model.', ''): v for k, v in state_dict.items()}
        model.load_state_dict(state_dict)

    model = model.to(device)
    model.eval()

    return model


def load_and_preprocess_image(image_path: str, target_size: Optional[Tuple[int, int]] = None) -> Tuple[torch.Tensor, Tuple[int, int]]:
    """
    Load image and preprocess for inference.

    Args:
        image_path: Path to input image
        target_size: Optional (height, width) to resize to. If None, uses original size.

    Returns:
        Preprocessed image tensor (1, 3, H, W) and original size (H, W)
    """
    # Load image
    image = Image.open(image_path).convert('RGB')
    original_size = image.size[::-1]  # PIL uses (W, H), we need (H, W)

    # Resize if needed
    if target_size is not None:
        image = image.resize((target_size[1], target_size[0]), Image.BILINEAR)

    # Convert to numpy array and normalize to [0, 1]
    image_np = np.array(image).astype(np.float32) / 255.0

    # Convert to tensor (H, W, C) -> (C, H, W)
    image_tensor = torch.from_numpy(image_np).permute(2, 0, 1)

    # Add batch dimension (C, H, W) -> (1, C, H, W)
    image_tensor = image_tensor.unsqueeze(0)

    return image_tensor, original_size


def predict(
    model: torch.nn.Module,
    image_tensor: torch.Tensor,
    device: torch.device,
    confidence_threshold: Optional[float] = None
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Run inference on preprocessed image tensor.

    Args:
        model: Loaded segmentation model
        image_tensor: Preprocessed image tensor (1, 3, H, W)
        device: Device to run inference on
        confidence_threshold: Optional threshold for predictions (0-1)

    Returns:
        Tuple of (predicted_mask, probability_map)
        - predicted_mask: (H, W) array with class indices 0-4
        - probability_map: (H, W, num_classes) array with class probabilities
    """
    image_tensor = image_tensor.to(device)

    with torch.no_grad():
        # Forward pass
        logits = model(image_tensor)  # (1, num_classes, H, W)

        # Convert logits to probabilities
        probabilities = F.softmax(logits, dim=1)  # (1, num_classes, H, W)

        # Get predicted class for each pixel
        predicted_classes = torch.argmax(probabilities, dim=1)  # (1, H, W)

        # Convert to numpy
        predicted_mask = predicted_classes.squeeze(0).cpu().numpy()  # (H, W)
        probability_map = probabilities.squeeze(0).permute(1, 2, 0).cpu().numpy()  # (H, W, num_classes)

        # Apply confidence threshold if specified
        if confidence_threshold is not None:
            max_probs = np.max(probability_map, axis=-1)
            low_confidence_mask = max_probs < confidence_threshold
            predicted_mask[low_confidence_mask] = 0  # Set low confidence pixels to background

    return predicted_mask, probability_map


def save_mask(mask: np.ndarray, output_path: str):
    """
    Save predicted mask as PNG image.

    Args:
        mask: (H, W) array with class indices 0-4
        output_path: Path to save mask
    """
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

    # Save as grayscale PNG (pixel values 0-4)
    mask_image = Image.fromarray(mask.astype(np.uint8), mode='L')
    mask_image.save(output_path)


def save_probability_maps(probability_map: np.ndarray, output_path: str, class_names: List[str]):
    """
    Save probability maps for each class as separate images.

    Args:
        probability_map: (H, W, num_classes) array with class probabilities
        output_path: Base path for output (will add class names)
        class_names: List of class names
    """
    base_path = Path(output_path)
    output_dir = base_path.parent / f"{base_path.stem}_probabilities"
    output_dir.mkdir(parents=True, exist_ok=True)

    for i, class_name in enumerate(class_names):
        prob_map = (probability_map[:, :, i] * 255).astype(np.uint8)
        prob_image = Image.fromarray(prob_map, mode='L')
        prob_image.save(output_dir / f"{class_name}.png")


def process_single_image(
    model: torch.nn.Module,
    image_path: str,
    output_path: str,
    device: torch.device,
    target_size: Optional[Tuple[int, int]] = None,
    confidence_threshold: Optional[float] = None,
    save_probabilities: bool = False,
    class_names: List[str] = None
):
    """Process a single image and save the predicted mask."""
    if class_names is None:
        class_names = ['background', 'building', 'road', 'water', 'forest']

    # Load and preprocess
    image_tensor, original_size = load_and_preprocess_image(image_path, target_size)

    # Predict
    predicted_mask, probability_map = predict(model, image_tensor, device, confidence_threshold)

    # Resize back to original size if needed
    if target_size is not None and target_size != original_size:
        mask_image = Image.fromarray(predicted_mask.astype(np.uint8), mode='L')
        mask_image = mask_image.resize((original_size[1], original_size[0]), Image.NEAREST)
        predicted_mask = np.array(mask_image)

    # Save mask
    save_mask(predicted_mask, output_path)

    # Save probability maps if requested
    if save_probabilities:
        save_probability_maps(probability_map, output_path, class_names)


def process_directory(
    model: torch.nn.Module,
    input_dir: str,
    output_dir: str,
    device: torch.device,
    target_size: Optional[Tuple[int, int]] = None,
    confidence_threshold: Optional[float] = None,
    save_probabilities: bool = False,
    batch_size: int = 1
):
    """Process all images in a directory."""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Find all image files
    image_extensions = ['.png', '.jpg', '.jpeg', '.tif', '.tiff']
    image_files = []
    for ext in image_extensions:
        image_files.extend(input_path.glob(f'*{ext}'))
        image_files.extend(input_path.glob(f'*{ext.upper()}'))

    if not image_files:
        print(f"No image files found in {input_dir}")
        return

    print(f"Found {len(image_files)} images to process")

    # Process with progress bar
    class_names = ['background', 'building', 'road', 'water', 'forest']

    for image_file in tqdm(image_files, desc="Processing images"):
        output_file = output_path / f"{image_file.stem}_mask.png"

        try:
            process_single_image(
                model=model,
                image_path=str(image_file),
                output_path=str(output_file),
                device=device,
                target_size=target_size,
                confidence_threshold=confidence_threshold,
                save_probabilities=save_probabilities,
                class_names=class_names
            )
        except Exception as e:
            print(f"\nError processing {image_file.name}: {e}")
            continue


def main():
    parser = argparse.ArgumentParser(description='Run inference on map images')

    # Model arguments
    parser.add_argument('--checkpoint', required=True, help='Path to model checkpoint (.pth file)')
    parser.add_argument('--num-classes', type=int, default=5, help='Number of output classes (default: 5)')

    # Input/output arguments
    parser.add_argument('--input', help='Path to input image')
    parser.add_argument('--output', help='Path to output mask')
    parser.add_argument('--input-dir', help='Path to input directory')
    parser.add_argument('--output-dir', help='Path to output directory')

    # Processing arguments
    parser.add_argument('--size', type=int, nargs=2, metavar=('HEIGHT', 'WIDTH'),
                       help='Target size for processing (e.g., --size 256 256). If not specified, uses original size.')
    parser.add_argument('--confidence-threshold', type=float, metavar='THRESHOLD',
                       help='Confidence threshold (0-1). Pixels with max probability below this are set to background.')
    parser.add_argument('--save-probabilities', action='store_true',
                       help='Save probability maps for each class')
    parser.add_argument('--batch-size', type=int, default=1,
                       help='Batch size for directory processing (default: 1)')

    # Device arguments
    parser.add_argument('--device', choices=['cuda', 'mps', 'cpu'],
                       help='Device to use (default: auto-detect)')

    args = parser.parse_args()

    # Validate arguments
    if args.input and args.input_dir:
        print("Error: Cannot specify both --input and --input-dir")
        sys.exit(1)

    if not args.input and not args.input_dir:
        print("Error: Must specify either --input or --input-dir")
        sys.exit(1)

    if args.input and not args.output:
        print("Error: --output is required when using --input")
        sys.exit(1)

    if args.input_dir and not args.output_dir:
        print("Error: --output-dir is required when using --input-dir")
        sys.exit(1)

    # Setup device
    if args.device:
        device = torch.device(args.device)
        print(f"Using specified device: {args.device}")
    else:
        device = get_device()

    # Parse target size
    target_size = tuple(args.size) if args.size else None

    # Load model
    print(f"Loading model from {args.checkpoint}...")
    model = load_model(args.checkpoint, device, args.num_classes)

    # Process images
    if args.input:
        print(f"Processing single image: {args.input}")
        process_single_image(
            model=model,
            image_path=args.input,
            output_path=args.output,
            device=device,
            target_size=target_size,
            confidence_threshold=args.confidence_threshold,
            save_probabilities=args.save_probabilities
        )
        print(f"Saved mask to {args.output}")
    else:
        process_directory(
            model=model,
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            device=device,
            target_size=target_size,
            confidence_threshold=args.confidence_threshold,
            save_probabilities=args.save_probabilities,
            batch_size=args.batch_size
        )
        print(f"Saved masks to {args.output_dir}")


if __name__ == '__main__':
    main()
