# Start Phase 4: Real Data Integration

Launch parallel workers to integrate real Kartverket historical maps.

## Prerequisites
Phase 3 must be complete. Verify: `ls models/checkpoints/`

## Overview
Phase 4 downloads real maps, creates annotations, and fine-tunes the model.

## Parallel Work Streams

Spawn **3 parallel agents**:

### Agent 1: Data Acquisition & Georeferencing
```
Download and prepare Kartverket maps.
- scripts/download_kartverket.py - fetch from kartkatalog.geonorge.no
- scripts/georeference.py - align to modern CRS using GDAL
- scripts/tile_maps.py - cut into 256x256 tiles with geo-coordinates
- Handle TIFF, JPEG2000 formats
- Output: data/kartverket/raw/, georeferenced/, tiles/
```

### Agent 2: Annotation Helper Tool
```
Create annotation assistance tool.
- scripts/annotation_helper.py
- Simple UI (tkinter or web-based)
- Load historical tile
- Show model prediction as starting overlay
- Allow manual correction
- Export corrected mask
- Track annotation progress
```

### Agent 3: Fine-tuning & Batch Processing
```
Create fine-tuning and extraction pipeline.
- scripts/fine_tune.py - load Phase 3 model, train on real annotations
- Lower learning rate, more augmentation
- scripts/batch_extract.py - process all historical tiles
- Merge results into GeoJSON per era
- Add temporal attributes from map metadata
```

## Coordination
This phase requires human work (annotation).
1. Download maps and generate tiles
2. Use annotation helper to label 30-50 tiles (10-20 hours human time)
3. Fine-tune model on annotations
4. Run batch extraction on all maps
