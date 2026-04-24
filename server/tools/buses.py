"""
Bus tools for SafeTravel MCP server.

Tries CTA Bus Tracker API first; falls back to buses.json on any failure.
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import List, Optional

import requests
from dotenv import load_dotenv
from pydantic import BaseModel

from server.schemas import RouteInput

load_dotenv()

CTA_API_URL = "https://www.ctabustracker.com/bustime/api/v2/getvehicles"
API_TIMEOUT = 10


class BusStatus(BaseModel):
    """Bus status information."""
    route: str
    lat: float
    lon: float
    delay: bool


def _extract_route_number(route_str: str) -> str:
    match = re.search(r"(\d+)", route_str)
    return match.group(1) if match else ""


def _fetch_buses_from_api(route_input: RouteInput) -> Optional[List[dict]]:
    """Try live CTA Bus Tracker API. Returns None on any failure."""
    api_key = os.getenv("CTA_API_KEY")
    if not api_key:
        print("[buses] CTA_API_KEY not set — skipping live API", file=sys.stderr)
        return None

    route_number = _extract_route_number(route_input.route)
    if not route_number:
        print(f"[buses] Could not extract route number from '{route_input.route}'", file=sys.stderr)
        return None

    try:
        response = requests.get(
            CTA_API_URL,
            params={"key": api_key, "rt": route_number, "format": "json"},
            timeout=API_TIMEOUT,
        )
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, dict):
            print("[buses] Unexpected API response format", file=sys.stderr)
            return None

        bustime_response = data.get("bustime-response", {})
        print(f"[buses] getvehicles raw response keys: {list(bustime_response.keys())}", file=sys.stderr)

        # Surface any API-level errors
        errors = bustime_response.get("error")
        if errors:
            msg = errors[0].get("msg", "unknown") if isinstance(errors, list) else str(errors)
            print(f"[buses] CTA API error: {msg}", file=sys.stderr)
            return None

        vehicles = bustime_response.get("vehicle")
        if vehicles is None:
            print("[buses] No vehicles returned from API (route may have no active buses)", file=sys.stderr)
            return []

        if not isinstance(vehicles, list):
            vehicles = [vehicles]

        print(f"[buses] CTA API returned {len(vehicles)} vehicles for route {route_number}", file=sys.stderr)
        return vehicles

    except Exception as e:
        print(f"[buses] CTA API failed ({type(e).__name__}: {e}) — will use mock data", file=sys.stderr)
        return None


def _load_buses_from_mock() -> List[dict]:
    """Load buses from local buses.json fallback."""
    data_dir = Path(__file__).parent.parent / "data"
    buses_file = data_dir / "buses.json"

    if not buses_file.exists():
        return []

    with open(buses_file, "r") as f:
        buses_data = json.load(f)

    return buses_data if isinstance(buses_data, list) else []


def get_bus_status(route_input: RouteInput) -> List[BusStatus]:
    """
    Get all buses on a given route with their current status.

    Tries CTA Bus Tracker API first; falls back to buses.json on any failure.
    """
    buses_data = _fetch_buses_from_api(route_input)

    if buses_data is None:
        print(f"[buses] Using MOCK DATA (buses.json) for {route_input.route}", file=sys.stderr)
        buses_data = _load_buses_from_mock()
    else:
        print(f"[buses] Using LIVE CTA API for {route_input.route}", file=sys.stderr)

    if not isinstance(buses_data, list):
        buses_data = []

    route_number = _extract_route_number(route_input.route)
    bus_statuses = []

    for bus in buses_data:
        try:
            lat = bus.get("lat")
            lon = bus.get("lon")
            if lat is None or lon is None:
                continue

            delay = bool(bus["dly"]) if "dly" in bus else bool(bus.get("delay", False))

            api_route = bus.get("rt")
            mock_route = bus.get("route")
            match_api = api_route and str(api_route) == route_number
            match_mock = mock_route == route_input.route

            if match_api or match_mock:
                bus_statuses.append(BusStatus(
                    route=f"Route {route_number}",
                    lat=float(lat),
                    lon=float(lon),
                    delay=delay,
                ))
        except Exception:
            continue

    return bus_statuses
