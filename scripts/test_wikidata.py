#!/usr/bin/env python3
"""
Standalone script to test Wikidata API queries for celebrity information.
Usage: python test_wikidata.py "Celebrity Name"
"""

import sys
import requests
from datetime import datetime
import json


def search_wikidata_entity(name):
    """Search for a Wikidata entity by name."""
    print(f"\n🔍 Searching Wikidata for: {name}")
    
    search_url = "https://www.wikidata.org/w/api.php"
    search_params = {
        'action': 'wbsearchentities',
        'search': name,
        'language': 'en',
        'format': 'json',
        'limit': 5  # Get top 5 results
    }
    
    headers = {
        'User-Agent': 'Necroporra/1.0 (Celebrity Death Pool App; Educational Project)'
    }
    
    try:
        response = requests.get(search_url, params=search_params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if not data.get('search'):
            print("❌ No results found")
            return None
        
        print(f"\n✅ Found {len(data['search'])} result(s):\n")
        for i, result in enumerate(data['search'], 1):
            entity_id = result.get('id', 'N/A')
            label = result.get('label', 'N/A')
            description = result.get('description', 'No description')
            print(f"{i}. {label} ({entity_id})")
            print(f"   Description: {description}\n")
        
        # Return the first (most relevant) result
        return data['search'][0]['id']
        
    except requests.RequestException as e:
        print(f"❌ Error searching Wikidata: {e}")
        return None


def get_entity_data(entity_id):
    """Retrieve full entity data from Wikidata."""
    print(f"\n📡 Fetching data for entity: {entity_id}")
    
    entity_url = f"https://www.wikidata.org/wiki/Special:EntityData/{entity_id}.json"
    
    headers = {
        'User-Agent': 'Necroporra/1.0 (Celebrity Death Pool App; Educational Project)'
    }
    
    try:
        response = requests.get(entity_url, headers=headers, timeout=10)
        response.raise_for_status()
        entity_data = response.json()
        
        if entity_id not in entity_data.get('entities', {}):
            print("❌ Entity data not found")
            return None
        
        return entity_data['entities'][entity_id]
        
    except requests.RequestException as e:
        print(f"❌ Error fetching entity data: {e}")
        return None


def extract_celebrity_info(entity):
    """Extract relevant information from entity data."""
    info = {
        'name': None,
        'description': None,
        'birth_date': None,
        'death_date': None,
        'occupation': [],
        'citizenship': [],
        'image': None
    }
    
    # Get label (name)
    if 'labels' in entity and 'en' in entity['labels']:
        info['name'] = entity['labels']['en']['value']
    
    # Get description
    if 'descriptions' in entity and 'en' in entity['descriptions']:
        info['description'] = entity['descriptions']['en']['value']
    
    # Extract claims
    claims = entity.get('claims', {})
    
    # Birth date (P569)
    if 'P569' in claims:
        birth_claim = claims['P569'][0]
        if 'mainsnak' in birth_claim:
            datavalue = birth_claim['mainsnak'].get('datavalue', {})
            if 'value' in datavalue and 'time' in datavalue['value']:
                date_str = datavalue['value']['time']
                info['birth_date'] = parse_wikidata_date(date_str)
    
    # Death date (P570)
    if 'P570' in claims:
        death_claim = claims['P570'][0]
        if 'mainsnak' in death_claim:
            datavalue = death_claim['mainsnak'].get('datavalue', {})
            if 'value' in datavalue and 'time' in datavalue['value']:
                date_str = datavalue['value']['time']
                info['death_date'] = parse_wikidata_date(date_str)
    
    # Occupation (P106)
    if 'P106' in claims:
        for claim in claims['P106'][:3]:  # Get first 3 occupations
            if 'mainsnak' in claim:
                datavalue = claim['mainsnak'].get('datavalue', {})
                if 'value' in datavalue and 'id' in datavalue['value']:
                    # You could fetch the occupation label here, but skipping for simplicity
                    info['occupation'].append(datavalue['value']['id'])
    
    # Image (P18)
    if 'P18' in claims:
        image_claim = claims['P18'][0]
        if 'mainsnak' in image_claim:
            datavalue = image_claim['mainsnak'].get('datavalue', {})
            if 'value' in datavalue:
                info['image'] = datavalue['value']
    
    return info


def parse_wikidata_date(date_str):
    """Parse Wikidata date string to Python date object."""
    try:
        # Wikidata format: +YYYY-MM-DDT00:00:00Z or -YYYY-MM-DDT00:00:00Z
        # Remove the leading + or - and everything after T
        date_part = date_str.lstrip('+-').split('T')[0]
        date_obj = datetime.fromisoformat(date_part)
        return date_obj.date()
    except (ValueError, IndexError) as e:
        print(f"⚠️  Error parsing date '{date_str}': {e}")
        return date_str  # Return raw string if parsing fails


def display_info(info):
    """Display extracted information in a readable format."""
    print("\n" + "="*60)
    print("📋 CELEBRITY INFORMATION")
    print("="*60)
    
    print(f"\n👤 Name: {info['name']}")
    print(f"📝 Description: {info['description']}")
    print(f"\n🎂 Birth Date: {info['birth_date'] or 'Not found'}")
    
    if info['death_date']:
        print(f"⚰️  Death Date: {info['death_date']} ✅ DECEASED")
    else:
        print(f"💚 Death Date: Not recorded (likely still alive)")
    
    if info['occupation']:
        print(f"\n💼 Occupations: {', '.join(info['occupation'])}")
    
    if info['image']:
        print(f"\n🖼️  Image: {info['image']}")
    
    print("\n" + "="*60)


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_wikidata.py \"Celebrity Name\"")
        print("\nExamples:")
        print("  python test_wikidata.py \"Jimmy Carter\"")
        print("  python test_wikidata.py \"Betty White\"")
        print("  python test_wikidata.py \"Queen Elizabeth II\"")
        sys.exit(1)
    
    celebrity_name = " ".join(sys.argv[1:])
    
    # Step 1: Search for the entity
    entity_id = search_wikidata_entity(celebrity_name)
    if not entity_id:
        sys.exit(1)
    
    # Step 2: Get full entity data
    entity_data = get_entity_data(entity_id)
    if not entity_data:
        sys.exit(1)
    
    # Step 3: Extract relevant information
    info = extract_celebrity_info(entity_data)
    
    # Step 4: Display the information
    display_info(info)
    
    # Step 5: Show raw JSON for debugging (optional)
    print("\n💾 Want to see the raw JSON? (y/n): ", end="")
    try:
        if input().lower() == 'y':
            print("\n" + json.dumps(entity_data, indent=2))
    except (EOFError, KeyboardInterrupt):
        pass
    
    print("\n✅ Test complete!")


if __name__ == "__main__":
    main()
