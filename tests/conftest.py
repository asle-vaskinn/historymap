"""
Pytest configuration and fixtures for pipeline tests.

This file is automatically loaded by pytest and provides common fixtures
for all tests in the tests/ directory.

Usage:
    pytest tests/
    pytest tests/test_extract/ -v
    pytest tests/ -k "test_geo"
"""

import json
import sys
import tempfile
from pathlib import Path
from typing import Dict, Any

import pytest

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from constants import GEO, Source, SourceShort


# =============================================================================
# Directory Fixtures
# =============================================================================

@pytest.fixture
def temp_data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory structure.

    Creates:
        tmp_path/
        ├── sources/
        │   └── test_source/
        │       ├── raw/
        │       └── normalized/
        ├── merged/
        └── export/
    """
    sources_dir = tmp_path / 'sources' / 'test_source'
    (sources_dir / 'raw').mkdir(parents=True)
    (sources_dir / 'normalized').mkdir(parents=True)
    (tmp_path / 'merged').mkdir()
    (tmp_path / 'export').mkdir()

    return tmp_path


@pytest.fixture
def sample_geojson() -> Dict[str, Any]:
    """Sample GeoJSON FeatureCollection with buildings."""
    return {
        'type': 'FeatureCollection',
        'features': [
            {
                'type': 'Feature',
                'geometry': {
                    'type': 'Polygon',
                    'coordinates': [[
                        [10.4, 63.43],
                        [10.401, 63.43],
                        [10.401, 63.431],
                        [10.4, 63.431],
                        [10.4, 63.43]
                    ]]
                },
                'properties': {
                    '_src': 'test',
                    '_src_id': 'test-1',
                    'sd': 1900,
                    'ev': 'h'
                }
            },
            {
                'type': 'Feature',
                'geometry': {
                    'type': 'Polygon',
                    'coordinates': [[
                        [10.402, 63.43],
                        [10.403, 63.43],
                        [10.403, 63.431],
                        [10.402, 63.431],
                        [10.402, 63.43]
                    ]]
                },
                'properties': {
                    '_src': 'test',
                    '_src_id': 'test-2',
                    'sd': 1950,
                    'ev': 'm'
                }
            }
        ]
    }


@pytest.fixture
def sample_roads_geojson() -> Dict[str, Any]:
    """Sample GeoJSON FeatureCollection with roads."""
    return {
        'type': 'FeatureCollection',
        'features': [
            {
                'type': 'Feature',
                'geometry': {
                    'type': 'LineString',
                    'coordinates': [
                        [10.4, 63.43],
                        [10.41, 63.43],
                        [10.42, 63.43]
                    ]
                },
                'properties': {
                    '_src': 'test',
                    '_src_id': 'road-1',
                    'nm': 'Test Street',
                    'rt': 'residential'
                }
            }
        ]
    }


@pytest.fixture
def sample_water_geojson() -> Dict[str, Any]:
    """Sample GeoJSON FeatureCollection with water features."""
    return {
        'type': 'FeatureCollection',
        'features': [
            {
                'type': 'Feature',
                'geometry': {
                    'type': 'Polygon',
                    'coordinates': [[
                        [10.38, 63.42],
                        [10.42, 63.42],
                        [10.42, 63.44],
                        [10.38, 63.44],
                        [10.38, 63.42]
                    ]]
                },
                'properties': {
                    '_src': 'osm',
                    '_src_id': 'water-1',
                    'wtype': 'fjord',
                    'nm': 'Trondheimsfjorden'
                }
            }
        ]
    }


# =============================================================================
# File Fixtures
# =============================================================================

@pytest.fixture
def geojson_file(temp_data_dir: Path, sample_geojson: Dict) -> Path:
    """Write sample GeoJSON to a file."""
    path = temp_data_dir / 'sources' / 'test_source' / 'raw' / 'buildings.geojson'
    with open(path, 'w') as f:
        json.dump(sample_geojson, f)
    return path


@pytest.fixture
def merge_config() -> Dict[str, Any]:
    """Sample merge configuration."""
    return {
        'version': '1.0',
        'feature_type': 'building',
        'sources': {
            'osm': {
                'enabled': True,
                'path': 'data/sources/osm/normalized/buildings.geojson',
                'priority': 1,
                'trust_dates': True
            },
            'sefrak': {
                'enabled': True,
                'path': 'data/sources/sefrak/normalized/buildings.geojson',
                'priority': 2,
                'trust_dates': True
            }
        },
        'matching': {
            'iou_threshold': 0.3,
            'buffer_distance_m': 10
        },
        'output': 'data/merged/buildings_merged.geojson'
    }


# =============================================================================
# GeoContext Fixtures
# =============================================================================

@pytest.fixture
def geo():
    """Get the default GeoContext (Trondheim)."""
    return GEO


@pytest.fixture
def trondheim_bbox():
    """Trondheim bounding box."""
    return (10.2, 63.35, 10.6, 63.5)


# =============================================================================
# Helper Functions
# =============================================================================

def create_test_manifest(source_dir: Path, source_id: str = 'test') -> Path:
    """Create a test manifest file."""
    manifest = {
        'source_id': source_id,
        'stages': {
            'extracted': {
                'success': True,
                'completed_at': '2026-01-01T00:00:00Z',
                'count': 10
            }
        }
    }
    manifest_path = source_dir / 'manifest.json'
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f)
    return manifest_path
