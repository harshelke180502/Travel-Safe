"""
Route safety assessment tools for SafeTravel MCP server.

Implements safety risk evaluation for travel routes.
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

from pydantic import BaseModel

from server.schemas import LocationInput, RouteInput
from server.tools.crimes import get_recent_crimes
from server.tools.buses import get_bus_status


class SafetyAssessmentResponse(BaseModel):
    """Safety assessment response."""
    risk_level: str
    recommendation: str
    reasons: List[str]
    crime_count: int
    incident_count: int
    recent_crimes: List[dict]


# Location mapping (shared with CLI for consistency)
LOCATION_MAP = {
    "downtown": (41.8781, -87.6298),
    "loop": (41.8781, -87.6298),
    "navy pier": (41.8917, -87.6078),
    "uic": (41.8708, -87.6505),
    "lincoln park": (41.9214, -87.6513),
    "hyde park": (41.7943, -87.5907),
    "chinatown": (41.8526, -87.6324)
}

# Distance threshold for nearby incidents (~1.5km in degrees at Chicago latitude)
DISTANCE_THRESHOLD_DEGREES = 0.015

# Time threshold for recent incidents (72 hours / 3 days)
TIME_THRESHOLD_HOURS = 72


def _parse_location_string(location_str: str) -> Optional[Tuple[float, float]]:
    """
    Parse location string to coordinates.
    
    Tries in order:
    1. Two floats: "41.8781 -87.6298"
    2. Location keyword: "downtown", "navy pier", etc.
    
    Args:
        location_str: Location as string (coordinates or keyword)
    
    Returns:
        (latitude, longitude) tuple, or None if cannot parse
    """
    location_str = location_str.strip().lower()
    
    # Try to extract two floats
    floats = re.findall(r"-?\d+\.\d+", location_str)
    if len(floats) >= 2:
        try:
            latitude = float(floats[0])
            longitude = float(floats[1])
            
            # Validate coordinate ranges
            if -90 <= latitude <= 90 and -180 <= longitude <= 180:
                return (latitude, longitude)
        except (ValueError, IndexError):
            pass
    
    # Check for location keywords
    for keyword, coords in LOCATION_MAP.items():
        if keyword in location_str:
            return coords
    
    return None


def _calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate simple Euclidean distance between two points (in degrees).
    
    Args:
        lat1, lon1: First point coordinates
        lat2, lon2: Second point coordinates
    
    Returns:
        Distance in degrees
    """
    lat_diff = lat2 - lat1
    lon_diff = lon2 - lon1
    return (lat_diff**2 + lon_diff**2)**0.5


def load_recent_incidents() -> List[dict]:
    """
    Load user-reported incidents from incidents.log file.
    
    File format: CSV with timestamp,latitude,longitude,description (one per line)
    
    Returns:
        List of incident dicts with keys: timestamp, latitude, longitude, description
        Empty list if file does not exist or contains no valid records
    """
    incidents = []
    
    data_dir = Path(__file__).parent.parent / "data"
    log_file = data_dir / "incidents.log"
    
    # Return empty list if file does not exist
    if not log_file.exists():
        return incidents
    
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                # Skip lines that don't have at least 4 comma-separated fields
                parts = line.split(",", 3)
                if len(parts) < 4:
                    continue
                
                try:
                    timestamp_str = parts[0].strip()
                    latitude_str = parts[1].strip()
                    longitude_str = parts[2].strip()
                    description = parts[3].strip()
                    
                    # Validate and convert fields
                    timestamp = datetime.fromisoformat(timestamp_str)
                    latitude = float(latitude_str)
                    longitude = float(longitude_str)
                    
                    # Validate coordinate ranges
                    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                        continue
                    
                    incidents.append({
                        "timestamp": timestamp,
                        "latitude": latitude,
                        "longitude": longitude,
                        "description": description
                    })
                except (ValueError, IndexError):
                    # Skip malformed lines
                    continue
    except IOError:
        # Return empty list if file cannot be read
        return incidents
    
    return incidents


