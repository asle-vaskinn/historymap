"""
Pipeline Constants - Single source of truth for paths and mappings.

This module provides:
- Canonical file paths for all pipeline stages
- Source ID mappings (full IDs vs short codes) as Enums
- Required export fields for validation
- Display names for UI
- Date inference and evidence constants

Import this module instead of defining paths/mappings in individual scripts.
"""

import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Tuple


# =============================================================================
# Geographic Context - Coordinate Conversions
# =============================================================================

@dataclass
class GeoContext:
    """
    Geographic context for coordinate conversions.

    Provides latitude-aware conversions between degrees and meters.
    Default context is Trondheim, Norway.

    Example:
        >>> GEO.degrees_to_meters(0.001)
        80.0  # approximately
        >>> GEO.meters_to_degrees(100)
        0.00125  # approximately
    """
    name: str
    bbox: Tuple[float, float, float, float]  # west, south, east, north
    center_lat: float

    @property
    def meters_per_degree_lat(self) -> float:
        """Meters per degree latitude (roughly constant ~111km)."""
        return 111_000

    @property
    def meters_per_degree_lon(self) -> float:
        """Meters per degree longitude (varies with latitude)."""
        return 111_000 * math.cos(math.radians(self.center_lat))

    @property
    def avg_meters_per_degree(self) -> float:
        """Average meters per degree (for approximate calculations)."""
        return (self.meters_per_degree_lat + self.meters_per_degree_lon) / 2

    def degrees_to_meters(self, deg: float) -> float:
        """Convert degrees to meters (approximate)."""
        return deg * self.avg_meters_per_degree

    def meters_to_degrees(self, meters: float) -> float:
        """Convert meters to degrees (approximate)."""
        return meters / self.avg_meters_per_degree

    def buffer_degrees(self, meters: float) -> float:
        """Get buffer in degrees for a given meter distance."""
        return self.meters_to_degrees(meters)


# Default geographic context: Trondheim, Norway
TRONDHEIM = GeoContext(
    name='Trondheim',
    bbox=(10.2, 63.35, 10.6, 63.5),
    center_lat=63.43
)

# Active geographic context (change this to support other cities)
GEO = TRONDHEIM


# =============================================================================
# Source Enums - Single Source of Truth
# =============================================================================

class Source(str, Enum):
    """
    Canonical source identifiers used throughout the pipeline.

    These are the "full" IDs used in normalized data and merge config.
    Use Source.OSM.value to get the string 'osm'.
    """
    OSM = 'osm'
    SEFRAK = 'sefrak'
    TRONDHEIM_KOMMUNE = 'trondheim_kommune'
    FINN = 'finn'
    MANUAL = 'manual'
    ML_DETECTED = 'ml_detected'
    MATRIKKELEN = 'matrikkelen'

    @classmethod
    def values(cls) -> list:
        """Get all source ID values as strings."""
        return [s.value for s in cls]


class SourceShort(str, Enum):
    """
    Short codes for frontend (compact JSON, ~40% smaller).

    Used only in export stage. Maps to Source enum values.
    """
    OSM = 'osm'
    SEF = 'sef'       # SEFRAK
    TK = 'tk'         # Trondheim Kommune
    FIN = 'fin'       # Finn
    MAN = 'man'       # Manual
    ML = 'ml'         # ML Detected
    MAT = 'mat'       # Matrikkelen
    INH = 'inh'       # Inherited (date computed from neighbors)

    @classmethod
    def values(cls) -> list:
        """Get all short code values as strings."""
        return [s.value for s in cls]


class RoadSource(str, Enum):
    """
    Canonical source identifiers for road data.

    These are the "full" IDs used in normalized road data.
    """
    NVDB = 'nvdb'
    OSM_ROADS = 'osm_roads'
    KULTURMINNER = 'kulturminner'
    ML_DETECTED = 'ml_detected'

    @classmethod
    def values(cls) -> list:
        """Get all road source ID values as strings."""
        return [s.value for s in cls]


class RoadSourceShort(str, Enum):
    """
    Short codes for road sources in frontend.
    """
    NVDB = 'nvdb'
    OSM = 'osm'       # OSM Roads
    KULT = 'kult'     # Kulturminner
    ML = 'ml'         # ML Detected

    @classmethod
    def values(cls) -> list:
        """Get all road short code values as strings."""
        return [s.value for s in cls]


