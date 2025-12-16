#!/usr/bin/env python3
"""
Georeference historical maps to modern coordinate systems.

This script aligns historical map images to modern coordinates using:
- Manual ground control points (GCPs) from JSON file
- Auto-detection of corner coordinates from map frame (if possible)
- GDAL for georeferencing transformations

Output: GeoTIFF with EPSG:4326 (WGS84) or EPSG:25832 (UTM 32N) projection.

Usage:
    # With GCP file
    python georeference.py input.tif --gcps gcps.json --output output.tif

    # Auto-detect (experimental)
    python georeference.py input.tif --auto-detect --output output.tif

    # Specify target CRS
    python georeference.py input.tif --gcps gcps.json --crs EPSG:25832
"""

import argparse
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple, Optional, Dict

try:
    from osgeo import gdal, osr
    import numpy as np
except ImportError:
    print("ERROR: GDAL is required. Install with: pip install gdal")
    print("Or on macOS: brew install gdal && pip install gdal==$(gdal-config --version)")
    sys.exit(1)

try:
    import cv2
except ImportError:
    cv2 = None
    print("WARNING: OpenCV not available. Auto-detection features disabled.")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Enable GDAL exceptions
gdal.UseExceptions()


class Georeferencer:
    """Georeference raster images using ground control points."""

    def __init__(
        self,
        input_path: Path,
        output_path: Path,
        target_crs: str = 'EPSG:4326',
        resampling: str = 'cubic'
    ):
        """
        Initialize georeferencer.

        Args:
            input_path: Path to input raster image
            output_path: Path to output GeoTIFF
            target_crs: Target coordinate reference system (default: EPSG:4326)
            resampling: Resampling method (nearest, bilinear, cubic, lanczos)
        """
        self.input_path = Path(input_path)
        self.output_path = Path(output_path)
        self.target_crs = target_crs
        self.resampling = self._get_resampling_method(resampling)

        if not self.input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        # Create output directory if needed
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

    def _get_resampling_method(self, method: str) -> int:
        """Get GDAL resampling constant."""
        methods = {
            'nearest': gdal.GRA_NearestNeighbour,
            'bilinear': gdal.GRA_Bilinear,
            'cubic': gdal.GRA_Cubic,
            'cubicspline': gdal.GRA_CubicSpline,
            'lanczos': gdal.GRA_Lanczos,
        }
        return methods.get(method.lower(), gdal.GRA_Cubic)

    def load_gcps_from_json(self, gcp_file: Path) -> List[gdal.GCP]:
        """
        Load ground control points from JSON file.

        JSON format:
        {
            "crs": "EPSG:4326",
            "gcps": [
                {"pixel_x": 100, "pixel_y": 200, "geo_x": 10.4, "geo_y": 63.4, "id": "GCP1"},
                {"pixel_x": 300, "pixel_y": 400, "geo_x": 10.5, "geo_y": 63.5, "id": "GCP2"},
                ...
            ]
        }

        Args:
            gcp_file: Path to JSON file with GCP data

        Returns:
            List of GDAL GCP objects
        """
        with open(gcp_file, 'r') as f:
            data = json.load(f)

        gcps = []
        for i, gcp_data in enumerate(data.get('gcps', [])):
            gcp = gdal.GCP(
                gcp_data['geo_x'],  # X (longitude or easting)
                gcp_data['geo_y'],  # Y (latitude or northing)
                0,  # Z (elevation, usually 0 for maps)
                gcp_data['pixel_x'],  # Pixel column
                gcp_data['pixel_y'],  # Pixel row
                gcp_data.get('id', f'GCP{i+1}'),  # GCP ID
                gcp_data.get('id', f'GCP{i+1}')   # GCP Info
            )
            gcps.append(gcp)

        # Verify CRS matches
        file_crs = data.get('crs', 'EPSG:4326')
        if file_crs != self.target_crs:
            logger.warning(
                f"GCP file CRS ({file_crs}) differs from target CRS ({self.target_crs}). "
                f"Assuming GCPs are in {file_crs}."
            )

        logger.info(f"Loaded {len(gcps)} ground control points")
        return gcps

    def auto_detect_corners(self) -> Optional[List[gdal.GCP]]:
        """
        Auto-detect map corners and extract coordinates from map frame.

        This is experimental and works best with clean map borders and
        visible coordinate labels.

        Returns:
            List of GCPs if successful, None otherwise
        """
        if cv2 is None:
            logger.error("OpenCV required for auto-detection")
            return None

        logger.info("Attempting to auto-detect map corners...")

        try:
            # Read image
            img = cv2.imread(str(self.input_path))
            if img is None:
                logger.error("Could not read image with OpenCV")
                return None

            # Convert to grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # Detect edges
            edges = cv2.Canny(gray, 50, 150)

            # Find contours
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            # Find largest rectangular contour (likely map boundary)
            max_area = 0
            best_contour = None

            for contour in contours:
                area = cv2.contourArea(contour)
                if area > max_area:
                    # Approximate contour to polygon
                    epsilon = 0.02 * cv2.arcLength(contour, True)
                    approx = cv2.approxPolyDP(contour, epsilon, True)

                    # Check if it's roughly rectangular (4 corners)
                    if len(approx) == 4:
                        max_area = area
                        best_contour = approx

            if best_contour is None:
                logger.warning("Could not detect map boundary")
                return None

            # Extract corner points
            corners = best_contour.reshape(4, 2)

            # Sort corners: top-left, top-right, bottom-right, bottom-left
            # by sum and difference of coordinates
            corners_sorted = np.zeros((4, 2), dtype=np.float32)
            s = corners.sum(axis=1)
            diff = np.diff(corners, axis=1)

            corners_sorted[0] = corners[np.argmin(s)]  # Top-left
            corners_sorted[2] = corners[np.argmax(s)]  # Bottom-right
            corners_sorted[1] = corners[np.argmin(diff)]  # Top-right
            corners_sorted[3] = corners[np.argmax(diff)]  # Bottom-left

            logger.info(f"Detected corners at: {corners_sorted}")

            # TODO: Extract coordinate labels from map (OCR)
            # For now, this is just a placeholder
            logger.warning("Auto-detection found corners but cannot extract coordinates yet")
            logger.warning("Please use manual GCP file instead")

            return None

        except Exception as e:
            logger.error(f"Auto-detection failed: {e}")
            return None

    def georeference_with_gcps(
        self,
        gcps: List[gdal.GCP],
        order: int = 1
    ) -> bool:
        """
        Georeference image using ground control points.

        Args:
            gcps: List of GDAL GCP objects
            order: Polynomial order for transformation (1=affine, 2=2nd order, 3=3rd order)

        Returns:
            True if successful, False otherwise
        """
        try:
            # Open input dataset
            src_ds = gdal.Open(str(self.input_path), gdal.GA_ReadOnly)
            if src_ds is None:
                raise RuntimeError(f"Could not open {self.input_path}")

            logger.info(f"Input image: {src_ds.RasterXSize}x{src_ds.RasterYSize}, "
                       f"{src_ds.RasterCount} bands")

            # Create temporary VRT with GCPs
            temp_vrt = tempfile.NamedTemporaryFile(suffix='.vrt', delete=False)
            temp_vrt.close()

            try:
                # Create VRT
                vrt_ds = gdal.AutoCreateWarpedVRT(
                    src_ds,
                    None,  # Source SRS (will be set by GCPs)
                    self.target_crs,
                    self.resampling
                )

                if vrt_ds is None:
                    # Alternative: create VRT manually
                    logger.info("Creating VRT with GCPs...")

                    # Set GCPs on source dataset
                    src_ds.SetGCPs(gcps, self._get_srs(self.target_crs).ExportToWkt())

                    # Create warped VRT
                    vrt_ds = gdal.AutoCreateWarpedVRT(
                        src_ds,
                        src_ds.GetGCPProjection(),
                        self.target_crs,
                        self.resampling
                    )

                if vrt_ds is None:
                    raise RuntimeError("Could not create warped VRT")

                # Calculate RMS error
                rms_error = self._calculate_rms_error(src_ds, gcps)
                logger.info(f"RMS error: {rms_error:.6f}")

                # Create output GeoTIFF
                logger.info(f"Creating GeoTIFF: {self.output_path}")

                driver = gdal.GetDriverByName('GTiff')
                out_ds = driver.CreateCopy(
                    str(self.output_path),
                    vrt_ds,
                    options=['COMPRESS=LZW', 'TILED=YES', 'BIGTIFF=IF_SAFER']
                )

                if out_ds is None:
                    raise RuntimeError("Could not create output file")

                # Set metadata
                out_ds.SetMetadataItem('GEOREFERENCING_RMS_ERROR', str(rms_error))
                out_ds.SetMetadataItem('GEOREFERENCING_GCP_COUNT', str(len(gcps)))
                out_ds.SetMetadataItem('SOURCE_FILE', str(self.input_path))

                # Close datasets
                out_ds = None
                vrt_ds = None
                src_ds = None

                logger.info(f"Successfully created georeferenced file: {self.output_path}")

                # Generate quality report
                self._write_quality_report(len(gcps), rms_error)

                return True

            finally:
                # Clean up temporary VRT
                if os.path.exists(temp_vrt.name):
                    os.unlink(temp_vrt.name)

        except Exception as e:
            logger.error(f"Georeferencing failed: {e}", exc_info=True)
            return False

    def _get_srs(self, crs: str) -> osr.SpatialReference:
        """Get spatial reference system from CRS string."""
        srs = osr.SpatialReference()
        if crs.startswith('EPSG:'):
            epsg_code = int(crs.split(':')[1])
            srs.ImportFromEPSG(epsg_code)
        else:
            srs.SetFromUserInput(crs)
        return srs

    def _calculate_rms_error(self, src_ds, gcps: List[gdal.GCP]) -> float:
        """
        Calculate root mean square error of GCP transformation.

        Args:
            src_ds: Source GDAL dataset
            gcps: List of GCPs

        Returns:
            RMS error in map units
        """
        try:
            # Use GDAL's transformer
            transformer = gdal.Transformer(
                src_ds,
                None,
                ['METHOD=GCP_POLYNOMIAL', f'ORDER=1']
            )

            if transformer is None:
                logger.warning("Could not create transformer for RMS calculation")
                return 0.0

            errors = []
            for gcp in gcps:
                # Transform pixel to geo
                success, points = transformer.TransformPoint(
                    0,  # Forward transform
                    gcp.GCPPixel,
                    gcp.GCPLine
                )

                if success:
                    # Calculate error
                    dx = points[0] - gcp.GCPX
                    dy = points[1] - gcp.GCPY
                    error = np.sqrt(dx*dx + dy*dy)
                    errors.append(error)

            if errors:
                rms = np.sqrt(np.mean(np.array(errors)**2))
                return rms
            else:
                return 0.0

        except Exception as e:
            logger.warning(f"Could not calculate RMS error: {e}")
            return 0.0

    def _write_quality_report(self, gcp_count: int, rms_error: float):
        """Write quality report to JSON file."""
        report_path = self.output_path.with_suffix('.quality.json')

        report = {
            'input_file': str(self.input_path),
            'output_file': str(self.output_path),
            'target_crs': self.target_crs,
            'gcp_count': gcp_count,
            'rms_error': rms_error,
            'rms_error_unit': 'map_units',
            'quality_assessment': self._assess_quality(rms_error),
        }

        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)

        logger.info(f"Quality report saved to: {report_path}")

    def _assess_quality(self, rms_error: float) -> str:
        """Assess georeferencing quality based on RMS error."""
        # These thresholds are approximate and depend on CRS units
        if rms_error < 0.0001:  # ~10m for WGS84
            return 'excellent'
        elif rms_error < 0.001:  # ~100m
            return 'good'
        elif rms_error < 0.01:  # ~1km
            return 'acceptable'
        else:
            return 'poor'


