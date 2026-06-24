# Feature: Feature Extraction Tool

## Overview

Originally designed as a debug page for inspecting data sources, this tool evolved into a comprehensive **Feature Extraction Tool** for data quality inspection, water/building annotation, and ML training preparation.

> **Note**: Two main tools exist:
> - `frontend/feature_extraction.*` - Multi-purpose data prep with editing capabilities
> - `frontend/source_manager.html` - Georeferencing workflow (see `feat_georeferencing`)
>
> Legacy tools moved to `frontend/legacy/`: dataprep, gcp_editor, georef_editor

## Problem

When debugging data quality issues, it's difficult to:
- See the original raw data before processing
- Understand what normalization did to the data
- Verify that features are correctly georeferenced
- Isolate issues to a specific source
- Manually correct ML detection errors

## Solution

A standalone page for inspecting and editing data sources with multiple capabilities:

| Capability | Description |
|------------|-------------|
| **Source Inspection** | View raw, normalized, and rendered data |
| **Water Editor** | Draw/edit water polygons with temporal attributes |
| **Building Annotation** | Mark building corrections for ML training |
| **Data Overlays** | Toggle buildings, roads, water from merged database |
| **WMS Integration** | View historical WMS layers for comparison |

## Current Implementation

### Files
- `frontend/feature_extraction.html` - standalone page
- `frontend/feature_extraction.js` - map logic, editing, layer management
- `frontend/feature_extraction.css` - styling

### Capabilities Implemented

**Data Inspection:**
- [x] Multiple source selection (not just kv1880)
- [x] WMS layer viewing (Trondheim Kommune, Geonorge historical)
- [x] Data overlay toggles (buildings, roads, water)
- [x] Feature inspection on click

**Water Editor:**
- [x] OSM water import via Overpass API
- [x] Polygon drawing with MapboxDraw
- [x] Property form (name, wtype, sd, ed)
- [x] Backend persistence (`/api/water/*`)

**Building Annotation:**
- [x] Building correction workflow
- [x] Backend API integration

### Backend APIs

| Endpoint | Purpose |
|----------|---------|
| `/api/water/add` | Add new water polygon |
| `/api/water/update` | Update water properties |
| `/api/water/delete` | Remove water polygon |
| `/api/align` | Alignment tools (TPS/TIN/Affine) |

## Original Scope (Phase 1) - COMPLETED

Single source: **Kartverket 1880 (kv1880)** - Now supports multiple sources.

## Dependencies

- MapLibre GL JS
- MapboxDraw (for polygon editing)
- Backend API (`backend/app.py`)

## Related Features

- `feat_georeferencing` - Uses `frontend/source_manager.html` for GCP-based georeferencing
- `feat_ml_extraction` - Consumes annotations from this tool

## Changelog

### 2026-01-03 (Consolidation)
- Renamed: `source_viewer.*` → `feature_extraction.*`
- Moved: Legacy tools (dataprep, gcp_editor, georef_editor) to `frontend/legacy/`
- Updated: All file references in documentation

### 2026-01-03
- Updated: Documented evolved capabilities beyond original Phase 1 scope
- Added: Water editor and building annotation documentation
- Changed: Title to reflect dual-purpose nature

### 2025-12-23 (Implementation)
- Added: Water editor mode with OSM import
- Added: Data overlay toggles
- Added: Backend API integration
- Expanded: Multi-source support