def count_nearby_incidents(
    latitude: float,
    longitude: float,
    incidents: List[dict],
    distance_threshold: float = DISTANCE_THRESHOLD_DEGREES,
    hours_threshold: int = TIME_THRESHOLD_HOURS
) -> int:
    """
    Count recent incidents near a location.
    
    Filters incidents by:
    - Distance: within distance_threshold degrees
    - Time: within hours_threshold hours (from now)
    
    Args:
        latitude, longitude: Query location
        incidents: List of incident dicts from load_recent_incidents()
        distance_threshold: Max distance in degrees (default ~1.5km)
        hours_threshold: Max age in hours (default 24)
    
    Returns:
        Count of nearby recent incidents
    """
    now = datetime.utcnow()
    time_cutoff = now - timedelta(hours=hours_threshold)
    
    nearby_count = 0
    
    for incident in incidents:
        # Check time filter
        if incident["timestamp"] < time_cutoff:
            continue
        
        # Check distance filter
        distance = _calculate_distance(
            latitude,
            longitude,
            incident["latitude"],
            incident["longitude"]
        )
        
        if distance <= distance_threshold:
            nearby_count += 1
    
    return nearby_count


def collect_nearby_incidents(
    origin: LocationInput,
    destination: LocationInput,
    incidents: List[dict],
    distance_threshold: float = DISTANCE_THRESHOLD_DEGREES,
    hours_threshold: int = TIME_THRESHOLD_HOURS
) -> int:
    """
    Collect unique incidents near either origin or destination.
    
    Deduplicates incidents that may be near both locations using
    unique key: timestamp + latitude + longitude
    
    Args:
        origin: Starting location
        destination: Destination location
        incidents: List of incident dicts from load_recent_incidents()
        distance_threshold: Max distance in degrees (default ~1.5km)
        hours_threshold: Max age in hours (default 72)
    
    Returns:
        Count of unique nearby recent incidents
    """
    now = datetime.utcnow()
    time_cutoff = now - timedelta(hours=hours_threshold)
    
    # Debug logging
    # print(f"NOW: {now}")
    # print(f"TIME CUTOFF: {time_cutoff}")
    # print(f"INCIDENT COUNT BEFORE FILTER: {len(incidents)}")
    
    # Use set to track unique incidents by (timestamp, lat, lon)
    unique_incidents = set()
    
    for incident in incidents:
        # Check time filter
        if incident["timestamp"] < time_cutoff:
            continue
        
        # Check if near origin
        distance_to_origin = _calculate_distance(
            origin.latitude,
            origin.longitude,
            incident["latitude"],
            incident["longitude"]
        )
        
        # Check if near destination
        distance_to_destination = _calculate_distance(
            destination.latitude,
            destination.longitude,
            incident["latitude"],
            incident["longitude"]
        )
        
        # Add to unique set if near either location
        if distance_to_origin <= distance_threshold or distance_to_destination <= distance_threshold:
            # Create unique key from incident data
            unique_key = (
                incident["timestamp"].isoformat(),
                incident["latitude"],
                incident["longitude"]
            )
            unique_incidents.add(unique_key)
    
    return len(unique_incidents)


