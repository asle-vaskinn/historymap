"""
U-Net model for map segmentation.

Uses segmentation_models_pytorch library with pretrained encoders.
Supports multiple backbone architectures with ImageNet initialization.
"""

from typing import Optional
import torch
import torch.nn as nn
import segmentation_models_pytorch as smp


class UNet(nn.Module):
    """
    U-Net segmentation model with pretrained encoder.

    Wraps segmentation_models_pytorch.Unet for convenience and
    provides a consistent interface for the training pipeline.

    Args:
        encoder: Encoder backbone name (e.g., 'resnet34', 'resnet50', 'efficientnet-b0')
        encoder_weights: Pretrained weights to use ('imagenet' or None)
        classes: Number of output classes
        activation: Output activation function (None for raw logits)
        in_channels: Number of input channels (3 for RGB)

    Input:
        x: Tensor of shape (batch_size, 3, H, W)

    Output:
        logits: Tensor of shape (batch_size, classes, H, W)
    """

    def __init__(
        self,
        encoder: str = 'resnet34',
        encoder_weights: Optional[str] = 'imagenet',
        classes: int = 5,
        activation: Optional[str] = None,
        in_channels: int = 3
    ):
        super().__init__()

        self.encoder = encoder
        self.encoder_weights = encoder_weights
        self.classes = classes

        # Create U-Net model using segmentation_models_pytorch
        self.model = smp.Unet(
            encoder_name=encoder,
            encoder_weights=encoder_weights,
            in_channels=in_channels,
            classes=classes,
            activation=activation,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass.

        Args:
            x: Input tensor of shape (batch_size, 3, H, W)

        Returns:
            logits: Output tensor of shape (batch_size, classes, H, W)
        """
        return self.model(x)

    def get_encoder_params(self):
        """Get encoder parameters (for differential learning rates)."""
        return self.model.encoder.parameters()

    def get_decoder_params(self):
        """Get decoder parameters (for differential learning rates)."""
        params = list(self.model.decoder.parameters())
        params += list(self.model.segmentation_head.parameters())
        return params


def get_model(
    encoder: str = 'resnet34',
    pretrained: bool = True,
    classes: int = 5,
    device: Optional[torch.device] = None
) -> UNet:
    """
    Factory function to create and initialize U-Net model.

    Args:
        encoder: Encoder backbone name
        pretrained: Whether to use ImageNet pretrained weights
        classes: Number of output classes
        device: Device to move model to (defaults to CUDA if available)

    Returns:
        Initialized U-Net model on specified device
    """
    if device is None:
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    encoder_weights = 'imagenet' if pretrained else None

    model = UNet(
        encoder=encoder,
        encoder_weights=encoder_weights,
        classes=classes,
        activation=None  # Use raw logits for CrossEntropyLoss
    )

    model = model.to(device)

    # Count parameters
    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)

    print(f"\nModel: U-Net with {encoder} encoder")
    print(f"  Pretrained: {pretrained}")
    print(f"  Total parameters: {total_params:,}")
    print(f"  Trainable parameters: {trainable_params:,}")
    print(f"  Device: {device}")

    return model


class UNetPlusPlus(nn.Module):
    """
    U-Net++ (nested U-Net) for potentially better performance.

    Similar interface to UNet but with nested skip connections.
    """

    def __init__(
        self,
        encoder: str = 'resnet34',
        encoder_weights: Optional[str] = 'imagenet',
        classes: int = 5,
        activation: Optional[str] = None,
        in_channels: int = 3
    ):
        super().__init__()

        self.encoder = encoder
        self.encoder_weights = encoder_weights
        self.classes = classes

        self.model = smp.UnetPlusPlus(
            encoder_name=encoder,
            encoder_weights=encoder_weights,
            in_channels=in_channels,
            classes=classes,
            activation=activation,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.model(x)


class FPN(nn.Module):
    """
    Feature Pyramid Network for multi-scale feature extraction.

    Alternative architecture that may work better for certain map styles.
    """

    def __init__(
        self,
        encoder: str = 'resnet34',
        encoder_weights: Optional[str] = 'imagenet',
        classes: int = 5,
        activation: Optional[str] = None,
        in_channels: int = 3
    ):
        super().__init__()

        self.encoder = encoder
        self.encoder_weights = encoder_weights
        self.classes = classes

        self.model = smp.FPN(
            encoder_name=encoder,
            encoder_weights=encoder_weights,
            in_channels=in_channels,
            classes=classes,
            activation=activation,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.model(x)


def get_model_by_name(
    architecture: str = 'unet',
    encoder: str = 'resnet34',
    pretrained: bool = True,
    classes: int = 5,
    device: Optional[torch.device] = None
) -> nn.Module:
    """
    Factory function supporting multiple architectures.

    Args:
        architecture: Model architecture ('unet', 'unetplusplus', 'fpn')
        encoder: Encoder backbone name
        pretrained: Whether to use ImageNet pretrained weights
        classes: Number of output classes
        device: Device to move model to

    Returns:
        Initialized model on specified device
    """
    if device is None:
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    encoder_weights = 'imagenet' if pretrained else None

    architecture = architecture.lower()

    if architecture == 'unet':
        model = UNet(
            encoder=encoder,
            encoder_weights=encoder_weights,
            classes=classes
        )
    elif architecture == 'unetplusplus' or architecture == 'unet++':
        model = UNetPlusPlus(
            encoder=encoder,
            encoder_weights=encoder_weights,
            classes=classes
        )
    elif architecture == 'fpn':
        model = FPN(
            encoder=encoder,
            encoder_weights=encoder_weights,
            classes=classes
        )
    else:
        raise ValueError(f"Unknown architecture: {architecture}. "
                         f"Choose from: unet, unetplusplus, fpn")

    model = model.to(device)

    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)

    print(f"\nModel: {architecture.upper()} with {encoder} encoder")
    print(f"  Pretrained: {pretrained}")
    print(f"  Total parameters: {total_params:,}")
    print(f"  Trainable parameters: {trainable_params:,}")
    print(f"  Device: {device}")

    return model


if __name__ == '__main__':
    # Test model creation
    print("Testing model creation...")

    # Test different architectures
    architectures = ['unet', 'unetplusplus', 'fpn']
    encoders = ['resnet34', 'resnet50', 'efficientnet-b0']

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"\nUsing device: {device}")

    for arch in architectures[:1]:  # Test just U-Net
        for enc in encoders[:1]:  # Test just ResNet34
            print(f"\n{'='*60}")
            model = get_model_by_name(
                architecture=arch,
                encoder=enc,
                pretrained=True,
                classes=5,
                device=device
            )

            # Test forward pass
            batch_size = 2
            x = torch.randn(batch_size, 3, 256, 256).to(device)

            print(f"\nTesting forward pass:")
            print(f"  Input shape: {x.shape}")

            with torch.no_grad():
                output = model(x)

            print(f"  Output shape: {output.shape}")
            print(f"  Output range: [{output.min():.3f}, {output.max():.3f}]")

    print(f"\n{'='*60}")
    print("Model tests completed successfully!")
