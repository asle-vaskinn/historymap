"""
Utility functions for tile coordinate conversions and PMTiles reading.

This module provides helper functions for:
- Converting between tile coordinates (z/x/y) and geographic coordinates (lat/lon)
- Web Mercator projection calculations
- Reading vector tile data from PMTiles archives
- Parsing and processing vector tile geometries
"""

import math
from typing import Tuple, List, Dict, Optional, Any
import struct


class TileCoordinates:
    """Handle conversions between tile coordinates and geographic coordinates."""

    EARTH_RADIUS = 6378137.0  # Earth radius in meters (WGS84)
    EARTH_CIRCUMFERENCE = 2 * math.pi * EARTH_RADIUS

    @staticmethod
    def tile_to_bbox(z: int, x: int, y: int) -> Tuple[float, float, float, float]:
        """
        Convert tile coordinates to geographic bounding box.

        Args:
            z: Zoom level (0-22)
            x: Tile X coordinate
            y: Tile Y coordinate

        Returns:
            Tuple of (min_lon, min_lat, max_lon, max_lat) in degrees
        """
        n = 2.0 ** z

        # Calculate longitude
        min_lon = x / n * 360.0 - 180.0
        max_lon = (x + 1) / n * 360.0 - 180.0

        # Calculate latitude using inverse Mercator projection
        min_lat = TileCoordinates._mercator_to_lat(math.pi * (1 - 2 * (y + 1) / n))
        max_lat = TileCoordinates._mercator_to_lat(math.pi * (1 - 2 * y / n))

        return (min_lon, min_lat, max_lon, max_lat)

    @staticmethod
    def _mercator_to_lat(y_rad: float) -> float:
        """Convert Mercator Y coordinate (radians) to latitude."""
        return math.degrees(math.atan(math.sinh(y_rad)))

    @staticmethod
    def tile_to_meters(z: int, x: int, y: int) -> Tuple[float, float, float, float]:
        """
        Convert tile coordinates to Web Mercator bounds in meters.

        Args:
            z: Zoom level
            x: Tile X coordinate
            y: Tile Y coordinate

        Returns:
            Tuple of (min_x, min_y, max_x, max_y) in meters
        """
        n = 2.0 ** z
        tile_size = TileCoordinates.EARTH_CIRCUMFERENCE / n

        min_x = -TileCoordinates.EARTH_CIRCUMFERENCE / 2 + x * tile_size
        max_x = min_x + tile_size
        max_y = TileCoordinates.EARTH_CIRCUMFERENCE / 2 - y * tile_size
        min_y = max_y - tile_size

        return (min_x, min_y, max_x, max_y)

    @staticmethod
    def lonlat_to_tile(lon: float, lat: float, zoom: int) -> Tuple[int, int]:
        """
        Convert longitude/latitude to tile coordinates at given zoom level.

        Args:
            lon: Longitude in degrees
            lat: Latitude in degrees
            zoom: Zoom level

        Returns:
            Tuple of (tile_x, tile_y)
        """
        n = 2.0 ** zoom

        x = int((lon + 180.0) / 360.0 * n)

        lat_rad = math.radians(lat)
        y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)

        return (x, y)

    @staticmethod
    def get_tile_center(z: int, x: int, y: int) -> Tuple[float, float]:
        """
        Get the center point of a tile in lon/lat coordinates.

        Args:
            z: Zoom level
            x: Tile X coordinate
            y: Tile Y coordinate

        Returns:
            Tuple of (lon, lat) in degrees
        """
        bbox = TileCoordinates.tile_to_bbox(z, x, y)
        center_lon = (bbox[0] + bbox[2]) / 2
        center_lat = (bbox[1] + bbox[3]) / 2
        return (center_lon, center_lat)


