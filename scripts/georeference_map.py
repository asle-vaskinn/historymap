#!/usr/bin/env python3
"""
Unified georeferencing for historical maps.

Handles two scenarios:
1. Already georeferenced (GeoTIFF) - passthrough with validation
2. Raw image with GCPs - apply GDAL georeferencing

Usage:
    # Check if already georeferenced
    python georeference_map.py --input map.tif --check

    # Georeference with GCPs
    python georeference_map.py --input map.png --gcps gcps.json --output map_georef.tif

    # Auto-detect (passthrough if georeferenced, require GCPs otherwise)
    python georeference_map.py --input map.tif --gcps gcps.json --auto
"""

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

try:
    from osgeo import gdal, osr
    HAS_GDAL = True
except ImportError:
    HAS_GDAL = False

try:
    import rasterio
    from rasterio.crs import CRS
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class GeorefInfo:
    """Information about a georeferenced raster."""
    is_georeferenced: bool
    crs: Optional[str]
    bounds: Optional[Tuple[float, float, float, float]]  # west, south, east, north
    pixel_size: Optional[Tuple[float, float]]
    width: int
    height: int
    source: str  # 'existing', 'gcp', 'none'


def check_georeferencing(input_path: Path) -> GeorefInfo:
    """
    Check if a raster is already georeferenced.

    Returns:
        GeorefInfo with georeferencing details
    """
    if HAS_RASTERIO:
        return _check_with_rasterio(input_path)
    elif HAS_GDAL:
        return _check_with_gdal(input_path)
    else:
        raise RuntimeError("Neither rasterio nor GDAL available")


def _check_with_rasterio(input_path: Path) -> GeorefInfo:
    """Check georeferencing using rasterio."""
    with rasterio.open(input_path) as src:
        has_crs = src.crs is not None
        has_transform = src.transform is not None and not src.transform.is_identity

        is_georef = has_crs and has_transform

        if is_georef:
            bounds = src.bounds
            return GeorefInfo(
                is_georeferenced=True,
                crs=str(src.crs),
                bounds=(bounds.left, bounds.bottom, bounds.right, bounds.top),
                pixel_size=(src.res[0], src.res[1]),
                width=src.width,
                height=src.height,
                source='existing'
            )
        else:
            return GeorefInfo(
                is_georeferenced=False,
                crs=None,
                bounds=None,
                pixel_size=None,
                width=src.width,
                height=src.height,
                source='none'
            )


def _check_with_gdal(input_path: Path) -> GeorefInfo:
    """Check georeferencing using GDAL."""
    gdal.UseExceptions()
    ds = gdal.Open(str(input_path), gdal.GA_ReadOnly)

    if ds is None:
        raise RuntimeError(f"Could not open {input_path}")

    # Check for GeoTransform
    gt = ds.GetGeoTransform()
    has_transform = gt is not None and gt != (0.0, 1.0, 0.0, 0.0, 0.0, 1.0)

    # Check for projection
    proj = ds.GetProjection()
    has_proj = proj is not None and proj != ''

    is_georef = has_transform and has_proj

    width = ds.RasterXSize
    height = ds.RasterYSize

    if is_georef:
        # Calculate bounds from geotransform
        # gt = (x_origin, x_pixel_size, x_rotation, y_origin, y_rotation, y_pixel_size)
        x_min = gt[0]
        y_max = gt[3]
        x_max = x_min + gt[1] * width
        y_min = y_max + gt[5] * height  # gt[5] is negative

        return GeorefInfo(
            is_georeferenced=True,
            crs=proj,
            bounds=(x_min, y_min, x_max, y_max),
            pixel_size=(abs(gt[1]), abs(gt[5])),
            width=width,
            height=height,
            source='existing'
        )
    else:
        return GeorefInfo(
            is_georeferenced=False,
            crs=None,
            bounds=None,
            pixel_size=None,
            width=width,
            height=height,
            source='none'
        )


def load_gcp_file(gcp_path: Path) -> dict:
    """
    Load GCP file in standard format.

    Expected format:
    {
        "version": "1.0",
        "map_id": "trondheim_1880",
        "map_date": 1880,
        "crs": "EPSG:4326",
        "source_file": "raw/trondheim_amt1.png",
        "gcps": [
            {"id": "GCP1", "pixel_x": 1234, "pixel_y": 567,
             "geo_x": 10.395, "geo_y": 63.430, "description": "Nidaros Cathedral"}
        ]
    }
    """
    with open(gcp_path, 'r') as f:
        data = json.load(f)

    # Validate required fields
    if 'gcps' not in data:
        raise ValueError(f"GCP file missing 'gcps' array: {gcp_path}")

    if len(data['gcps']) < 3:
        raise ValueError(f"Need at least 3 GCPs, got {len(data['gcps'])}")

    # Validate GCP structure
    for i, gcp in enumerate(data['gcps']):
        required = ['pixel_x', 'pixel_y', 'geo_x', 'geo_y']
        missing = [f for f in required if f not in gcp]
        if missing:
            raise ValueError(f"GCP {i} missing fields: {missing}")

    return data


