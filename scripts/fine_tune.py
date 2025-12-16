#!/usr/bin/env python3
"""
Fine-tuning script for historical map segmentation model.

Takes a pretrained model from Phase 3 (trained on synthetic data) and fine-tunes
it on real annotated historical map data with lower learning rate and more aggressive
augmentation.

Features:
- Load pretrained model checkpoint
- Load real annotated data from data/annotations/
- Fine-tuning with lower learning rate (1e-4 or 1e-5)
- Fewer epochs (10-20)
- More aggressive augmentation
- Optional encoder freezing initially, then unfreezing
- Compare metrics before/after fine-tuning

Usage:
    python fine_tune.py --pretrained ../models/checkpoints/best_model.pth \
                        --annotations ../data/annotations/ \
                        --output ../models/checkpoints/finetuned_model.pth \
                        --epochs 20 --lr 1e-4

    python fine_tune.py --pretrained ../models/checkpoints/best_model.pth \
                        --annotations ../data/annotations/ \
                        --output ../models/checkpoints/finetuned_model.pth \
                        --freeze-encoder --unfreeze-at-epoch 5
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.cuda.amp import GradScaler, autocast
from torch.utils.data import DataLoader
from tqdm import tqdm
import yaml

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent / 'ml'))

from dataset import MapSegmentationDataset, create_train_val_test_datasets
from model import get_model
from losses import get_loss_function
from evaluate import evaluate


def setup_logging(log_dir: str, log_file: bool = True):
    """Configure logging to console and file."""
    os.makedirs(log_dir, exist_ok=True)

    # Create logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # Remove existing handlers
    logger.handlers = []

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # File handler
    if log_file:
        log_path = os.path.join(log_dir, 'fine_tuning.log')
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)

    return logger


def get_device(device_name: str = 'auto') -> torch.device:
    """Get compute device (CUDA, MPS, or CPU)."""
    if device_name == 'auto':
        if torch.cuda.is_available():
            device = torch.device('cuda')
            logging.info(f"Using CUDA device: {torch.cuda.get_device_name(0)}")
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            device = torch.device('mps')
            logging.info("Using Apple MPS device")
        else:
            device = torch.device('cpu')
            logging.info("Using CPU device")
    else:
        device = torch.device(device_name)
        logging.info(f"Using specified device: {device_name}")

    return device


def load_pretrained_model(checkpoint_path: str, device: torch.device, num_classes: int = 5):
    """
    Load pretrained model from Phase 3 checkpoint.

    Args:
        checkpoint_path: Path to pretrained model checkpoint
        device: Device to load model on
        num_classes: Number of output classes

    Returns:
        Loaded model in train mode
    """
    if not os.path.exists(checkpoint_path):
        raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")

    logging.info(f"Loading pretrained model from {checkpoint_path}")

    # Create model (must match training architecture)
    model = get_model(
        encoder='resnet34',
        pretrained=False,  # We'll load our own weights
        classes=num_classes,
        device=device
    )

    # Load checkpoint
    checkpoint = torch.load(checkpoint_path, map_location=device)

    # Handle different checkpoint formats
    if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
        model.load_state_dict(checkpoint['model_state_dict'])
        logging.info(f"Loaded checkpoint from epoch {checkpoint.get('epoch', 'unknown')}")
        if 'best_metric' in checkpoint:
            logging.info(f"Pretrained model best IoU: {checkpoint['best_metric']:.4f}")
    else:
        model.load_state_dict(checkpoint)

    return model


def freeze_encoder(model):
    """Freeze encoder parameters (for transfer learning)."""
    logging.info("Freezing encoder parameters")

    # Access encoder through the wrapped model
    if hasattr(model, 'model'):
        # Our UNet wrapper
        encoder = model.model.encoder
    else:
        # Direct smp.Unet
        encoder = model.encoder

    for param in encoder.parameters():
        param.requires_grad = False

    # Count frozen parameters
    frozen_params = sum(p.numel() for p in encoder.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)

    logging.info(f"Frozen parameters: {frozen_params:,}")
    logging.info(f"Trainable parameters: {trainable_params:,}")


def unfreeze_encoder(model):
    """Unfreeze encoder parameters."""
    logging.info("Unfreezing encoder parameters")

    # Access encoder through the wrapped model
    if hasattr(model, 'model'):
        encoder = model.model.encoder
    else:
        encoder = model.encoder

    for param in encoder.parameters():
        param.requires_grad = True

    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    logging.info(f"Trainable parameters: {trainable_params:,}")


def create_dataloaders(
    annotations_dir: str,
    batch_size: int,
    train_split: float = 0.8,
    val_split: float = 0.1,
    num_workers: int = 4,
    seed: int = 42
) -> Tuple[DataLoader, DataLoader, DataLoader]:
    """
    Create dataloaders for fine-tuning on real annotated data.

    Args:
        annotations_dir: Directory containing images/ and masks/ subdirectories
        batch_size: Batch size for training
        train_split: Fraction of data for training
        val_split: Fraction of data for validation
        num_workers: Number of data loading workers
        seed: Random seed for splits

    Returns:
        Tuple of (train_loader, val_loader, test_loader)
    """
    annotations_path = Path(annotations_dir)
    images_dir = annotations_path / 'images'
    masks_dir = annotations_path / 'masks'

    if not images_dir.exists() or not masks_dir.exists():
        raise ValueError(
            f"Expected {images_dir} and {masks_dir} to exist. "
            f"Please place annotated images in {images_dir}/ and masks in {masks_dir}/"
        )

    # Check if data exists
    image_files = list(images_dir.glob('*.png'))
    if len(image_files) == 0:
        raise ValueError(f"No PNG images found in {images_dir}")

    logging.info(f"Found {len(image_files)} annotated images")

    # Create datasets with aggressive augmentation
    train_dataset, val_dataset, test_dataset = create_train_val_test_datasets(
        str(annotations_path),
        train_split=train_split,
        val_split=val_split,
        test_split=1.0 - train_split - val_split,
        normalize='imagenet',
        seed=seed
    )

    # Create dataloaders
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=True
    )

    val_loader = DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=True
    )

    test_loader = DataLoader(
        test_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=True
    )

    logging.info(f"Dataset sizes - Train: {len(train_dataset)}, Val: {len(val_dataset)}, Test: {len(test_dataset)}")

    return train_loader, val_loader, test_loader


def train_epoch(
    model,
    dataloader,
    criterion,
    optimizer,
    device,
    scaler,
    grad_clip: float = 1.0,
    use_tqdm: bool = True
):
    """Train for one epoch."""
    model.train()
    total_loss = 0.0
    num_batches = len(dataloader)

    iterator = tqdm(dataloader, desc="Training") if use_tqdm else dataloader

    for batch_idx, (images, masks) in enumerate(iterator):
        images = images.to(device)
        masks = masks.to(device)

        # Zero gradients
        optimizer.zero_grad()

        # Mixed precision training
        with autocast(enabled=(scaler is not None)):
            outputs = model(images)
            loss = criterion(outputs, masks)

        # Backward pass
        if scaler is not None:
            scaler.scale(loss).backward()
            if grad_clip > 0:
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
            scaler.step(optimizer)
            scaler.update()
        else:
            loss.backward()
            if grad_clip > 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
            optimizer.step()

        total_loss += loss.item()

        # Update progress bar
        if use_tqdm:
            iterator.set_postfix({'loss': loss.item()})

    avg_loss = total_loss / num_batches
    return avg_loss


def save_checkpoint(model, optimizer, scheduler, epoch, best_metric, filepath):
    """Save fine-tuned checkpoint."""
    checkpoint = {
        'epoch': epoch,
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
        'scheduler_state_dict': scheduler.state_dict() if scheduler else None,
        'best_metric': best_metric,
        'fine_tuned': True,
    }
    torch.save(checkpoint, filepath)
    logging.info(f"Checkpoint saved to {filepath}")


def fine_tune(
    pretrained_checkpoint: str,
    annotations_dir: str,
    output_checkpoint: str,
    epochs: int = 20,
    learning_rate: float = 1e-4,
    batch_size: int = 8,
    freeze_encoder: bool = False,
    unfreeze_at_epoch: Optional[int] = None,
    device_name: str = 'auto',
    num_workers: int = 4,
    grad_clip: float = 1.0,
    early_stopping_patience: int = 10,
    log_dir: Optional[str] = None
):
    """
    Main fine-tuning function.

    Args:
        pretrained_checkpoint: Path to pretrained model from Phase 3
        annotations_dir: Directory with real annotated data
        output_checkpoint: Path to save fine-tuned model
        epochs: Number of fine-tuning epochs
        learning_rate: Learning rate (typically 1e-4 or 1e-5)
        batch_size: Batch size
        freeze_encoder: Whether to freeze encoder initially
        unfreeze_at_epoch: Epoch at which to unfreeze encoder (if frozen)
        device_name: Device to use ('auto', 'cuda', 'mps', 'cpu')
        num_workers: Number of data loading workers
        grad_clip: Gradient clipping value
        early_stopping_patience: Early stopping patience
        log_dir: Directory for logs (default: same as output_checkpoint)

    Returns:
        Best validation IoU
    """
    # Setup
    device = get_device(device_name)

    if log_dir is None:
        log_dir = Path(output_checkpoint).parent / 'fine_tuning_logs'

    os.makedirs(log_dir, exist_ok=True)
    logger = setup_logging(log_dir, log_file=True)

    logger.info("=" * 80)
    logger.info("Starting fine-tuning")
    logger.info("=" * 80)
    logger.info(f"Pretrained checkpoint: {pretrained_checkpoint}")
    logger.info(f"Annotations directory: {annotations_dir}")
    logger.info(f"Output checkpoint: {output_checkpoint}")
    logger.info(f"Epochs: {epochs}")
    logger.info(f"Learning rate: {learning_rate}")
    logger.info(f"Batch size: {batch_size}")
    logger.info(f"Freeze encoder: {freeze_encoder}")
    if freeze_encoder and unfreeze_at_epoch:
        logger.info(f"Unfreeze at epoch: {unfreeze_at_epoch}")

    # Load pretrained model
    model = load_pretrained_model(pretrained_checkpoint, device, num_classes=5)

    # Evaluate pretrained model on real data first
    logger.info("\nEvaluating pretrained model on real data...")
    train_loader, val_loader, test_loader = create_dataloaders(
        annotations_dir,
        batch_size=batch_size,
        num_workers=num_workers
    )

    pretrained_metrics = evaluate(model, val_loader, device)
    logger.info("Pretrained model metrics on real data:")
    logger.info(f"  Mean IoU: {pretrained_metrics['mean_iou']:.4f}")
    logger.info(f"  Pixel Accuracy: {pretrained_metrics['pixel_accuracy']:.4f}")
    for i, class_name in enumerate(['background', 'building', 'road', 'water', 'forest']):
        if i in pretrained_metrics['class_iou']:
            logger.info(f"  {class_name} IoU: {pretrained_metrics['class_iou'][i]:.4f}")

    # Freeze encoder if requested
    if freeze_encoder:
        freeze_encoder(model)

    # Loss function
    criterion = get_loss_function('dice')
    criterion = criterion.to(device)

    # Optimizer with lower learning rate
    optimizer = optim.Adam(
        filter(lambda p: p.requires_grad, model.parameters()),
        lr=learning_rate,
        weight_decay=1e-4
    )

    # Learning rate scheduler
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer,
        mode='max',
        factor=0.5,
        patience=5,
        min_lr=1e-6,
        verbose=True
    )

    # Mixed precision scaler (only for CUDA)
    scaler = GradScaler() if device.type == 'cuda' else None
    if scaler:
        logger.info("Mixed precision training enabled")

    # Training loop
    best_metric = pretrained_metrics['mean_iou']
    epochs_without_improvement = 0

    logger.info("\nStarting fine-tuning loop")

    for epoch in range(epochs):
        logger.info(f"\nEpoch {epoch + 1}/{epochs}")
        logger.info("-" * 80)

        # Unfreeze encoder at specified epoch
        if freeze_encoder and unfreeze_at_epoch and epoch == unfreeze_at_epoch:
            unfreeze_encoder(model)
            # Recreate optimizer to include encoder parameters
            optimizer = optim.Adam(
                model.parameters(),
                lr=learning_rate / 10,  # Lower LR for encoder
                weight_decay=1e-4
            )
            logger.info(f"Unfroze encoder at epoch {epoch + 1}, reduced LR to {learning_rate / 10}")

        # Train
        train_loss = train_epoch(
            model, train_loader, criterion, optimizer, device, scaler, grad_clip, use_tqdm=True
        )
        logger.info(f"Train Loss: {train_loss:.4f}")

        # Validate
        val_metrics = evaluate(model, val_loader, device)

        logger.info(f"Validation Metrics:")
        logger.info(f"  Loss: {val_metrics['loss']:.4f}")
        logger.info(f"  Mean IoU: {val_metrics['mean_iou']:.4f}")
        logger.info(f"  Pixel Accuracy: {val_metrics['pixel_accuracy']:.4f}")

        for i, class_name in enumerate(['background', 'building', 'road', 'water', 'forest']):
            if i in val_metrics['class_iou']:
                logger.info(f"  {class_name} IoU: {val_metrics['class_iou'][i]:.4f}")

        # Update learning rate scheduler
        scheduler.step(val_metrics['mean_iou'])

        # Check for improvement
        current_metric = val_metrics['mean_iou']

        if current_metric > best_metric:
            improvement = current_metric - best_metric
            best_metric = current_metric
            epochs_without_improvement = 0

            # Save best model
            save_checkpoint(model, optimizer, scheduler, epoch, best_metric, output_checkpoint)
            logger.info(f"New best model! IoU: {best_metric:.4f} (+{improvement:.4f})")
        else:
            epochs_without_improvement += 1
            logger.info(f"No improvement for {epochs_without_improvement} epoch(s)")

        # Early stopping check
        if epochs_without_improvement >= early_stopping_patience:
            logger.info(f"Early stopping triggered after {epoch + 1} epochs")
            break

    # Final evaluation on test set
    logger.info("\n" + "=" * 80)
    logger.info("Fine-tuning completed!")
    logger.info(f"Best validation IoU: {best_metric:.4f}")
    logger.info(f"Improvement over pretrained: {best_metric - pretrained_metrics['mean_iou']:.4f}")
    logger.info("=" * 80)

    # Evaluate on test set
    logger.info("\nEvaluating fine-tuned model on test set...")
    model.load_state_dict(torch.load(output_checkpoint)['model_state_dict'])
    test_metrics = evaluate(model, test_loader, device)

    logger.info("Test Set Results:")
    logger.info(f"  Mean IoU: {test_metrics['mean_iou']:.4f}")
    logger.info(f"  Pixel Accuracy: {test_metrics['pixel_accuracy']:.4f}")

    for i, class_name in enumerate(['background', 'building', 'road', 'water', 'forest']):
        if i in test_metrics['class_iou']:
            logger.info(f"  {class_name} IoU: {test_metrics['class_iou'][i]:.4f}")

    logger.info("\nComparison:")
    logger.info(f"  Pretrained IoU: {pretrained_metrics['mean_iou']:.4f}")
    logger.info(f"  Fine-tuned IoU: {test_metrics['mean_iou']:.4f}")
    logger.info(f"  Improvement: {test_metrics['mean_iou'] - pretrained_metrics['mean_iou']:.4f}")

    return best_metric


def main():
    parser = argparse.ArgumentParser(
        description='Fine-tune pretrained model on real historical map annotations',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # Required arguments
    parser.add_argument('--pretrained', required=True,
                       help='Path to pretrained model checkpoint from Phase 3')
    parser.add_argument('--annotations', required=True,
                       help='Path to annotations directory (should contain images/ and masks/ subdirs)')
    parser.add_argument('--output', required=True,
                       help='Path to save fine-tuned model checkpoint')

    # Training arguments
    parser.add_argument('--epochs', type=int, default=20,
                       help='Number of fine-tuning epochs')
    parser.add_argument('--lr', type=float, default=1e-4,
                       help='Learning rate (typically 1e-4 or 1e-5)')
    parser.add_argument('--batch-size', type=int, default=8,
                       help='Batch size')

    # Transfer learning arguments
    parser.add_argument('--freeze-encoder', action='store_true',
                       help='Freeze encoder initially (only train decoder)')
    parser.add_argument('--unfreeze-at-epoch', type=int, default=None,
                       help='Epoch at which to unfreeze encoder (if frozen)')

    # Other arguments
    parser.add_argument('--device', type=str, default='auto',
                       choices=['auto', 'cuda', 'mps', 'cpu'],
                       help='Device to use')
    parser.add_argument('--num-workers', type=int, default=4,
                       help='Number of data loading workers')
    parser.add_argument('--grad-clip', type=float, default=1.0,
                       help='Gradient clipping value')
    parser.add_argument('--early-stopping-patience', type=int, default=10,
                       help='Early stopping patience (epochs)')
    parser.add_argument('--log-dir', type=str, default=None,
                       help='Directory for logs (default: same dir as output)')

    args = parser.parse_args()

    # Create output directory
    os.makedirs(Path(args.output).parent, exist_ok=True)

    # Run fine-tuning
    fine_tune(
        pretrained_checkpoint=args.pretrained,
        annotations_dir=args.annotations,
        output_checkpoint=args.output,
        epochs=args.epochs,
        learning_rate=args.lr,
        batch_size=args.batch_size,
        freeze_encoder=args.freeze_encoder,
        unfreeze_at_epoch=args.unfreeze_at_epoch,
        device_name=args.device,
        num_workers=args.num_workers,
        grad_clip=args.grad_clip,
        early_stopping_patience=args.early_stopping_patience,
        log_dir=args.log_dir
    )


if __name__ == '__main__':
    main()
