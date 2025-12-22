# LSS (Longest Similar Subsequence) Algorithm Explained

## Concept

LSS measures geometric similarity between two line segments by finding the longest sequence of matching points.

## Visual Example

### Scenario: Road widening

```
Historical Road (1880):        OSM Road (2024):
════════════════════          ████████████████████
  samples: o-o-o-o-o            samples: •-•-•-•-•
```

**Sampling:**
```
Historical: [p1, p2, p3, p4, p5]
OSM:        [q1, q2, q3, q4, q5]
```

**Distance Matrix (meters):**
```
      q1   q2   q3   q4   q5
  p1  2    8   15   22   28
  p2  4    2    9   16   23
  p3  9    3    2    8   15
  p4 16    9    3    2    8
  p5 23   16    9    4    2
```

**Matching (threshold = 10m):**
```
      q1   q2   q3   q4   q5
  p1  ✓    ✓    X    X    X
  p2  ✓    ✓    ✓    X    X
  p3  ✓    ✓    ✓    ✓    X
  p4  X    ✓    ✓    ✓    ✓
  p5  X    X    ✓    ✓    ✓
```

**LSS Calculation (Dynamic Programming):**
```
      q1   q2   q3   q4   q5
  p1  1    1    0    0    0
  p2  1    2    1    0    0
  p3  1    2    3    1    0
  p4  0    1    2    4    1
  p5  0    0    1    2    5
```

**Result:**
- LSS length = 5 (diagonal: p1→p2→p3→p4→p5 matches q1→q2→q3→q4→q5)
- Shorter road length = 5 points
- **LSS ratio = 5/5 = 1.0** (perfect match)

## Algorithm Steps

### 1. Sample Points

```python
def sample_line_points(line, interval_m=5):
    points = []
    distance = 0
    while distance <= line.length:
        point = line.interpolate(distance)
        points.append(point)
        distance += interval_m
    return points
```

### 2. Calculate Distance Matrix

```python
distances = []
for p in points1:
    row = []
    for q in points2:
        dist = point_distance_m(p, q)
        row.append(dist)
    distances.append(row)
```

### 3. Find LSS (Dynamic Programming)

```python
dp = [[0] * n2 for _ in range(n1)]
max_lss = 0

for i in range(n1):
    for j in range(n2):
        if distances[i][j] <= threshold:
            if i > 0 and j > 0:
                dp[i][j] = dp[i-1][j-1] + 1
            else:
                dp[i][j] = 1
            max_lss = max(max_lss, dp[i][j])
```

### 4. Calculate Ratio

```python
lss_ratio = max_lss / min(n1, n2)
```

## Example Cases

### Case 1: Same Road (LSS = 0.95)

```
Historical:  o──o──o──o──o
OSM:         •──•──•──•──•

Distance:    1m 2m 1m 2m 1m (all < 10m)
LSS length:  5/5 = 1.0
Hausdorff:   2m
→ Classification: SAME
```

### Case 2: Widened Road (LSS = 0.85)

```
Historical:  o──o──o──o──o
             ║  ║  ║  ║  ║  (road widened)
OSM:         •══•══•══•══•

Distance:    8m 7m 9m 8m 7m (all < 10m)
LSS length:  5/5 = 1.0
Hausdorff:   9m
Width diff:  detected
→ Classification: WIDENED
```

### Case 3: Rerouted Road (LSS = 0.6)

```
Historical:  o──o──o──o──o
                 ╱  ╱
OSM:         •──•──•──•──•

Matches:     3/5 points < 10m
LSS length:  3/5 = 0.6
Hausdorff:   18m
→ Classification: REROUTED
```

### Case 4: Replaced Road (LSS = 0.2)

```
Historical:  o────────o
              ╲      ╱
                ╲  ╱
OSM:             •─────•

Matches:     1/5 points < 10m
LSS length:  1/5 = 0.2
Endpoints:   match within 50m
→ Classification: REPLACED
```

### Case 5: Removed Road (LSS = 0.0)

```
Historical:  o──o──o──o──o
              (demolished)
OSM:         (no match)

LSS length:  0
→ Classification: REMOVED
```

## Why LSS Works Better Than Simple Overlap

### Buffer Overlap Approach (old method)

```python
# Problem: Sensitive to line offset
buffer1 = line1.buffer(10m)
buffer2 = line2.buffer(10m)
overlap = buffer1.intersection(buffer2).area / buffer1.area
```

**Issues:**
1. Same road offset by 5m → overlap drops significantly
2. Doesn't capture geometric similarity, only proximity
3. Sensitive to road width changes

### LSS Approach (new method)

```python
# Better: Captures shape similarity
points1 = sample_line(line1, 5m)
points2 = sample_line(line2, 5m)
lss_ratio = find_lss(points1, points2, threshold=10m)
```

**Advantages:**
1. Robust to parallel offsets (widening)
2. Captures sequential matching (geometry preservation)
3. Works for curved roads (follows shape)
4. Combined with Hausdorff for distance constraint

## Computational Complexity

### Time Complexity

- Sampling: O(L/i) where L = line length, i = interval
- Distance matrix: O(n₁ × n₂) where n = number of samples
- LSS DP: O(n₁ × n₂)
- **Total: O(n²)** per road pair

### Space Complexity

- O(n²) for DP matrix
- Can be optimized to O(n) with rolling array

### Optimization: Early Termination

```python
# Skip if bounding boxes don't overlap
if not bbox1.intersects(bbox2.buffer(hausdorff_max)):
    continue

# Skip if LSS can't possibly meet threshold
if max_possible_lss < lss_threshold:
    continue
```

## Tuning Parameters

### sample_interval (default: 5m)

- **Smaller (2-3m):** More precise, slower, better for curved roads
- **Larger (10-15m):** Faster, less precise, OK for straight roads

### match_threshold (default: 10m)

- **Smaller (5m):** Stricter point matching, fewer false positives
- **Larger (15-20m):** More lenient, better for low-quality maps

### lss_threshold (default: 0.7)

- **Higher (0.8-0.9):** Only very similar roads match
- **Lower (0.5-0.6):** More lenient, catches rerouted roads

### hausdorff_max (default: 20m)

- **Smaller (10-15m):** Tight constraint, only close roads
- **Larger (30-50m):** Looser constraint, catches offset roads

## Comparison with Other Metrics

| Metric | Strengths | Weaknesses |
|--------|-----------|------------|
| **LSS** | Shape similarity, robust to offset | O(n²) complexity |
| **Hausdorff** | Max distance, simple | Doesn't capture shape |
| **Fréchet** | Shape + direction | More complex, slower |
| **Buffer overlap** | Fast | Sensitive to offset |
| **DTW** | Handles variable speed | Allows non-monotonic matching |

## Why LSS + Hausdorff?

**Combining both gives best of both worlds:**

1. **LSS** ensures geometric similarity (shape preserved)
2. **Hausdorff** ensures proximity (lines are close)
3. Together: "Similar shape AND close proximity"

## References

- Longest Common Subsequence (LCS): Classic DP problem
- Hausdorff Distance: Max min-distance metric
- Dynamic Time Warping (DTW): Related sequence matching algorithm