def assess_route_safety(
    origin: LocationInput,
    destination: LocationInput,
    route: Optional[str] = None
) -> SafetyAssessmentResponse:
    """
    Assess travel safety between two locations.
    
    Analyzes crime incidents, user-reported incidents, and bus delays to determine risk level.
    
    Safety scoring logic (crime as primary signal, incidents as weak signal):
    - if crime_count >= 5 → risk = "high"
    - elif crime_count >= 2 → risk = "medium"
    - elif incident_count >= 3 → risk = "medium"
    - elif incident_count == 1 → risk remains "low", add reason only
    - else → risk = "low"
    
    Bus delays can lower medium risk but won't change high risk determination.
    
    Args:
        origin: Starting location (LocationInput)
        destination: Destination location (LocationInput)
        route: Optional route name for bus delay checking
    
    Returns:
        SafetyAssessmentResponse with risk level, recommendation, reasons, 
        crime_count, and incident_count
    """
    reasons = []
    risk_level = "low"
    total_crime_count = 0
    total_incident_count = 0
    origin_crime_count = 0
    dest_crime_count = 0
    all_crimes = []  # Collect all crimes for top-5 selection
    
    # Load user-reported incidents (gracefully handles missing file)
    try:
        incidents = load_recent_incidents()
    except Exception:
        incidents = []
    
    # Check crimes at origin
    try:
        crimes_at_origin = get_recent_crimes(origin, limit=50)
        origin_crime_count = len(crimes_at_origin)
        total_crime_count += origin_crime_count
        all_crimes.extend(crimes_at_origin)
        
        if origin_crime_count > 0:
            reasons.append(
                f"Crime activity detected near origin ({origin_crime_count} incidents in nearby area)"
            )
    except Exception as e:
        reasons.append(f"Unable to check crimes at origin: {str(e)}")
    
    # Check crimes at destination
    try:
        crimes_at_destination = get_recent_crimes(destination, limit=10)
        dest_crime_count = len(crimes_at_destination)
        total_crime_count += dest_crime_count
        all_crimes.extend(crimes_at_destination)
        
        if dest_crime_count > 0:
            reasons.append(
                f"Crime activity detected near destination ({dest_crime_count} incidents in nearby area)"
            )
    except Exception as e:
        reasons.append(f"Unable to check crimes at destination: {str(e)}")
    
    # Extract recent crimes details: top 5 by distance
    recent_crimes = []
    if all_crimes:
        # Sort by distance (ascending) and take top 5
        sorted_crimes = sorted(all_crimes, key=lambda c: c.distance)[:5]
        recent_crimes = [
            {
                "type": crime.type,
                "severity": crime.severity,
                "distance": round(crime.distance, 4)
            }
            for crime in sorted_crimes
        ]
    
    # Check user-reported incidents near origin and/or destination
    # Deduplicated to avoid double-counting
    try:
        total_incident_count = collect_nearby_incidents(
            origin,
            destination,
            incidents
        )
        
        if total_incident_count > 0:
            reasons.append(
                f"User-reported incidents nearby ({total_incident_count} recent reports)"
            )
    except Exception as e:
        reasons.append(f"Unable to check user incidents: {str(e)}")
    
    
    # Determine risk level based on refined scoring logic
    # Crime data is the primary signal (using max of origin/destination, not total)
    # User incidents strengthen risk but do not dominate
    
    max_crime = max(origin_crime_count, dest_crime_count)
    
    # HIGH risk: significant crime concentration OR high crime + user reports
    if max_crime >= 15 or (max_crime >= 10 and total_incident_count >= 2):
        risk_level = "high"
    # MEDIUM risk: moderate crime OR multiple user reports
    elif max_crime >= 5 or total_incident_count >= 3:
        risk_level = "medium"
    # LOW risk: minimal or no crime/reports
    else:
        risk_level = "low"
    
    # Check bus delays if route is provided
    has_delays = False
    if route:
        try:
            route_input = RouteInput(route=route)
            buses = get_bus_status(route_input)
            
            # Check for any delays
            delayed_buses = [bus for bus in buses if bus.delay]
            
            if delayed_buses:
                has_delays = True
                delay_count = len(delayed_buses)
                bus_reason = f"Bus delays on route {route} ({delay_count} of {len(buses)} buses delayed)"
                reasons.append(bus_reason)
        except Exception as e:
            reasons.append(f"Unable to check bus status for route {route}: {str(e)}")
    
    # Generate recommendation based on risk level
    if risk_level == "high":
        recommendation = "Avoid this route. Consider alternative routes or modes of transportation."
    elif risk_level == "medium":
        if has_delays:
            recommendation = "Exercise caution. Bus delays detected - consider alternatives or plan extra travel time."
        else:
            recommendation = "Exercise caution. Consider alternatives or take extra precautions."
    else:
        recommendation = "Route appears safe for travel."
    
    # Ensure we always have at least one reason
    if not reasons:
        reasons.append("No significant safety concerns detected.")
    
    return SafetyAssessmentResponse(
        risk_level=risk_level,
        recommendation=recommendation,
        reasons=reasons,
        crime_count=total_crime_count,
        incident_count=total_incident_count,
        recent_crimes=recent_crimes
    )
