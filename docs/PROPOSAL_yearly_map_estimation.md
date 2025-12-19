# Proposal: Robust Yearly Map Estimation

## Executive Summary

This proposal outlines a comprehensive methodology for estimating what the map of Trondheim looked like at **any given year** between 1850-2025, even when no direct historical map exists for that specific year. The approach combines temporal interpolation, multi-source fusion, probabilistic modeling, and domain-specific heuristics to produce high-confidence map estimates.

---

## Problem Statement

### Current Limitations

1. **Sparse Historical Data**: Historical maps exist only for specific years (e.g., 1880, 1900, 1920, 1950)
2. **Binary Temporal Filtering**: Features simply appear/disappear based on `start_date`/`end_date`
3. **No Uncertainty Quantification**: All features shown with equal confidence regardless of temporal proximity
4. **Abrupt Transitions**: Features pop in/out suddenly at year boundaries
5. **Missing Interpolation**: No estimation of intermediate states between known data points

### Goal

Create a system that can generate a **probabilistically-scored map estimate** for any year `Y` in [1850, 2025], with:
- Confidence scores reflecting data quality and temporal proximity
- Smooth transitions between known states
- Domain-appropriate change modeling (buildings don't appear overnight)
- Multi-source evidence fusion

---

## Proposed Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                  YEARLY MAP ESTIMATION ENGINE                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐    ┌──────────────────┐                   │
│  │  Historical Map  │    │  Modern OSM      │                   │
│  │  Observations    │    │  Ground Truth    │                   │
│  │  (1880,1900,...) │    │  (2020-2025)     │                   │
│  └────────┬─────────┘    └────────┬─────────┘                   │
│           │                       │                              │
│           ▼                       ▼                              │
│  ┌─────────────────────────────────────────────┐                │
│  │         TEMPORAL EVIDENCE COLLECTOR          │                │
│  │  • Extract features per source year          │                │
│  │  • Track feature lineage across time         │                │
│  │  • Build temporal observation matrix         │                │
│  └────────────────────┬────────────────────────┘                │
│                       │                                          │
│                       ▼                                          │
│  ┌─────────────────────────────────────────────┐                │
│  │         FEATURE LIFECYCLE MODELER            │                │
│  │  • Construction probability curves           │                │
│  │  • Demolition/change detection               │                │
│  │  • Feature type-specific priors              │                │
│  └────────────────────┬────────────────────────┘                │
│                       │                                          │
│                       ▼                                          │
│  ┌─────────────────────────────────────────────┐                │
│  │         TEMPORAL INTERPOLATOR                │                │
│  │  • Bayesian state estimation                 │                │
│  │  • Multi-source fusion                       │                │
│  │  • Confidence propagation                    │                │
│  └────────────────────┬────────────────────────┘                │
│                       │                                          │
│                       ▼                                          │
│  ┌─────────────────────────────────────────────┐                │
│  │         MAP STATE GENERATOR                  │                │
│  │  • Generate features for year Y              │                │
│  │  • Attach confidence/uncertainty             │                │
│  │  • Spatial consistency enforcement           │                │
│  └────────────────────┬────────────────────────┘                │
│                       │                                          │
│                       ▼                                          │
│               [Map Estimate for Year Y]                          │
│               with confidence scores                             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. Temporal Evidence Model

Each feature `f` has observations at discrete years. We model this as:

```python
class TemporalEvidence:
    """Evidence for a feature's existence across time."""

    feature_id: str
    geometry: Geometry
    observations: List[Observation]  # (year, present: bool, source, confidence)

@dataclass
class Observation:
    year: int
    present: bool           # True = observed, False = confirmed absent
    source: str             # 'osm', 'kartverket_1880', 'ml_extracted', etc.
    confidence: float       # Source reliability (0.0-1.0)
    geometry_hash: str      # Track geometry changes over time
```

**Key insight**: Absence of observation ≠ absence of feature. We distinguish:
- **Positive observation**: Feature confirmed present
- **Negative observation**: Feature confirmed absent
- **No observation**: Unknown state (requires interpolation)

### 2. Feature Lifecycle Priors

Different feature types have different temporal dynamics:

```python
FEATURE_LIFECYCLE_PRIORS = {
    'building': {
        'min_construction_time': 1,      # years
        'typical_lifespan': 80,          # years
        'demolition_rate': 0.008,        # per year (after typical lifespan)
        'appearance_curve': 'step',      # buildings appear suddenly
        'persistence_prior': 0.95,       # if seen in year Y, P(exists in Y+1)
    },
    'road': {
        'min_construction_time': 0.5,
        'typical_lifespan': 150,
        'modification_rate': 0.02,       # roads change alignment
        'appearance_curve': 'step',
        'persistence_prior': 0.98,
    },
    'water': {
        'min_construction_time': 0,      # natural features
        'typical_lifespan': 1000,        # effectively permanent
        'change_rate': 0.001,            # very slow (except for harbors)
        'appearance_curve': 'constant',
        'persistence_prior': 0.999,
    },
    'forest': {
        'min_construction_time': 20,     # trees take time to grow
        'typical_lifespan': 100,
        'change_rate': 0.01,
        'appearance_curve': 'gradual',   # forests grow/shrink gradually
        'persistence_prior': 0.92,
    },
    'railway': {
        'min_construction_time': 2,
        'typical_lifespan': 120,
        'modification_rate': 0.005,
        'appearance_curve': 'step',
        'persistence_prior': 0.97,
    }
}
```

### 3. Temporal State Estimation

For each feature at target year `Y`, compute existence probability:

```python
def estimate_feature_state(feature: TemporalEvidence, target_year: int) -> FeatureState:
    """
    Estimate feature state at target_year using all available observations.

    Returns:
        FeatureState with existence_probability, geometry_confidence, source_attribution
    """

    # Get bracketing observations
    before = get_latest_observation_before(feature.observations, target_year)
    after = get_earliest_observation_after(feature.observations, target_year)

    lifecycle = FEATURE_LIFECYCLE_PRIORS[feature.feature_class]

    # Case 1: Target year has direct observation
    if has_observation_at(feature, target_year):
        obs = get_observation_at(feature, target_year)
        return FeatureState(
            exists=obs.present,
            probability=obs.confidence,
            source='direct_observation',
            geometry=feature.geometry
        )

    # Case 2: Interpolate between observations
    if before and after:
        return interpolate_state(before, after, target_year, lifecycle)

    # Case 3: Extrapolate from single observation
    if before:
        return extrapolate_forward(before, target_year, lifecycle)
    if after:
        return extrapolate_backward(after, target_year, lifecycle)

    # Case 4: No observations - use spatial context
    return estimate_from_context(feature, target_year)
```

### 4. Interpolation Strategies

#### 4.1 Between Positive Observations (Present → Present)

If feature observed at Y1 and Y2, assume continuous existence:

```python
def interpolate_present_present(obs1, obs2, target_year, lifecycle):
    """Feature seen at both endpoints - interpolate confidence."""

    # Distance-weighted confidence
    dist1 = abs(target_year - obs1.year)
    dist2 = abs(target_year - obs2.year)
    total_dist = obs2.year - obs1.year

    # Confidence decays with distance from observations
    decay_rate = 0.02  # 2% per year
    confidence = min(obs1.confidence, obs2.confidence) * (1 - decay_rate * min(dist1, dist2))

    # Geometry: use closer observation's geometry
    geometry = obs1.geometry if dist1 <= dist2 else obs2.geometry

    return FeatureState(
        exists=True,
        probability=max(0.7, confidence),  # High floor - we have bracketing evidence
        source='interpolated',
        geometry=geometry,
        uncertainty_radius=min(dist1, dist2) * 0.5  # meters uncertainty
    )
```

#### 4.2 Between Positive and Negative (Present → Absent)

Feature disappeared sometime in the interval:

```python
def interpolate_present_absent(obs_present, obs_absent, target_year, lifecycle):
    """Feature present at obs1, absent at obs2 - estimate transition."""

    interval = obs_absent.year - obs_present.year
    position = (target_year - obs_present.year) / interval

    # Demolition typically happens later in interval (structures persist)
    # Use beta distribution skewed toward later demolition
    alpha, beta = 3, 2  # Skewed toward end of interval
    from scipy.stats import beta as beta_dist

    # P(still exists at target_year)
    p_exists = 1 - beta_dist.cdf(position, alpha, beta)

    # Adjust for feature type
    p_exists *= lifecycle['persistence_prior'] ** (target_year - obs_present.year)

    return FeatureState(
        exists=p_exists > 0.5,
        probability=p_exists,
        source='transition_interpolated',
        geometry=obs_present.geometry,
        transition_window=(obs_present.year, obs_absent.year)
    )
```

#### 4.3 Between Negative and Positive (Absent → Present)

Feature appeared sometime in the interval:

```python
def interpolate_absent_present(obs_absent, obs_present, target_year, lifecycle):
    """Feature absent at obs1, present at obs2 - estimate construction."""

    interval = obs_present.year - obs_absent.year
    position = (target_year - obs_absent.year) / interval

    # Account for construction time
    min_construction = lifecycle['min_construction_time']
    effective_interval = interval - min_construction

    if target_year > obs_present.year - min_construction:
        # Feature was being constructed - partial existence
        construction_progress = (target_year - (obs_present.year - min_construction)) / min_construction
        return FeatureState(
            exists=True,
            probability=construction_progress * obs_present.confidence,
            source='under_construction',
            geometry=obs_present.geometry,
            construction_state='partial'
        )
    else:
        # Before construction started
        return FeatureState(
            exists=False,
            probability=0.0,
            source='pre_construction',
            geometry=None
        )
```

### 5. Confidence Propagation

Confidence scores account for:

```python
def compute_confidence(
    base_confidence: float,
    temporal_distance: int,      # years from nearest observation
    source_reliability: float,   # reliability of data source
    feature_class: str,
    observation_count: int       # number of supporting observations
) -> float:
    """
    Compute final confidence score for feature existence.

    Factors:
    1. Temporal decay: confidence decreases with distance from observations
    2. Source reliability: ML-extracted < manual annotation < OSM
    3. Feature stability: water more stable than buildings
    4. Corroboration: multiple sources increase confidence
    """

    # Temporal decay
    TEMPORAL_DECAY = {
        'building': 0.015,   # 1.5% per year
        'road': 0.010,       # 1% per year
        'water': 0.002,      # 0.2% per year
        'forest': 0.020,     # 2% per year
        'railway': 0.008,    # 0.8% per year
    }
    decay = TEMPORAL_DECAY.get(feature_class, 0.015)
    temporal_factor = math.exp(-decay * temporal_distance)

    # Source reliability multiplier
    SOURCE_RELIABILITY = {
        'osm': 0.95,
        'manual_annotation': 0.90,
        'ml_extracted_finetuned': 0.80,
        'ml_extracted_synthetic': 0.65,
        'interpolated': 0.50,
    }
    source_factor = SOURCE_RELIABILITY.get(source_reliability, 0.7)

    # Corroboration bonus
    corroboration_bonus = min(0.2, 0.05 * (observation_count - 1))

    confidence = base_confidence * temporal_factor * source_factor + corroboration_bonus
    return min(1.0, max(0.0, confidence))
```

---

## Data Model Extensions

### Enhanced Feature Schema

```python
@dataclass
class TemporalFeature:
    """Extended feature schema with temporal estimation data."""

    # Core identity
    id: str
    geometry: Geometry
    feature_class: str  # building, road, water, forest, railway

    # Temporal bounds (estimated or known)
    start_year: int
    start_confidence: float      # How sure we are about start year
    start_source: str            # What determined start year

    end_year: Optional[int]      # None = still exists
    end_confidence: float
    end_source: str

    # Estimation metadata
    estimation_method: str       # 'direct', 'interpolated', 'extrapolated', 'inferred'
    temporal_observations: List[Observation]

    # Confidence at estimation time
    existence_probability: float
    geometry_confidence: float
    overall_confidence: float

    # Provenance
    sources: List[str]
    last_updated: datetime
```

### PMTiles Schema Extension

Add properties to vector tiles:

```json
{
  "type": "Feature",
  "properties": {
    "id": "bld_12345",
    "feature_class": "building",
    "start_year": 1892,
    "start_confidence": 0.75,
    "end_year": null,
    "end_confidence": null,
    "existence_probability": 0.85,
    "geometry_confidence": 0.70,
    "estimation_method": "interpolated",
    "source_years": [1880, 1900, 2020],
    "primary_source": "kartverket_1900"
  },
  "geometry": { ... }
}
```

---

## Implementation Phases

### Phase A: Temporal Evidence Collection (Week 1-2)

1. **Extend ML extraction pipeline** to track source year per feature
2. **Build observation database** linking features across time
3. **Implement feature matching** across different source years
   - Spatial matching (IoU > 0.5)
   - Attribute matching (same feature class)
   - Topology matching (connected road segments)

```python
class FeatureMatcher:
    """Match features across different source years."""

    def match_features(
        self,
        features_year1: List[Feature],
        features_year2: List[Feature],
        year1: int,
        year2: int
    ) -> List[FeatureMatch]:
        """
        Find corresponding features between two years.

        Returns list of (feature1, feature2, similarity_score) tuples.
        Unmatched features indicate appearance/disappearance.
        """
        matches = []

        # Build spatial index for year2 features
        idx = build_rtree_index(features_year2)

        for f1 in features_year1:
            candidates = idx.intersection(f1.geometry.bounds)
            best_match = None
            best_score = 0.0

            for f2_id in candidates:
                f2 = features_year2[f2_id]

                # Same feature class required
                if f1.feature_class != f2.feature_class:
                    continue

                # Compute similarity
                score = self.compute_similarity(f1, f2)
                if score > best_score and score > 0.5:
                    best_score = score
                    best_match = f2

            if best_match:
                matches.append(FeatureMatch(f1, best_match, best_score))
            else:
                matches.append(FeatureMatch(f1, None, 0.0))  # Disappeared

        return matches

    def compute_similarity(self, f1: Feature, f2: Feature) -> float:
        """Compute geometric and attribute similarity."""

        # IoU of geometries
        iou = f1.geometry.intersection(f2.geometry).area / \
              f1.geometry.union(f2.geometry).area

        # Hausdorff distance (normalized)
        hausdorff = f1.geometry.hausdorff_distance(f2.geometry)
        hausdorff_score = 1.0 / (1.0 + hausdorff / 50.0)  # 50m normalization

        # Combined score
        return 0.7 * iou + 0.3 * hausdorff_score
```

### Phase B: Lifecycle Modeling (Week 2-3)

1. **Analyze historical data** to calibrate lifecycle priors
2. **Validate transition models** against known demolition/construction dates
3. **Implement confidence propagation** functions

```python
class LifecycleCalibrator:
    """Calibrate lifecycle priors from historical data."""

    def calibrate(self, matched_features: List[FeatureMatch]) -> LifecycleParams:
        """
        Analyze feature matches to estimate:
        - Typical construction rates by era
        - Demolition rates by building age
        - Feature persistence probabilities
        """

        # Count appearances, disappearances, modifications
        appearances = []  # (year, feature_class)
        disappearances = []
        modifications = []

        for match in matched_features:
            if match.feature2 is None:  # Disappeared
                disappearances.append((match.year2, match.feature1.feature_class))
            elif match.feature1 is None:  # Appeared
                appearances.append((match.year1, match.feature2.feature_class))
            elif match.similarity < 0.9:  # Modified
                modifications.append((match.year1, match.year2, match.feature1.feature_class))

        # Compute rates
        params = {}
        for feature_class in ['building', 'road', 'water', 'forest', 'railway']:
            class_appearances = [a for a in appearances if a[1] == feature_class]
            class_disappearances = [d for d in disappearances if d[1] == feature_class]

            params[feature_class] = {
                'appearance_rate': len(class_appearances) / total_observations,
                'disappearance_rate': len(class_disappearances) / total_observations,
                'persistence_prior': 1 - (len(class_disappearances) / len(class_appearances))
            }

        return LifecycleParams(params)
```

### Phase C: State Estimation Engine (Week 3-4)

1. **Implement interpolation algorithms**
2. **Build estimation API**
3. **Create visualization for uncertainty**

```python
class MapEstimator:
    """Main estimation engine."""

    def __init__(
        self,
        observations_db: ObservationsDatabase,
        lifecycle_params: LifecycleParams
    ):
        self.observations = observations_db
        self.lifecycle = lifecycle_params

    def estimate_map(self, target_year: int) -> EstimatedMap:
        """
        Generate complete map estimate for target_year.

        Returns:
            EstimatedMap with all features and their confidence scores
        """

        features = []

        # Get all known features
        all_feature_ids = self.observations.get_all_feature_ids()

        for feature_id in all_feature_ids:
            evidence = self.observations.get_evidence(feature_id)
            state = self.estimate_feature_state(evidence, target_year)

            if state.probability > 0.3:  # Threshold for inclusion
                features.append(EstimatedFeature(
                    id=feature_id,
                    geometry=state.geometry,
                    feature_class=evidence.feature_class,
                    probability=state.probability,
                    confidence=state.confidence,
                    source=state.source
                ))

        return EstimatedMap(
            year=target_year,
            features=features,
            metadata={
                'observation_years': self.observations.get_observation_years(),
                'closest_observation': self._find_closest_year(target_year),
                'estimation_quality': self._compute_overall_quality(features)
            }
        )

    def estimate_feature_state(
        self,
        evidence: TemporalEvidence,
        target_year: int
    ) -> FeatureState:
        """Estimate single feature state at target year."""

        # [Implementation from Section 3 above]
        ...
```

### Phase D: Frontend Integration (Week 4-5)

1. **Extend PMTiles with estimation data**
2. **Update frontend to show confidence visually**
3. **Add uncertainty visualization options**

```javascript
// Enhanced temporal filtering with confidence visualization
function updateMapWithEstimation(year) {
    const layers = ['buildings', 'roads', 'water', 'landuse'];

    layers.forEach(layer => {
        // Filter by year
        map.setFilter(layer, createTemporalFilter(year));

        // Style by confidence
        map.setPaintProperty(layer, `${layer}-opacity`, [
            'interpolate', ['linear'],
            ['get', 'existence_probability'],
            0.3, 0.2,   // Low confidence = very transparent
            0.5, 0.5,   // Medium confidence = semi-transparent
            0.8, 0.8,   // High confidence = mostly opaque
            1.0, 1.0    // Full confidence = opaque
        ]);

        // Optional: dashed outlines for estimated features
        if (layer === 'buildings') {
            map.setPaintProperty('building-outline', 'line-dasharray', [
                'case',
                ['==', ['get', 'estimation_method'], 'interpolated'],
                [2, 2],  // Dashed for interpolated
                [1]      // Solid for direct observation
            ]);
        }
    });
}

// Show estimation quality indicator
function showEstimationQuality(year) {
    const closestYear = getClosestObservationYear(year);
    const distance = Math.abs(year - closestYear);

    let quality;
    if (distance === 0) quality = 'exact';
    else if (distance <= 5) quality = 'high';
    else if (distance <= 15) quality = 'medium';
    else quality = 'estimated';

    document.getElementById('quality-indicator').className = `quality-${quality}`;
    document.getElementById('quality-text').textContent =
        `Data quality: ${quality} (nearest observation: ${closestYear})`;
}
```

---

## Validation Strategy

### Ground Truth Comparison

1. **Known demolition dates**: Compare estimated disappearance years with documented demolitions
2. **Construction records**: Validate appearance years against building permits (where available)
3. **Cross-validation**: Hold out one source year, estimate it, compare with actual

```python
def validate_estimation(
    estimator: MapEstimator,
    test_year: int,
    ground_truth: GroundTruth
) -> ValidationMetrics:
    """
    Validate estimation accuracy against known ground truth.
    """

    estimated = estimator.estimate_map(test_year)

    # Compute metrics
    true_positives = 0
    false_positives = 0
    false_negatives = 0
    confidence_calibration = []

    for gt_feature in ground_truth.features:
        est_feature = find_matching_feature(estimated, gt_feature)

        if est_feature:
            if gt_feature.exists:
                true_positives += 1
                confidence_calibration.append((est_feature.probability, 1))
            else:
                false_positives += 1
                confidence_calibration.append((est_feature.probability, 0))
        else:
            if gt_feature.exists:
                false_negatives += 1

    return ValidationMetrics(
        precision=true_positives / (true_positives + false_positives),
        recall=true_positives / (true_positives + false_negatives),
        calibration_error=compute_calibration_error(confidence_calibration),
        temporal_accuracy=compute_temporal_accuracy(estimated, ground_truth)
    )
```

### Calibration Verification

Ensure confidence scores are well-calibrated:
- If we say "80% confident", features should exist ~80% of the time
- Plot reliability diagrams to verify calibration

---

## Fallback Strategies

### When Data is Sparse

For years far from any observation:

1. **Use spatial context**: If surrounding buildings exist, enclosed building likely exists
2. **Use temporal trends**: Extrapolate from city growth patterns
3. **Apply conservative estimates**: Default to "unknown" rather than guessing

```python
def estimate_from_context(
    feature: Feature,
    target_year: int,
    spatial_context: SpatialContext
) -> FeatureState:
    """
    Estimate feature state when no temporal observations available.
    Uses spatial neighbors and historical trends.
    """

    # Check if feature is in an area that existed at target_year
    containing_area = spatial_context.get_containing_area(feature.geometry)
    if containing_area and containing_area.established_year > target_year:
        # Area didn't exist yet
        return FeatureState(exists=False, probability=0.1, source='context_area')

    # Check neighbors
    neighbors = spatial_context.get_neighbors(feature.geometry, radius=100)
    neighbor_states = [n.get_state(target_year) for n in neighbors]
    neighbor_confidence = sum(n.probability for n in neighbor_states) / len(neighbor_states)

    # If neighbors mostly exist, feature likely exists
    return FeatureState(
        exists=neighbor_confidence > 0.5,
        probability=neighbor_confidence * 0.7,  # Discount for indirect inference
        source='context_neighbors'
    )
```

---

## API Specification

### Core Estimation API

```python
class YearlyMapEstimationAPI:
    """Public API for map estimation."""

    def estimate_full_map(
        self,
        year: int,
        bounds: Optional[BoundingBox] = None,
        feature_classes: Optional[List[str]] = None,
        min_confidence: float = 0.3
    ) -> EstimatedMap:
        """
        Get complete map estimate for a year.

        Args:
            year: Target year (1850-2025)
            bounds: Optional geographic bounds to filter
            feature_classes: Optional list of classes to include
            min_confidence: Minimum confidence threshold

        Returns:
            EstimatedMap with all matching features
        """
        pass

    def estimate_feature(
        self,
        feature_id: str,
        year: int
    ) -> FeatureState:
        """Get state estimate for a single feature at a year."""
        pass

    def get_feature_timeline(
        self,
        feature_id: str,
        start_year: int = 1850,
        end_year: int = 2025,
        resolution: int = 5
    ) -> Timeline:
        """
        Get existence probability over time for a feature.

        Returns timeline of (year, probability, geometry) tuples.
        """
        pass

    def get_observation_years(self) -> List[int]:
        """Get list of years with direct observations."""
        pass

    def get_estimation_quality(self, year: int) -> QualityMetrics:
        """Get quality metrics for estimation at a given year."""
        pass
```

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Over-confident interpolation | Medium | High | Conservative confidence decay; validation testing |
| Feature matching errors | Medium | Medium | Manual review of critical matches; confidence thresholds |
| Computational complexity | Low | Medium | Spatial indexing; caching; lazy evaluation |
| User confusion about uncertainty | Medium | Medium | Clear UI indicators; documentation; tooltips |
| Sparse data in early years | High | Medium | Explicit "low confidence" warnings; graceful degradation |

---

## Success Metrics

1. **Accuracy**: >80% precision/recall on held-out test years
2. **Calibration**: <10% expected calibration error
3. **Coverage**: Meaningful estimates for all years 1850-2025
4. **Performance**: <2s to generate full map estimate
5. **User Satisfaction**: Clear uncertainty communication in UI

---

## Recommended Next Steps

1. **Review & Feedback**: Discuss this proposal, identify gaps
2. **Prototype Phase A**: Build feature matching pipeline
3. **Calibration Study**: Analyze existing data to calibrate lifecycle priors
4. **Incremental Integration**: Add estimation to existing pipeline
5. **Frontend Iteration**: Design uncertainty visualization with user feedback

---

## Appendix: Alternative Approaches Considered

### A. Hidden Markov Model (HMM)

Model feature existence as hidden states, observations as emissions.
- **Pro**: Principled probabilistic framework
- **Con**: Requires more training data; complex implementation

### B. Gaussian Process Regression

Treat existence probability as continuous function over time.
- **Pro**: Elegant uncertainty quantification
- **Con**: Computationally expensive for many features

### C. Rule-Based System

Handcrafted rules for each feature type.
- **Pro**: Interpretable; no training data needed
- **Con**: Inflexible; hard to maintain; doesn't generalize

### D. Neural Temporal Model

Train neural network to predict feature states.
- **Pro**: Can learn complex patterns
- **Con**: Requires substantial training data; black box

**Recommendation**: Start with the proposed hybrid approach (interpolation + priors), with option to add ML components later if data supports it.

---

*Proposal Version: 1.0*
*Date: December 2025*
*Status: Draft for Review*
