#!/usr/bin/env python3
"""
Export Manifest Generator - Cache busting support.

Generates a manifest.json with file hashes and timestamps for all exported files.
The frontend fetches this manifest and appends version parameters to data URLs.

Usage:
    python scripts/export/export_manifest.py
    python scripts/export/export_manifest.py --export-dir data/export
"""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

# Import constants
try:
    from constants import EXPORT_DIR, EXPORT_MANIFEST
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from constants import EXPORT_DIR, EXPORT_MANIFEST


def compute_file_hash(path: Path, algorithm: str = 'sha256') -> str:
    """Compute hash of file contents.

    Args:
        path: Path to file
        algorithm: Hash algorithm (default: sha256)

    Returns:
        Hex digest of file hash (first 12 chars for brevity)
    """
    h = hashlib.new(algorithm)
    with open(path, 'rb') as f:
        # Read in chunks for large files
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()[:12]


def generate_manifest(export_dir: Path, output_path: Path = None) -> Dict[str, Any]:
    """Generate manifest with file info for cache busting.

    Args:
        export_dir: Directory containing exported files
        output_path: Where to write manifest (default: export_dir/manifest.json)

    Returns:
        Manifest dict
    """
    if output_path is None:
        output_path = export_dir / 'manifest.json'

    manifest = {
        'version': '1.0',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'files': {}
    }

    # Track all exported data files
    patterns = ['*.geojson', '*.pmtiles', '*.json']

    for pattern in patterns:
        for path in export_dir.glob(pattern):
            # Skip manifest itself
            if path.name == 'manifest.json':
                continue
            # Skip metadata files
            if path.name.endswith('.meta.json'):
                continue

            try:
                stat = path.stat()
                file_info = {
                    'size': stat.st_size,
                    'mtime': int(stat.st_mtime),
                    'hash': compute_file_hash(path),
                }
                # Use just filename for frontend compatibility
                manifest['files'][path.name] = file_info
            except Exception as e:
                print(f"Warning: Failed to process {path}: {e}")

    # Generate version string from newest file
    if manifest['files']:
        newest_mtime = max(f['mtime'] for f in manifest['files'].values())
        manifest['build_version'] = str(newest_mtime)
    else:
        manifest['build_version'] = str(int(datetime.now(timezone.utc).timestamp()))

    # Write manifest
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(manifest, f, indent=2)

    print(f"Generated manifest: {output_path}")
    print(f"  Files: {len(manifest['files'])}")
    print(f"  Build version: {manifest['build_version']}")

    return manifest


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Generate export manifest for cache busting'
    )
    parser.add_argument(
        '--export-dir', '-d',
        type=Path,
        default=EXPORT_DIR,
        help=f'Export directory (default: {EXPORT_DIR})'
    )
    parser.add_argument(
        '--output', '-o',
        type=Path,
        default=None,
        help='Output manifest path (default: export_dir/manifest.json)'
    )

    args = parser.parse_args()

    if not args.export_dir.exists():
        print(f"Error: Export directory not found: {args.export_dir}")
        sys.exit(1)

    manifest = generate_manifest(args.export_dir, args.output)

    # Print summary
    print("\nFiles in manifest:")
    for name, info in manifest['files'].items():
        size_kb = info['size'] / 1024
        print(f"  {name}: {size_kb:.1f}KB (hash: {info['hash']})")


if __name__ == '__main__':
    main()
