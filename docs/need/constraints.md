# Constraints

## Technical Constraints

### Data Availability

**Historical Maps**:
- Limited to what Kartverket has digitized and made available
- Not all time periods have equal coverage
- Map quality varies by age and condition
- Some eras have no available maps (gaps in 1700s-1850s)
- Rural areas less documented than urban centers

**Building Registries**:
- SEFRAK focuses on pre-1900 cultural heritage buildings (not comprehensive)
- Matrikkelen API has rate limits and access restrictions
- OSM completeness varies by area and feature type
- Historical records often incomplete or lost

**Temporal Precision**:
- Many buildings lack exact construction dates
- Demolition dates rarely recorded
- Maps only provide "not later than" bounds (building existed when map was made)

### Machine Learning Limitations

**Model Accuracy**:
- Cannot achieve 100% accuracy on historical map extraction
- Performance degrades with poor map quality
- Misclassifications inevitable (roads vs. rivers, buildings vs. shadows)
- Small features often missed (<5m width)

**Training Data**:
- Synthetic data only approximates real historical maps
- Manual annotation is time-consuming (10-20 hours for 50 tiles)
- Limited GPU resources for training (affects model complexity and training time)

**Domain Gap**:
- Each historical map era has unique style
- Aging effects vary by preservation conditions
- Cannot train on all possible variations

### Infrastructure

**Computational Resources**:
- ML training requires GPU access (limited by budget/availability)
- Inference on large map collections is time-intensive
- Storage requirements for high-resolution tiles significant

**Hosting**:
- PMTiles file can become large (multi-GB) with comprehensive data
- Static hosting with range request support required
- CDN costs if traffic is high
- No server-side processing available (fully client-side)

**Browser Compatibility**:
- Must work without WebGL 2 on some older devices
- Mobile performance limited by device capabilities
- Memory constraints on mobile browsers

## Legal and Licensing Constraints

### Data Licensing

**Kartverket Maps**:
- Maps >100 years old: Public domain (freely usable)
- Maps <100 years old: CC BY 4.0 (requires attribution)
- Cannot redistribute high-resolution originals without permission
- Extracted features (vectors) may have different license than source

**OpenStreetMap**:
- ODbL license requires attribution and share-alike
- Cannot mix with incompatible licenses
- Derivative works must be ODbL unless extraction qualifies as "produced work"

**SEFRAK**:
- Public data, freely available via API
- Requires attribution
- Terms of use may restrict certain applications

**Matrikkelen**:
- API access requires registration
- Rate limits apply
- Commercial use may have restrictions
- Privacy concerns for residential addresses

### Attribution Requirements

Must clearly attribute:
- OpenStreetMap contributors
- Kartverket (Norwegian Mapping Authority)
- SEFRAK / Riksantikvaren
- Any other data sources used

### Privacy

**Address Information**:
- Cannot expose private residential information
- Must respect privacy laws (GDPR in Norway)
- Cannot enable stalking or surveillance use cases

**User Data**:
- Should not track users unnecessarily
- Cookie consent required if analytics used
- Cannot sell or share user data

## Resource Constraints

### Development Time

**Solo Developer Reality**:
- Limited time for development, testing, documentation
- Cannot build every desired feature immediately
- Must prioritize ruthlessly
- Maintenance burden grows with feature complexity

**Iterative Approach Required**:
- MVP first, enhancements later
- Cannot perfect everything before launch
- Must accept "good enough" for first version

### Budget

**Zero-Budget Assumptions**:
- No funding for commercial APIs or services
- Free tier hosting only (GitHub Pages, Cloudflare R2 free tier)
- Cannot hire annotators or data processors
- Limited to free/open-source tools
- Cannot purchase proprietary datasets

**GPU Access**:
- Dependent on free Google Colab or local GPU availability
- Training time constrained by free tier limits
- Cannot run large-scale parallel processing

### Expertise

**Skills Limitations**:
- ML expertise limited to practical application (not research-level)
- Frontend development capabilities (not full-stack)
- Limited UX design experience
- No cartography background

**Learning Curve**:
- Must learn historical map interpretation
- Georeferencing techniques need practice
- ML model tuning requires experimentation

## Scope Constraints

### Geographic Scope

**Focus Area**: Trondheim and immediately surrounding region
- Cannot process all of Norway
- Limited to areas with available historical maps
- Must prioritize based on data availability and user interest

### Temporal Scope

**Coverage**: 1700-2025 with significant gaps
- Very limited data pre-1850
- Best coverage 1880-present
- Cannot fill historical gaps where data doesn't exist

### Feature Types

**Initial Focus**: Buildings only, then roads
- Other features (water, forests, railways) are lower priority
- Cannot extract everything from maps simultaneously
- Must prioritize based on user needs and extraction difficulty

## Quality vs. Speed Tradeoffs

### Accuracy vs. Coverage

**Dilemma**: Process many maps quickly with lower accuracy OR fewer maps with high accuracy?

**Decision**: Balanced approach
- Automate what works well (buildings in good maps)
- Manual verification for critical data points
- Transparency about confidence levels

### Completeness vs. Launch

**Dilemma**: Wait until comprehensive coverage OR launch early with limited data?

**Decision**: Launch MVP early
- Demonstrate value with partial coverage
- Gather user feedback
- Iterate based on actual usage

### Performance vs. Features

**Dilemma**: Rich feature set with slower performance OR minimal features running fast?

**Decision**: Performance first
- Core temporal exploration must be smooth
- Advanced features added only if performance maintained
- Client-side simplicity over server-side complexity

## Maintenance Constraints

### Long-term Sustainability

**Data Updates**:
- OSM changes constantly (buildings demolished, new construction)
- Cannot continuously re-process entire dataset
- Need strategy for incremental updates

**Technology Evolution**:
- Libraries and frameworks require updates
- Browser API changes may break functionality
- PMTiles format evolution

**Community Expectations**:
- Users may expect frequent updates
- Bug reports and feature requests need management
- Documentation must be maintained

### Bus Factor

**Solo Project Risk**:
- Knowledge concentrated in one person
- No continuity plan if developer unavailable
- Documentation critical for future maintainers

## Ethical Constraints

### Accuracy and Trust

**Responsibility**:
- Users may make decisions based on this data
- Misrepresentation of history has consequences
- Must not claim certainty where uncertainty exists

**Transparency Obligation**:
- Cannot hide limitations or known issues
- Must acknowledge when data is speculative
- Sources must be clearly cited

### Cultural Sensitivity

**Heritage Respect**:
- Historical buildings may have cultural/religious significance
- Demolition data may be sensitive (forced relocations, war damage)
- Must respect Indigenous history and land claims

**Representation**:
- Map choices reflect values (what to include/exclude)
- Must avoid reinforcing harmful narratives
- Balance preservation advocacy with factual presentation

## Mitigation Strategies

### For Technical Constraints
- Prioritize highest-quality data sources first
- Document accuracy limitations clearly
- Use confidence scores to indicate uncertainty
- Graceful degradation on older devices

### For Resource Constraints
- Leverage free/open-source tools exclusively
- Automate repetitive tasks to save time
- Community engagement for validation and testing
- Phased development to spread work over time

### For Legal Constraints
- Comprehensive attribution system
- License compatibility matrix
- Privacy-by-design approach
- Legal review before launch (if possible)

### For Quality Constraints
- Clear MVP definition
- Iterative improvement process
- User feedback mechanisms
- Validation against ground truth where available
