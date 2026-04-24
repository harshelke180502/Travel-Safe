"""
Tools for SafeTravel MCP server.

Implements safety and travel-related operations.
"""

import math
import sys
from typing import List

import requests
from pydantic import BaseModel

from server.schemas import LocationInput


class CrimeRecord(BaseModel):
    """Crime incident with distance calculation."""
    type: str
    severity: str
    distance: float
    description: str = ""


# Chicago Open Data API endpoint (Socrata v2)
CHICAGO_API_URL = "https://data.cityofchicago.org/resource/x2n5-8w5q.json"

# Timeout for API requests
API_TIMEOUT = 5  # seconds

# Final distance threshold in kilometers for haversine filtering
DISTANCE_THRESHOLD_KM = 1.5

# Bounding-box prefilter in degrees (~1.5km near Chicago)
BOUNDING_BOX_DEGREES = 0.015


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
    bounding_box_degrees: float = BOUNDING_BOX_DEGREES
) -> List[dict]:
    """
    Fetch crimes from Chicago Open Data API using geospatial filter.
    
    Uses Socrata v2 within_circle query to get crimes within specified radius
    of the given location.
    
    Args:
        location: Target location (latitude, longitude)
        bounding_box_degrees: Bounding-box half-width in degrees (default ~1.5km)
    
    Returns:
        List of crime records from API

    Raises:
        RuntimeError: If the API request fails or returns an unexpected payload
    """
    lat_min = location.latitude - bounding_box_degrees
    lat_max = location.latitude + bounding_box_degrees
    lon_min = location.longitude - bounding_box_degrees
    lon_max = location.longitude + bounding_box_degrees
    where_clause = (
        f"latitude IS NOT NULL AND longitude IS NOT NULL "
        f"AND latitude > {lat_min} AND latitude < {lat_max} "
        f"AND longitude > {lon_min} AND longitude < {lon_max}"
    )

    params = {
        "$limit": 50,
        "$where": where_clause,
    }

    try:
        response = requests.get(
            CHICAGO_API_URL,
            params=params,
            timeout=API_TIMEOUT
        )
        print(f"[crimes] URL: {response.url}", file=sys.stderr)
        print(f"[crimes] status: {response.status_code}", file=sys.stderr)
        response.raise_for_status()
        data = response.json()
        print(f"[crimes] records returned: {len(data)}", file=sys.stderr)
       
        if data:
            print(f"[crimes] sample record: {list(data[0])}", file=sys.stderr)
    except Exception as exc:
        raise RuntimeError(f"Chicago crime API request failed: {exc}") from exc

    if not isinstance(data, list):
        raise RuntimeError("Chicago crime API returned an unexpected payload")

    return data

def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in km

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2

    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _load_nearby_incidents(location: LocationInput) -> List[CrimeRecord]:
    """Load user-reported incidents from DB and filter to those within DISTANCE_THRESHOLD_KM."""
    try:
        from server.db import load_recent_incidents
        incidents = load_recent_incidents()
    except Exception as exc:
        print(f"[crimes] could not load DB incidents: {exc}", file=sys.stderr)
        return []

    records = []
    for inc in incidents:
        dist = haversine(location.latitude, location.longitude, inc["latitude"], inc["longitude"])
        if dist <= DISTANCE_THRESHOLD_KM:
            records.append(CrimeRecord(
                type="User Report",
                severity=_derive_severity(inc["description"]),
                distance=dist,
                description=inc["description"],
            ))
    print(f"[crimes] {len(records)} nearby reported incidents from DB", file=sys.stderr)
    return records


def get_recent_crimes(location: LocationInput, limit: int = 10) -> List[CrimeRecord]:
    crimes_data = _fetch_crimes_from_api(location)
    
    crimes_with_distance = []
    
    for crime in crimes_data:
        crime_type = (
            crime.get("_primary_decsription") or
            crime.get("primary_type") or
            crime.get("PRIMARY_TYPE") or
            "Unknown"
        )
        sub_description = (
            crime.get("_secondary_description") or
            crime.get("description") or
            ""
        )
        lat_val = crime.get("latitude") or crime.get("lat")
        lon_val = crime.get("longitude") or crime.get("lon")

        if lat_val is None or lon_val is None:
            continue
        try:
            # latitude = float(crime.get("latitude") or crime.get("lat", 0))
            # longitude = float(crime.get("longitude") or crime.get("lon", 0))
            latitude = float(lat_val)
            longitude = float(lon_val)

        except (ValueError, TypeError):
            # Skip records with invalid coordinates
            continue

        if latitude == 0 or longitude == 0:
            continue
        
        # Calculate Euclidean distance in degrees
        # lat_diff = latitude - location.latitude
        # lon_diff = longitude - location.longitude
        # distance = math.sqrt(lat_diff**2 + lon_diff**2)

        if abs(latitude - location.latitude) > BOUNDING_BOX_DEGREES:
            continue
        if abs(longitude - location.longitude) > BOUNDING_BOX_DEGREES:
            continue

        distance = haversine(location.latitude,location.longitude,latitude,longitude)

        
        
        # Final filter: retain only crimes within haversine radius in km.
        if distance > DISTANCE_THRESHOLD_KM:
            continue
        
        record = CrimeRecord(
            type=crime_type,
            severity=_derive_severity(crime_type),
            distance=distance,
            description=sub_description,
        )
        crimes_with_distance.append(record)

    crimes_with_distance += _load_nearby_incidents(location)

    crimes_with_distance.sort(key=lambda x: x.distance)
    print(
        f"[crimes] {len(crimes_with_distance)} crimes within {DISTANCE_THRESHOLD_KM}km, "
        f"returning {min(limit, len(crimes_with_distance))}",
        file=sys.stderr,
    )
    return crimes_with_distance[:limit]
