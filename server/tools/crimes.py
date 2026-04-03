"""
Tools for SafeTravel MCP server.

Implements safety and travel-related operations.
"""

import json
import math
from pathlib import Path
from typing import List, Optional

import requests
from pydantic import BaseModel

from server.schemas import LocationInput


class CrimeRecord(BaseModel):
    """Crime incident with distance calculation."""
    type: str
    severity: str
    distance: float


# Chicago Open Data API endpoint (Socrata v2)
CHICAGO_API_URL = "https://data.cityofchicago.org/resource/x2n5-8w5q.json"

# Timeout for API requests
API_TIMEOUT = 5  # seconds

# Distance threshold for nearby crimes: ~1.5km in degrees at Chicago latitude
# 0.015 degrees ≈ 1.5km at latitude 41.8°N
DISTANCE_THRESHOLD_DEGREES = 0.015


def _derive_severity(crime_type: str) -> str:
    """
    Derive severity level from crime type.
    
    Args:
        crime_type: Primary crime type from API
    
    Returns:
        Severity level: "high", "medium", or "low"
    """
    high_severity_types = {
        "assault", "robbery", "murder", "rape", "sexual", "homicide",
        "aggravated"
    }
    
    medium_severity_types = {
        "theft", "burglary", "auto theft", "motor vehicle", "criminal damage",
        "arson"
    }
    
    crime_lower = crime_type.lower()
    
    # Check if any high severity keyword matches
    if any(keyword in crime_lower for keyword in high_severity_types):
        return "high"
    
    # Check if any medium severity keyword matches
    if any(keyword in crime_lower for keyword in medium_severity_types):
        return "medium"
    
    # Default to low
    return "low"


def _fetch_crimes_from_api(
    location: LocationInput,
    radius_degrees: float = DISTANCE_THRESHOLD_DEGREES
) -> Optional[List[dict]]:
    """
    Fetch crimes from Chicago Open Data API using geospatial filter.
    
    Uses Socrata v2 within_circle query to get crimes within specified radius
    of the given location.
    
    Args:
        location: Target location (latitude, longitude)
        radius_degrees: Search radius in degrees (default ~1.5km)
    
    Returns:
        List of crime records from API, or None on failure
    """
    try:
        # Build SODA v2 query with within_circle geospatial filter
        where_clause = (
            f"within_circle(location, {location.latitude}, {location.longitude}, {radius_degrees})"
        )
        
        params = {
            "$limit": 50,  # Retrieve more from API, will filter again
            "$where": where_clause,
        }
        
        response = requests.get(
            CHICAGO_API_URL,
            params=params,
            timeout=API_TIMEOUT
        )
        response.raise_for_status()
        
        data = response.json()
        if isinstance(data, list):
            return data
        return None
    except Exception as e:
        # Note: silently return None on any API failure for graceful fallback
        return None


def _load_crimes_from_mock() -> List[dict]:
    """
    Load crimes from local mock data file.
    
    Returns:
        List of crime records from mock data
    
    Raises:
        FileNotFoundError: If crimes.json cannot be found
        json.JSONDecodeError: If crimes.json is invalid
    """
    data_dir = Path(__file__).parent.parent / "data"
    crimes_file = data_dir / "crimes.json"
    
    if not crimes_file.exists():
        raise FileNotFoundError(f"Crimes data file not found: {crimes_file}")
    
    with open(crimes_file, "r") as f:
        crimes_data = json.load(f)
    
    if not isinstance(crimes_data, list):
        raise ValueError("Crimes data must be a JSON array")
    
    return crimes_data


def get_recent_crimes(location: LocationInput, limit: int = 5) -> List[CrimeRecord]:
    """
    Get crimes nearest to a given location.
    
    Attempts to fetch live data from Chicago Open Data API (Socrata v2).
    Falls back to local crimes.json if API is unavailable or returns empty results.
    
    Filters results by location to ensure only nearby crimes are returned.
    Distance filtering is applied consistently regardless of data source.
    
    Args:
        location: LocationInput with latitude and longitude
        limit: Maximum number of crimes to return after filtering (default: 5)
    
    Returns:
        List of CrimeRecord sorted by distance (nearest first).
        Only includes crimes within DISTANCE_THRESHOLD_DEGREES of location.
    """
    crimes_data = None
    
    # Try to fetch from live API first
    crimes_data = _fetch_crimes_from_api(location)
    
    # Fall back to mock data if API fails OR returns empty
    if not crimes_data:
        crimes_data = _load_crimes_from_mock()
    
    # Validate data structure
    if not isinstance(crimes_data, list):
        raise ValueError("Crimes data must be a JSON array")
    
    crimes_with_distance = []
    
    for crime in crimes_data:
        # Extract fields from API or mock data
        # API uses: primary_type, latitude, longitude
        # Mock uses: type, lat, lon
        crime_type = crime.get("primary_type") or crime.get("type", "Unknown")
        
        try:
            latitude = float(crime.get("latitude") or crime.get("lat", 0))
            longitude = float(crime.get("longitude") or crime.get("lon", 0))
        except (ValueError, TypeError):
            # Skip records with invalid coordinates
            continue
        
        # Skip invalid records (zero or missing coordinates)
        if not latitude or not longitude:
            continue
        
        # Calculate Euclidean distance in degrees
        lat_diff = latitude - location.latitude
        lon_diff = longitude - location.longitude
        distance = math.sqrt(lat_diff**2 + lon_diff**2)
        
        # CRITICAL: Apply strict distance filter
        # Only include crimes within the defined threshold
        if distance > DISTANCE_THRESHOLD_DEGREES:
            continue
        
        # Create record with derived severity
        record = CrimeRecord(
            type=crime_type,
            severity=_derive_severity(crime_type),
            distance=distance
        )
        crimes_with_distance.append(record)
    
    # Sort by distance (nearest first) and apply limit AFTER filtering
    crimes_with_distance.sort(key=lambda x: x.distance)
    
    # print(f"🔍 Location: ({location.latitude}, {location.longitude})")
    # print(f"📊 Total crimes within {DISTANCE_THRESHOLD_DEGREES}° radius: {len(crimes_with_distance)}")
    # print(f"✂️  Returning top {min(limit, len(crimes_with_distance))} crimes")
    
    return crimes_with_distance[:limit]