def get_default_output_path(input_path: Path, gcp_data: dict) -> Path:
    """
    Determine default output path based on folder structure.

    Expected structure:
        data/kartverket/{year}/raw/image.png
        -> data/kartverket/{year}/georeferenced/image.tif

    Falls back to input_georef.tif in same directory.
    """
    map_date = gcp_data.get('map_date')

    # Check if input is in a year/raw folder structure
    if input_path.parent.name == 'raw' and input_path.parent.parent.name.isdigit():
        year_dir = input_path.parent.parent
        georef_dir = year_dir / 'georeferenced'
        georef_dir.mkdir(parents=True, exist_ok=True)
        return georef_dir / f"{input_path.stem}.tif"

    # Check for kartverket/{year} structure
    if map_date and 'kartverket' in str(input_path):
        kartverket_dir = None
        for parent in input_path.parents:
            if parent.name == 'kartverket':
                kartverket_dir = parent
                break

        if kartverket_dir:
            georef_dir = kartverket_dir / str(map_date) / 'georeferenced'
            georef_dir.mkdir(parents=True, exist_ok=True)
            return georef_dir / f"{input_path.stem}.tif"

    # Fallback: same directory with _georef suffix
    return input_path.with_stem(f"{input_path.stem}_georef").with_suffix('.tif')


def georeference_with_gcps(
    input_path: Path,
    gcp_data: dict,
    output_path: Path,
    target_crs: str = 'EPSG:4326'
) -> GeorefInfo:
    """
    Georeference an image using GCPs.

    Uses rasterio if available (affine transform from GCPs).
    Falls back to GDAL if needed for more complex transforms.
    """
    if HAS_RASTERIO:
        return _georeference_with_rasterio(input_path, gcp_data, output_path, target_crs)
    elif HAS_GDAL:
        return _georeference_with_gdal(input_path, gcp_data, output_path, target_crs)
    else:
        raise RuntimeError("Neither rasterio nor GDAL available for georeferencing")


def _georeference_with_rasterio(
    input_path: Path,
    gcp_data: dict,
    output_path: Path,
    target_crs: str = 'EPSG:4326'
) -> GeorefInfo:
    """
    Georeference using rasterio with affine transform from GCPs.
    """
    import numpy as np
    from rasterio.transform import from_gcps
    from rasterio.control import GroundControlPoint

    # Convert GCPs to rasterio format
    gcps = []
    for gcp in gcp_data['gcps']:
        gcps.append(GroundControlPoint(
            row=gcp['pixel_y'],
            col=gcp['pixel_x'],
            x=gcp['geo_x'],
            y=gcp['geo_y']
        ))

    # Calculate affine transform from GCPs
    transform = from_gcps(gcps)

    # Read source image
    from PIL import Image
    img = Image.open(input_path)
    img_array = np.array(img)

    # Handle different image formats
    if len(img_array.shape) == 2:
        # Grayscale
        count = 1
        img_array = img_array[np.newaxis, :, :]
    elif len(img_array.shape) == 3:
        # RGB or RGBA
        count = img_array.shape[2]
        # Rasterio expects (bands, height, width)
        img_array = np.transpose(img_array, (2, 0, 1))
    else:
        raise ValueError(f"Unexpected image shape: {img_array.shape}")

    height, width = img_array.shape[1], img_array.shape[2]

    # Write georeferenced output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(
        output_path,
        'w',
        driver='GTiff',
        height=height,
        width=width,
        count=count,
        dtype=img_array.dtype,
        crs=target_crs,
        transform=transform
    ) as dst:
        dst.write(img_array)

    logger.info(f"Created georeferenced file with rasterio: {output_path}")

    return check_georeferencing(output_path)


def _georeference_with_gdal(
    input_path: Path,
    gcp_data: dict,
    output_path: Path,
    target_crs: str = 'EPSG:4326'
) -> GeorefInfo:
    """
    Georeference using GDAL (original method).
    """
    if not HAS_GDAL:
        raise RuntimeError("GDAL required for GCP-based georeferencing")

    # Import the existing Georeferencer
    from georeference import Georeferencer

    georef = Georeferencer(
        input_path=input_path,
        output_path=output_path,
        target_crs=target_crs,
        resampling='cubic'
    )

    # Convert GCP data to GDAL GCP objects
    gcps = []
    for gcp in gcp_data['gcps']:
        gcps.append(gdal.GCP(
            gcp['geo_x'],
            gcp['geo_y'],
            0,  # Z
            gcp['pixel_x'],
            gcp['pixel_y'],
            gcp.get('id', ''),
            gcp.get('description', '')
        ))

    logger.info(f"Georeferencing with {len(gcps)} GCPs...")
    success = georef.georeference_with_gcps(gcps, order=1)

    if not success:
        raise RuntimeError("Georeferencing failed")

    # Return info about the result
    return check_georeferencing(output_path)


