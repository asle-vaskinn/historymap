"""
Historical Map Aging Effects Package

This package provides realistic aging effects for synthetic historical map generation.
"""

from .age_effects import (
    age_map,
    MapAger,
    get_available_styles,
    batch_age_maps,
    ERA_PRESETS,
)

from .textures import TextureGenerator

__version__ = "1.0.0"
__all__ = [
    "age_map",
    "MapAger",
    "get_available_styles",
    "batch_age_maps",
    "ERA_PRESETS",
    "TextureGenerator",
]
