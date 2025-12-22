# Problem Statement

## The Core Problem

There is no easy way to explore how Trondheim looked historically. Existing solutions either:
- Show static historical maps without context
- Lack temporal navigation (can't "slide through time")
- Don't connect historical data to modern geography
- Require expert knowledge to interpret

## Data Challenge

Historical building dates are scattered across multiple sources with varying reliability:

| Source | Coverage | Reliability | Accessibility |
|--------|----------|-------------|---------------|
| SEFRAK | Pre-1900 buildings | High | Available |
| Matrikkelen | Official records | High | API available |
| Kartverket maps | 1880s onwards | Visual only | WMS available |
| Aerial photos | 1940s onwards | High | Restricted access |
| OSM | Modern | Variable | Open |

**Challenge**: No single source provides complete temporal coverage.

## Why This Matters

### Cultural Heritage
Understanding how the urban environment evolved over time preserves cultural memory and helps future generations understand their heritage.

### Urban Planning
Learning from historical development patterns informs better planning decisions. Seeing what worked (and what didn't) provides valuable insights.

### Personal Connection
People want to know: "When was my building built?" and "What stood here before?" These questions create emotional connection to place.

### Education
Teaching local history becomes interactive and engaging when students can visually explore changes over time.

## Gap Analysis

### What Exists Today
- Kartverket provides WMS access to historical maps (static rasters)
- SEFRAK database lists cultural heritage buildings with dates
- Academic projects have digitized some historical maps
- OSM provides excellent modern baseline data

### What's Missing
- No unified temporal view combining all sources
- No way to smoothly navigate through time
- Historical map data locked in raster format (not queryable)
- No transparency about data quality and confidence
- Limited accessibility for non-experts

## Impact of Not Solving This

Without a solution:
- Historical knowledge remains fragmented and inaccessible
- Research requires specialized GIS skills and multiple data sources
- Public engagement with local history remains limited
- Valuable historical patterns go unnoticed
- Each generation becomes more disconnected from urban heritage
