"""
Training utilities for ML pipeline.

Provides device detection, seed setting, class weight calculation,
and checkpoint management for reproducible training.
"""

import os
import random
from pathlib import Path
from typing import Dict, Optional, Any
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset


def set_seed(seed: int = 42):
    """
    Set random seeds for reproducibility.

    Sets seeds for:
        - Python random
        - NumPy
        - PyTorch (CPU and CUDA)
        - PyTorch backends (deterministic algorithms)

    Args:
        seed: Random seed value
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)

    # Make PyTorch operations deterministic (may impact performance)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

    # Set environment variable for Python hash seed
    os.environ['PYTHONHASHSEED'] = str(seed)

    print(f"Random seed set to {seed}")


def get_device(prefer_mps: bool = True) -> torch.device:
    """
    Detect and return the best available device.

    Priority:
        1. CUDA (NVIDIA GPU)
        2. MPS (Apple Silicon GPU) if prefer_mps=True
        3. CPU (fallback)

    Args:
        prefer_mps: Whether to prefer MPS over CPU on Apple Silicon

    Returns:
        torch.device: Best available device
    """
    if torch.cuda.is_available():
        device = torch.device('cuda')
        device_name = torch.cuda.get_device_name(0)
        print(f"Using CUDA device: {device_name}")
        print(f"  Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB")
    elif prefer_mps and torch.backends.mps.is_available():
        device = torch.device('mps')
        print(f"Using Apple MPS (Metal Performance Shaders)")
    else:
        device = torch.device('cpu')
        print(f"Using CPU")

    return device


def calculate_class_weights(
    dataset: Dataset,
    num_classes: int = 5,
    normalize: bool = True,
    sample_size: Optional[int] = None
) -> torch.Tensor:
    """
    Calculate class weights for handling imbalanced data.

    Computes inverse frequency weights: weight = 1 / frequency
    Useful for weighted loss functions to handle class imbalance.

    Args:
        dataset: PyTorch Dataset with masks
        num_classes: Number of segmentation classes
        normalize: Whether to normalize weights to mean=1
        sample_size: Number of samples to use (None = use all)

    Returns:
        Tensor of shape (num_classes,) with class weights
    """
    print(f"\nCalculating class weights...")

    if sample_size is None:
        sample_size = len(dataset)
    else:
        sample_size = min(sample_size, len(dataset))

    # Sample evenly across dataset
    indices = np.linspace(0, len(dataset) - 1, sample_size, dtype=int)

    class_counts = np.zeros(num_classes, dtype=np.int64)

    for idx in indices:
        _, mask = dataset[idx]

        # Convert to numpy if needed
        if isinstance(mask, torch.Tensor):
            mask = mask.cpu().numpy()

        # Count pixels per class
        for class_id in range(num_classes):
            class_counts[class_id] += np.sum(mask == class_id)

    # Calculate weights (inverse frequency)
    total_pixels = class_counts.sum()
    class_weights = total_pixels / (class_counts + 1e-10)  # Avoid division by zero

    if normalize:
        # Normalize so mean weight = 1
        class_weights = class_weights / class_weights.mean()

    class_weights = torch.from_numpy(class_weights).float()

    print(f"  Sampled {sample_size} images")
    print(f"  Class weights:")
    for class_id in range(num_classes):
        percentage = 100 * class_counts[class_id] / total_pixels if total_pixels > 0 else 0
        print(f"    Class {class_id}: {class_weights[class_id]:.3f} "
              f"(frequency: {percentage:.2f}%)")

    return class_weights


def save_checkpoint(
    model: nn.Module,
    optimizer: torch.optim.Optimizer,
    epoch: int,
    metrics: Dict[str, float],
    checkpoint_path: str,
    scheduler: Optional[Any] = None,
    extra_state: Optional[Dict] = None
):
    """
    Save model checkpoint with training state.

    Saves:
        - Model state dict
        - Optimizer state dict
        - Scheduler state dict (if provided)
        - Current epoch
        - Metrics
        - Extra state (custom data)

    Args:
        model: PyTorch model
        optimizer: Optimizer
        epoch: Current epoch number
        metrics: Dictionary of metric values
        checkpoint_path: Path to save checkpoint
        scheduler: Learning rate scheduler (optional)
        extra_state: Additional state to save (optional)
    """
    checkpoint_path = Path(checkpoint_path)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    checkpoint = {
        'epoch': epoch,
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
        'metrics': metrics,
    }

    if scheduler is not None:
        checkpoint['scheduler_state_dict'] = scheduler.state_dict()

    if extra_state is not None:
        checkpoint['extra_state'] = extra_state

    torch.save(checkpoint, checkpoint_path)
    print(f"  Checkpoint saved: {checkpoint_path}")


def load_checkpoint(
    checkpoint_path: str,
    model: nn.Module,
    optimizer: Optional[torch.optim.Optimizer] = None,
    scheduler: Optional[Any] = None,
    device: Optional[torch.device] = None
) -> Dict:
    """
    Load model checkpoint and restore training state.

    Args:
        checkpoint_path: Path to checkpoint file
        model: Model to load state into
        optimizer: Optimizer to load state into (optional)
        scheduler: Scheduler to load state into (optional)
        device: Device to map tensors to (optional)

    Returns:
        Dictionary with checkpoint contents (epoch, metrics, extra_state)
    """
    checkpoint_path = Path(checkpoint_path)

    if not checkpoint_path.exists():
        raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")

    print(f"Loading checkpoint: {checkpoint_path}")

    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)

    # Load model state
    model.load_state_dict(checkpoint['model_state_dict'])

    # Load optimizer state
    if optimizer is not None and 'optimizer_state_dict' in checkpoint:
        optimizer.load_state_dict(checkpoint['optimizer_state_dict'])

    # Load scheduler state
    if scheduler is not None and 'scheduler_state_dict' in checkpoint:
        scheduler.load_state_dict(checkpoint['scheduler_state_dict'])

    epoch = checkpoint.get('epoch', 0)
    metrics = checkpoint.get('metrics', {})
    extra_state = checkpoint.get('extra_state', {})

    print(f"  Restored from epoch {epoch}")
    if metrics:
        print(f"  Metrics: {metrics}")

    return {
        'epoch': epoch,
        'metrics': metrics,
        'extra_state': extra_state
    }


def count_parameters(model: nn.Module) -> Dict[str, int]:
    """
    Count model parameters.

    Returns:
        Dictionary with total and trainable parameter counts
    """
    total = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)

    return {
        'total': total,
        'trainable': trainable,
        'frozen': total - trainable
    }


def format_time(seconds: float) -> str:
    """
    Format seconds as human-readable time string.

    Args:
        seconds: Time in seconds

    Returns:
        Formatted string (e.g., "1h 23m 45s")
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"


