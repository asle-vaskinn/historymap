"""
Realistic aging effects for historical map synthesis.

This module applies various aging effects to make rendered maps look like
historical documents from different eras. All effects are configurable and
reproducible via seed parameter.
"""

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageChops
from typing import Optional, Dict, Tuple
import warnings

from textures import TextureGenerator


# Era-specific presets
ERA_PRESETS = {
    "1880": {
        "name": "1880s Military Survey",
        "yellowing": 0.7,
        "sepia_tint": (1.0, 0.95, 0.7),  # RGB multipliers
        "blur": 0.8,
        "noise": 0.15,
        "paper_texture": 0.6,
        "ink_bleed": 0.4,
        "stains": 0.3,
        "fold_lines": 0.2,
        "edge_wear": 0.5,
        "ink_spots": 0.2,
    },
    "1900": {
        "name": "1900s Cadastral Map",
        "yellowing": 0.5,
        "sepia_tint": (1.0, 0.97, 0.85),
        "blur": 0.5,
        "noise": 0.12,
        "paper_texture": 0.5,
        "ink_bleed": 0.3,
        "stains": 0.2,
        "fold_lines": 0.15,
        "edge_wear": 0.4,
        "ink_spots": 0.15,
    },
    "1920": {
        "name": "1920s Topographic Map",
        "yellowing": 0.35,
        "sepia_tint": (1.0, 0.98, 0.90),
        "blur": 0.3,
        "noise": 0.08,
        "paper_texture": 0.4,
        "ink_bleed": 0.2,
        "stains": 0.15,
        "fold_lines": 0.1,
        "edge_wear": 0.3,
        "ink_spots": 0.1,
    },
    "1950": {
        "name": "1950s Modern Print",
        "yellowing": 0.2,
        "sepia_tint": (1.0, 0.99, 0.95),
        "blur": 0.15,
        "noise": 0.05,
        "paper_texture": 0.3,
        "ink_bleed": 0.1,
        "stains": 0.05,
        "fold_lines": 0.05,
        "edge_wear": 0.2,
        "ink_spots": 0.05,
    },
}


