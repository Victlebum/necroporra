"""
Utility functions for interacting with Wikidata API.
"""
import requests
from datetime import datetime
from typing import Optional, List, Dict, Any


def search_wikidata_people(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Search for people on Wikidata by name.
    
    Args:
        query: Search term (person's name)
        limit: Maximum number of results to return (default: 20)
    
    Returns:
        List of dictionaries containing celebrity information:
        - id: Temporary ID in format "wikidata:{Q_ID}"
        - name: Person's name
        - bio: Description from Wikidata
        - birth_date: Birth date (ISO format string or None)
        - death_date: Death date (ISO format string or None)
        - wikidata_id: Wikidata entity ID (e.g., "Q392")
        - image_url: URL to image (or empty string)
    """
    if not query or len(query) < 2:
        return []
    
    try:
        # Use Wikidata's Cirrus full-text search with haswbstatement:P31=Q5.
        # Unlike wbsearchentities (prefix-only matching), this finds people whose
        # label or alias CONTAINS the query term — e.g. "Trump" → "Donald Trump".
        search_url = "https://www.wikidata.org/w/api.php"
        search_params = {
            'action': 'query',
            'list': 'search',
            'srsearch': f'{query} haswbstatement:P31=Q5',
            'srnamespace': '0',
            'srlimit': '50',   # over-fetch; wbgetentities max is 50 IDs per call
            'format': 'json',
        }
        
        headers = {
            'User-Agent': 'Necroporra/1.0 (Celebrity Death Pool App; Educational Project)'
        }
        
        response = requests.get(search_url, params=search_params, headers=headers, timeout=10)
        if response.status_code != 200:
            return []
        
        search_data = response.json()
        search_items = search_data.get('query', {}).get('search', [])
        if not search_items:
            return []
        
        # Extract entity IDs (title field contains the Wikidata item ID, e.g. "Q22686")
        entity_ids = [item['title'] for item in search_items if item['title'].startswith('Q')]
        
        # Batch-fetch all entity details in a single API call, human-filter as a safety net
        results = get_wikidata_entities_batch(entity_ids)
        
        return results[:limit]
    
    except (requests.RequestException, KeyError, ValueError) as e:
        print(f"Error searching Wikidata: {str(e)}")
        return []


def get_wikidata_entities_batch(entity_ids: List[str]) -> List[Dict[str, Any]]:
    """
    Fetch and filter multiple Wikidata entities in a single API call.

    Uses wbgetentities (supports up to 50 pipe-separated IDs) instead of
    one HTTP request per entity and filters results to humans (P31=Q5).

    Args:
        entity_ids: List of Wikidata entity IDs (e.g. ["Q22686", "Q392"])

    Returns:
        List of human entity dicts in the same order as entity_ids, same
        format as search_wikidata_people results.
    """
    if not entity_ids:
        return []

    try:
        url = "https://www.wikidata.org/w/api.php"
        params = {
            'action': 'wbgetentities',
            'ids': '|'.join(entity_ids[:50]),  # API max is 50 IDs per request
            'props': 'labels|descriptions|claims',
            'languages': 'en',
            'format': 'json',
        }
        headers = {
            'User-Agent': 'Necroporra/1.0 (Celebrity Death Pool App; Educational Project)'
        }

        response = requests.get(url, params=params, headers=headers, timeout=15)
        if response.status_code != 200:
            return []

        entities = response.json().get('entities', {})

        results = []
        # Preserve the relevance order from the original search
        for entity_id in entity_ids[:50]:
            entity = entities.get(entity_id)
            if not entity:
                continue

            # Skip non-humans (no P31 claim or P31 != Q5)
            if 'claims' not in entity or 'P31' not in entity['claims']:
                continue

            is_human = False
            for instance_claim in entity['claims']['P31']:
                if 'mainsnak' in instance_claim:
                    datavalue = instance_claim['mainsnak'].get('datavalue', {})
                    if datavalue.get('value', {}).get('id') == 'Q5':
                        is_human = True
                        break

            if not is_human:
                continue

            name = entity.get('labels', {}).get('en', {}).get('value', '')
            if not name:
                continue

            bio = entity.get('descriptions', {}).get('en', {}).get('value', '')
            birth_date = _extract_date_from_claims(entity, 'P569')
            death_date = _extract_date_from_claims(entity, 'P570')
            image_url = _extract_image_from_claims(entity, 'P18')

            results.append({
                'id': f"wikidata:{entity_id}",
                'name': name,
                'bio': bio,
                'birth_date': birth_date,
                'death_date': death_date,
                'wikidata_id': entity_id,
                'image_url': image_url or ''
            })

        return results

    except (requests.RequestException, KeyError, ValueError) as e:
        print(f"Error batch-fetching Wikidata entities: {str(e)}")
        return []


def get_wikidata_entity(entity_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch full details for a Wikidata entity.
    
    Args:
        entity_id: Wikidata entity ID (e.g., "Q392")
    
    Returns:
        Dictionary containing celebrity information or None if not found/not a person.
        Same format as search_wikidata_people results.
    """
    try:
        entity_url = f"https://www.wikidata.org/wiki/Special:EntityData/{entity_id}.json"
        headers = {
            'User-Agent': 'Necroporra/1.0 (Celebrity Death Pool App; Educational Project)'
        }
        
        response = requests.get(entity_url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
        
        entity_data = response.json()
        entity = entity_data['entities'][entity_id]
        
        # Check if this is a person (instance of Q5 - human)
        if 'claims' not in entity or 'P31' not in entity['claims']:
            return None
        
        # Verify it's a human
        is_human = False
        for instance_claim in entity['claims']['P31']:
            if 'mainsnak' in instance_claim:
                datavalue = instance_claim['mainsnak'].get('datavalue', {})
                if datavalue.get('value', {}).get('id') == 'Q5':
                    is_human = True
                    break
        
        if not is_human:
            return None
        
        # Extract name from labels
        name = entity.get('labels', {}).get('en', {}).get('value', '')
        if not name:
            return None
        
        # Extract description (bio)
        bio = entity.get('descriptions', {}).get('en', {}).get('value', '')
        
        # Extract birth date (P569)
        birth_date = _extract_date_from_claims(entity, 'P569')
        
        # Extract death date (P570)
        death_date = _extract_date_from_claims(entity, 'P570')
        
        # Extract image (P18)
        image_url = _extract_image_from_claims(entity, 'P18')
        
        return {
            'id': f"wikidata:{entity_id}",
            'name': name,
            'bio': bio,
            'birth_date': birth_date,
            'death_date': death_date,
            'wikidata_id': entity_id,
            'image_url': image_url or ''
        }
    
    except (requests.RequestException, KeyError, ValueError, IndexError) as e:
        print(f"Error fetching Wikidata entity {entity_id}: {str(e)}")
        return None


def _extract_date_from_claims(entity: Dict, property_id: str) -> Optional[str]:
    """
    Extract a date from Wikidata claims.
    
    Args:
        entity: Wikidata entity data
        property_id: Property ID (e.g., 'P569' for birth date, 'P570' for death date)
    
    Returns:
        Date string in ISO format (YYYY-MM-DD) or None
    """
    try:
        if 'claims' in entity and property_id in entity['claims']:
            date_claim = entity['claims'][property_id][0]
            if 'mainsnak' in date_claim:
                datavalue = date_claim['mainsnak'].get('datavalue', {})
                if 'value' in datavalue:
                    # Parse the date string (format: +YYYY-MM-DDT00:00:00Z or +YYYY-00-00T00:00:00Z)
                    time_str = datavalue['value']['time']
                    # Extract just the date part and remove the leading +
                    date_str = time_str.split('T')[0].lstrip('+')
                    
                    # Handle cases where month or day are 00
                    parts = date_str.split('-')
                    if len(parts) == 3:
                        year, month, day = parts
                        # If month or day is 00, set to 01 for valid date
                        if month == '00':
                            month = '01'
                        if day == '00':
                            day = '01'
                        date_str = f"{year}-{month}-{day}"
                    
                    # Validate the date
                    datetime.fromisoformat(date_str)
                    return date_str
    except (KeyError, IndexError, ValueError):
        pass
    
    return None


def _extract_image_from_claims(entity: Dict, property_id: str) -> Optional[str]:
    """
    Extract image URL from Wikidata claims.
    
    Args:
        entity: Wikidata entity data
        property_id: Property ID (e.g., 'P18' for image)
    
    Returns:
        Image URL or None
    """
    try:
        if 'claims' in entity and property_id in entity['claims']:
            image_claim = entity['claims'][property_id][0]
            if 'mainsnak' in image_claim:
                datavalue = image_claim['mainsnak'].get('datavalue', {})
                if 'value' in datavalue:
                    # Get the image filename
                    filename = datavalue['value']
                    # Convert filename to Wikimedia Commons URL
                    # Replace spaces with underscores
                    filename = filename.replace(' ', '_')
                    # Construct the URL (simplified version)
                    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{filename}"
    except (KeyError, IndexError, ValueError):
        pass
    
    return None