class WaterSource(str, Enum):
    """
    Canonical source identifiers for water data.
    """
    OSM = 'osm'
    MANUAL = 'manual'
    ML_WATER = 'ml_water'

    @classmethod
    def values(cls) -> list:
        """Get all water source ID values as strings."""
        return [s.value for s in cls]


class WaterSourceShort(str, Enum):
    """
    Short codes for water sources in frontend.
    """
    OSM = 'osm'
    MAN = 'man'       # Manual
    ML = 'ml'         # ML Detected

    @classmethod
    def values(cls) -> list:
        """Get all water short code values as strings."""
        return [s.value for s in cls]


# =============================================================================
# Directory Structure
# =============================================================================

# Base directories (relative to project root)
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
FRONTEND_DIR = PROJECT_ROOT / "frontend"

# Source data directories
SOURCES_DIR = DATA_DIR / "sources"

# Pipeline stage directories
MERGED_DIR = DATA_DIR / "merged"
EXPORT_DIR = DATA_DIR / "export"

# Frontend data directory (for non-Docker development)
FRONTEND_DATA_DIR = FRONTEND_DIR / "data"

# =============================================================================
# Canonical Output Paths
# =============================================================================

# Merged outputs (intermediate)
BUILDINGS_MERGED = MERGED_DIR / "buildings_merged.geojson"
BUILDINGS_UNMATCHED = MERGED_DIR / "buildings_unmatched.geojson"
ROADS_MERGED = MERGED_DIR / "roads_merged.geojson"
WATER_MERGED = MERGED_DIR / "water_merged.geojson"

# Merge reports
MERGE_REPORT = MERGED_DIR / "buildings_merged.report.json"
QUALITY_REPORT = MERGED_DIR / "buildings_merged.quality.json"

# Export outputs (final)
BUILDINGS_EXPORT = EXPORT_DIR / "buildings.geojson"
ROADS_EXPORT = EXPORT_DIR / "roads_temporal.geojson"
WATER_EXPORT = EXPORT_DIR / "water.geojson"

# PMTiles (vector tiles)
BUILDINGS_PMTILES = EXPORT_DIR / "buildings_temporal.pmtiles"
ROADS_PMTILES = EXPORT_DIR / "roads_temporal.pmtiles"
WATER_PMTILES = EXPORT_DIR / "water.pmtiles"

# Export manifest (for cache-busting)
EXPORT_MANIFEST = EXPORT_DIR / "manifest.json"

# =============================================================================
# Source Configuration (derived from Enums)
# =============================================================================

# Mapping from full Source to SourceShort (buildings)
_SOURCE_TO_SHORT = {
    Source.OSM: SourceShort.OSM,
    Source.SEFRAK: SourceShort.SEF,
    Source.TRONDHEIM_KOMMUNE: SourceShort.TK,
    Source.FINN: SourceShort.FIN,
    Source.MANUAL: SourceShort.MAN,
    Source.ML_DETECTED: SourceShort.ML,
    Source.MATRIKKELEN: SourceShort.MAT,
}

# Reverse mapping: SourceShort to Source
_SHORT_TO_SOURCE = {v: k for k, v in _SOURCE_TO_SHORT.items()}

# Mapping from RoadSource to RoadSourceShort
_ROAD_SOURCE_TO_SHORT = {
    RoadSource.NVDB: RoadSourceShort.NVDB,
    RoadSource.OSM_ROADS: RoadSourceShort.OSM,
    RoadSource.KULTURMINNER: RoadSourceShort.KULT,
    RoadSource.ML_DETECTED: RoadSourceShort.ML,
}

# Reverse mapping: RoadSourceShort to RoadSource
_ROAD_SHORT_TO_SOURCE = {v: k for k, v in _ROAD_SOURCE_TO_SHORT.items()}

# Mapping from WaterSource to WaterSourceShort
_WATER_SOURCE_TO_SHORT = {
    WaterSource.OSM: WaterSourceShort.OSM,
    WaterSource.MANUAL: WaterSourceShort.MAN,
    WaterSource.ML_WATER: WaterSourceShort.ML,
}

