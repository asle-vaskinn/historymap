# Feature Specifications

This directory contains detailed specifications for each major feature in the Trondheim Historical Map project. Each feature is documented in its own subdirectory with implementation details, data flows, and status tracking.

## Specification Structure

Each feature spec (`feat_*`) includes:
- Overview and purpose
- Technical implementation details
- Data schemas and workflows
- Current status and dependencies

For product-level specifications (UX, visual design, user requirements), see [PRODUCT_SPEC.md](./PRODUCT_SPEC.md).

## Feature Catalog

| Feature | Description | Status | Dependencies |
|---------|-------------|--------|--------------|
| [feat_temporal_pipeline](./feat_temporal_pipeline/) | Combines multiple sources to build temporal dataset (core framework) | In Progress | - |
| [feat_ml_extraction](./feat_ml_extraction/) | ML segmentation from historical maps using U-Net | Implemented | feat_temporal_pipeline |
| [feat_sefrak_import](./feat_sefrak_import/) | Import SEFRAK cultural heritage data with construction dates | Implemented | feat_temporal_pipeline |
| [feat_osm_baseline](./feat_osm_baseline/) | Import OSM as modern baseline for all features | Implemented | - |
| [feat_timeline_ui](./feat_timeline_ui/) | Frontend time slider interface with year navigation | Implemented | feat_temporal_pipeline |
| [feat_source_filter](./feat_source_filter/) | Filter map by data source (SEFRAK, ML, OSM, etc.) | Implemented | feat_timeline_ui |

## Status Legend

- **Implemented**: Feature is complete and deployed
- **In Progress**: Actively being developed
- **Planned**: Designed but not yet started
- **Blocked**: Waiting on dependencies or decisions

## Related Documentation

- [PRODUCT_SPEC.md](./PRODUCT_SPEC.md) - UX and product requirements
- [../tech/DATA_SCHEMA.md](../tech/DATA_SCHEMA.md) - Data structure documentation
- [../tech/DATA_PIPELINE_ARCHITECTURE.md](../tech/DATA_PIPELINE_ARCHITECTURE.md) - Data processing pipeline
- [../../CLAUDE.md](../../CLAUDE.md) - Project architecture overview
