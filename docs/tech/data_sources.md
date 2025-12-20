# Data Sources and Attribution

This document details all data sources used in the Trondheim Historical Map project, their licenses, and proper attribution requirements.

## Overview

The Trondheim Historical Map combines multiple data sources:
1. **Modern geographic data** from OpenStreetMap
2. **Historical maps** from Kartverket (Norwegian Mapping Authority)
3. **Machine learning-extracted features** from historical maps
4. **Synthetic training data** generated from modern data

## Primary Data Sources

### 1. OpenStreetMap (OSM)

**Website**: https://www.openstreetmap.org/

**What We Use**:
- Current building footprints
- Road network
- Railway lines
- Water bodies (rivers, lakes, coastline)
- Land use and land cover
- Place names and administrative boundaries

**Geographic Coverage**:
- Trondheim municipality (Trøndelag, Norway)
- Surrounding municipalities: Malvik, Stjørdal, Meråker, Melhus, Skaun, Klæbu
- Approximate area: 3,000 km²
- Bounding box: [10.0°E, 63.3°N, 10.8°E, 63.5°N]

**Data Freshness**:
- Extract date: 2025-12-16 (or as indicated in project files)
- OSM is continuously updated by community contributors
- Our extract is a snapshot from a specific date

**License**: Open Database License (ODbL) 1.0

**Attribution Required**:
> © OpenStreetMap contributors

**License Details**:
- **Permissions**: Free to copy, distribute, transmit, and adapt the data
- **Conditions**: Must attribute OpenStreetMap and contributors
- **ShareAlike**: Derivative works must use same license (ODbL)
- **Full license**: https://opendatacommons.org/licenses/odbl/

**How to Attribute**:
- Maps and derived works must include: "© OpenStreetMap contributors"
- Include link to https://www.openstreetmap.org/copyright
- If using data files directly, include ODbL license

**Data Quality**:
- Community-maintained, quality varies by area
- Trondheim area is well-mapped with high detail
- Urban areas generally more detailed than rural areas
- Temporal attributes (construction dates) may be incomplete

**Temporal Attributes in OSM**:
OSM features may include:
- `start_date`: When feature was created/built (not always present)
- `end_date`: When feature was demolished/removed (rarely present)
- Building age estimation from other tags when available

### 2. Kartverket Historical Maps

**Organization**: Kartverket (Norwegian Mapping Authority)
**Website**: https://www.kartverket.no/
**Map Archive**: https://kartkatalog.geonorge.no/

**What We Use**:
Historical map raster images for the Trondheim region, spanning:
- Late 19th century (1850s-1890s)
- Early 20th century (1900s-1930s)
- Mid 20th century (1940s-1970s)
- Late 20th century (1980s-2000s)

**Map Types**:

1. **Amtskart (County Maps)**
   - Period: 1826-1916
   - Scale: Typically 1:100,000
   - Content: Topographic features, settlements, roads, boundaries
   - Quality: Varies, some aged/degraded

2. **Topographic Maps**
   - Period: 1900s-present
   - Scale: 1:50,000 and 1:25,000
   - Content: Detailed topography, buildings, infrastructure
   - Quality: Generally good

3. **Cadastral Maps**
   - Period: Various eras
   - Scale: Large scale (1:5,000 or larger)
   - Content: Property boundaries, buildings, lot numbers
   - Quality: High detail, focused on urban areas

4. **Economic Maps (Økonomisk kartverk)**
   - Period: 1960s-present
   - Scale: 1:5,000
   - Content: Comprehensive detail, buildings, land use
   - Quality: Excellent

**Licensing**:

Maps are divided into two categories based on age:

**Public Domain (Maps >100 years old)**:
- Any map published before ~1925 (as of 2025)
- No copyright restrictions
- No attribution legally required (but recommended)
- Free for any use

**CC BY 4.0 (Maps <100 years old)**:
- Maps published after ~1925
- Creative Commons Attribution 4.0 International
- Full license: https://creativecommons.org/licenses/by/4.0/

**Attribution Required for CC BY 4.0**:
> © Kartverket

**License Details (CC BY 4.0)**:
- **Permissions**: Free to share, adapt, use commercially
- **Conditions**: Must give appropriate credit
- **No ShareAlike**: Can use different license for derivatives
- **No restrictions**: Cannot add legal or technical restrictions

**How to Attribute**:
```
Historical maps © Kartverket
Available under CC BY 4.0 license
Source: https://kartkatalog.geonorge.no/
```