def ensure_georeferenced(
    input_path: Path,
    gcp_path: Optional[Path] = None,
    output_path: Optional[Path] = None,
    force: bool = False
) -> Tuple[Path, GeorefInfo]:
    """
    Ensure a map is georeferenced.

    - If already georeferenced and not force: passthrough
    - If not georeferenced or force: apply GCPs

    Args:
        input_path: Path to input raster
        gcp_path: Path to GCP JSON file (required if not georeferenced)
        output_path: Output path for georeferenced file (default: input_georef.tif)
        force: Force re-georeferencing even if already georeferenced

    Returns:
        Tuple of (output_path, GeorefInfo)
    """
    input_path = Path(input_path)

    # Check current state
    info = check_georeferencing(input_path)

    if info.is_georeferenced and not force:
        logger.info(f"Already georeferenced: {input_path}")
        logger.info(f"  CRS: {info.crs}")
        logger.info(f"  Bounds: {info.bounds}")
        return input_path, info

    # Need to georeference
    if gcp_path is None:
        raise ValueError(
            f"Image not georeferenced and no GCP file provided: {input_path}"
        )

    gcp_path = Path(gcp_path)
    if not gcp_path.exists():
        raise FileNotFoundError(f"GCP file not found: {gcp_path}")

    # Load GCPs
    gcp_data = load_gcp_file(gcp_path)
    target_crs = gcp_data.get('crs', 'EPSG:4326')

    # Determine output path
    if output_path is None:
        output_path = get_default_output_path(input_path, gcp_data)
    output_path = Path(output_path)

    # Perform georeferencing
    result_info = georeference_with_gcps(
        input_path=input_path,
        gcp_data=gcp_data,
        output_path=output_path,
        target_crs=target_crs
    )

    logger.info(f"Created georeferenced file: {output_path}")
    logger.info(f"  CRS: {result_info.crs}")
    logger.info(f"  Bounds: {result_info.bounds}")

    return output_path, result_info


def create_gcp_template(output_path: Path, map_id: str = "unknown", map_date: int = 1900):
    """Create a template GCP file."""
    template = {
        "version": "1.0",
        "map_id": map_id,
        "map_date": map_date,
        "crs": "EPSG:4326",
        "source_file": "",
        "gcps": [
            {
                "id": "GCP1",
                "pixel_x": 0,
                "pixel_y": 0,
                "geo_x": 10.39,
                "geo_y": 63.44,
                "description": "Top-left reference point"
            },
            {
                "id": "GCP2",
                "pixel_x": 1000,
                "pixel_y": 0,
                "geo_x": 10.42,
                "geo_y": 63.44,
                "description": "Top-right reference point"
            },
            {
                "id": "GCP3",
                "pixel_x": 1000,
                "pixel_y": 1000,
                "geo_x": 10.42,
                "geo_y": 63.42,
                "description": "Bottom-right reference point"
            },
            {
                "id": "GCP4",
                "pixel_x": 0,
                "pixel_y": 1000,
                "geo_x": 10.39,
                "geo_y": 63.42,
                "description": "Bottom-left reference point"
            }
        ]
    }

    with open(output_path, 'w') as f:
        json.dump(template, f, indent=2)

    logger.info(f"Created GCP template: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Unified georeferencing for historical maps'
    )
    parser.add_argument('--input', '-i', help='Input raster file')
    parser.add_argument('--gcps', '-g', help='GCP JSON file')
    parser.add_argument('--output', '-o', help='Output path')
    parser.add_argument('--check', action='store_true',
                       help='Only check georeferencing status')
    parser.add_argument('--force', '-f', action='store_true',
                       help='Force re-georeferencing')
    parser.add_argument('--create-template', type=str,
                       help='Create GCP template at path')
    parser.add_argument('--map-id', default='unknown',
                       help='Map ID for template')
    parser.add_argument('--map-date', type=int, default=1900,
                       help='Map date for template')

    args = parser.parse_args()

    # Handle template creation
    if args.create_template:
        create_gcp_template(
            Path(args.create_template),
            map_id=args.map_id,
            map_date=args.map_date
        )
        return

    if not args.input:
        parser.error("--input is required (unless using --create-template)")

    input_path = Path(args.input)
    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        sys.exit(1)

    # Check-only mode
    if args.check:
        info = check_georeferencing(input_path)
        print(json.dumps({
            'is_georeferenced': info.is_georeferenced,
            'crs': info.crs,
            'bounds': info.bounds,
            'pixel_size': info.pixel_size,
            'width': info.width,
            'height': info.height,
            'source': info.source
        }, indent=2))
        sys.exit(0 if info.is_georeferenced else 1)

    # Ensure georeferenced
    try:
        gcp_path = Path(args.gcps) if args.gcps else None
        output_path = Path(args.output) if args.output else None

        result_path, info = ensure_georeferenced(
            input_path=input_path,
            gcp_path=gcp_path,
            output_path=output_path,
            force=args.force
        )

        print(f"Georeferenced file: {result_path}")
        print(f"Bounds: {info.bounds}")

    except Exception as e:
        logger.error(str(e))
        sys.exit(1)


if __name__ == '__main__':
    main()