def create_gcp_template(output_path: Path):
    """Create a template GCP JSON file."""
    template = {
        "crs": "EPSG:4326",
        "description": "Ground Control Points for georeferencing",
        "gcps": [
            {
                "id": "GCP1",
                "pixel_x": 100,
                "pixel_y": 100,
                "geo_x": 10.4,
                "geo_y": 63.4,
                "description": "Top-left corner"
            },
            {
                "id": "GCP2",
                "pixel_x": 500,
                "pixel_y": 100,
                "geo_x": 10.5,
                "geo_y": 63.4,
                "description": "Top-right corner"
            },
            {
                "id": "GCP3",
                "pixel_x": 500,
                "pixel_y": 500,
                "geo_x": 10.5,
                "geo_y": 63.3,
                "description": "Bottom-right corner"
            },
            {
                "id": "GCP4",
                "pixel_x": 100,
                "pixel_y": 500,
                "geo_x": 10.4,
                "geo_y": 63.3,
                "description": "Bottom-left corner"
            }
        ]
    }

    with open(output_path, 'w') as f:
        json.dump(template, f, indent=2)

    logger.info(f"GCP template created: {output_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Georeference historical map images',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Georeference with GCP file
  python georeference.py map.tif --gcps gcps.json

  # Specify output path and CRS
  python georeference.py map.tif --gcps gcps.json --output georef.tif --crs EPSG:25832

  # Create GCP template
  python georeference.py --create-template gcps_template.json

  # Auto-detect (experimental)
  python georeference.py map.tif --auto-detect

GCP File Format:
  {
    "crs": "EPSG:4326",
    "gcps": [
      {"pixel_x": 100, "pixel_y": 200, "geo_x": 10.4, "geo_y": 63.4, "id": "GCP1"},
      ...
    ]
  }
        """
    )

    parser.add_argument(
        'input',
        nargs='?',
        type=str,
        help='Input raster image (TIFF, JPEG2000, PNG, etc.)'
    )
    parser.add_argument(
        '--gcps',
        type=str,
        help='JSON file with ground control points'
    )
    parser.add_argument(
        '--auto-detect',
        action='store_true',
        help='Attempt to auto-detect map corners (experimental)'
    )
    parser.add_argument(
        '--output',
        type=str,
        help='Output GeoTIFF path (default: input_georef.tif)'
    )
    parser.add_argument(
        '--crs',
        type=str,
        default='EPSG:4326',
        help='Target coordinate reference system (default: EPSG:4326)'
    )
    parser.add_argument(
        '--resampling',
        type=str,
        default='cubic',
        choices=['nearest', 'bilinear', 'cubic', 'cubicspline', 'lanczos'],
        help='Resampling method (default: cubic)'
    )
    parser.add_argument(
        '--order',
        type=int,
        default=1,
        choices=[1, 2, 3],
        help='Polynomial order for transformation (default: 1=affine)'
    )
    parser.add_argument(
        '--create-template',
        type=str,
        metavar='FILE',
        help='Create a GCP template JSON file and exit'
    )

    args = parser.parse_args()

    # Handle template creation
    if args.create_template:
        create_gcp_template(Path(args.create_template))
        return

    # Validate required arguments
    if not args.input:
        parser.error("input file is required (unless using --create-template)")

    if not args.gcps and not args.auto_detect:
        parser.error("either --gcps or --auto-detect is required")

    # Determine output path
    input_path = Path(args.input)
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_stem(f"{input_path.stem}_georef")

    # Create georeferencer
    georef = Georeferencer(
        input_path=input_path,
        output_path=output_path,
        target_crs=args.crs,
        resampling=args.resampling
    )

    # Get GCPs
    gcps = None

    if args.gcps:
        gcps = georef.load_gcps_from_json(Path(args.gcps))
    elif args.auto_detect:
        gcps = georef.auto_detect_corners()

    if not gcps:
        logger.error("No ground control points available")
        sys.exit(1)

    if len(gcps) < 3:
        logger.error("At least 3 GCPs required for georeferencing")
        sys.exit(1)

    # Perform georeferencing
    success = georef.georeference_with_gcps(gcps, order=args.order)

    if success:
        logger.info("Georeferencing completed successfully")
        sys.exit(0)
    else:
        logger.error("Georeferencing failed")
        sys.exit(1)


if __name__ == '__main__':
    main()
