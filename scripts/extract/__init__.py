"""
Extraction Pipeline - Data extraction from external sources.

The extraction pipeline retrieves data from external sources before the
combining pipeline (Ingest -> Normalize -> Merge -> Export) processes it.

Extractors:
- OSMExtractor: Extract features from OpenStreetMap via Overpass API
- NVDBExtractor: Extract road network from Norwegian road database
- MLExtractor: Run ML inference and vectorization on historical maps

Usage:
    from extract import OSMExtractor, NVDBExtractor, run_extraction

    # Extract OSM buildings
    osm = OSMExtractor(feature_type='buildings')
    result = osm.run()

    # Extract NVDB roads
    nvdb = NVDBExtractor()
    result = nvdb.run()

    # Run all extractors
    from extract import run_extraction
    results = run_extraction(sources=['osm', 'nvdb'])
"""

from .base import BaseExtractor
from .extract_osm import OSMExtractor
from .extract_nvdb import NVDBExtractor
from .orchestrate import run_extraction, get_extractors

__all__ = [
    'BaseExtractor',
    'OSMExtractor',
    'NVDBExtractor',
    'run_extraction',
    'get_extractors',
]