class MapAger:
    """Apply realistic aging effects to map images."""

    def __init__(self, seed: Optional[int] = None):
        """
        Initialize map ager.

        Args:
            seed: Random seed for reproducibility
        """
        self.seed = seed
        self.texture_gen = TextureGenerator(seed=seed)
        if seed is not None:
            np.random.seed(seed)

    def age_map(
        self,
        image: Image.Image,
        intensity: float = 0.5,
        style: str = "1900",
        custom_params: Optional[Dict[str, float]] = None
    ) -> Image.Image:
        """
        Apply comprehensive aging effects to a map image.

        Args:
            image: Input PIL Image (RGB or RGBA)
            intensity: Overall intensity of aging effects (0.0-1.0)
            style: Era preset name ("1880", "1900", "1920", "1950")
            custom_params: Optional dict to override specific parameters

        Returns:
            Aged PIL Image

        Example:
            >>> from PIL import Image
            >>> ager = MapAger(seed=42)
            >>> img = Image.open("modern_map.png")
            >>> aged = ager.age_map(img, intensity=0.7, style="1900")
            >>> aged.save("historical_map.png")
        """
        # Convert to RGB if needed
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # Get preset parameters
        if style not in ERA_PRESETS:
            warnings.warn(f"Unknown style '{style}', using '1900' as default")
            style = "1900"

        params = ERA_PRESETS[style].copy()

        # Apply custom parameter overrides
        if custom_params:
            params.update(custom_params)

        # Scale all parameters by intensity
        for key in params:
            if key != "name" and isinstance(params[key], (int, float)):
                params[key] = params[key] * intensity
            elif key == "sepia_tint":
                # Interpolate sepia tint based on intensity
                r, g, b = params[key]
                params[key] = (
                    1.0 - (1.0 - r) * intensity,
                    1.0 - (1.0 - g) * intensity,
                    1.0 - (1.0 - b) * intensity,
                )

        # Apply effects in order
        aged = image.copy()

        # 1. Print artifacts (blur and ink bleed)
        if params.get("blur", 0) > 0 or params.get("ink_bleed", 0) > 0:
            aged = self._apply_print_artifacts(aged, params)

        # 2. Color transformation (yellowing and sepia)
        if params.get("yellowing", 0) > 0 or params.get("sepia_tint"):
            aged = self._apply_color_aging(aged, params)

        # 3. Paper texture overlay
        if params.get("paper_texture", 0) > 0:
            aged = self._apply_paper_texture(aged, params["paper_texture"])

        # 4. Noise and grain
        if params.get("noise", 0) > 0:
            aged = self._apply_noise(aged, params["noise"])

        # 5. Stains (optional)
        if params.get("stains", 0) > 0:
            aged = self._apply_stains(aged, params["stains"])

        # 6. Ink spots
        if params.get("ink_spots", 0) > 0:
            aged = self._apply_ink_spots(aged, params["ink_spots"])

        # 7. Fold lines (optional)
        if params.get("fold_lines", 0) > 0:
            aged = self._apply_fold_lines(aged, params["fold_lines"])

        # 8. Edge wear
        if params.get("edge_wear", 0) > 0:
            aged = self._apply_edge_wear(aged, params["edge_wear"])

        return aged

    def _apply_print_artifacts(
        self,
        image: Image.Image,
        params: Dict[str, float]
    ) -> Image.Image:
        """Apply blur and ink bleed effects from old printing."""
        result = image.copy()

        # Gaussian blur for old printing
        blur_intensity = params.get("blur", 0)
        if blur_intensity > 0:
            radius = blur_intensity * 1.5
            result = result.filter(ImageFilter.GaussianBlur(radius=radius))

        # Ink bleed effect (slight expansion of dark areas)
        ink_bleed = params.get("ink_bleed", 0)
        if ink_bleed > 0:
            # Convert to numpy for processing
            img_array = np.array(result).astype(np.float32)

            # Calculate darkness (inverse of brightness)
            darkness = 255 - img_array.mean(axis=2)

            # Expand dark areas slightly
            from scipy.ndimage import grey_dilation
            try:
                dilated = grey_dilation(darkness, size=int(ink_bleed * 3 + 1))
                bleed_amount = (dilated - darkness) * ink_bleed * 0.3

                # Apply bleed (darken)
                for c in range(3):
                    img_array[:, :, c] -= bleed_amount

                img_array = np.clip(img_array, 0, 255)
                result = Image.fromarray(img_array.astype(np.uint8))
            except ImportError:
                # Fallback without scipy - just use blur
                pass

        return result

    def _apply_color_aging(
        self,
        image: Image.Image,
        params: Dict[str, float]
    ) -> Image.Image:
        """Apply yellowing and sepia tone."""
        img_array = np.array(image).astype(np.float32)
        height, width = img_array.shape[:2]

        # Get sepia tint multipliers
        r_mult, g_mult, b_mult = params.get("sepia_tint", (1.0, 1.0, 1.0))

        # Apply sepia tint
        img_array[:, :, 0] *= r_mult  # Red
        img_array[:, :, 1] *= g_mult  # Green
        img_array[:, :, 2] *= b_mult  # Blue

        # Non-uniform yellowing (edges more yellowed)
        yellowing = params.get("yellowing", 0)
        if yellowing > 0:
            # Create gradient from center to edges
            y_coords, x_coords = np.ogrid[:height, :width]
            center_y, center_x = height / 2, width / 2

            # Distance from center (normalized)
            dist = np.sqrt(
                ((x_coords - center_x) / width) ** 2 +
                ((y_coords - center_y) / height) ** 2
            )
            dist = dist / dist.max()

            # Yellowing increases toward edges
            yellow_factor = 1 + dist * yellowing * 0.3

            # Add yellow/brown tint (increase red, slight green, decrease blue)
            img_array[:, :, 0] *= yellow_factor * 1.1  # More red
            img_array[:, :, 1] *= yellow_factor * 1.05  # Slight green
            img_array[:, :, 2] *= yellow_factor * 0.9  # Less blue

            # Add slight color variance
            noise = np.random.normal(1.0, 0.02, (height, width))
            for c in range(3):
                img_array[:, :, c] *= noise

        img_array = np.clip(img_array, 0, 255)
        return Image.fromarray(img_array.astype(np.uint8))

    def _apply_paper_texture(
        self,
        image: Image.Image,
        intensity: float
    ) -> Image.Image:
        """Apply paper texture overlay."""
        width, height = image.size

        # Generate paper texture
        paper = self.texture_gen.generate_paper_texture(width, height, scale=1.0)

        # Convert paper to RGB
        paper_rgb = Image.merge('RGB', (paper, paper, paper))

        # Blend with original image using multiply mode
        # Paper texture darkens the image slightly
        result = ImageChops.multiply(image, paper_rgb)

        # Blend based on intensity
        result = Image.blend(image, result, intensity * 0.3)

        return result

    def _apply_noise(
        self,
        image: Image.Image,
        intensity: float
    ) -> Image.Image:
        """Apply film grain / paper surface noise."""
        width, height = image.size

        # Generate noise
        noise = self.texture_gen.generate_noise_pattern(width, height, intensity)

        # Convert to RGB
        noise_rgb = Image.merge('RGB', (noise, noise, noise))

        # Blend with original
        result = Image.blend(image, noise_rgb, intensity * 0.15)

        return result

    def _apply_stains(
        self,
        image: Image.Image,
        intensity: float
    ) -> Image.Image:
        """Apply random stains."""
        width, height = image.size

        # Generate stains
        num_stains = max(1, int(intensity * 5))
        max_size = int(min(width, height) * 0.2)

        stains = self.texture_gen.generate_stains(
            width, height,
            num_stains=num_stains,
            max_size=max_size
        )

        # Composite stains over image
        result = image.copy()
        result.paste(stains, (0, 0), stains)

        return result

    def _apply_ink_spots(
        self,
        image: Image.Image,
        intensity: float
    ) -> Image.Image:
        """Apply small ink spots."""
        width, height = image.size

        # Generate ink spots
        num_spots = max(1, int(intensity * 10))
        spots = self.texture_gen.generate_ink_spots(width, height, num_spots)

        # Composite over image
        result = image.copy()
        result.paste(spots, (0, 0), spots)

        return result

    def _apply_fold_lines(
        self,
        image: Image.Image,
        intensity: float
    ) -> Image.Image:
        """Apply fold line effects."""
        width, height = image.size

        # Generate fold lines
        num_folds = max(1, int(intensity * 3))
        folds = self.texture_gen.generate_fold_lines(width, height, num_folds)

        # Convert to RGB and apply as darkening
        folds_rgb = Image.merge('RGB', (folds, folds, folds))

        # Blend to create darkening effect
        result = ImageChops.multiply(image, folds_rgb)
        result = Image.blend(image, result, intensity * 0.3)

        return result

    def _apply_edge_wear(
        self,
        image: Image.Image,
        intensity: float
    ) -> Image.Image:
        """Apply edge darkening and wear."""
        width, height = image.size

        # Generate edge wear mask
        border_size = int(min(width, height) * 0.15)
        edge_wear = self.texture_gen.generate_edge_wear(
            width, height,
            border_size=border_size
        )

        # Convert to RGB
        edge_rgb = Image.merge('RGB', (edge_wear, edge_wear, edge_wear))

        # Apply as darkening
        result = ImageChops.multiply(image, edge_rgb)
        result = Image.blend(image, result, intensity * 0.4)

        return result


