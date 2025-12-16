"""
Procedural texture generation for aging effects.

This module generates realistic paper textures, noise patterns, and stains
to make synthetic maps look like historical documents.
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from typing import Tuple, Optional
import random


class TextureGenerator:
    """Generate procedural textures for aging effects."""

    def __init__(self, seed: Optional[int] = None):
        """
        Initialize texture generator.

        Args:
            seed: Random seed for reproducibility
        """
        self.seed = seed
        if seed is not None:
            np.random.seed(seed)
            random.seed(seed)

    def generate_paper_texture(
        self,
        width: int,
        height: int,
        scale: float = 1.0
    ) -> Image.Image:
        """
        Generate realistic paper texture with fibers and grain.

        Args:
            width: Texture width in pixels
            height: Texture height in pixels
            scale: Scale of texture details (0.5-2.0)

        Returns:
            Grayscale PIL Image of paper texture
        """
        # Create base noise using multiple octaves
        texture = np.zeros((height, width), dtype=np.float32)

        # Multiple noise layers for realistic paper grain
        octaves = [
            (1, 0.3),   # Large scale variations
            (2, 0.2),   # Medium grain
            (4, 0.15),  # Fine grain
            (8, 0.1),   # Very fine fibers
        ]

        for freq, amp in octaves:
            freq_scaled = int(freq * scale)
            if freq_scaled < 1:
                freq_scaled = 1

            noise = self._perlin_noise(height, width, freq_scaled)
            texture += noise * amp

        # Add directional paper fibers
        fiber_texture = self._generate_fibers(height, width, scale)
        texture += fiber_texture * 0.15

        # Normalize to 0-255 range, centered around light gray
        texture = (texture - texture.min()) / (texture.max() - texture.min())
        texture = texture * 30 + 225  # Range: 225-255 (light)

        texture = np.clip(texture, 0, 255).astype(np.uint8)

        return Image.fromarray(texture, mode='L')

    def _perlin_noise(
        self,
        height: int,
        width: int,
        frequency: int
    ) -> np.ndarray:
        """
        Generate Perlin-like noise pattern.

        Args:
            height: Height in pixels
            width: Width in pixels
            frequency: Frequency of noise pattern

        Returns:
            Numpy array with noise values
        """
        # Simplified Perlin noise using interpolation
        grid_h = max(1, height // frequency)
        grid_w = max(1, width // frequency)

        # Generate random grid
        grid = np.random.randn(grid_h + 1, grid_w + 1).astype(np.float32)

        # Interpolate to full size
        from scipy.ndimage import zoom
        try:
            noise = zoom(grid, (height / grid_h, width / grid_w), order=1)
        except ImportError:
            # Fallback if scipy not available - use simple nearest neighbor
            noise = np.repeat(np.repeat(grid, frequency, axis=0), frequency, axis=1)
            noise = noise[:height, :width]

        return noise

    def _generate_fibers(
        self,
        height: int,
        width: int,
        scale: float
    ) -> np.ndarray:
        """
        Generate directional paper fiber texture.

        Args:
            height: Height in pixels
            width: Width in pixels
            scale: Scale factor

        Returns:
            Numpy array with fiber texture
        """
        fibers = np.zeros((height, width), dtype=np.float32)

        # Add horizontal and slight diagonal streaks
        num_fibers = int(height * 0.3 * scale)

        for _ in range(num_fibers):
            y = np.random.randint(0, height)
            thickness = np.random.randint(1, 3)
            intensity = np.random.uniform(0.1, 0.3)

            # Horizontal fiber with slight wave
            for x in range(width):
                wave = int(np.sin(x / 50.0) * 2)
                y_pos = (y + wave) % height

                for dy in range(thickness):
                    if y_pos + dy < height:
                        fibers[y_pos + dy, x] += intensity

        return fibers

    def generate_noise_pattern(
        self,
        width: int,
        height: int,
        intensity: float = 0.1
    ) -> Image.Image:
        """
        Generate random noise pattern (film grain effect).

        Args:
            width: Width in pixels
            height: Height in pixels
            intensity: Noise intensity (0.0-1.0)

        Returns:
            Grayscale PIL Image of noise
        """
        # Generate Gaussian noise
        noise = np.random.normal(128, intensity * 50, (height, width))
        noise = np.clip(noise, 0, 255).astype(np.uint8)

        return Image.fromarray(noise, mode='L')

    def generate_stains(
        self,
        width: int,
        height: int,
        num_stains: int = 3,
        max_size: int = 100
    ) -> Image.Image:
        """
        Generate random stain patterns.

        Args:
            width: Width in pixels
            height: Height in pixels
            num_stains: Number of stains to generate
            max_size: Maximum stain diameter

        Returns:
            RGBA PIL Image with stains (transparent background)
        """
        stain_img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(stain_img)

        for _ in range(num_stains):
            # Random position
            x = np.random.randint(0, width)
            y = np.random.randint(0, height)

            # Random size
            size = np.random.randint(max_size // 4, max_size)

            # Random color (brownish stains)
            r = np.random.randint(120, 160)
            g = np.random.randint(80, 120)
            b = np.random.randint(40, 80)

            # Random opacity
            alpha = np.random.randint(10, 40)

            # Draw irregular stain (multiple overlapping circles)
            num_circles = np.random.randint(3, 8)
            for _ in range(num_circles):
                offset_x = np.random.randint(-size//3, size//3)
                offset_y = np.random.randint(-size//3, size//3)
                circle_size = size // 2 + np.random.randint(-size//4, size//4)

                bbox = [
                    x + offset_x - circle_size,
                    y + offset_y - circle_size,
                    x + offset_x + circle_size,
                    y + offset_y + circle_size
                ]

                draw.ellipse(bbox, fill=(r, g, b, alpha))

        # Blur stains for more realistic look
        stain_img = stain_img.filter(ImageFilter.GaussianBlur(radius=3))

        return stain_img

    def generate_fold_lines(
        self,
        width: int,
        height: int,
        num_folds: int = 2
    ) -> Image.Image:
        """
        Generate fold line patterns.

        Args:
            width: Width in pixels
            height: Height in pixels
            num_folds: Number of fold lines

        Returns:
            Grayscale PIL Image with fold lines
        """
        fold_img = Image.new('L', (width, height), 255)
        draw = ImageDraw.Draw(fold_img)

        for _ in range(num_folds):
            # Random orientation
            if np.random.random() > 0.5:
                # Vertical fold
                x = np.random.randint(width // 4, 3 * width // 4)

                # Draw line with some waviness
                points = []
                for y in range(0, height, 5):
                    offset = int(np.sin(y / 100.0) * 5)
                    points.append((x + offset, y))

                # Draw thick line
                for i in range(len(points) - 1):
                    draw.line([points[i], points[i + 1]], fill=180, width=3)
            else:
                # Horizontal fold
                y = np.random.randint(height // 4, 3 * height // 4)

                # Draw line with some waviness
                points = []
                for x in range(0, width, 5):
                    offset = int(np.sin(x / 100.0) * 5)
                    points.append((x, y + offset))

                # Draw thick line
                for i in range(len(points) - 1):
                    draw.line([points[i], points[i + 1]], fill=180, width=3)

        # Blur for softer look
        fold_img = fold_img.filter(ImageFilter.GaussianBlur(radius=2))

        return fold_img

    def generate_ink_spots(
        self,
        width: int,
        height: int,
        num_spots: int = 5
    ) -> Image.Image:
        """
        Generate small ink spots and blots.

        Args:
            width: Width in pixels
            height: Height in pixels
            num_spots: Number of ink spots

        Returns:
            RGBA PIL Image with ink spots
        """
        spot_img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(spot_img)

        for _ in range(num_spots):
            # Random position
            x = np.random.randint(0, width)
            y = np.random.randint(0, height)

            # Small size
            size = np.random.randint(2, 8)

            # Dark ink color
            alpha = np.random.randint(30, 80)

            # Draw irregular spot
            num_circles = np.random.randint(1, 4)
            for _ in range(num_circles):
                offset_x = np.random.randint(-size//2, size//2)
                offset_y = np.random.randint(-size//2, size//2)

                bbox = [
                    x + offset_x - size,
                    y + offset_y - size,
                    x + offset_x + size,
                    y + offset_y + size
                ]

                draw.ellipse(bbox, fill=(20, 20, 20, alpha))

        return spot_img

    def generate_edge_wear(
        self,
        width: int,
        height: int,
        border_size: int = 50
    ) -> Image.Image:
        """
        Generate edge darkening/wear effect.

        Args:
            width: Width in pixels
            height: Height in pixels
            border_size: Size of darkened border area

        Returns:
            Grayscale PIL Image (darker at edges)
        """
        # Create gradient from edges
        edge_img = np.ones((height, width), dtype=np.float32) * 255

        # Create distance from edge
        for y in range(height):
            for x in range(width):
                # Distance from nearest edge
                dist = min(x, y, width - x - 1, height - y - 1)

                if dist < border_size:
                    # Darken based on distance
                    factor = dist / border_size
                    # Smooth curve
                    factor = factor ** 0.5
                    edge_img[y, x] = 255 - (1 - factor) * 40

        # Add some noise to edge wear
        noise = np.random.normal(0, 5, (height, width))
        edge_img += noise

        edge_img = np.clip(edge_img, 0, 255).astype(np.uint8)

        return Image.fromarray(edge_img, mode='L')


# Helper function for quick texture preview
def preview_texture(texture_name: str, width: int = 512, height: int = 512):
    """
    Generate and save a preview of a specific texture.

    Args:
        texture_name: Name of texture to preview
        width: Preview width
        height: Preview height
    """
    gen = TextureGenerator(seed=42)

    textures = {
        'paper': gen.generate_paper_texture,
        'noise': gen.generate_noise_pattern,
        'stains': gen.generate_stains,
        'folds': gen.generate_fold_lines,
        'ink_spots': gen.generate_ink_spots,
        'edge_wear': gen.generate_edge_wear,
    }

    if texture_name not in textures:
        print(f"Unknown texture: {texture_name}")
        print(f"Available: {', '.join(textures.keys())}")
        return

    print(f"Generating {texture_name} texture...")
    texture = textures[texture_name](width, height)

    output_path = f"texture_preview_{texture_name}.png"
    texture.save(output_path)
    print(f"Saved to {output_path}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        texture_name = sys.argv[1]
        preview_texture(texture_name)
    else:
        print("Usage: python textures.py <texture_name>")
        print("Available textures: paper, noise, stains, folds, ink_spots, edge_wear")
        print("\nGenerating all textures...")

        for name in ['paper', 'noise', 'stains', 'folds', 'ink_spots', 'edge_wear']:
            preview_texture(name)
