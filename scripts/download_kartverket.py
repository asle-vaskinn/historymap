#!/usr/bin/env python3
"""
Download historical maps from Kartverket via Geonorge API.

This script downloads historical maps for the Trondheim area from Kartverket's
map catalog (kartkatalog.geonorge.no). It focuses on:
- Amtskart (county maps) 1826-1916
- Topographic maps
- Cadastral maps

Maps are saved to ../data/kartverket/raw/ with metadata JSON files.

Usage:
    python download_kartverket.py --bbox 10.0,63.3,10.8,63.5
    python download_kartverket.py --place Trondheim
    python download_kartverket.py --resume
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode, quote

import requests
from tqdm import tqdm

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class KartverketDownloader:
    """Download historical maps from Kartverket/Geonorge."""

    # API endpoints
    SEARCH_API = "https://kartkatalog.geonorge.no/api/search"
    METADATA_API = "https://kartkatalog.geonorge.no/api/getdata"

    # Map series of interest
    MAP_SERIES = {
        'amtskart': ['Amtskart', 'amtskart', 'county map'],
        'topographic': ['Topografisk', 'topographic', 'gradteigskart'],
        'cadastral': ['Økonomisk', 'økonomisk kartverk', 'cadastral'],
    }

    # Trondheim default bounding box (approximate)
    TRONDHEIM_BBOX = (10.0, 63.3, 10.8, 63.5)  # (west, south, east, north)

    def __init__(self, output_dir: Path, resume: bool = True):
        """
        Initialize downloader.

        Args:
            output_dir: Directory to save downloaded maps
            resume: If True, skip already downloaded files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.resume = resume
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'HistoricalMapProject/1.0 (Educational Research)',
        })

        # Load or create download state
        self.state_file = self.output_dir / 'download_state.json'
        self.state = self._load_state()

    def _load_state(self) -> Dict:
        """Load download state from file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load state file: {e}")
        return {'downloaded': [], 'failed': [], 'last_update': None}

    def _save_state(self):
        """Save download state to file."""
        self.state['last_update'] = time.strftime('%Y-%m-%d %H:%M:%S')
        with open(self.state_file, 'w') as f:
            json.dump(self.state, f, indent=2)

    def search_maps(
        self,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        place_name: Optional[str] = None,
        map_types: Optional[List[str]] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Search for historical maps.

        Args:
            bbox: Bounding box (west, south, east, north) in WGS84
            place_name: Place name to search for
            map_types: List of map types to search (amtskart, topographic, cadastral)
            limit: Maximum number of results per query

        Returns:
            List of map metadata dictionaries
        """
        if bbox is None:
            bbox = self.TRONDHEIM_BBOX

        if map_types is None:
            map_types = list(self.MAP_SERIES.keys())

        all_results = []

        for map_type in map_types:
            keywords = self.MAP_SERIES.get(map_type, [])

            for keyword in keywords:
                results = self._search_by_keyword(keyword, bbox, place_name, limit)
                all_results.extend(results)
                logger.info(f"Found {len(results)} maps for keyword '{keyword}'")
                time.sleep(0.5)  # Rate limiting

        # Deduplicate by UUID
        unique_results = {r['uuid']: r for r in all_results}
        logger.info(f"Total unique maps found: {len(unique_results)}")

        return list(unique_results.values())

    def _search_by_keyword(
        self,
        keyword: str,
        bbox: Tuple[float, float, float, float],
        place_name: Optional[str],
        limit: int
    ) -> List[Dict]:
        """Search for maps by keyword."""
        params = {
            'text': keyword,
            'limit': limit,
            'facets[0]name': 'type',
            'facets[0]value': 'dataset',
        }

        # Add bounding box filter
        if bbox:
            west, south, east, north = bbox
            params['bbox'] = f"{west},{south},{east},{north}"

        # Add place name filter
        if place_name:
            params['text'] = f"{keyword} {place_name}"

        try:
            response = self.session.get(self.SEARCH_API, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            results = []
            for item in data.get('Results', []):
                # Filter for historical maps (look for year ranges in title/abstract)
                title = item.get('Title', '')
                abstract = item.get('Abstract', '')

                # Try to identify historical maps by date or keywords
                if self._is_historical_map(title, abstract):
                    results.append({
                        'uuid': item.get('Uuid', ''),
                        'title': title,
                        'abstract': abstract,
                        'organization': item.get('Organization', ''),
                        'type': item.get('Type', ''),
                        'theme': item.get('Theme', ''),
                        'thumbnail': item.get('ThumbnailUrl', ''),
                        'metadata_url': item.get('ShowDetailsUrl', ''),
                    })

            return results

        except Exception as e:
            logger.error(f"Search failed for keyword '{keyword}': {e}")
            return []

    def _is_historical_map(self, title: str, abstract: str) -> bool:
        """Check if a map is likely historical based on title/abstract."""
        text = (title + ' ' + abstract).lower()

        # Look for year ranges or keywords
        historical_keywords = [
            'historisk', 'historical',
            'amtskart', 'økonomisk kartverk',
            '1800', '1900', '19[0-9]{2}',  # Years
            'gammel', 'old',
        ]

        for keyword in historical_keywords:
            if keyword in text:
                return True

        return False

    def get_download_links(self, uuid: str) -> List[Dict]:
        """
        Get download links for a specific map.

        Args:
            uuid: Map UUID

        Returns:
            List of download link dictionaries with 'url', 'format', 'name'
        """
        try:
            # Get metadata
            url = f"{self.METADATA_API}/{uuid}"
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            metadata = response.json()

            links = []

            # Look for distribution URLs
            distributions = metadata.get('DistributionDetails', {}).get('Distributions', [])
            for dist in distributions:
                protocol = dist.get('Protocol', '').lower()
                url = dist.get('URL', '')
                format_name = dist.get('FormatName', '')

                # We want direct download links (HTTP/HTTPS)
                if protocol in ['www:download', 'http', 'https'] and url:
                    links.append({
                        'url': url,
                        'format': format_name,
                        'name': dist.get('Name', ''),
                        'organization': dist.get('Organization', ''),
                    })

            # Alternative: look for WMS/WCS services (could be downloaded as images)
            # For now, we focus on direct downloads

            return links

        except Exception as e:
            logger.error(f"Failed to get download links for {uuid}: {e}")
            return []

    def download_map(self, map_info: Dict, force: bool = False) -> Optional[Path]:
        """
        Download a map and save metadata.

        Args:
            map_info: Map metadata dictionary
            force: If True, re-download even if file exists

        Returns:
            Path to downloaded file, or None if failed
        """
        uuid = map_info['uuid']

        # Check if already downloaded
        if self.resume and not force and uuid in self.state['downloaded']:
            logger.info(f"Skipping {uuid} (already downloaded)")
            return None

        # Get download links
        links = self.get_download_links(uuid)
        if not links:
            logger.warning(f"No download links found for {uuid}")
            self.state['failed'].append({
                'uuid': uuid,
                'reason': 'no_download_links',
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
            })
            self._save_state()
            return None

        # Prefer certain formats
        preferred_formats = ['geotiff', 'tiff', 'tif', 'jpeg2000', 'jp2', 'png']
        selected_link = None

        for fmt in preferred_formats:
            for link in links:
                if fmt in link['format'].lower():
                    selected_link = link
                    break
            if selected_link:
                break

        # If no preferred format, take first available
        if not selected_link:
            selected_link = links[0]

        # Download file
        try:
            logger.info(f"Downloading {map_info['title']} ({selected_link['format']})")

            response = self.session.get(selected_link['url'], stream=True, timeout=60)
            response.raise_for_status()

            # Determine file extension
            format_lower = selected_link['format'].lower()
            if 'tif' in format_lower:
                ext = '.tif'
            elif 'jp2' in format_lower or 'jpeg2000' in format_lower:
                ext = '.jp2'
            elif 'png' in format_lower:
                ext = '.png'
            else:
                ext = '.dat'

            # Save file
            filename = f"{uuid}{ext}"
            filepath = self.output_dir / filename

            # Get file size for progress bar
            total_size = int(response.headers.get('content-length', 0))

            with open(filepath, 'wb') as f:
                if total_size > 0:
                    with tqdm(total=total_size, unit='B', unit_scale=True) as pbar:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                            pbar.update(len(chunk))
                else:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

            # Save metadata
            metadata = {
                'uuid': uuid,
                'title': map_info['title'],
                'abstract': map_info['abstract'],
                'organization': map_info['organization'],
                'type': map_info['type'],
                'theme': map_info['theme'],
                'thumbnail': map_info['thumbnail'],
                'download_url': selected_link['url'],
                'format': selected_link['format'],
                'download_timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'filename': filename,
            }

            metadata_path = self.output_dir / f"{uuid}_metadata.json"
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            # Update state
            self.state['downloaded'].append(uuid)
            self._save_state()

            logger.info(f"Successfully downloaded to {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"Failed to download {uuid}: {e}")
            self.state['failed'].append({
                'uuid': uuid,
                'reason': str(e),
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
            })
            self._save_state()
            return None

    def download_all(
        self,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        place_name: Optional[str] = None,
        map_types: Optional[List[str]] = None,
        max_maps: Optional[int] = None
    ):
        """
        Search and download all matching maps.

        Args:
            bbox: Bounding box (west, south, east, north)
            place_name: Place name to search
            map_types: List of map types
            max_maps: Maximum number of maps to download
        """
        logger.info("Searching for maps...")
        maps = self.search_maps(bbox, place_name, map_types)

        if not maps:
            logger.warning("No maps found matching criteria")
            return

        logger.info(f"Found {len(maps)} maps to download")

        if max_maps:
            maps = maps[:max_maps]
            logger.info(f"Limiting to {max_maps} maps")

        # Download each map
        successful = 0
        failed = 0

        for i, map_info in enumerate(maps, 1):
            logger.info(f"Processing {i}/{len(maps)}: {map_info['title']}")
            result = self.download_map(map_info)

            if result:
                successful += 1
            else:
                failed += 1

            # Rate limiting
            time.sleep(1)

        logger.info(f"Download complete: {successful} successful, {failed} failed")
        logger.info(f"Files saved to: {self.output_dir}")


def parse_bbox(bbox_str: str) -> Tuple[float, float, float, float]:
    """Parse bounding box string."""
    try:
        parts = [float(x.strip()) for x in bbox_str.split(',')]
        if len(parts) != 4:
            raise ValueError("Bounding box must have 4 values")
        return tuple(parts)
    except Exception as e:
        raise ValueError(f"Invalid bounding box format: {e}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Download historical maps from Kartverket',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download maps for Trondheim (default bbox)
  python download_kartverket.py

  # Download maps for specific bounding box
  python download_kartverket.py --bbox 10.0,63.3,10.8,63.5

  # Download maps by place name
  python download_kartverket.py --place "Trondheim"

  # Download only specific map types
  python download_kartverket.py --types amtskart topographic

  # Limit number of downloads
  python download_kartverket.py --max 10

  # Force re-download (ignore resume state)
  python download_kartverket.py --no-resume
        """
    )

    parser.add_argument(
        '--bbox',
        type=str,
        help='Bounding box: west,south,east,north (WGS84 decimal degrees)'
    )
    parser.add_argument(
        '--place',
        type=str,
        help='Place name to search for'
    )
    parser.add_argument(
        '--types',
        nargs='+',
        choices=['amtskart', 'topographic', 'cadastral'],
        help='Map types to download'
    )
    parser.add_argument(
        '--max',
        type=int,
        help='Maximum number of maps to download'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='../data/kartverket/raw',
        help='Output directory (default: ../data/kartverket/raw)'
    )
    parser.add_argument(
        '--no-resume',
        action='store_true',
        help='Do not resume previous downloads'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Parse bounding box
    bbox = None
    if args.bbox:
        try:
            bbox = parse_bbox(args.bbox)
        except ValueError as e:
            logger.error(str(e))
            sys.exit(1)

    # Resolve output directory (handle relative paths)
    script_dir = Path(__file__).parent
    output_dir = (script_dir / args.output).resolve()

    # Create downloader
    downloader = KartverketDownloader(
        output_dir=output_dir,
        resume=not args.no_resume
    )

    # Download maps
    try:
        downloader.download_all(
            bbox=bbox,
            place_name=args.place,
            map_types=args.types,
            max_maps=args.max
        )
    except KeyboardInterrupt:
        logger.info("Download interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Download failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
