"""
Data ingestion modules for different sources.

Each source has its own ingestion script that:
1. Downloads or extracts raw data
2. Saves to data/sources/{source}/raw/
3. Updates manifest.json with ingestion metadata
"""
