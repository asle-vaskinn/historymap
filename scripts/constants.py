"""
Centralized constants for the Trondheim Historical Map data pipeline.

These values were previously hardcoded across multiple files.
Import from here to ensure consistency.
"""

# Date inference fallbacks
DATE_FALLBACK = 1960  # Default year for buildings with unknown construction date

# Date inheritance parameters
NEAREST_K_DONORS = 3  # Number of nearest donors to use for median date calculation

# Spatial parameters (roads)
ROAD_BUFFER_M = 50  # Buffer for road-to-building proximity
ROAD_OFFSET_YEARS = 2  # Years to subtract from building date for road inference

# ML confidence thresholds
ML_CONFIDENCE_HIGH = 0.9  # Threshold for high evidence
ML_CONFIDENCE_MEDIUM = 0.7  # Threshold for medium evidence

# Era boundaries for replacement detection rules
ERA_PRE_1900 = 1900  # Buildings before this require high evidence for replacement
ERA_POST_1950 = 1950  # Buildings after this accept any replacement evidence

# Evidence levels (string constants)
EVIDENCE_HIGH = 'h'
EVIDENCE_MEDIUM = 'm'
EVIDENCE_LOW = 'l'

# Evidence priority order (for comparisons)
EVIDENCE_ORDER = {EVIDENCE_HIGH: 3, EVIDENCE_MEDIUM: 2, EVIDENCE_LOW: 1}


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