class PMTilesReader:
    """
    Simple reader for PMTiles format.

    Note: For production use, consider using the official pmtiles library.
    This is a minimal implementation for reading basic tile data.
    """

    def __init__(self, filepath: str):
        """
        Initialize PMTiles reader.

        Args:
            filepath: Path to .pmtiles file
        """
        self.filepath = filepath
        self._file = None
        self._header = None
        self._metadata = None

    def __enter__(self):
        """Context manager entry."""
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def open(self):
        """Open the PMTiles file."""
        if self._file is None:
            self._file = open(self.filepath, 'rb')
            self._read_header()

    def close(self):
        """Close the PMTiles file."""
        if self._file:
            self._file.close()
            self._file = None

    def _read_header(self):
        """Read and parse the PMTiles header."""
        # PMTiles v3 header is 127 bytes
        self._file.seek(0)
        header_bytes = self._file.read(127)

        if len(header_bytes) < 127:
            raise ValueError("Invalid PMTiles file: header too short")

        # Basic header parsing (simplified)
        # Magic number should be "PMTiles" or specific bytes
        # For full implementation, see PMTiles spec
        self._header = {
            'version': 3,
            'root_offset': 127,  # Typically starts after header
        }

    def get_tile(self, z: int, x: int, y: int) -> Optional[bytes]:
        """
        Read a tile from the PMTiles archive.

        Args:
            z: Zoom level
            x: Tile X coordinate
            y: Tile Y coordinate

        Returns:
            Tile data as bytes, or None if tile doesn't exist

        Note:
            This is a placeholder implementation. For production use,
            use the official pmtiles Python library which handles the
            complex directory structure and compression.
        """
        if self._file is None:
            self.open()

        # This would require full PMTiles directory parsing
        # For now, return None to indicate this needs the official library
        raise NotImplementedError(
            "Full PMTiles reading requires the 'pmtiles' library. "
            "Install with: pip install pmtiles"
        )

    def get_metadata(self) -> Dict[str, Any]:
        """
        Get metadata from the PMTiles archive.

        Returns:
            Dictionary containing metadata (name, bounds, etc.)
        """
        if self._metadata is None:
            # Would parse metadata JSON from file
            self._metadata = {
                'format': 'pbf',
                'bounds': [-180, -85, 180, 85],
            }
        return self._metadata


def decode_vector_tile(tile_data: bytes) -> Dict[str, List[Dict]]:
    """
    Decode Mapbox Vector Tile (MVT) format to GeoJSON-like structure.

    Args:
        tile_data: Raw MVT tile data (protobuf format)

    Returns:
        Dictionary with layer names as keys, each containing list of features

    Note:
        This is a placeholder. For production, use mapbox-vector-tile library:
        pip install mapbox-vector-tile
    """
    raise NotImplementedError(
        "Vector tile decoding requires 'mapbox-vector-tile' library. "
        "Install with: pip install mapbox-vector-tile"
    )


def project_geometry(geometry: List,
                     extent: int,
                     tile_bbox: Tuple[float, float, float, float],
                     target_size: int) -> List:
    """
    Project vector tile geometry coordinates to pixel coordinates.

    Args:
        geometry: List of coordinate pairs from vector tile (in tile extent units)
        extent: Tile extent (usually 4096 for MVT)
        tile_bbox: Geographic bounds (min_lon, min_lat, max_lon, max_lat)
        target_size: Target image size in pixels (e.g., 512)

    Returns:
        List of (x, y) pixel coordinates
    """
    scale = target_size / extent

    projected = []
    for coord in geometry:
        # Scale from tile extent to pixel coordinates
        x = coord[0] * scale
        y = coord[1] * scale
        projected.append((x, y))

    return projected


def simplify_geometry(coords: List[Tuple[float, float]],
                      tolerance: float = 1.0) -> List[Tuple[float, float]]:
    """
    Simplify geometry using Douglas-Peucker algorithm.

    Args:
        coords: List of (x, y) coordinate pairs
        tolerance: Simplification tolerance in pixels

    Returns:
        Simplified list of coordinates
    """
    if len(coords) < 3:
        return coords

    # Find the point with maximum distance from line
    dmax = 0.0
    index = 0
    end = len(coords) - 1

    for i in range(1, end):
        d = perpendicular_distance(coords[i], coords[0], coords[end])
        if d > dmax:
            index = i
            dmax = d

    # If max distance is greater than tolerance, recursively simplify
    if dmax > tolerance:
        # Recursive call
        rec_results1 = simplify_geometry(coords[:index+1], tolerance)
        rec_results2 = simplify_geometry(coords[index:], tolerance)

        # Build result list
        result = rec_results1[:-1] + rec_results2
    else:
        result = [coords[0], coords[end]]

    return result


