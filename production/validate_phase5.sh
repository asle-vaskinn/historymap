#!/bin/bash
################################################################################
# Phase 5: Validation Script
#
# Validates the output from data merging and PMTiles generation.
#
# Checks:
# 1. Merged GeoJSON exists and is valid
# 2. Features have required temporal attributes
# 3. PMTiles file exists and is valid
# 4. Feature count and distribution is reasonable
# 5. Temporal range is correct
#
# Usage:
#   ./validate_phase5.sh [merged_geojson] [pmtiles_file]
#
# Example:
#   ./validate_phase5.sh ../data/final/trondheim_all_eras.geojson ../data/final/trondheim_all_eras.pmtiles
################################################################################

set -e
set -u
set -o pipefail

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ERRORS=0
WARNINGS=0

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
    ((WARNINGS++))
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
    ((ERRORS++))
}

check_file_exists() {
    local file="$1"
    local description="$2"

    if [[ ! -f "$file" ]]; then
        log_error "$description not found: $file"
        return 1
    fi

    log_success "$description exists"
    return 0
}

validate_geojson_structure() {
    local file="$1"

    log_info "Validating GeoJSON structure..."

    if ! command -v jq &> /dev/null; then
        log_warning "jq not installed, skipping JSON validation"
        return 0
    fi

    # Check valid JSON
    if ! jq empty "$file" 2>/dev/null; then
        log_error "Invalid JSON in $file"
        return 1
    fi

    # Check FeatureCollection type
    local type
    type=$(jq -r '.type' "$file" 2>/dev/null)
    if [[ "$type" != "FeatureCollection" ]]; then
        log_error "Not a FeatureCollection (type: $type)"
        return 1
    fi

    log_success "Valid GeoJSON FeatureCollection"
    return 0
}

validate_feature_count() {
    local file="$1"
    local min_features=10

    log_info "Checking feature count..."

    if ! command -v jq &> /dev/null; then
        log_warning "jq not installed, skipping feature count"
        return 0
    fi

    local count
    count=$(jq '.features | length' "$file" 2>/dev/null)

    if [[ "$count" -lt "$min_features" ]]; then
        log_error "Too few features: $count (minimum: $min_features)"
        return 1
    fi

    log_success "Feature count: $count"
    return 0
}

validate_temporal_attributes() {
    local file="$1"

    log_info "Validating temporal attributes..."

    if ! command -v jq &> /dev/null; then
        log_warning "jq not installed, skipping temporal validation"
        return 0
    fi

    # Check that features have required properties
    local total_features
    total_features=$(jq '.features | length' "$file")

    local features_with_start_date
    features_with_start_date=$(jq '[.features[].properties | select(.start_date != null)] | length' "$file")

    local features_with_class
    features_with_class=$(jq '[.features[].properties | select(.feature_class != null)] | length' "$file")

    local features_with_source
    features_with_source=$(jq '[.features[].properties | select(.source != null)] | length' "$file")

    log_info "Features with temporal attributes:"
    log_info "  start_date: $features_with_start_date / $total_features"
    log_info "  feature_class: $features_with_class / $total_features"
    log_info "  source: $features_with_source / $total_features"

    # Warnings for missing attributes
    local start_date_pct=$((features_with_start_date * 100 / total_features))
    if [[ "$start_date_pct" -lt 50 ]]; then
        log_warning "Less than 50% of features have start_date"
    fi

    if [[ "$features_with_class" -ne "$total_features" ]]; then
        log_warning "Not all features have feature_class"
    fi

    if [[ "$features_with_source" -ne "$total_features" ]]; then
        log_warning "Not all features have source"
    fi

    log_success "Temporal attributes validated"
    return 0
}

validate_feature_classes() {
    local file="$1"

    log_info "Checking feature class distribution..."

    if ! command -v jq &> /dev/null; then
        log_warning "jq not installed, skipping class distribution"
        return 0
    fi

    log_info "Feature classes:"
    jq -r '.features[].properties.feature_class' "$file" 2>/dev/null | \
        sort | uniq -c | while read -r count class; do
            log_info "  $class: $count"
        done

    log_success "Feature classes validated"
    return 0
}

