"""
Custom loss functions for semantic segmentation.

Includes:
- Dice Loss: Good for imbalanced classes, focuses on overlap
- Focal Loss: Reduces weight of easy examples, focuses on hard negatives
- Combined Loss: Dice + Cross Entropy for balanced training
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class DiceLoss(nn.Module):
    """
    Dice Loss for semantic segmentation.

    Measures overlap between prediction and target.
    Better for imbalanced datasets than Cross Entropy.

    Formula: 1 - (2 * |X ∩ Y| + smooth) / (|X| + |Y| + smooth)
    """

    def __init__(self, smooth=1.0, ignore_index=-100):
        super(DiceLoss, self).__init__()
        self.smooth = smooth
        self.ignore_index = ignore_index

    def forward(self, pred, target):
        """
        Args:
            pred: (N, C, H, W) logits
            target: (N, H, W) class indices

        Returns:
            Scalar loss value
        """
        # Convert logits to probabilities
        pred = F.softmax(pred, dim=1)

        # One-hot encode target
        num_classes = pred.shape[1]
        target_one_hot = F.one_hot(target, num_classes=num_classes)
        target_one_hot = target_one_hot.permute(0, 3, 1, 2).float()

        # Flatten spatial dimensions
        pred = pred.contiguous().view(pred.size(0), pred.size(1), -1)
        target_one_hot = target_one_hot.contiguous().view(target_one_hot.size(0), target_one_hot.size(1), -1)

        # Calculate intersection and union
        intersection = (pred * target_one_hot).sum(dim=2)
        union = pred.sum(dim=2) + target_one_hot.sum(dim=2)

        # Dice coefficient per class
        dice = (2.0 * intersection + self.smooth) / (union + self.smooth)

        # Average over batch and classes
        dice_loss = 1.0 - dice.mean()

        return dice_loss


class FocalLoss(nn.Module):
    """
    Focal Loss for semantic segmentation.

    Reduces weight of easy examples, focusing on hard negatives.
    Useful when there's significant class imbalance.

    Formula: -α(1-p)^γ * log(p)
    """

    def __init__(self, alpha=1.0, gamma=2.0, ignore_index=-100):
        super(FocalLoss, self).__init__()
        self.alpha = alpha
        self.gamma = gamma
        self.ignore_index = ignore_index

    def forward(self, pred, target):
        """
        Args:
            pred: (N, C, H, W) logits
            target: (N, H, W) class indices

        Returns:
            Scalar loss value
        """
        # Cross entropy loss (no reduction)
        ce_loss = F.cross_entropy(pred, target, reduction='none', ignore_index=self.ignore_index)

        # Get probabilities
        p = torch.exp(-ce_loss)

        # Focal loss formula
        focal_loss = self.alpha * (1 - p) ** self.gamma * ce_loss

        return focal_loss.mean()


class CombinedLoss(nn.Module):
    """
    Combined Dice + Cross Entropy Loss.

    Combines the benefits of both losses:
    - Dice: Good overlap, handles imbalance
    - CE: Stable gradients, well-understood

    Default weight: 50% Dice, 50% Cross Entropy
    """

    def __init__(self, dice_weight=0.5, ce_weight=0.5, smooth=1.0, ignore_index=-100):
        super(CombinedLoss, self).__init__()
        self.dice_weight = dice_weight
        self.ce_weight = ce_weight
        self.dice_loss = DiceLoss(smooth=smooth, ignore_index=ignore_index)
        self.ce_loss = nn.CrossEntropyLoss(ignore_index=ignore_index)

    def forward(self, pred, target):
        """
        Args:
            pred: (N, C, H, W) logits
            target: (N, H, W) class indices

        Returns:
            Scalar loss value
        """
        dice = self.dice_loss(pred, target)
        ce = self.ce_loss(pred, target)

        return self.dice_weight * dice + self.ce_weight * ce


def get_loss_function(loss_name, **kwargs):
    """
    Factory function to get loss by name.

    Args:
        loss_name: One of 'dice', 'focal', 'ce', 'combined'
        **kwargs: Additional arguments for loss function

    Returns:
        Loss function instance

    Example:
        >>> loss_fn = get_loss_function('dice', smooth=1.0)
        >>> loss_fn = get_loss_function('combined', dice_weight=0.6, ce_weight=0.4)
    """
    losses = {
        'dice': DiceLoss,
        'focal': FocalLoss,
        'ce': nn.CrossEntropyLoss,
        'combined': CombinedLoss,
    }

    if loss_name not in losses:
        raise ValueError(f"Unknown loss: {loss_name}. Choose from {list(losses.keys())}")

    return losses[loss_name](**kwargs)
