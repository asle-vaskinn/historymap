#!/usr/bin/env python3
"""
Base class for data ingestion.
"""

import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class BaseIngestor(ABC):
    """Base class for source-specific data ingestors."""

    def __init__(self, source_id: str, data_dir: Optional[Path] = None):
        self.source_id = source_id
        self.data_dir = data_dir or Path(__file__).parent.parent.parent / 'data'
        self.source_dir = self.data_dir / 'sources' / source_id
        self.raw_dir = self.source_dir / 'raw'
        self.manifest_path = self.source_dir / 'manifest.json'

        # Ensure directories exist
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def load_manifest(self) -> Dict:
        """Load the source manifest."""
        if self.manifest_path.exists():
            with open(self.manifest_path) as f:
                return json.load(f)
        return {}

    def save_manifest(self, manifest: Dict) -> None:
        """Save the source manifest."""
        with open(self.manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)

    def update_manifest(self, raw_files: List[str], record_count: int,
                        version: Optional[str] = None, notes: Optional[str] = None) -> None:
        """Update manifest after ingestion."""
        manifest = self.load_manifest()
        manifest.update({
            'ingested_at': datetime.utcnow().isoformat() + 'Z',
            'raw_files': raw_files,
            'record_count': record_count,
        })
        if version:
            manifest['version'] = version
        if notes:
            manifest['notes'] = notes
        self.save_manifest(manifest)

    @abstractmethod
    def ingest(self) -> Dict:
        """
        Perform the ingestion.

        Returns:
            Dict with keys:
                - success: bool
                - files: List[str] - raw files created
                - count: int - number of records
                - message: str - status message
        """
        pass

    def run(self) -> bool:
        """Run the ingestion and update manifest."""
        print(f"Ingesting {self.source_id}...")

        try:
            result = self.ingest()

            if result['success']:
                self.update_manifest(
                    raw_files=result.get('files', []),
                    record_count=result.get('count', 0),
                    version=result.get('version'),
                    notes=result.get('notes')
                )
                print(f"  Success: {result['message']}")
                print(f"  Files: {result.get('files', [])}")
                print(f"  Records: {result.get('count', 0)}")
                return True
            else:
                print(f"  Failed: {result['message']}")
                return False

        except Exception as e:
            print(f"  Error: {e}")
            return False
