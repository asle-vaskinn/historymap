"""
PyTorch Dataset for map segmentation.

Loads image/mask pairs from directories and applies augmentations.
Supports train/val/test splits with configurable transforms.
"""

import os
from pathlib import Path
from typing import Optional, Tuple, Callable, List
import numpy as np
from PIL import Image
import torch
from torch.utils.data import Dataset
import albumentations as A
from albumentations.pytorch import ToTensorV2


class MapSegmentationDataset(Dataset):
    """
    Dataset for historical map segmentation.

    Loads PNG images and corresponding masks, applies augmentations,
    and returns normalized tensors for training.

    Args:
        images_dir: Directory containing input images
        masks_dir: Directory containing segmentation masks
        transform: Optional custom transform (Albumentations Compose)
        augment: Whether to apply data augmentation (default: True)
        normalize: Normalization strategy: 'imagenet', '0-1', or None
        split: Dataset split name for logging (e.g., 'train', 'val', 'test')

    Mask format:
        - Single-channel PNG where pixel values represent class indices
        - Class 0: background
        - Class 1: building
        - Class 2: road
        - Class 3: water
        - Class 4: forest
    """

    # ImageNet normalization constants
    IMAGENET_MEAN = [0.485, 0.456, 0.406]
    IMAGENET_STD = [0.229, 0.224, 0.225]

    # Class names for reporting
    CLASS_NAMES = ['background', 'building', 'road', 'water', 'forest']
    NUM_CLASSES = 5

    def __init__(
        self,
        images_dir: str,
        masks_dir: str,
        transform: Optional[Callable] = None,
        augment: bool = True,
        normalize: str = 'imagenet',
        split: str = 'train'
    ):
        self.images_dir = Path(images_dir)
        self.masks_dir = Path(masks_dir)
        self.split = split
        self.normalize = normalize

        # Find all image files
        self.image_files = sorted([
            f for f in self.images_dir.glob('*.png')
            if f.is_file()
        ])

        if len(self.image_files) == 0:
            raise ValueError(f"No images found in {images_dir}")

        # Verify masks exist
        self._verify_masks()

        # Setup transforms
        if transform is not None:
            self.transform = transform
        else:
            self.transform = self._get_default_transform(augment)

        # Report class distribution
        print(f"\n{split.upper()} Dataset Statistics:")
        print(f"  Total samples: {len(self.image_files)}")
        self._report_class_distribution()

    def _verify_masks(self):
        """Verify that corresponding mask exists for each image."""
        missing_masks = []
        for img_path in self.image_files:
            mask_path = self.masks_dir / img_path.name
            if not mask_path.exists():
                missing_masks.append(img_path.name)

        if missing_masks:
            print(f"Warning: {len(missing_masks)} images have no corresponding masks:")
            for name in missing_masks[:5]:
                print(f"  - {name}")
            if len(missing_masks) > 5:
                print(f"  ... and {len(missing_masks) - 5} more")

    def _get_default_transform(self, augment: bool) -> A.Compose:
        """
        Create default augmentation pipeline.

        Training augmentations:
            - Horizontal flip (p=0.5)
            - Vertical flip (p=0.5)
            - Rotation ±15 degrees (p=0.5)
            - Brightness/contrast jitter (p=0.3)

        All splits:
            - Normalization (ImageNet or [0,1])
            - Convert to tensor
        """
        transforms = []

        if augment and self.split == 'train':
            transforms.extend([
                A.HorizontalFlip(p=0.5),
                A.VerticalFlip(p=0.5),
                A.Rotate(limit=15, p=0.5, border_mode=0),
                A.ColorJitter(
                    brightness=0.2,
                    contrast=0.2,
                    saturation=0.1,
                    hue=0.05,
                    p=0.3
                ),
            ])

        # Normalization
        if self.normalize == 'imagenet':
            transforms.append(
                A.Normalize(mean=self.IMAGENET_MEAN, std=self.IMAGENET_STD)
            )
        elif self.normalize == '0-1':
            transforms.append(
                A.Normalize(mean=[0.0, 0.0, 0.0], std=[1.0, 1.0, 1.0])
            )

        # Convert to tensor (always last)
        transforms.append(ToTensorV2())

        return A.Compose(transforms)

    def _report_class_distribution(self, sample_size: int = 100):
        """
        Sample masks and report class distribution.

        Args:
            sample_size: Number of masks to sample (or all if fewer exist)
        """
        sample_size = min(sample_size, len(self.image_files))

        # Sample evenly across dataset
        indices = np.linspace(0, len(self.image_files) - 1, sample_size, dtype=int)

        class_pixels = np.zeros(self.NUM_CLASSES)

        for idx in indices:
            mask_path = self.masks_dir / self.image_files[idx].name
            if mask_path.exists():
                mask = np.array(Image.open(mask_path))
                for class_id in range(self.NUM_CLASSES):
                    class_pixels[class_id] += np.sum(mask == class_id)

        total_pixels = class_pixels.sum()

        print(f"  Class distribution (sampled {sample_size} masks):")
        for class_id, class_name in enumerate(self.CLASS_NAMES):
            percentage = 100 * class_pixels[class_id] / total_pixels if total_pixels > 0 else 0
            print(f"    {class_name:12s}: {percentage:6.2f}%")

        # Warn about severe imbalance
        if total_pixels > 0:
            max_ratio = class_pixels.max() / (class_pixels.min() + 1e-10)
            if max_ratio > 100:
                print(f"  ⚠ Warning: Severe class imbalance detected (ratio: {max_ratio:.1f}:1)")
                print(f"    Consider using class weights or focal loss")

    def __len__(self) -> int:
        return len(self.image_files)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Load and return image and mask pair.

        Returns:
            image: Tensor of shape (3, H, W), normalized
            mask: Tensor of shape (H, W) with class indices (long dtype)
        """
        # Load image
        img_path = self.image_files[idx]
        image = Image.open(img_path).convert('RGB')
        image = np.array(image)

        # Load mask
        mask_path = self.masks_dir / img_path.name
        if not mask_path.exists():
            # Create empty mask if missing
            mask = np.zeros(image.shape[:2], dtype=np.uint8)
        else:
            mask = Image.open(mask_path)
            mask = np.array(mask, dtype=np.uint8)

        # Ensure mask is single channel
        if len(mask.shape) == 3:
            mask = mask[:, :, 0]

        # Apply transforms
        transformed = self.transform(image=image, mask=mask)
        image = transformed['image']
        mask = transformed['mask']

        # Convert mask to long tensor for cross-entropy loss
        mask = mask.long()

        return image, mask

    def get_sample_paths(self, idx: int) -> Tuple[Path, Path]:
        """Return file paths for a sample (useful for debugging)."""
        img_path = self.image_files[idx]
        mask_path = self.masks_dir / img_path.name
        return img_path, mask_path


def create_train_val_test_datasets(
    data_dir: str,
    train_split: float = 0.8,
    val_split: float = 0.1,
    test_split: float = 0.1,
    normalize: str = 'imagenet',
    seed: int = 42
) -> Tuple[MapSegmentationDataset, MapSegmentationDataset, MapSegmentationDataset]:
    """
    Create train/val/test datasets from a single directory.

    Assumes structure:
        data_dir/
            images/
                img1.png
                img2.png
                ...
            masks/
                img1.png
                img2.png
                ...

    Args:
        data_dir: Root directory containing images/ and masks/ subdirs
        train_split: Fraction of data for training
        val_split: Fraction of data for validation
        test_split: Fraction of data for testing
        normalize: Normalization strategy
        seed: Random seed for reproducibility

    Returns:
        train_dataset, val_dataset, test_dataset
    """
    data_dir = Path(data_dir)
    images_dir = data_dir / 'images'
    masks_dir = data_dir / 'masks'

    if not images_dir.exists() or not masks_dir.exists():
        raise ValueError(f"Expected {images_dir} and {masks_dir} to exist")

    # Get all image files
    all_images = sorted([f for f in images_dir.glob('*.png')])

    # Shuffle with seed
    np.random.seed(seed)
    indices = np.random.permutation(len(all_images))

    # Calculate split points
    n_train = int(len(all_images) * train_split)
    n_val = int(len(all_images) * val_split)

    train_indices = indices[:n_train]
    val_indices = indices[n_train:n_train + n_val]
    test_indices = indices[n_train + n_val:]

    # Create temporary directories for splits (symlinks would be better in production)
    import tempfile
    import shutil

    temp_dir = Path(tempfile.mkdtemp(prefix='map_seg_'))

    def create_split_dirs(split_name: str, split_indices: np.ndarray) -> Tuple[Path, Path]:
        split_images_dir = temp_dir / split_name / 'images'
        split_masks_dir = temp_dir / split_name / 'masks'
        split_images_dir.mkdir(parents=True, exist_ok=True)
        split_masks_dir.mkdir(parents=True, exist_ok=True)

        for idx in split_indices:
            src_img = all_images[idx]
            src_mask = masks_dir / src_img.name

            shutil.copy(src_img, split_images_dir / src_img.name)
            if src_mask.exists():
                shutil.copy(src_mask, split_masks_dir / src_img.name)

        return split_images_dir, split_masks_dir

    train_img_dir, train_mask_dir = create_split_dirs('train', train_indices)
    val_img_dir, val_mask_dir = create_split_dirs('val', val_indices)
    test_img_dir, test_mask_dir = create_split_dirs('test', test_indices)

    # Create datasets
    train_dataset = MapSegmentationDataset(
        train_img_dir, train_mask_dir,
        augment=True, normalize=normalize, split='train'
    )

    val_dataset = MapSegmentationDataset(
        val_img_dir, val_mask_dir,
        augment=False, normalize=normalize, split='val'
    )

    test_dataset = MapSegmentationDataset(
        test_img_dir, test_mask_dir,
        augment=False, normalize=normalize, split='test'
    )

    return train_dataset, val_dataset, test_dataset


# Compatibility aliases for train.py and evaluate.py
HistoricalMapDataset = MapSegmentationDataset


def get_transforms(image_size=512, augmentation=None, mean=None, std=None):
    """
    Get train and validation transforms.

    Compatibility wrapper for MapSegmentationDataset.

    Args:
        image_size: Image size (not used - dataset expects pre-sized images)
        augmentation: Dict of augmentation parameters (or None)
        mean: Mean for normalization (not used - uses ImageNet by default)
        std: Std for normalization (not used - uses ImageNet by default)

    Returns:
        train_transform: None (MapSegmentationDataset handles transforms internally)
        val_transform: None (MapSegmentationDataset handles transforms internally)
    """
    # MapSegmentationDataset handles transforms internally via augment parameter
    # Return None so the dataset uses its own transforms
    return None, None


if __name__ == '__main__':
    # Example usage
    import sys

    if len(sys.argv) < 2:
        print("Usage: python dataset.py <data_dir>")
        print("  data_dir should contain images/ and masks/ subdirectories")
        sys.exit(1)

    data_dir = sys.argv[1]

    print("Creating datasets...")
    train_ds, val_ds, test_ds = create_train_val_test_datasets(data_dir)

    print(f"\nDataset sizes:")
    print(f"  Train: {len(train_ds)}")
    print(f"  Val:   {len(val_ds)}")
    print(f"  Test:  {len(test_ds)}")

    # Test loading a sample
    print(f"\nTesting data loading...")
    img, mask = train_ds[0]
    print(f"  Image shape: {img.shape}, dtype: {img.dtype}")
    print(f"  Mask shape:  {mask.shape}, dtype: {mask.dtype}")
    print(f"  Mask classes present: {torch.unique(mask).tolist()}")
