"""
Bus tools for SafeTravel MCP server.

Implements bus status and route operations.
"""

import json
import os
import re
from pathlib import Path
from typing import List, Optional

import requests
from pydantic import BaseModel

from server.schemas import RouteInput
from dotenv import load_dotenv
load_dotenv()


class BusStatus(BaseModel):
    """Bus status information."""
    route: str
    lat: float
    lon: float
    delay: bool


# CTA Bus Tracker API endpoint (Socrata v2)
CTA_API_URL = "http://www.ctabustracker.com/bustime/api/v2/getvehicles"

# API timeout
API_TIMEOUT = 5  # seconds


def _extract_route_number(route_str: str) -> str:
    """
    Extract route number from route string.
    
    Args:
        route_str: Route string like "Route 22"
    
    Returns:
        Route number like "22", or empty string if not found
    """
    match = re.search(r"(\d+)", route_str)
    if match:
        return match.group(1)
    return ""


def _fetch_buses_from_api(route_input: RouteInput) -> Optional[List[dict]]:
    """
    Fetch buses from CTA Bus Tracker API.
    
    Args:
        route_input: RouteInput with route name
    
    Returns:
        List of bus records from API, or None on failure
    """
    api_key = os.getenv("CTA_API_KEY")
    if not api_key:
        # API key not available, fail silently for fallback
        return None
    
    route_number = _extract_route_number(route_input.route)
    if not route_number:
        return None
    
    try:
        params = {
            "key": api_key,
            "rt": route_number,
            "format": "json"
        }
        
        response = requests.get(
            CTA_API_URL,
            params=params,
            timeout=API_TIMEOUT
        )
        response.raise_for_status()
        
        data = response.json()
        # print(f"API response data: {data}")
        
        # CTA API returns response with bustime-response structure
        # Access vehicle list: data["bustime-response"]["vehicle"]
        if not isinstance(data, dict):
            return None
        
        bustime_response = data.get("bustime-response")
        if not isinstance(bustime_response, dict):
            return None
        
        vehicles = bustime_response.get("vehicle")
        # print(f"Extracted vehicles from API: {vehicles}")
        
        # Handle case where "vehicle" key is missing or empty
        if vehicles is None:
            return None
        
        # Ensure vehicles is a list (can be single item)
        if not isinstance(vehicles, list):
            vehicles = [vehicles]
        
        return vehicles
    except Exception:
        # Silently return None on any API failure for graceful fallback
        return None


def _load_buses_from_mock(route_input: RouteInput) -> List[dict]:
    """
    Load buses from local mock data file.
    
    Args:
        route_input: RouteInput with route name
    
    Returns:
        List of bus records from mock data
    
    Raises:
        FileNotFoundError: If buses.json cannot be found
        json.JSONDecodeError: If buses.json is invalid
    """
    data_dir = Path(__file__).parent.parent / "data"
    buses_file = data_dir / "buses.json"
    
    if not buses_file.exists():
        raise FileNotFoundError(f"Buses data file not found: {buses_file}")
    
    with open(buses_file, "r") as f:
        buses_data = json.load(f)
    
    if not isinstance(buses_data, list):
        raise ValueError("Buses data must be a JSON array")
    
    return buses_data


def get_bus_status(route_input: RouteInput) -> List[BusStatus]:
    """
    Get all buses on a given route with their current status.
    
    Attempts to fetch live data from CTA Bus Tracker API.
    Falls back to mock data if API is unavailable or API key is not configured.
    
    Args:
        route_input: RouteInput with route name
    
    Returns:
        List of BusStatus records for buses on the specified route.
        Empty list if no buses found on route (not an error).
    """
    buses_data = None
    
    # Try to fetch from live API first
    buses_data = _fetch_buses_from_api(route_input)
    # print("FINAL buses_data of api:", buses_data[:2] if buses_data else "EMPTY")
    
    # Fall back to mock data if API fails or returns empty
    if buses_data is None:
        buses_data = _load_buses_from_mock(route_input)
    # print("FINAL buses_data (after fallback to mock):", buses_data[:2] if buses_data else "EMPTY")
    # Validate data structure
    if not isinstance(buses_data, list):
        buses_data = []
    
    # Filter and create records
    bus_statuses = []
    route_number = _extract_route_number(route_input.route)

    route_number = _extract_route_number(route_input.route)

    for bus in buses_data:
        try:
            latitude_val = bus.get("lat")
            longitude_val = bus.get("lon")

            if latitude_val is None or longitude_val is None:
                continue

            latitude = float(latitude_val)
            longitude = float(longitude_val)

            # FIX delay
            if "dly" in bus:
                delay = bool(bus["dly"])
                # print("API bus record found")
            else:
                delay = bool(bus.get("delay", False))
                # print("Mock bus record found")

            # FIX route matching
            api_route = bus.get("rt")
            mock_route = bus.get("route")

            match_api = api_route and str(api_route) == route_number
            match_mock = mock_route == route_input.route

            if match_api or match_mock:
                record = BusStatus(
                    route=f"Route {route_number}",
                    lat=latitude,
                    lon=longitude,
                    delay=delay
                )
                bus_statuses.append(record)

        except Exception:
            continue
        
    return bus_statuses