# Reverse mapping: WaterSourceShort to WaterSource
_WATER_SHORT_TO_SOURCE = {v: k for k, v in _WATER_SOURCE_TO_SHORT.items()}

# Legacy dict format for water
WATER_SOURCE_SHORT_CODES = {s.value: _WATER_SOURCE_TO_SHORT[s].value for s in WaterSource}
WATER_SHORT_TO_FULL = {v: k for k, v in WATER_SOURCE_SHORT_CODES.items()}

# Legacy dict format for roads
ROAD_SOURCE_SHORT_CODES = {s.value: _ROAD_SOURCE_TO_SHORT[s].value for s in RoadSource}
ROAD_SHORT_TO_FULL = {v: k for k, v in ROAD_SOURCE_SHORT_CODES.items()}

# Legacy dict format (for backward compatibility)
# Prefer using Source enum directly in new code
SOURCE_IDS = {s.value: s.value for s in Source}

# ML Map Sources - historical map specific sources
# Pattern: ml_kartverket_{year} -> kv{year}
ML_MAP_SOURCES = {
    'ml_kartverket_1880': 'kv1880',
    'ml_kartverket_1904': 'kv1904',
    'ml_kartverket_1937': 'kv1937',
    'ml_kartverket_1947': 'kv1947',
    'ml_kartverket_1964': 'kv1964',
    'ml_kartverket_2006': 'kv2006',
    'ml_ortofoto_1937': 'orto1937',
    'ml_air_1947': 'air1947',
}

# Reverse mapping: short code -> full ML map source
ML_MAP_SHORT_TO_FULL = {v: k for k, v in ML_MAP_SOURCES.items()}

# Short codes for frontend (compact JSON, ~40% smaller)
SOURCE_SHORT_CODES = {s.value: _SOURCE_TO_SHORT[s].value for s in Source}

# Reverse lookup: short code → full ID
SHORT_TO_FULL = {v: k for k, v in SOURCE_SHORT_CODES.items()}

# Display names for UI (legend, tooltips)
SOURCE_DISPLAY_NAMES = {
    # Short codes
    SourceShort.OSM.value: 'OpenStreetMap',
    SourceShort.SEF.value: 'SEFRAK',
    SourceShort.TK.value: 'Trondheim Kommune',
    SourceShort.FIN.value: 'Finn.no',
    SourceShort.MAN.value: 'Manual',
    SourceShort.ML.value: 'ML Detected',
    SourceShort.MAT.value: 'Matrikkelen',
    # Full IDs (also supported)
    Source.OSM.value: 'OpenStreetMap',
    Source.SEFRAK.value: 'SEFRAK',
    Source.TRONDHEIM_KOMMUNE.value: 'Trondheim Kommune',
    Source.FINN.value: 'Finn.no',
    Source.MANUAL.value: 'Manual',
    Source.ML_DETECTED.value: 'ML Detected',
    Source.MATRIKKELEN.value: 'Matrikkelen',
}

# =============================================================================
# Helper Functions for Source Mapping
# =============================================================================

def to_short_code(full_id: str | Source) -> str:
    """Convert full source ID to short code for frontend export.

    Args:
        full_id: Full source ID (e.g., 'sefrak', Source.SEFRAK, 'ml_kartverket_1880')

    Returns:
        Short code (e.g., 'sef', 'tk', 'kv1880')

    Raises:
        ValueError: If full_id is not a valid source

    Example:
        >>> to_short_code('sefrak')
        'sef'
        >>> to_short_code(Source.TRONDHEIM_KOMMUNE)
        'tk'
        >>> to_short_code('ml_kartverket_1880')
        'kv1880'
    """
    # Handle Source enum input
    if isinstance(full_id, Source):
        return _SOURCE_TO_SHORT[full_id].value

    # Handle string input - validate it's a known source
    if full_id in SOURCE_SHORT_CODES:
        return SOURCE_SHORT_CODES[full_id]

    # Check ML map sources (e.g., ml_kartverket_1880 -> kv1880)
    if full_id in ML_MAP_SOURCES:
        return ML_MAP_SOURCES[full_id]

    # Unknown source - raise error instead of silently passing through
    valid = Source.values() + list(ML_MAP_SOURCES.keys())
    raise ValueError(f"Unknown source ID '{full_id}'. Valid sources: {valid}")