def get_learning_rate(optimizer: torch.optim.Optimizer) -> float:
    """
    Get current learning rate from optimizer.

    Args:
        optimizer: PyTorch optimizer

    Returns:
        Current learning rate
    """
    for param_group in optimizer.param_groups:
        return param_group['lr']
    return 0.0


class AverageMeter:
    """
    Computes and stores the average and current value.

    Useful for tracking metrics during training.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.val = 0
        self.avg = 0
        self.sum = 0
        self.count = 0

    def update(self, val, n=1):
        self.val = val
        self.sum += val * n
        self.count += n
        self.avg = self.sum / self.count


if __name__ == '__main__':
    # Test utilities
    print("Testing utilities...")

    # Test seed setting
    print("\n1. Testing seed setting:")
    set_seed(42)

    # Test device detection
    print("\n2. Testing device detection:")
    device = get_device()

    # Test parameter counting
    print("\n3. Testing parameter counting:")
    model = nn.Sequential(
        nn.Conv2d(3, 64, 3),
        nn.ReLU(),
        nn.Conv2d(64, 128, 3),
    )
    params = count_parameters(model)
    print(f"  Total parameters: {params['total']:,}")
    print(f"  Trainable parameters: {params['trainable']:,}")

    # Test time formatting
    print("\n4. Testing time formatting:")
    for seconds in [30, 125, 3725, 86425]:
        print(f"  {seconds}s = {format_time(seconds)}")

    # Test AverageMeter
    print("\n5. Testing AverageMeter:")
    meter = AverageMeter()
    for i in [1, 2, 3, 4, 5]:
        meter.update(i)
    print(f"  Average: {meter.avg}")

    print("\nUtilities tests completed successfully!")
