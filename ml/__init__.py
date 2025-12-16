"""
ML module for historical map segmentation.

This module provides PyTorch Dataset, U-Net model, and training utilities
for extracting features from historical maps.
"""

from .dataset import MapSegmentationDataset
from .model import UNet, get_model
from .utils import set_seed, get_device, calculate_class_weights, save_checkpoint, load_checkpoint

__all__ = [
    'MapSegmentationDataset',
    'UNet',
    'get_model',
    'set_seed',
    'get_device',
    'calculate_class_weights',
    'save_checkpoint',
    'load_checkpoint',
]
