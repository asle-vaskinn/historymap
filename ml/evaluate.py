#!/usr/bin/env python3
"""
Evaluation script for historical map segmentation model.

Features:
- IoU (Intersection over Union) per class
- Mean IoU across classes
- Overall pixel accuracy
- Confusion matrix generation
- Visual comparison: input → prediction → ground truth
- Save evaluation report

Usage:
    python evaluate.py --checkpoint best_model.pth --data ../data/synthetic
    python evaluate.py --checkpoint best_model.pth --data ../data/synthetic --visualize
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader
from tqdm import tqdm
import yaml

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent))

from dataset import HistoricalMapDataset, get_transforms
from model import get_model
from losses import get_loss_function


def compute_iou(pred, target, num_classes, ignore_index=-100):
    """
    Compute Intersection over Union (IoU) per class.

    Args:
        pred: (N, H, W) predicted class indices
        target: (N, H, W) ground truth class indices
        num_classes: Number of classes
        ignore_index: Index to ignore in computation

    Returns:
        iou_per_class: dict mapping class index to IoU score
    """
    iou_per_class = {}

    for cls in range(num_classes):
        # Create masks for this class
        pred_mask = (pred == cls)
        target_mask = (target == cls)

        # Ignore pixels with ignore_index
        valid_mask = (target != ignore_index)
        pred_mask = pred_mask & valid_mask
        target_mask = target_mask & valid_mask

        # Compute intersection and union
        intersection = (pred_mask & target_mask).sum().item()
        union = (pred_mask | target_mask).sum().item()

        # Compute IoU
        if union > 0:
            iou = intersection / union
        else:
            iou = float('nan')  # No pixels of this class

        iou_per_class[cls] = iou

    return iou_per_class


def compute_pixel_accuracy(pred, target, ignore_index=-100):
    """
    Compute overall pixel accuracy.

    Args:
        pred: (N, H, W) predicted class indices
        target: (N, H, W) ground truth class indices
        ignore_index: Index to ignore in computation

    Returns:
        accuracy: Pixel accuracy (0-1)
    """
    valid_mask = (target != ignore_index)
    correct = ((pred == target) & valid_mask).sum().item()
    total = valid_mask.sum().item()

    if total > 0:
        accuracy = correct / total
    else:
        accuracy = 0.0

    return accuracy


def compute_confusion_matrix(pred, target, num_classes, ignore_index=-100):
    """
    Compute confusion matrix.

    Args:
        pred: (N, H, W) predicted class indices
        target: (N, H, W) ground truth class indices
        num_classes: Number of classes
        ignore_index: Index to ignore in computation

    Returns:
        confusion_matrix: (num_classes, num_classes) array
    """
    # Flatten arrays
    pred = pred.flatten()
    target = target.flatten()

    # Filter out ignore_index
    valid_mask = (target != ignore_index)
    pred = pred[valid_mask]
    target = target[valid_mask]

    # Compute confusion matrix
    confusion = np.zeros((num_classes, num_classes), dtype=np.int64)

    for t, p in zip(target, pred):
        confusion[t, p] += 1

    return confusion


@torch.no_grad()
def evaluate(model, dataloader, device, criterion=None, num_classes=5):
    """
    Evaluate model on a dataset.

    Args:
        model: PyTorch model
        dataloader: DataLoader for evaluation
        device: Device to run evaluation on
        criterion: Loss function (optional)
        num_classes: Number of classes

    Returns:
        metrics: Dictionary of evaluation metrics
    """
    model.eval()

    total_loss = 0.0
    all_preds = []
    all_targets = []

    for images, masks in dataloader:
        images = images.to(device)
        masks = masks.to(device)

        # Forward pass
        outputs = model(images)

        # Compute loss if criterion provided
        if criterion:
            loss = criterion(outputs, masks)
            total_loss += loss.item()

        # Get predictions
        preds = torch.argmax(outputs, dim=1)

        # Store predictions and targets
        all_preds.append(preds.cpu().numpy())
        all_targets.append(masks.cpu().numpy())

    # Concatenate all batches
    all_preds = np.concatenate(all_preds, axis=0)
    all_targets = np.concatenate(all_targets, axis=0)

    # Compute metrics
    iou_per_class = compute_iou(all_preds, all_targets, num_classes)
    pixel_accuracy = compute_pixel_accuracy(all_preds, all_targets)
    confusion = compute_confusion_matrix(all_preds, all_targets, num_classes)

    # Mean IoU (excluding NaN values)
    valid_ious = [iou for iou in iou_per_class.values() if not np.isnan(iou)]
    mean_iou = np.mean(valid_ious) if valid_ious else 0.0

    # Average loss
    avg_loss = total_loss / len(dataloader) if criterion else 0.0

    metrics = {
        'loss': avg_loss,
        'mean_iou': mean_iou,
        'class_iou': iou_per_class,
        'pixel_accuracy': pixel_accuracy,
        'confusion_matrix': confusion,
    }

    return metrics


def visualize_predictions(model, dataset, device, num_samples=5, save_dir=None, class_names=None):
    """
    Visualize model predictions.

    Creates a grid showing: input image | prediction | ground truth

    Args:
        model: PyTorch model
        dataset: Dataset to sample from
        device: Device to run inference on
        num_samples: Number of samples to visualize
        save_dir: Directory to save visualizations (optional)
        class_names: Dict mapping class indices to names
    """
    model.eval()

    # Create figure
    fig, axes = plt.subplots(num_samples, 3, figsize=(15, 5 * num_samples))

    if num_samples == 1:
        axes = axes.reshape(1, -1)

    # Color map for segmentation masks
    cmap = plt.cm.get_cmap('tab10')

    for i in range(num_samples):
        # Get random sample
        idx = np.random.randint(len(dataset))
        image, mask = dataset[idx]

        # Add batch dimension
        image_batch = image.unsqueeze(0).to(device)

        # Predict
        with torch.no_grad():
            output = model(image_batch)
            pred = torch.argmax(output, dim=1).squeeze(0).cpu().numpy()

        # Convert image to numpy (denormalize if needed)
        img_np = image.permute(1, 2, 0).cpu().numpy()
        img_np = (img_np - img_np.min()) / (img_np.max() - img_np.min())  # Normalize to [0, 1]

        mask_np = mask.cpu().numpy()

        # Plot
        axes[i, 0].imshow(img_np)
        axes[i, 0].set_title('Input Image')
        axes[i, 0].axis('off')

        axes[i, 1].imshow(pred, cmap=cmap, vmin=0, vmax=9)
        axes[i, 1].set_title('Prediction')
        axes[i, 1].axis('off')

        axes[i, 2].imshow(mask_np, cmap=cmap, vmin=0, vmax=9)
        axes[i, 2].set_title('Ground Truth')
        axes[i, 2].axis('off')

    plt.tight_layout()

    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, 'predictions.png')
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        logging.info(f"Visualization saved to {save_path}")

    plt.show()


def plot_confusion_matrix(confusion, class_names, save_path=None):
    """
    Plot confusion matrix.

    Args:
        confusion: (num_classes, num_classes) confusion matrix
        class_names: Dict mapping class indices to names
        save_path: Path to save plot (optional)
    """
    fig, ax = plt.subplots(figsize=(10, 8))

    # Normalize by row (ground truth)
    confusion_norm = confusion.astype('float') / (confusion.sum(axis=1, keepdims=True) + 1e-10)

    im = ax.imshow(confusion_norm, cmap='Blues', vmin=0, vmax=1)

    # Labels
    num_classes = len(class_names)
    ax.set_xticks(range(num_classes))
    ax.set_yticks(range(num_classes))
    ax.set_xticklabels([class_names[i] for i in range(num_classes)], rotation=45, ha='right')
    ax.set_yticklabels([class_names[i] for i in range(num_classes)])

    # Add text annotations
    for i in range(num_classes):
        for j in range(num_classes):
            text = ax.text(j, i, f'{confusion[i, j]}\n({confusion_norm[i, j]:.2f})',
                          ha="center", va="center", color="black" if confusion_norm[i, j] < 0.5 else "white")

    ax.set_xlabel('Predicted Class')
    ax.set_ylabel('True Class')
    ax.set_title('Confusion Matrix')

    plt.colorbar(im, ax=ax)
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        logging.info(f"Confusion matrix saved to {save_path}")

    plt.show()


def save_evaluation_report(metrics, config, save_path):
    """
    Save evaluation report to JSON.

    Args:
        metrics: Dictionary of evaluation metrics
        config: Configuration dictionary
        save_path: Path to save report
    """
    report = {
        'model': {
            'encoder': config['model']['encoder'],
            'classes': config['model']['classes'],
        },
        'metrics': {
            'mean_iou': float(metrics['mean_iou']),
            'pixel_accuracy': float(metrics['pixel_accuracy']),
            'class_iou': {config['class_names'][k]: float(v)
                          for k, v in metrics['class_iou'].items() if not np.isnan(v)},
        },
        'confusion_matrix': metrics['confusion_matrix'].tolist(),
    }

    with open(save_path, 'w') as f:
        json.dump(report, f, indent=2)

    logging.info(f"Evaluation report saved to {save_path}")


def main():
    parser = argparse.ArgumentParser(description='Evaluate historical map segmentation model')
    parser.add_argument('--checkpoint', type=str, required=True, help='Path to model checkpoint')
    parser.add_argument('--data', type=str, required=True, help='Path to data directory')
    parser.add_argument('--split', type=str, default='test', choices=['train', 'val', 'test'],
                       help='Dataset split to evaluate')
    parser.add_argument('--batch_size', type=int, default=16, help='Batch size for evaluation')
    parser.add_argument('--visualize', action='store_true', help='Generate visualizations')
    parser.add_argument('--num_vis', type=int, default=5, help='Number of samples to visualize')
    parser.add_argument('--output', type=str, default='../results/evaluation',
                       help='Output directory for results')
    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    # Create output directory
    os.makedirs(args.output, exist_ok=True)

    # Load checkpoint
    logging.info(f"Loading checkpoint from {args.checkpoint}")
    checkpoint = torch.load(args.checkpoint, map_location='cpu', weights_only=False)
    config = checkpoint['config']

    # Device
    if torch.cuda.is_available():
        device = torch.device('cuda')
    elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
        device = torch.device('mps')
    else:
        device = torch.device('cpu')
    logging.info(f"Using device: {device}")

    # Create model
    model = get_model(
        encoder=config['model']['encoder'],
        pretrained=False,  # We'll load trained weights
        classes=config['model']['classes'],
        device=device
    )
    model.load_state_dict(checkpoint['model_state_dict'])
    model.eval()
    logging.info("Model loaded successfully")

    # Create dataset
    # Determine dataset structure
    data_path = Path(args.data)
    if (data_path / args.split).exists():
        # Split structure
        images_dir = data_path / args.split / 'images'
        masks_dir = data_path / args.split / 'masks'
    elif (data_path / 'images').exists():
        # Flat structure - need to create temp split
        from dataset import create_train_val_test_datasets
        logging.info("Using flat structure - splitting dataset...")
        train_ds, val_ds, test_ds = create_train_val_test_datasets(
            str(data_path),
            train_split=config['data']['train_split'],
            val_split=config['data']['val_split'],
            test_split=config['data']['test_split'],
            normalize='imagenet',
            seed=config['seed']
        )
        dataset = {'train': train_ds, 'val': val_ds, 'test': test_ds}[args.split]
    else:
        raise ValueError(f"Could not find dataset structure in {data_path}")

    # Only create dataset if not already created above
    if 'dataset' not in locals():
        dataset = HistoricalMapDataset(
            images_dir=str(images_dir),
            masks_dir=str(masks_dir),
            augment=False,
            normalize='imagenet',
            split=args.split
        )

    dataloader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=4,
        pin_memory=True
    )

    logging.info(f"Evaluating on {len(dataset)} {args.split} samples")

    # Evaluate
    criterion = get_loss_function(config['training']['loss'])
    criterion = criterion.to(device)

    metrics = evaluate(model, dataloader, device, criterion, num_classes=config['model']['classes'])

    # Print results
    print("\n" + "=" * 80)
    print("EVALUATION RESULTS")
    print("=" * 80)
    print(f"Mean IoU: {metrics['mean_iou']:.4f}")
    print(f"Pixel Accuracy: {metrics['pixel_accuracy']:.4f}")
    print(f"Loss: {metrics['loss']:.4f}")
    print("\nPer-Class IoU:")

    for i, class_name in config['class_names'].items():
        if i in metrics['class_iou'] and not np.isnan(metrics['class_iou'][i]):
            print(f"  {class_name}: {metrics['class_iou'][i]:.4f}")
        else:
            print(f"  {class_name}: N/A (no pixels)")

    print("=" * 80)

    # Save report
    report_path = os.path.join(args.output, f'evaluation_report_{args.split}.json')
    save_evaluation_report(metrics, config, report_path)

    # Plot confusion matrix
    cm_path = os.path.join(args.output, f'confusion_matrix_{args.split}.png')
    plot_confusion_matrix(metrics['confusion_matrix'], config['class_names'], save_path=cm_path)

    # Visualize predictions
    if args.visualize:
        vis_dir = os.path.join(args.output, 'visualizations')
        visualize_predictions(model, dataset, device, num_samples=args.num_vis,
                            save_dir=vis_dir, class_names=config['class_names'])

    logging.info("Evaluation complete!")


if __name__ == '__main__':
    main()
