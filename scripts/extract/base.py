"""
Base class for data extraction from external sources.

Extractors retrieve data from external APIs (OSM, NVDB) or run ML inference
on historical maps. The extracted data is saved to the raw/ directory for
subsequent processing by the combining pipeline.

Example:
    class OSMExtractor(BaseExtractor):
        def extract(self) -> Dict:
            # Fetch from Overpass API
            response = requests.get(...)
            return {'success': True, 'count': len(features)}

    extractor = OSMExtractor()
    result = extractor.run()
"""

import json
import sys
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

# Import constants
try:
    from constants import DATA_DIR, SOURCES_DIR
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from constants import DATA_DIR, SOURCES_DIR


class BaseExtractor(ABC):
    """Base class for data extraction from external sources.

    Subclasses must implement:
        - extract(): The actual extraction logic

    Attributes:
        source_id: Unique identifier for this source (e.g., 'osm', 'nvdb')
        feature_type: Type of features being extracted ('buildings', 'roads', 'water')
        data_dir: Base data directory
        raw_dir: Directory for raw extracted data
    """

    def __init__(
        self,
        source_id: str,
        feature_type: str = 'buildings',
        data_dir: Path = None
    ):
        """Initialize extractor.

        Args:
            source_id: Source identifier (e.g., 'osm', 'nvdb', 'ml_kartverket_1880')
            feature_type: Feature type ('buildings', 'roads', 'water')
            data_dir: Base data directory (defaults to DATA_DIR from constants)
        """
        self.source_id = source_id
        self.feature_type = feature_type
        self.data_dir = data_dir or DATA_DIR
        self.raw_dir = self.data_dir / 'sources' / source_id / 'raw'
        self._start_time: Optional[datetime] = None
        self._end_time: Optional[datetime] = None

    @property
    def manifest_path(self) -> Path:
        """Path to source manifest file."""
        return self.data_dir / 'sources' / self.source_id / 'manifest.json'

    @abstractmethod
    def extract(self) -> Dict[str, Any]:
        """Extract data from external source.

        Subclasses must implement this method to perform the actual extraction.
        The method should save extracted data to self.raw_dir and return
        a result dictionary.

        Returns:
            Dict with at minimum:
                - success: bool - Whether extraction succeeded
                - count: int - Number of features extracted
                - files: List[str] - Files created in raw_dir

            Optional fields:
                - message: str - Human-readable status message
                - error: str - Error message if success=False
                - duration_seconds: float - Time taken
        """
        pass

    def run(self) -> Dict[str, Any]:
        """Run extraction with manifest update.

        This method:
        1. Creates the raw directory if needed
        2. Records start time
        3. Calls extract()
        4. Records end time
        5. Updates the manifest

        Returns:
            Result dictionary from extract() with added timing info
        """
        # Create output directory
        self.raw_dir.mkdir(parents=True, exist_ok=True)

        # Record timing
        self._start_time = datetime.utcnow()

        try:
            result = self.extract()
        except Exception as e:
            result = {
                'success': False,
                'error': str(e),
                'count': 0,
                'files': []
            }

        self._end_time = datetime.utcnow()

        # Add timing
        duration = (self._end_time - self._start_time).total_seconds()
        result['duration_seconds'] = duration
        result['started_at'] = self._start_time.isoformat()
        result['completed_at'] = self._end_time.isoformat()

        # Update manifest
        self._update_manifest(result)

        return result

    def _update_manifest(self, result: Dict[str, Any]) -> None:
        """Update source manifest with extraction result.

        Args:
            result: Result dictionary from extract()
        """
        # Load existing manifest or create new
        manifest = self._load_manifest()

        # Initialize stages if not present
        if 'stages' not in manifest:
            manifest['stages'] = {}

        # Update extraction stage
        manifest['stages']['extracted'] = {
            'success': result.get('success', False),
            'completed_at': result.get('completed_at'),
            'duration_seconds': result.get('duration_seconds'),
            'count': result.get('count', 0),
            'files': result.get('files', [])
        }

        if not result.get('success'):
            manifest['stages']['extracted']['error'] = result.get('error', 'Unknown error')

        # Update source metadata
        manifest['source_id'] = self.source_id
        manifest['feature_type'] = self.feature_type
        manifest['last_extracted'] = result.get('completed_at')

        # Save manifest
        self._save_manifest(manifest)

    def _load_manifest(self) -> Dict[str, Any]:
        """Load source manifest, returning empty dict if not found."""
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path) as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {}

    def _save_manifest(self, manifest: Dict[str, Any]) -> None:
        """Save source manifest."""
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)

    def needs_extraction(self, max_age_hours: float = 24) -> bool:
        """Check if extraction is needed.

        Args:
            max_age_hours: Maximum age of extraction before refresh needed

        Returns:
            True if extraction is needed (never run, too old, or failed)
        """
        manifest = self._load_manifest()

        extracted = manifest.get('stages', {}).get('extracted', {})

        # Never extracted
        if not extracted.get('completed_at'):
            return True

        # Last extraction failed
        if not extracted.get('success'):
            return True

        # Check age
        try:
            completed = datetime.fromisoformat(extracted['completed_at'])
            age_hours = (datetime.utcnow() - completed).total_seconds() / 3600
            return age_hours > max_age_hours
        except (ValueError, KeyError):
            return True

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(source_id='{self.source_id}', feature_type='{self.feature_type}')"
