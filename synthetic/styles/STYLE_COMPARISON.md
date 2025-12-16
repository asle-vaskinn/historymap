# Historical Map Style Comparison

Quick reference guide comparing the three historical Norwegian map styles.

## Visual Comparison Table

| Feature | Military 1880 | Cadastral 1900 | Topographic 1920 |
|---------|--------------|----------------|------------------|
| **Era** | 1880s | 1900s | 1920s |
| **Purpose** | Military survey | Property/land registry | Topographic reference |
| **Overall Tone** | Warm earth tones | Cool, technical | Balanced natural |
| **Background** | Cream/beige (#e8e0d0) | Off-white (#faf8f5) | Light cream (#f5f3ed) |

## Feature-by-Feature Comparison

### Buildings

| Style | Fill Color | Outline | Appearance |
|-------|------------|---------|------------|
| **Military 1880** | Dark gray (#3d3530) | None | Solid, dense blocks |
| **Cadastral 1900** | Pink/red (#e6b8b8) | Dark pink (#b08080) | Traditional cadastral |
| **Topographic 1920** | Light tan (#d8d0c0) | Black (#2a2520) | Outlined structures |

**Use Case:**
- Military: Buildings as obstacles/fortifications
- Cadastral: Property identification
- Topographic: Structural reference points

### Roads

| Style | Primary | Secondary | Minor | Character |
|-------|---------|-----------|-------|-----------|
| **Military 1880** | Dark tan (#7a6542) | Med tan (#94805a) | Light tan (#a89578) | Uniform brown tones |
| **Cadastral 1900** | Black (#1a1a1a) | Black (#2a2a2a) | Black (#3a3a3a) | Simple black lines |
| **Topographic 1920** | **Red** (#c84030) | Black (#1a1510) | Black w/ casing | Hierarchical |

**Key Difference:**
- Military: Roads by width only, all brown
- Cadastral: Minimal styling, technical
- Topographic: **Red for main roads** (distinctive!)

### Water

| Style | Fill Color | Treatment | Texture |
|-------|------------|-----------|---------|
| **Military 1880** | Steel blue (#5f7a8a) | Hatching pattern | Stippled |
| **Cadastral 1900** | Light blue (#c5e3f0) | Clean outline | Smooth |
| **Topographic 1920** | Medium blue (#b8d9e8) | Shore lines | Contoured |

**Emphasis:**
- Military: Water as terrain feature
- Cadastral: Property boundaries (shore)
- Topographic: Hydrographic accuracy

### Forests/Vegetation

| Style | Color | Pattern | Opacity |
|-------|-------|---------|---------|
| **Military 1880** | Muted green (#a8c3a0) | Stippled | 0.3-0.4 |
| **Cadastral 1900** | Very light green (#e8f0e8) | Outlined | 0.5 |
| **Topographic 1920** | Natural green (#d5e5c8) | Filled | 0.6 |

**Detail Level:**
- Military: Forest extent important
- Cadastral: Forest as land classification
- Topographic: Vegetation cover for terrain

### Typography

| Style | City Labels | Font | Character |
|-------|------------|------|-----------|
| **Military 1880** | Uppercase, serif | Noto Serif | Formal military |
| **Cadastral 1900** | Uppercase, sans | Noto Sans | Technical precision |
| **Topographic 1920** | Mixed, bold | Noto Sans Bold | Modern clarity |

### Boundaries

| Style | Treatment | Emphasis |
|-------|-----------|----------|
| **Military 1880** | Dashed, muted | Low emphasis |
| **Cadastral 1900** | Clear lines, multiple levels | **High emphasis** |
| **Topographic 1920** | Complex dashes | Medium emphasis |

## Color Palette Summary

### Military 1880 Palette
```
Background:   #e8e0d0 (warm cream)
Water:        #5f7a8a (steel blue)
Forest:       #a8c3a0 (muted green)
Buildings:    #3d3530 (dark gray)
Roads:        #7a6542 to #a89578 (tan spectrum)
```

### Cadastral 1900 Palette
```
Background:   #faf8f5 (cool white)
Water:        #c5e3f0 (light blue)
Forest:       #e8f0e8 (pale green)
Buildings:    #e6b8b8 (cadastral pink)
Roads:        #1a1a1a to #3a3a3a (black spectrum)
```

### Topographic 1920 Palette
```
Background:   #f5f3ed (neutral cream)
Water:        #b8d9e8 (clear blue)
Forest:       #d5e5c8 (natural green)
Buildings:    #d8d0c0 + #2a2520 outline (tan + black)
Roads:        #c84030 (red) + black variants
```

## Best Use Cases for ML Training

### Military 1880
- **Best for:** Building extraction in dense urban areas
- **Strength:** High contrast buildings
- **Weakness:** Roads may blend together
- **Training data:** Use for building segmentation

### Cadastral 1900
- **Best for:** Property boundary detection
- **Strength:** Clear outlines, precise geometry
- **Weakness:** Low visual interest, limited color variation
- **Training data:** Use for precise footprint extraction

### Topographic 1920
- **Best for:** Multi-class segmentation
- **Strength:** Clear feature hierarchy, diverse styling
- **Weakness:** More complex to parse
- **Training data:** Use for full-feature extraction (buildings, roads, water)

## Variation Recommendations

For synthetic training data generation:

### Low Variation (0.05-0.10)
- Use when historical accuracy is critical
- Preserves period-specific appearance
- Good for testing model on "clean" examples

### Medium Variation (0.10-0.15) ⭐ **Recommended**
- Balance between accuracy and diversity
- Helps model generalize
- Mimics printing/scanning variations

### High Variation (0.15-0.25)
- Maximum domain randomization
- Helps model handle degraded inputs
- May sacrifice historical authenticity

## Historical Context

### Military Survey Maps (1880s)
- Created by Norwegian military cartographers
- Purpose: Strategic planning, troop movement
- Characteristics: Functional, less decorative
- Source: Generalstaben (General Staff)

### Cadastral Maps (1900s)
- Property registration and taxation
- Purpose: Legal land boundaries
- Characteristics: Precise, technical, standardized
- Source: Matrikkelverket (Cadastre)

### Topographic Maps (1920s)
- General-purpose reference maps
- Purpose: Navigation, planning
- Characteristics: Detailed terrain, standardized symbols
- Source: Norges Geografiske Oppmåling (Geographic Survey)

## References

- [Kartverket Historical Map Collection](https://www.kartverket.no/)
- [Norwegian Mapping Authority Archives](https://www.kartverket.no/en/about-kartverket/history)
- [Nordic Cartographic Conventions (early 20th century)](https://www.kartverket.no/)

## Version History

- v1.0 (2024-12): Initial style definitions for Phase 2 of Trondheim Historical Map project
