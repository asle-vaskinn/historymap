"""
Tests for scripts/constants.py

Tests the core constants, GeoContext, and source mapping functions.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from constants import (
    GEO,
    GeoContext,
    Source,
    SourceShort,
    ML_MAP_SOURCES,
    to_short_code,
    to_full_id,
    is_valid_source,
)


class TestGeoContext:
    """Tests for GeoContext coordinate conversions."""

    def test_trondheim_center_lat(self, geo):
        """GEO should be centered on Trondheim."""
        assert geo.center_lat == 63.43

    def test_meters_per_degree_lat(self, geo):
        """Latitude degrees are ~111km."""
        assert geo.meters_per_degree_lat == 111000

    def test_meters_per_degree_lon(self, geo):
        """Longitude degrees vary with latitude."""
        # At 63°N, cos(63°) ≈ 0.45
        assert 45000 < geo.meters_per_degree_lon < 55000

    def test_degrees_to_meters(self, geo):
        """Convert degrees to meters."""
        meters = geo.degrees_to_meters(0.001)  # ~0.001 degrees
        assert 70 < meters < 100  # Should be ~80m

    def test_meters_to_degrees(self, geo):
        """Convert meters to degrees."""
        degrees = geo.meters_to_degrees(100)  # 100 meters
        assert 0.001 < degrees < 0.002  # Should be ~0.00125 degrees

    def test_round_trip(self, geo):
        """degrees_to_meters and meters_to_degrees are inverses."""
        original = 50  # meters
        degrees = geo.meters_to_degrees(original)
        back = geo.degrees_to_meters(degrees)
        assert abs(back - original) < 0.01  # Within 1cm

    def test_bbox(self, geo, trondheim_bbox):
        """GEO bbox covers Trondheim."""
        assert geo.bbox == trondheim_bbox


class TestSourceMapping:
    """Tests for source ID and short code mappings."""

    def test_to_short_code_basic(self):
        """Basic source to short code conversion."""
        assert to_short_code('sefrak') == 'sef'
        assert to_short_code('osm') == 'osm'
        assert to_short_code('trondheim_kommune') == 'tk'
        assert to_short_code('manual') == 'man'

    def test_to_short_code_enum(self):
        """Convert Source enum to short code."""
        assert to_short_code(Source.SEFRAK) == 'sef'
        assert to_short_code(Source.TRONDHEIM_KOMMUNE) == 'tk'

    def test_to_short_code_ml_sources(self):
        """ML map sources get specific short codes."""
        assert to_short_code('ml_kartverket_1880') == 'kv1880'
        assert to_short_code('ml_kartverket_1904') == 'kv1904'

    def test_to_short_code_invalid(self):
        """Invalid source raises ValueError."""
        with pytest.raises(ValueError):
            to_short_code('invalid_source')

    def test_to_full_id_basic(self):
        """Short code to full ID conversion."""
        assert to_full_id('sef') == 'sefrak'
        assert to_full_id('tk') == 'trondheim_kommune'
        assert to_full_id('man') == 'manual'

    def test_to_full_id_ml(self):
        """ML short codes to full ID."""
        assert to_full_id('kv1880') == 'ml_kartverket_1880'
        assert to_full_id('kv1904') == 'ml_kartverket_1904'

    def test_is_valid_source(self):
        """Test source validation."""
        assert is_valid_source('osm') is True
        assert is_valid_source('sefrak') is True
        assert is_valid_source('invalid') is False


class TestMLMapSources:
    """Tests for ML map source definitions."""

    def test_ml_sources_defined(self):
        """ML map sources should be defined."""
        assert 'ml_kartverket_1880' in ML_MAP_SOURCES
        assert 'ml_kartverket_1904' in ML_MAP_SOURCES

    def test_ml_short_codes(self):
        """ML short codes should be year-based."""
        assert ML_MAP_SOURCES['ml_kartverket_1880'] == 'kv1880'
        assert ML_MAP_SOURCES['ml_kartverket_1904'] == 'kv1904'
