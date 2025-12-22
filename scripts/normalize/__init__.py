"""
Data normalization modules.

Each source has its own normalization script that:
1. Reads raw data from data/sources/{source}/raw/
2. Converts to common schema
3. Validates output
4. Saves to data/sources/{source}/normalized/
5. Updates manifest.json with normalization metadata
"""