def to_full_id(short_code: str | SourceShort) -> str:
    """Convert short code back to full source ID.

    Args:
        short_code: Short code (e.g., 'sef', SourceShort.SEF, 'kv1880')

    Returns:
        Full source ID (e.g., 'sefrak', 'trondheim_kommune', 'ml_kartverket_1880')

    Raises:
        ValueError: If short_code is not valid

    Example:
        >>> to_full_id('tk')
        'trondheim_kommune'
        >>> to_full_id(SourceShort.SEF)
        'sefrak'
        >>> to_full_id('kv1880')
        'ml_kartverket_1880'
    """
    # Handle SourceShort enum input
    if isinstance(short_code, SourceShort):
        return _SHORT_TO_SOURCE[short_code].value

    # Handle string input - validate it's a known short code
    if short_code in SHORT_TO_FULL:
        return SHORT_TO_FULL[short_code]

    # Check ML map short codes (e.g., kv1880 -> ml_kartverket_1880)
    if short_code in ML_MAP_SHORT_TO_FULL:
        return ML_MAP_SHORT_TO_FULL[short_code]

    # Unknown short code - raise error
    valid = SourceShort.values() + list(ML_MAP_SHORT_TO_FULL.keys())
    raise ValueError(f"Unknown short code '{short_code}'. Valid codes: {valid}")


def get_display_name(source_code: str | Source | SourceShort) -> str:
    """Get human-readable display name for a source.

    Args:
        source_code: Either full ID, short code, or Source/SourceShort enum

    Returns:
        Display name for UI

    Example:
        >>> get_display_name('sef')
        'SEFRAK'
        >>> get_display_name(Source.TRONDHEIM_KOMMUNE)
        'Trondheim Kommune'
    """
    # Handle enum input
    if isinstance(source_code, (Source, SourceShort)):
        source_code = source_code.value

    return SOURCE_DISPLAY_NAMES.get(source_code, source_code)


def validate_source(source_id: str) -> Source:
    """Validate and convert a source ID string to Source enum.

    Args:
        source_id: Source ID string to validate

    Returns:
        Source enum value

    Raises:
        ValueError: If source_id is not valid

    Example:
        >>> validate_source('sefrak')
        Source.SEFRAK
    """
    try:
        return Source(source_id)
    except ValueError:
        valid = Source.values()
        raise ValueError(f"Invalid source ID '{source_id}'. Valid sources: {valid}")


def is_valid_source(source_id: str) -> bool:
    """Check if a source ID is valid.

    Args:
        source_id: Source ID string to check

    Returns:
        True if valid, False otherwise

    Example:
        >>> is_valid_source('sefrak')
        True
        >>> is_valid_source('unknown')
        False
    """
    return source_id in Source.values()


def to_road_short_code(full_id: str | RoadSource) -> str:
    """Convert full road source ID to short code for frontend export.

    Args:
        full_id: Full road source ID (e.g., 'nvdb', 'osm_roads')

    Returns:
        Short code (e.g., 'nvdb', 'osm')

    Raises:
        ValueError: If full_id is not a valid road source

    Example:
        >>> to_road_short_code('osm_roads')
        'osm'
        >>> to_road_short_code(RoadSource.KULTURMINNER)
        'kult'
    """
    # Handle RoadSource enum input
    if isinstance(full_id, RoadSource):
        return _ROAD_SOURCE_TO_SHORT[full_id].value

    # Handle string input - validate it's a known road source
    if full_id in ROAD_SOURCE_SHORT_CODES:
        return ROAD_SOURCE_SHORT_CODES[full_id]

    # Unknown source - raise error
    valid = RoadSource.values()
    raise ValueError(f"Unknown road source ID '{full_id}'. Valid sources: {valid}")


def is_valid_road_source(source_id: str) -> bool:
    """Check if a road source ID is valid.

    Args:
        source_id: Road source ID string to check

    Returns:
        True if valid, False otherwise
    """
    return source_id in RoadSource.values()