**Data Access**:
- Maps available through Geonorge portal
- Some maps require account/login (free)
- Download formats: GeoTIFF, JPEG2000, PDF
- Coordinate systems: Various (typically UTM Zone 33N or older Norwegian systems)

**Geographic Accuracy**:
- Older maps (pre-1900): ±50-100m typical error
- Early 20th century: ±20-50m
- Mid-20th century: ±10-20m
- Modern maps: ±1-5m

**Temporal Accuracy**:
- Map date indicates survey/publication year
- Features may be several years older than map date
- Updates not always immediate

### 3. FINN.no Property Listings

**Website**: https://www.finn.no/
**Data Type**: Real estate property listings with construction dates

**What We Use**:
- Construction year (`sd`) from property metadata
- Property addresses for geocoding
- OSM building references for matching

**Date Priority**: 1 (higher than SEFRAK's 10-year ranges, lower than MANUAL)

**Evidence Level**: Medium (property listings generally reliable but may have errors)

**Matching Strategy**:
1. Primary: Match via `osm_ref` field (explicit link to OSM building)
2. Fallback: Spatial matching (centroid within 10m + 50% overlap)

**Data Quality**:
- Exact construction years (single year, not ranges)
- Sourced from property records and seller information
- May include renovation dates mistaken for construction
- Coverage limited to listed properties

**Licensing**: Data scraped for research purposes only
- Not redistributable
- Used only for date enrichment of existing OSM buildings

### 4. Machine Learning Extracted Features

**What These Are**:
Geographic features (buildings, roads, water bodies) automatically extracted from Kartverket historical maps using computer vision and machine learning.

**Creation Process**:
1. Historical maps downloaded from Kartverket
2. Maps georeferenced to modern coordinate system
3. ML model (U-Net) processes map images
4. Features vectorized and attributed with dates

**Accuracy**:
- Not ground truth - ML predictions have errors
- Estimated accuracy: 70-85% for buildings, 60-80% for roads
- Quality varies by map age, condition, and clarity
- See [methodology.md](../tech/methodology.md) for details

**Licensing**:
Derived from Kartverket maps, inherits same license:
- Maps >100 years: Public domain
- Maps <100 years: CC BY 4.0

**Attribution**:
```
Features extracted from Kartverket historical maps using machine learning
Original maps © Kartverket (CC BY 4.0)
Extraction accuracy not guaranteed - see documentation
```

**Confidence Scores**:
Each extracted feature includes confidence score:
- `confidence: 0.95` - Very high confidence
- `confidence: 0.75` - Medium confidence
- `confidence: 0.50` - Low confidence (threshold)

Features below 0.50 confidence are typically excluded.

**Known Limitations**:
- Small buildings may be missed
- Complex building shapes may be simplified
- Roads in poor-quality map areas less accurate
- Handwritten text not extracted
- Some features may be misclassified

### 4. Synthetic Training Data

**What This Is**:
Artificially generated "historical-looking" map images created from modern OSM data, used to train the ML model.

**Creation Process**:
1. Modern OSM vector data styled to look historical
2. Aging effects applied (yellowing, degradation, etc.)
3. Ground truth masks generated from vector data
4. Used for initial ML model training

**Licensing**:
Derived from OpenStreetMap data:
- Subject to ODbL license
- Not distributed publicly (training data only)
- Methodology described in project documentation

**Attribution Not Required**:
Synthetic data is intermediate/training data, not included in final product.

## Data Processing and Derivatives

### PMTiles

**What It Is**:
Vector tile archive format combining all data sources into a single file for web delivery.

**Contents**:
- Modern OSM features
- ML-extracted historical features
- Merged and deduplicated data
- Temporal attributes (start_date, end_date)

**Licensing**:
As a derivative work combining OSM and Kartverket data:
- Must comply with ODbL (OSM requirement)
- Must comply with CC BY 4.0 (Kartverket requirement)
- Therefore: Dual-licensed under both terms

**Attribution**:
```
Map data © OpenStreetMap contributors (ODbL)
Historical maps © Kartverket (CC BY 4.0)
```

### GeoJSON Files

Intermediate vector data files in GeoJSON format.

**Licensing**: Same as PMTiles (dual-licensed)

**Attribution**: Same as PMTiles

## Additional Data and Resources

### Base Map Tiles (Background)

If using third-party base map tiles for context:

**Options**:
- **OpenMapTiles**: © OpenMapTiles, © OpenStreetMap contributors
- **Mapbox**: Requires Mapbox account and attribution
- **Stamen**: © Stamen Design, © OpenStreetMap contributors

**Current Implementation**:
This project uses direct PMTiles rendering without external base maps, but background imagery can be added.

### Elevation Data (Optional)

If terrain/elevation added in future:

**Source**: Kartverket DTM (Digital Terrain Model)
**License**: CC BY 4.0 or public domain
**Attribution**: © Kartverket

### Satellite Imagery (Optional)

If satellite imagery used for validation:

**Source**: Various (Sentinel, Landsat, commercial)
**License**: Depends on source
**Not currently used in production**

## Combined Attribution

### For the Complete Application

```
Trondheim Historical Map

Map data © OpenStreetMap contributors
Licensed under Open Database License (ODbL)
https://www.openstreetmap.org/copyright

Historical maps © Kartverket
Licensed under CC BY 4.0
https://www.kartverket.no/

ML-extracted features derived from Kartverket maps
Accuracy not guaranteed - see documentation

Application built with:
- MapLibre GL JS (BSD-3-Clause)
- PMTiles (BSD-3-Clause)
- PyTorch (BSD-style)
```

### For Printed Maps or Static Images

If creating static maps or screenshots:

```
© OpenStreetMap contributors (ODbL)
Historical maps © Kartverket (CC BY 4.0)
Trondheim Historical Map project
```

### For Academic/Research Use

```
Data sources:
- Modern features: OpenStreetMap contributors.
  Open Database License (ODbL). Retrieved 2025-12-16.
- Historical maps: Kartverket (Norwegian Mapping Authority).
  Creative Commons Attribution 4.0 International (CC BY 4.0).
- Feature extraction: Machine learning pipeline described in [methodology.md](../tech/methodology.md).
```

## Data Quality and Accuracy Disclaimer

**Important**: This application combines multiple data sources with varying accuracy levels:

1. **OpenStreetMap**: Community-maintained, generally accurate but not surveyed
2. **Historical maps**: Source maps have inherent inaccuracies (±5-100m depending on age)
3. **ML extractions**: Automated process with 70-85% accuracy, not manually verified

**This data is provided "as-is" without warranty of accuracy, completeness, or fitness for any particular purpose.**

**Not suitable for**:
- Legal/cadastral purposes
- Navigation (use modern maps)
- Property boundary determination
- Any use requiring surveyed accuracy

**Suitable for**:
- Historical research and exploration
- Educational purposes
- Urban development visualization
- Cultural heritage documentation

## Updates and Corrections

### OSM Updates
- OSM data can be refreshed by downloading new extract
- Update frequency: As needed (monthly, quarterly, etc.)

### Historical Map Additions
- New historical maps can be processed as they become available
- Kartverket continuously digitizes archive

### Corrections
If you find errors in the data:
1. OSM errors: Edit directly on OpenStreetMap.org
2. Historical feature errors: Report via project repository
3. Classification errors: Flag for manual review

## License Compatibility

**ODbL + CC BY 4.0 Compatibility**:
- Both are "copyleft" but different strengths
- ODbL requires ShareAlike for database derivatives
- CC BY 4.0 does not require ShareAlike
- Combined work subject to stricter ODbL terms for database aspect
- Individual map images can cite CC BY 4.0 only if no OSM data

**Project Code License**:
- Application code: MIT License
- Allows commercial use, modification, distribution
- See LICENSE file in repository

## Third-Party Libraries

All third-party libraries used comply with license requirements:

- **MapLibre GL JS**: BSD-3-Clause
- **Nginx**: 2-clause BSD
- **PyTorch**: BSD-style license
- **segmentation_models_pytorch**: MIT
- **GDAL**: MIT/X style
- **Pillow**: PIL License (permissive)

See full list in project dependencies.

## Contact and Permissions

### For OpenStreetMap:
- Website: https://www.openstreetmap.org/
- License questions: https://wiki.openstreetmap.org/wiki/Legal_FAQ

### For Kartverket:
- Website: https://www.kartverket.no/
- Email: post@kartverket.no
- Data portal: https://kartkatalog.geonorge.no/

### For This Project:
See repository README for contact information.

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-12-16 | Initial data sources documentation |
| 1.1 | 2025-12-20 | Added FINN.no property listings as data source |

---

**Last Updated**: 2025-12-20

This document is part of the Trondheim Historical Map project documentation.
See also: [user_guide.md](../user_guide.md), [methodology.md](../tech/methodology.md)
