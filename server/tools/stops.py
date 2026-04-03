"""
Stop tools for SafeTravel MCP server.

Implements bus stop operations using mock data for deterministic behavior.
"""

import json
from pathlib import Path
from typing import List

from pydantic import BaseModel

from server.schemas import RouteInput


class StopInfo(BaseModel):
    """Bus stop information."""
    stop_id: str
    name: str
    lat: float
    lon: float


def get_stops(route_input: RouteInput) -> List[StopInfo]:
    """
    Get all bus stops on a given route.
    
    Uses mock data from server/data/stops.json for deterministic behavior.
    CTA stop API is complex and adds unnecessary volatility; mock ensures
    consistent, testable results.
    
    Args:
        route_input: RouteInput with route name
    
    Returns:
        List of StopInfo records for stops on the specified route.
        Empty list if no stops found on route (not an error).
    """
    # Load stops data from mock file
    data_dir = Path(__file__).parent.parent / "data"
    stops_file = data_dir / "stops.json"
    
    if not stops_file.exists():
        raise FileNotFoundError(f"Stops data file not found: {stops_file}")
    
    with open(stops_file, "r") as f:
        stops_data = json.load(f)
    
    if not isinstance(stops_data, list):
        raise ValueError("Stops data must be a JSON array")
    
    # Filter and create records
    stop_infos = []
    
    for stop in stops_data:
        # Check if stop is on the requested route
        if stop.get("route") == route_input.route:
            record = StopInfo(
                stop_id=stop["stop_id"],
                name=stop["name"],
                lat=float(stop["lat"]),
                lon=float(stop["lon"])
            )
            stop_infos.append(record)
    
    return stop_infos