def age_map(
    image: Image.Image,
    intensity: float = 0.5,
    style: str = "1900",
    seed: Optional[int] = None,
    custom_params: Optional[Dict[str, float]] = None
) -> Image.Image:
    """
    Convenience function to age a map image.

    This is the main entry point for applying aging effects.

    Args:
        image: Input PIL Image (RGB or RGBA)
        intensity: Overall intensity of aging effects (0.0-1.0)
        style: Era preset name ("1880", "1900", "1920", "1950")
        seed: Random seed for reproducibility
        custom_params: Optional dict to override specific effect parameters

    Returns:
        Aged PIL Image

    Example:
        >>> from PIL import Image
        >>> from age_effects import age_map
        >>>
        >>> img = Image.open("modern_map.png")
        >>> aged = age_map(img, intensity=0.7, style="1900", seed=42)
        >>> aged.save("historical_map.png")
        >>>
        >>> # Custom parameters
        >>> custom = {"stains": 0.1, "fold_lines": 0.0}  # Reduce stains, remove folds
        >>> aged = age_map(img, intensity=0.5, style="1880", custom_params=custom)
    """
    ager = MapAger(seed=seed)
    return ager.age_map(image, intensity, style, custom_params)


def get_available_styles() -> Dict[str, str]:
    """
    Get available era presets.

    Returns:
        Dictionary mapping style IDs to descriptive names
    """
    return {
        style_id: params["name"]
        for style_id, params in ERA_PRESETS.items()
    }


def batch_age_maps(
    input_paths: list,
    output_dir: str,
    intensity: float = 0.5,
    style: str = "1900",
    seed: Optional[int] = None,
    parallel: bool = True
) -> None:
    """
    Age multiple maps in batch.

    Args:
        input_paths: List of input image paths
        output_dir: Directory to save aged images
        intensity: Aging intensity (0.0-1.0)
        style: Era preset
        seed: Base random seed (incremented for each image)
        parallel: Use multiprocessing if available
    """
    import os
    from pathlib import Path

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    def process_image(args):
        idx, input_path = args
        img_seed = None if seed is None else seed + idx

        try:
            img = Image.open(input_path)
            aged = age_map(img, intensity=intensity, style=style, seed=img_seed)

            # Save with same filename
            filename = Path(input_path).name
            output_file = output_path / filename
            aged.save(output_file)

            return f"✓ {filename}"
        except Exception as e:
            return f"✗ {Path(input_path).name}: {e}"

    if parallel:
        try:
            from multiprocessing import Pool, cpu_count
            with Pool(cpu_count()) as pool:
                results = pool.map(process_image, enumerate(input_paths))
        except ImportError:
            # Fallback to sequential
            results = [process_image((i, p)) for i, p in enumerate(input_paths)]
    else:
        results = [process_image((i, p)) for i, p in enumerate(input_paths)]

    # Print results
    for result in results:
        print(result)


if __name__ == "__main__":
    print("Age Effects Module")
    print("=" * 50)
    print("\nAvailable styles:")
    for style_id, name in get_available_styles().items():
        print(f"  {style_id}: {name}")
    print("\nUsage:")
    print("  from age_effects import age_map")
    print("  aged = age_map(image, intensity=0.7, style='1900', seed=42)")