def perpendicular_distance(point: Tuple[float, float],
                          line_start: Tuple[float, float],
                          line_end: Tuple[float, float]) -> float:
    """
    Calculate perpendicular distance from point to line segment.

    Args:
        point: Point coordinates
        line_start: Line start coordinates
        line_end: Line end coordinates

    Returns:
        Distance in same units as coordinates
    """
    x, y = point
    x1, y1 = line_start
    x2, y2 = line_end

    # Calculate line length squared
    line_length_sq = (x2 - x1) ** 2 + (y2 - y1) ** 2

    if line_length_sq == 0:
        # Line is a point
        return math.sqrt((x - x1) ** 2 + (y - y1) ** 2)

    # Calculate perpendicular distance
    numerator = abs((y2 - y1) * x - (x2 - x1) * y + x2 * y1 - y2 * x1)
    distance = numerator / math.sqrt(line_length_sq)

    return distance


def get_neighboring_tiles(z: int, x: int, y: int,
                          radius: int = 1) -> List[Tuple[int, int, int]]:
    """
    Get neighboring tiles around a given tile.

    Args:
        z: Zoom level
        x: Tile X coordinate
        y: Tile Y coordinate
        radius: Number of tiles in each direction (default: 1 for immediate neighbors)

    Returns:
        List of (z, x, y) tuples for neighboring tiles
    """
    max_tile = 2 ** z - 1
    neighbors = []

    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx == 0 and dy == 0:
                continue  # Skip the center tile

            nx = x + dx
            ny = y + dy

            # Check bounds
            if 0 <= nx <= max_tile and 0 <= ny <= max_tile:
                neighbors.append((z, nx, ny))

    return neighbors


def tile_to_quadkey(z: int, x: int, y: int) -> str:
    """
    Convert tile coordinates to quadkey string.

    Args:
        z: Zoom level
        x: Tile X coordinate
        y: Tile Y coordinate

    Returns:
        Quadkey string
    """
    quadkey = ""
    for i in range(z, 0, -1):
        digit = 0
        mask = 1 << (i - 1)
        if x & mask:
            digit += 1
        if y & mask:
            digit += 2
        quadkey += str(digit)
    return quadkey


def quadkey_to_tile(quadkey: str) -> Tuple[int, int, int]:
    """
    Convert quadkey string to tile coordinates.

    Args:
        quadkey: Quadkey string

    Returns:
        Tuple of (z, x, y)
    """
    z = len(quadkey)
    x = y = 0

    for i, digit in enumerate(quadkey):
        mask = 1 << (z - i - 1)
        d = int(digit)
        if d & 1:
            x |= mask
        if d & 2:
            y |= mask

    return (z, x, y)


if __name__ == "__main__":
    # Example usage and tests
    print("Tile Utilities - Example Usage\n")

    # Test coordinate conversions
    z, x, y = 10, 524, 340  # Trondheim area

    print(f"Tile: z={z}, x={x}, y={y}")

    bbox = TileCoordinates.tile_to_bbox(z, x, y)
    print(f"Bounding box (lon/lat): {bbox}")

    center = TileCoordinates.get_tile_center(z, x, y)
    print(f"Center: {center}")

    meters = TileCoordinates.tile_to_meters(z, x, y)
    print(f"Bounds (meters): {meters}")

    # Test reverse conversion
    lon, lat = 10.4, 63.43  # Trondheim
    tile_coords = TileCoordinates.lonlat_to_tile(lon, lat, z)
    print(f"\nLon/Lat {lon}, {lat} -> Tile {tile_coords} at zoom {z}")

    # Test quadkey conversion
    quadkey = tile_to_quadkey(z, x, y)
    print(f"\nQuadkey: {quadkey}")
    back_to_tile = quadkey_to_tile(quadkey)
    print(f"Back to tile: {back_to_tile}")

    # Test neighbors
    neighbors = get_neighboring_tiles(z, x, y, radius=1)
    print(f"\nNeighboring tiles: {len(neighbors)} tiles")
