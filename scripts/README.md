# Development Scripts

This directory contains development and testing utilities for the Necroporra project.

## Available Scripts

### test_wikidata.py

A standalone testing script for manually exploring and debugging Wikidata API queries.

**Usage:**
```bash
cd /path/to/necroporra/django
source .venv/bin/activate
python scripts/test_wikidata.py
```

**Purpose:**
- Test Wikidata entity searches
- Verify API responses and data extraction
- Debug celebrity data retrieval
- Explore Wikidata property formats

**Note:** This is a development utility and not part of the main test suite. For automated tests, see `necroporra/necroporra/tests.py`.

## Adding New Scripts

When adding new development utilities:
1. Place them in this `scripts/` directory
2. Add documentation to this README
3. Keep them separate from production code
4. Use descriptive names that indicate their purpose