def to_water_short_code(full_id: str | WaterSource) -> str:
    """Convert full water source ID to short code for frontend export.

    Args:
        full_id: Full water source ID (e.g., 'manual', 'ml_water')

    Returns:
        Short code (e.g., 'man', 'ml')

    Raises:
        ValueError: If full_id is not a valid water source

    Example:
        >>> to_water_short_code('manual')
        'man'
        >>> to_water_short_code(WaterSource.ML_WATER)
        'ml'
    """
    # Handle WaterSource enum input
    if isinstance(full_id, WaterSource):
        return _WATER_SOURCE_TO_SHORT[full_id].value

    # Handle string input - validate it's a known water source
    if full_id in WATER_SOURCE_SHORT_CODES:
        return WATER_SOURCE_SHORT_CODES[full_id]

    # Unknown source - raise error
    valid = WaterSource.values()
    raise ValueError(f"Unknown water source ID '{full_id}'. Valid sources: {valid}")


def is_valid_water_source(source_id: str) -> bool:
    """Check if a water source ID is valid.

    Args:
        source_id: Water source ID string to check

    Returns:
        True if valid, False otherwise
    """
    return source_id in WaterSource.values()


def get_source_dir(source_id: str | Source) -> Path:
    """Get directory path for a source.

    Args:
        source_id: Full source ID or Source enum

    Returns:
        Path to source directory
    """
    if isinstance(source_id, Source):
        source_id = source_id.value
    return SOURCES_DIR / source_id


def get_normalized_path(source_id: str | Source, feature_type: str = 'buildings') -> Path:
    """Get path to normalized GeoJSON for a source.

    Args:
        source_id: Full source ID or Source enum
        feature_type: 'buildings', 'roads', or 'water'

    Returns:
        Path to normalized GeoJSON
    """
    if isinstance(source_id, Source):
        source_id = source_id.value
    return SOURCES_DIR / source_id / "normalized" / f"{feature_type}.geojson"


# =============================================================================
# Export Field Requirements
# =============================================================================

# Required fields in exported GeoJSON (frontend contract)
# Validation script checks these exist in output
REQUIRED_EXPORT_FIELDS = {
    'buildings': [
        'bid',      # Building ID
        'sd',       # Start date (construction year)
        'ev',       # Evidence level (h/m/l)
        'src',      # Primary source
        'sd_src',   # Date source (who provided the date)
    ],
    'roads': [
        'rid',      # Road ID
        'sd',       # Start date
        'ev',       # Evidence level
        'src',      # Primary source
    ],
    'water': [
        'wid',      # Water feature ID
        'sd',       # Start date
        'wtype',    # Water type (fjord, river, lake, etc.)
        'src',      # Primary source
    ],
}

# Optional fields (exported if available)
OPTIONAL_EXPORT_FIELDS = {
    'buildings': [
        'ed',       # End date (demolition year)
        'nm',       # Name
        'sd_t',     # Date type (x=exact, n=not-later-than, u=unknown)
        'sd_c',     # Date confidence (0-1)
        'repl_by',  # Replaced by (building ID)
        'repl_of',  # Replacement of (building ID)
    ],
    'roads': [
        'ed',       # End date
        'nm',       # Name
    ],
    'water': [
        'ed',       # End date (when filled)
        'nm',       # Name
    ],
}

# =============================================================================
# Merge Configuration
# =============================================================================

# Default merge config paths
MERGE_CONFIG = MERGED_DIR / "merge_config.json"
ROADS_MERGE_CONFIG = MERGED_DIR / "roads_merge_config.json"
WATER_MERGE_CONFIG = MERGED_DIR / "water_merge_config.json"

# Date priority (lower = higher priority, used when multiple sources have dates)
DEFAULT_DATE_PRIORITY = {
    'manual': 0,           # Highest: human-verified
    'trondheim_kommune': 1,
    'finn': 2,
    'sefrak': 3,
    'matrikkelen': 4,
    'ml_detected': 5,
    'osm': 6,              # Lowest: often missing dates
}

# =============================================================================
# Date Inference Constants (existing)
# =============================================================================

# Date inference fallbacks
DATE_FALLBACK = 1960  # Default year for buildings with unknown construction date
FALLBACK_YEAR_BUILDINGS = DATE_FALLBACK  # Alias for consistency

