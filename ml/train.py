#!/usr/bin/env python3
"""
Training script for historical map segmentation model.

Features:
- Load config from YAML
- Mixed precision training (torch.cuda.amp)
- Learning rate scheduler (ReduceLROnPlateau)
- Early stopping
- Save best model checkpoint by validation IoU
- Progress bar with current metrics (tqdm)
- Logging to console and file
- Resume from checkpoint support

Usage:
    python train.py --config config.yaml
    python train.py --config config.yaml --resume checkpoint.pth
"""

import argparse
import logging
import os
import random
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.cuda.amp import GradScaler, autocast
from torch.utils.data import DataLoader
from tqdm import tqdm
import yaml

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent))

from dataset import HistoricalMapDataset, get_transforms
from model import get_model
from losses import get_loss_function
from evaluate import evaluate


def setup_logging(log_dir, log_file=True, console_level='INFO', file_level='DEBUG'):
    """Configure logging to console and file."""
    os.makedirs(log_dir, exist_ok=True)

    # Create logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, console_level))
    console_format = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # File handler
    if log_file:
        log_path = os.path.join(log_dir, 'training.log')
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(getattr(logging, file_level))
        file_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)

    return logger


def set_seed(seed):
    """Set random seed for reproducibility."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False


def get_device(device_name='auto'):
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


def load_config(config_path):
    """Load configuration from YAML file."""
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    return config


def create_dataloaders(config):
    """Create train, validation, and test dataloaders."""
    data_dir = Path(config['paths']['data_dir'])

    # Determine dataset structure
    # Check if data_dir has train/val/test subdirectories (split structure)
    # or if it has images/ and masks/ subdirectories (flat structure)
    if (data_dir / 'train').exists():
        # Split structure: data_dir/train/images/, data_dir/train/masks/, etc.
        train_images_dir = data_dir / 'train' / 'images'
        train_masks_dir = data_dir / 'train' / 'masks'
        val_images_dir = data_dir / 'val' / 'images'
        val_masks_dir = data_dir / 'val' / 'masks'
        test_images_dir = data_dir / 'test' / 'images'
        test_masks_dir = data_dir / 'test' / 'masks'
    elif (data_dir / 'images').exists():
        # Flat structure: data_dir/images/, data_dir/masks/
        # Will use create_train_val_test_datasets to split
        from dataset import create_train_val_test_datasets

        logging.info("Using flat structure - splitting dataset...")
        train_dataset, val_dataset, test_dataset = create_train_val_test_datasets(
            str(data_dir),
            train_split=config['data']['train_split'],
            val_split=config['data']['val_split'],
            test_split=config['data']['test_split'],
            normalize='imagenet',
            seed=config['seed']
        )

        # Create dataloaders
        train_loader = DataLoader(
            train_dataset,
            batch_size=config['training']['batch_size'],
            shuffle=True,
            num_workers=config['data']['num_workers'],
            pin_memory=config['data']['pin_memory']
        )

        val_loader = DataLoader(
            val_dataset,
            batch_size=config['training']['batch_size'],
            shuffle=False,
            num_workers=config['data']['num_workers'],
            pin_memory=config['data']['pin_memory']
        )

        test_loader = DataLoader(
            test_dataset,
            batch_size=config['training']['batch_size'],
            shuffle=False,
            num_workers=config['data']['num_workers'],
            pin_memory=config['data']['pin_memory']
        )

        logging.info(f"Dataset sizes - Train: {len(train_dataset)}, Val: {len(val_dataset)}, Test: {len(test_dataset)}")

        return train_loader, val_loader, test_loader
    else:
        raise ValueError(f"Could not find dataset structure in {data_dir}. "
                        f"Expected either train/val/test subdirs or images/masks subdirs.")

    # Create datasets for split structure
    train_dataset = HistoricalMapDataset(
        images_dir=str(train_images_dir),
        masks_dir=str(train_masks_dir),
        augment=config['data']['augmentation']['enabled'],
        normalize='imagenet',
        split='train'
    )

    val_dataset = HistoricalMapDataset(
        images_dir=str(val_images_dir),
        masks_dir=str(val_masks_dir),
        augment=False,
        normalize='imagenet',
        split='val'
    )

    test_dataset = HistoricalMapDataset(
        images_dir=str(test_images_dir),
        masks_dir=str(test_masks_dir),
        augment=False,
        normalize='imagenet',
        split='test'
    )

    # Create dataloaders
    train_loader = DataLoader(
        train_dataset,
        batch_size=config['training']['batch_size'],
        shuffle=True,
        num_workers=config['data']['num_workers'],
        pin_memory=config['data']['pin_memory']
    )

    val_loader = DataLoader(
        val_dataset,
        batch_size=config['training']['batch_size'],
        shuffle=False,
        num_workers=config['data']['num_workers'],
        pin_memory=config['data']['pin_memory']
    )

    test_loader = DataLoader(
        test_dataset,
        batch_size=config['training']['batch_size'],
        shuffle=False,
        num_workers=config['data']['num_workers'],
        pin_memory=config['data']['pin_memory']
    )

    logging.info(f"Dataset sizes - Train: {len(train_dataset)}, Val: {len(val_dataset)}, Test: {len(test_dataset)}")

    return train_loader, val_loader, test_loader


def train_epoch(model, dataloader, criterion, optimizer, device, scaler, grad_clip, use_tqdm=True):
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


def save_checkpoint(model, optimizer, scheduler, epoch, best_metric, config, filepath):
    """Save training checkpoint."""
    checkpoint = {
        'epoch': epoch,
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
        'scheduler_state_dict': scheduler.state_dict() if scheduler else None,
        'best_metric': best_metric,
        'config': config,
    }
    torch.save(checkpoint, filepath)
    logging.info(f"Checkpoint saved to {filepath}")


def load_checkpoint(model, optimizer, scheduler, filepath, device):
    """Load training checkpoint."""
    checkpoint = torch.load(filepath, map_location=device)
    model.load_state_dict(checkpoint['model_state_dict'])
    optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
    if scheduler and checkpoint['scheduler_state_dict']:
        scheduler.load_state_dict(checkpoint['scheduler_state_dict'])

    logging.info(f"Checkpoint loaded from {filepath}")
    logging.info(f"Resuming from epoch {checkpoint['epoch']}")

    return checkpoint['epoch'], checkpoint['best_metric']


def train(config, resume_from=None):
    """Main training function."""
    # Setup
    set_seed(config['seed'])
    device = get_device(config['device'])

    # Create directories
    os.makedirs(config['paths']['checkpoint_dir'], exist_ok=True)
    os.makedirs(config['paths']['log_dir'], exist_ok=True)

    # Setup logging
    logger = setup_logging(
        config['paths']['log_dir'],
        log_file=config['logging']['log_file'],
        console_level=config['logging']['console_level'],
        file_level=config['logging']['file_level']
    )

    logger.info("=" * 80)
    logger.info("Starting training")
    logger.info("=" * 80)
    logger.info(f"Configuration: {config}")

    # Create dataloaders
    train_loader, val_loader, test_loader = create_dataloaders(config)

    # Create model
    model = get_model(
        encoder=config['model']['encoder'],
        pretrained=config['model']['pretrained'],
        classes=config['model']['classes'],
        device=device
    )
    logger.info(f"Model architecture: {config['model']['encoder']}")

    # Loss function
    criterion = get_loss_function(config['training']['loss'])
    criterion = criterion.to(device)
    logger.info(f"Loss function: {config['training']['loss']}")

    # Optimizer
    if config['training']['optimizer'] == 'adam':
        optimizer = optim.Adam(
            model.parameters(),
            lr=config['training']['learning_rate'],
            weight_decay=config['training']['weight_decay']
        )
    elif config['training']['optimizer'] == 'adamw':
        optimizer = optim.AdamW(
            model.parameters(),
            lr=config['training']['learning_rate'],
            weight_decay=config['training']['weight_decay']
        )
    elif config['training']['optimizer'] == 'sgd':
        optimizer = optim.SGD(
            model.parameters(),
            lr=config['training']['learning_rate'],
            momentum=0.9,
            weight_decay=config['training']['weight_decay']
        )
    else:
        raise ValueError(f"Unknown optimizer: {config['training']['optimizer']}")

    logger.info(f"Optimizer: {config['training']['optimizer']}")

    # Learning rate scheduler
    scheduler = None
    if config['training']['scheduler']['type'] == 'reduce_on_plateau':
        scheduler = optim.lr_scheduler.ReduceLROnPlateau(
            optimizer,
            mode=config['training']['scheduler']['mode'],
            factor=config['training']['scheduler']['factor'],
            patience=config['training']['scheduler']['patience'],
            min_lr=config['training']['scheduler']['min_lr'],
            verbose=True
        )
        logger.info("Using ReduceLROnPlateau scheduler")

    # Mixed precision scaler
    scaler = GradScaler() if config['training']['mixed_precision'] and device.type == 'cuda' else None
    if scaler:
        logger.info("Mixed precision training enabled")

    # Resume from checkpoint
    start_epoch = 0
    best_metric = 0.0

    if resume_from:
        start_epoch, best_metric = load_checkpoint(model, optimizer, scheduler, resume_from, device)
        start_epoch += 1  # Start from next epoch

    # Early stopping
    epochs_without_improvement = 0
    early_stopping_patience = config['training']['early_stopping']['patience']

    # Training loop
    logger.info("Starting training loop")

    for epoch in range(start_epoch, config['training']['epochs']):
        logger.info(f"\nEpoch {epoch + 1}/{config['training']['epochs']}")
        logger.info("-" * 80)

        # Train
        train_loss = train_epoch(
            model, train_loader, criterion, optimizer, device, scaler,
            config['training']['grad_clip'],
            use_tqdm=config['logging']['use_tqdm']
        )
        logger.info(f"Train Loss: {train_loss:.4f}")

        # Validate
        if (epoch + 1) % config['logging']['val_freq'] == 0:
            val_metrics = evaluate(model, val_loader, device)

            logger.info(f"Validation Metrics:")
            logger.info(f"  Loss: {val_metrics['loss']:.4f}")
            logger.info(f"  Mean IoU: {val_metrics['mean_iou']:.4f}")
            logger.info(f"  Pixel Accuracy: {val_metrics['pixel_accuracy']:.4f}")

            for i, class_name in config['class_names'].items():
                if i in val_metrics['class_iou']:
                    logger.info(f"  {class_name} IoU: {val_metrics['class_iou'][i]:.4f}")

            # Update learning rate scheduler
            if scheduler:
                scheduler.step(val_metrics['mean_iou'])

            # Check for improvement
            current_metric = val_metrics['mean_iou']

            if current_metric > best_metric:
                best_metric = current_metric
                epochs_without_improvement = 0

                # Save best model
                save_checkpoint(
                    model, optimizer, scheduler, epoch, best_metric,
                    config, config['paths']['best_model']
                )
                logger.info(f"New best model! IoU: {best_metric:.4f}")
            else:
                epochs_without_improvement += 1
                logger.info(f"No improvement for {epochs_without_improvement} epoch(s)")

            # Early stopping check
            if config['training']['early_stopping']['enabled']:
                if epochs_without_improvement >= early_stopping_patience:
                    logger.info(f"Early stopping triggered after {epoch + 1} epochs")
                    break

        # Save checkpoint periodically
        if (epoch + 1) % config['training']['save_freq'] == 0:
            checkpoint_path = os.path.join(
                config['paths']['checkpoint_dir'],
                f'checkpoint_epoch_{epoch + 1}.pth'
            )
            save_checkpoint(model, optimizer, scheduler, epoch, best_metric, config, checkpoint_path)

        # Save last checkpoint
        save_checkpoint(
            model, optimizer, scheduler, epoch, best_metric,
            config, config['paths']['last_checkpoint']
        )

    logger.info("=" * 80)
    logger.info("Training completed!")
    logger.info(f"Best validation IoU: {best_metric:.4f}")
    logger.info("=" * 80)

    # Evaluate on test set
    logger.info("\nEvaluating on test set...")
    model.load_state_dict(torch.load(config['paths']['best_model'])['model_state_dict'])
    test_metrics = evaluate(model, test_loader, device)

    logger.info("Test Set Results:")
    logger.info(f"  Mean IoU: {test_metrics['mean_iou']:.4f}")
    logger.info(f"  Pixel Accuracy: {test_metrics['pixel_accuracy']:.4f}")

    for i, class_name in config['class_names'].items():
        if i in test_metrics['class_iou']:
            logger.info(f"  {class_name} IoU: {test_metrics['class_iou'][i]:.4f}")

    return best_metric


def main():
    parser = argparse.ArgumentParser(description='Train historical map segmentation model')
    parser.add_argument('--config', type=str, required=True, help='Path to config YAML file')
    parser.add_argument('--resume', type=str, default=None, help='Path to checkpoint to resume from')
    args = parser.parse_args()

    # Load config
    config = load_config(args.config)

    # Train
    train(config, resume_from=args.resume)


if __name__ == '__main__':
    main()
