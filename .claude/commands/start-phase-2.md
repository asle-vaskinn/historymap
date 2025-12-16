# Start Phase 2: Synthetic Data Pipeline

Launch parallel workers to build the synthetic training data pipeline.

## Prerequisites
Phase 1 must be complete. Verify: `ls data/trondheim.pmtiles`

## Overview
Phase 2 generates synthetic "historical map" images paired with ground truth masks.

## Parallel Work Streams

Spawn **4 parallel agents**:

### Agent 1: Historical Style Generator
```
Create MapLibre styles that mimic historical cartography.
- synthetic/styles/military_1880.json
- synthetic/styles/cadastral_1900.json  
- synthetic/styles/topographic_1920.json
- synthetic/generate_styles.py (can generate more via prompts)
Research Norwegian historical maps for authentic colors/patterns.
```

### Agent 2: Rendering Pipeline
```
Create tile rendering system.
- synthetic/render_tiles.py
- Input: OSM vectors for tile area
- Output: PNG image (512x512) in historical style
- Use headless MapLibre or static tile renderer
```

### Agent 3: Aging Effects
```
Create realistic map aging effects.
- synthetic/age_effects.py
- Paper texture overlay
- Yellowing/sepia color shift
- Print blur, ink bleed
- Noise and grain
- Configurable intensity
```

### Agent 4: Mask Generator & Dataset Pipeline
```
Create segmentation masks and dataset generator.
- synthetic/create_masks.py - vector to mask (5 classes)
- synthetic/generate_dataset.py - orchestrate full pipeline
- Classes: background(0), building(1), road(2), water(3), forest(4)
- Output: data/synthetic/images/, data/synthetic/masks/, metadata.json
```

## Coordination
After agents complete, integrate and test:
1. Verify masks align with rendered images
2. Test dataset generation produces valid pairs
3. Sample 10 random outputs for visual QA