# Date inheritance parameters
NEAREST_K_DONORS = 3  # Number of nearest donors to use for median date calculation

# =============================================================================
# Spatial Parameters (Roads)
# =============================================================================

ROAD_BUFFER_M = 50  # Buffer for road-to-building proximity
ROAD_OFFSET_YEARS = 2  # Years to subtract from building date for road inference

# Road date inference fallbacks
ROAD_FALLBACK_YEAR = 2000  # Final fallback year for roads without dates
FALLBACK_YEAR_ROADS = ROAD_FALLBACK_YEAR  # Alias for consistency
ROAD_BUILDING_OFFSET = 2  # Years to subtract from earliest building date

# =============================================================================
# ML Confidence Thresholds
# =============================================================================

ML_CONFIDENCE_HIGH = 0.9  # Threshold for high evidence
ML_CONFIDENCE_MEDIUM = 0.7  # Threshold for medium evidence

# =============================================================================
# Era Boundaries
# =============================================================================

ERA_PRE_1900 = 1900  # Buildings before this require high evidence for replacement
ERA_POST_1950 = 1950  # Buildings after this accept any replacement evidence

# =============================================================================
# Evidence Levels
# =============================================================================

EVIDENCE_HIGH = 'h'
EVIDENCE_MEDIUM = 'm'
EVIDENCE_LOW = 'l'

# Evidence priority order (for comparisons)
EVIDENCE_ORDER = {EVIDENCE_HIGH: 3, EVIDENCE_MEDIUM: 2, EVIDENCE_LOW: 1}

# Valid evidence levels (for validation)
VALID_EVIDENCE_LEVELS = {'h', 'm', 'l'}

# =============================================================================
# Validation Constants
# =============================================================================

# Valid date types
VALID_DATE_TYPES = {'x', 'n', 'e', 's', 'u'}  # exact, not-later, not-earlier, estimated, unknown

# Valid water types
VALID_WATER_TYPES = {'fjord', 'river', 'lake', 'canal', 'harbor', 'pond', 'stream'}

# Year range for validation
MIN_VALID_YEAR = 1700
MAX_VALID_YEAR = 2030

# =============================================================================
# Docker/Deployment Paths
# =============================================================================

# Paths inside Docker container (for backend)
DOCKER_DATA_DIR = Path("/app/data")
DOCKER_EXPORT_DIR = DOCKER_DATA_DIR / "export"
DOCKER_SOURCES_DIR = DOCKER_DATA_DIR / "sources"

# =============================================================================
# Helper Functions (existing)
# =============================================================================

def determine_era(year: int) -> str:
    """
    Determine which era a year falls into.

    Args:
        year: The year to categorize

    Returns:
        One of: 'pre_1900', '1900_1950', or 'post_1950'

    Examples:
        >>> determine_era(1850)
        'pre_1900'
        >>> determine_era(1925)
        '1900_1950'
        >>> determine_era(1975)
        'post_1950'
    """
    if year < ERA_PRE_1900:
        return 'pre_1900'
    elif year < ERA_POST_1950:
        return '1900_1950'
    else:
        return 'post_1950'


def check_evidence_meets_threshold(evidence: str, min_evidence: str) -> bool:
    """
    Check if evidence level meets or exceeds a minimum threshold.

    Evidence hierarchy: 'h' (high) > 'm' (medium) > 'l' (low)

    Args:
        evidence: The evidence level to check
        min_evidence: The minimum required evidence level

    Returns:
        True if evidence meets or exceeds the threshold, False otherwise

    Examples:
        >>> check_evidence_meets_threshold('h', 'm')
        True
        >>> check_evidence_meets_threshold('m', 'h')
        False
        >>> check_evidence_meets_threshold('m', 'm')
        True
        >>> check_evidence_meets_threshold('l', 'h')
        False
    """
    return EVIDENCE_ORDER.get(evidence, 0) >= EVIDENCE_ORDER.get(min_evidence, 0)


# =============================================================================
# Ensure Directories Exist
# =============================================================================

def ensure_directories():
    """Create required directories if they don't exist."""
    for directory in [MERGED_DIR, EXPORT_DIR]:
        directory.mkdir(parents=True, exist_ok=True)
