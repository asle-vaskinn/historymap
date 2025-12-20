# Current Work: Nearest-Neighbor Date Inheritance

## Status: APPROVED
## Approved: 2025-12-20

## Summary

Add a fallback mechanism where buildings without construction dates inherit the date from the nearest building that has a high-evidence construction year (within 1km). This provides better temporal estimates than the blanket "1960 fallback" by using spatial proximity as a proxy for construction era.

## Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Max distance | 1000m (1km) | Buildings within 1km likely same era |
| Donor evidence | High only (`ev: 'h'`) | Only trust reliable dates |
| Result evidence | Low (`ev: 'l'`) | Inherited = uncertain |
| Frontend | Normal slider behavior | Inherited dates work like regular dates |

## Schema Additions

```
sd_inherited : bool      # true = date inherited from neighbor
sd_from      : string    # _src_id of donor building
sd_dist      : float     # distance in meters to donor
```

## Tasks

### 1. Implement date inheritance in merge pipeline
- [ ] Add `inherit_dates_from_neighbors()` function to `merge_sources.py`
- [ ] Collect donor pool: buildings with `ev: 'h'` and `sd`
- [ ] Build spatial index of donors using shapely STRtree
- [ ] For each undated building, find nearest donor within 1km
- [ ] Copy `sd`, set `ev: 'l'`, add metadata fields

### 2. Integrate into merge workflow
- [ ] Call after OSM-centric merge, before output
- [ ] Log statistics (donors, recipients, avg distance)
- [ ] Handle edge cases (no donors nearby)

### 3. Regenerate output
- [ ] Run merge pipeline
- [ ] Regenerate PMTiles
- [ ] Verify in frontend

### 4. Update documentation
- [ ] Update DATA_SCHEMA.md with new fields

## Algorithm

```python
def inherit_dates_from_neighbors(features, max_distance_m=1000):
    # 1. Separate donors (high evidence + has sd) from recipients (no sd)
    donors = [f for f in features if f['properties'].get('ev') == 'h'
              and f['properties'].get('sd')]
    recipients = [f for f in features if not f['properties'].get('sd')]

    # 2. Build spatial index of donor centroids
    donor_index = build_spatial_index(donors)

    # 3. For each recipient, find nearest donor
    for recipient in recipients:
        centroid = get_centroid(recipient)
        nearest_donor, distance = find_nearest(centroid, donor_index)

        if distance <= max_distance_m:
            recipient['properties']['sd'] = nearest_donor['properties']['sd']
            recipient['properties']['ev'] = 'l'
            recipient['properties']['sd_inherited'] = True
            recipient['properties']['sd_from'] = nearest_donor['properties']['_src_id']
            recipient['properties']['sd_dist'] = round(distance, 1)

    return features
```

## Expected Impact

- Donor pool: ~1,400 high-evidence buildings (SEFRAK, FINN with `ev: 'h'`)
- Recipients: ~65,000 undated OSM buildings
- Result: Many buildings get era-appropriate dates instead of 1960 fallback

## Success Criteria

- Buildings near historical city center get 1800s dates
- Buildings in newer suburbs still get 1960 fallback (no donors nearby)
- Year slider shows gradual city growth pattern

---

## Archive

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
