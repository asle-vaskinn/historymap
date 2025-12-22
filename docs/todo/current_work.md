# Current Work: Multi-Layer Date Inheritance

## Status: IMPLEMENTED
## Approved: 2025-12-22
## Implemented: 2025-12-22

## Summary

Enhance the date inheritance algorithm with a three-tier fallback strategy. Instead of just copying the nearest building's date within 1km, we use:
1. **Median** of all donors within 2km (most robust)
2. **Nearest** donor at any distance (for isolated buildings)
3. **1960 fallback** (ultimate fallback, should be rare)

SEFRAK buildings are excluded from the donor pool as they represent heritage buildings with unusually old dates that would skew estimates.

## Fallback Chain

| Priority | Method | Radius | Min Donors | Rationale |
|----------|--------|--------|------------|-----------|
| 1 | **Median** | 2km | 1 | Uses local neighborhood pattern |
| 2 | **Nearest** | unlimited | 1 | Fallback for isolated buildings |
| 3 | **1960** | - | 0 | Ultimate fallback |

## Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Median radius | 2000m (2km) | Captures neighborhood pattern |
| Donor sources | Exclude SEFRAK (`src != 'sef'`) | Heritage buildings are outliers |
| Donor evidence | High or Medium (`ev: 'h'` or `ev: 'm'`) | FINN has medium evidence |
| Result evidence | Low (`ev: 'l'`) | Inherited = uncertain |
| Distance weighting | None | Keep simple, equal treatment |

## Schema Additions

```
sd_inherited : bool      # true = date inherited from neighbor
sd_method    : string    # 'median' | 'nearest' | 'fallback'
sd_donors    : int       # number of donors used (for median)
sd_dist      : float     # distance in meters (for nearest)
```

## Tasks

### 1. Update inherit_dates_from_neighbors() function
- [x] Filter donor pool: exclude SEFRAK (`src != 'sef'`)
- [x] Implement median calculation for donors within 2km
- [x] Fall back to nearest (any distance) if no donors in 2km
- [x] Fall back to 1960 if no donors at all
- [x] Add `sd_method` field to track which method was used

### 2. Update merge workflow
- [x] Log statistics per method (median count, nearest count, fallback count)
- [x] Log median donor counts (avg donors per building)

### 3. Regenerate output
- [ ] Run merge pipeline
- [ ] Regenerate PMTiles
- [ ] Verify in frontend

### 4. Update documentation
- [x] Update DATA_SCHEMA.md with `sd_method` field

## Algorithm

```python
def inherit_dates_from_neighbors(features, median_radius_m=2000):
    # 1. Separate donors from recipients
    # Donors: has sd, high/medium evidence, NOT SEFRAK
    donors = [f for f in features
              if f['properties'].get('sd')
              and f['properties'].get('ev') in ('h', 'm')
              and f['properties'].get('src') != 'sef']

    recipients = [f for f in features if not f['properties'].get('sd')]

    # 2. Build spatial index of donor centroids
    donor_index = build_spatial_index(donors)

    # 3. For each recipient, apply fallback chain
    for recipient in recipients:
        centroid = get_centroid(recipient)

        # Try median within 2km
        nearby_donors = find_all_within(centroid, donor_index, median_radius_m)

        if nearby_donors:
            dates = [d['properties']['sd'] for d in nearby_donors]
            median_date = statistics.median(dates)
            recipient['properties']['sd'] = int(median_date)
            recipient['properties']['ev'] = 'l'
            recipient['properties']['sd_inherited'] = True
            recipient['properties']['sd_method'] = 'median'
            recipient['properties']['sd_donors'] = len(nearby_donors)
        else:
            # Fall back to nearest (any distance)
            nearest_donor, distance = find_nearest(centroid, donor_index)

            if nearest_donor:
                recipient['properties']['sd'] = nearest_donor['properties']['sd']
                recipient['properties']['ev'] = 'l'
                recipient['properties']['sd_inherited'] = True
                recipient['properties']['sd_method'] = 'nearest'
                recipient['properties']['sd_dist'] = round(distance, 1)
            else:
                # Ultimate fallback
                recipient['properties']['sd'] = 1960
                recipient['properties']['ev'] = 'l'
                recipient['properties']['sd_inherited'] = True
                recipient['properties']['sd_method'] = 'fallback'

    return features
```

## Expected Impact

- Donor pool: ~1,200 buildings (FINN with dates, excluding SEFRAK)
- Recipients: ~65,000 undated OSM buildings
- Most buildings get median-based dates from neighborhood
- Isolated buildings get nearest-based dates
- Very few should need 1960 fallback

## Success Criteria

- Buildings in dense areas use median (more robust)
- Buildings in sparse areas use nearest
- Year slider shows gradual city growth pattern
- Minimal 1960 fallbacks

---

## Archive

### Nearest-Neighbor Date Inheritance v1 (2025-12-20) - SUPERSEDED

Simple 1km radius, nearest neighbor copy. Replaced by multi-layer approach.

### Procedural Building Generation Phase 1 (2025-12-20) - IMPLEMENTED

Proof-of-concept procedural building generation from historical map zones.

**Completed:**
- `scripts/generate/subdivide_parcels.py` - Parcel subdivision algorithm
- `scripts/generate/generate_buildings.py` - Building footprint generation
- `data/sources/generated/zones/test_zone.geojson` - Test zone definitions
- `data/sources/generated/zones/test_streets.geojson` - Test street network
- `data/sources/generated/kv1880/buildings_test.geojson` - Generated output (52 buildings)
- Source viewer integration with amber/dashed styling for generated buildings

**Pending (Phase 2):**
- Automated zone segmentation from historical map colors
- Full coverage of Amtskart 1880

### OSM-Centric Building Model (2025-12-20) - IMPLEMENTED

OSM buildings as canonical geometry, dates attached from SEFRAK/FINN/MANUAL. Fallback year 1960.