validate_temporal_range() {
    local file="$1"

    log_info "Checking temporal range..."

    if ! command -v jq &> /dev/null; then
        log_warning "jq not installed, skipping temporal range"
        return 0
    fi

    local min_year
    min_year=$(jq '[.features[].properties.start_date | select(. != null)] | min' "$file" 2>/dev/null)

    local max_year
    max_year=$(jq '[.features[].properties | select(.end_date != null) | .end_date] | max' "$file" 2>/dev/null)

    if [[ "$min_year" != "null" ]]; then
        log_info "Earliest start_date: $min_year"

        if [[ "$min_year" -lt 1700 ]] || [[ "$min_year" -gt 2100 ]]; then
            log_warning "Suspicious minimum year: $min_year"
        fi
    fi

    if [[ "$max_year" != "null" ]]; then
        log_info "Latest end_date: $max_year"

        local current_year
        current_year=$(date +%Y)
        if [[ "$max_year" -gt $((current_year + 10)) ]]; then
            log_warning "Suspicious maximum year: $max_year"
        fi
    fi

    log_success "Temporal range validated"
    return 0
}

validate_metadata() {
    local file="$1"

    log_info "Checking metadata..."

    if ! command -v jq &> /dev/null; then
        log_warning "jq not installed, skipping metadata check"
        return 0
    fi

    if jq -e '.metadata' "$file" > /dev/null 2>&1; then
        log_info "Metadata:"
        jq '.metadata' "$file" 2>/dev/null || true
        log_success "Metadata present"
    else
        log_warning "No metadata found"
    fi

    return 0
}

validate_pmtiles() {
    local file="$1"

    log_info "Validating PMTiles file..."

    # Check file size
    local file_size
    file_size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null || echo "0")

    if [[ "$file_size" -eq 0 ]]; then
        log_error "PMTiles file is empty"
        return 1
    fi

    local size_mb=$((file_size / 1024 / 1024))
    log_info "File size: ${size_mb} MB"

    # Validate with pmtiles CLI if available
    if command -v pmtiles &> /dev/null; then
        log_info "Validating PMTiles structure with pmtiles CLI..."

        if pmtiles show "$file" > /dev/null 2>&1; then
            log_success "PMTiles structure is valid"

            # Show summary
            log_info "PMTiles summary:"
            pmtiles show "$file" | head -15 | while IFS= read -r line; do
                log_info "  $line"
            done
        else
            log_error "PMTiles validation failed"
            return 1
        fi
    else
        log_warning "pmtiles CLI not installed, skipping structure validation"
    fi

    log_success "PMTiles file validated"
    return 0
}

show_summary() {
    echo ""
    echo "=================================================="
    echo "  Validation Summary"
    echo "=================================================="

    if [[ $ERRORS -eq 0 ]] && [[ $WARNINGS -eq 0 ]]; then
        log_success "All checks passed!"
    elif [[ $ERRORS -eq 0 ]]; then
        echo -e "${YELLOW}Validation completed with $WARNINGS warning(s)${NC}"
    else
        echo -e "${RED}Validation failed with $ERRORS error(s) and $WARNINGS warning(s)${NC}"
    fi

    echo "=================================================="
    echo ""
}

main() {
    local merged_geojson="${1:-../data/final/trondheim_all_eras.geojson}"
    local pmtiles_file="${2:-../data/final/trondheim_all_eras.pmtiles}"

    echo ""
    echo "=================================================="
    echo "  Phase 5 Validation"
    echo "  Trondheim Historical Map Project"
    echo "=================================================="
    echo ""

    log_info "Validating merged GeoJSON: $merged_geojson"
    log_info "Validating PMTiles: $pmtiles_file"
    echo ""

    # Check files exist
    check_file_exists "$merged_geojson" "Merged GeoJSON" || true
    check_file_exists "$pmtiles_file" "PMTiles file" || true

    echo ""

    # Validate GeoJSON if it exists
    if [[ -f "$merged_geojson" ]]; then
        validate_geojson_structure "$merged_geojson" || true
        validate_feature_count "$merged_geojson" || true
        validate_temporal_attributes "$merged_geojson" || true
        validate_feature_classes "$merged_geojson" || true
        validate_temporal_range "$merged_geojson" || true
        validate_metadata "$merged_geojson" || true
    fi

    echo ""

    # Validate PMTiles if it exists
    if [[ -f "$pmtiles_file" ]]; then
        validate_pmtiles "$pmtiles_file" || true
    fi

    # Show summary
    show_summary

    # Exit with error if there were errors
    if [[ $ERRORS -gt 0 ]]; then
        exit 1
    fi

    exit 0
}

main "$@"
