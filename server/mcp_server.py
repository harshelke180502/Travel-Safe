"""
Main MCP server implementation for SafeTravel.

Orchestrates the MCP server, tools, and safety mechanisms.
"""

import sys
import requests
from mcp.server.fastmcp import FastMCP

from server.schemas.models import LocationInput, RouteInput, IncidentReportInput
from server.tools import (
    get_recent_crimes,
    get_bus_status,
    get_stops,
    assess_route_safety,
    report_incident,
)

mcp = FastMCP("SafeTravel")


def _resolve_location(location: str) -> tuple:
    """Parse 'lat,lon' or geocode a Chicago place name via Nominatim."""
    parts = location.split(",")
    if len(parts) == 2:
        try:
            return float(parts[0].strip()), float(parts[1].strip())
        except ValueError:
            pass
    print(f"[mcp] geocoding '{location}' via Nominatim", file=sys.stderr)
    resp = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": f"{location}, Chicago, IL", "format": "json", "limit": 1},
        headers={"User-Agent": "SafeTravel/1.0"},
        timeout=5,
    )
    resp.raise_for_status()
    results = resp.json()
    if not results:
        raise ValueError(f"Could not geocode location: '{location}'")
    lat, lon = float(results[0]["lat"]), float(results[0]["lon"])
    print(f"[mcp] geocoded to ({lat}, {lon})", file=sys.stderr)
    return lat, lon


@mcp.tool()
def get_recent_crimes_tool(location: str) -> list:
    """Get recent crimes near a location. Accepts 'lat,lon' or a place name like 'UIC', 'Pilsen', 'Michigan Avenue'."""
    lat, lon = _resolve_location(location)
    loc = LocationInput(latitude=lat, longitude=lon)
    crimes = get_recent_crimes(loc)
    return [crime.model_dump() for crime in crimes]


@mcp.tool()
def get_bus_status_tool(route: str) -> list:
    """Get current bus status for a given route."""
    route_input = RouteInput(route=route)
    buses = get_bus_status(route_input)
    return [bus.model_dump() for bus in buses]


@mcp.tool()
def get_stops_tool(route: str) -> list:
    """Get all bus stops on a given route."""
    route_input = RouteInput(route=route)
    stops = get_stops(route_input)
    return [stop.model_dump() for stop in stops]


@mcp.tool()
def assess_route_safety_tool(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    route: str = None,
) -> dict:
    """Assess travel safety between two locations."""
    origin = LocationInput(latitude=origin_lat, longitude=origin_lon)
    destination = LocationInput(latitude=dest_lat, longitude=dest_lon)
    result = assess_route_safety(origin, destination, route)
    return result.model_dump()


@mcp.tool()
def report_incident_tool(location: str, description: str) -> dict:
    """Report a travel safety incident. Location can be 'lat,lon' or any place name like 'UIC', 'N LaSalle St', 'Wicker Park'."""
    lat, lon = _resolve_location(location)
    loc_input = LocationInput(latitude=lat, longitude=lon)
    incident = IncidentReportInput(location=loc_input, description=description)
    result = report_incident(incident)
    return result.model_dump()


@mcp.tool()
def get_incidents_tool(location: str) -> list:
    """Get all safety incidents near a location — combines Chicago Open Data API crimes and user-reported DB incidents, sorted by severity then distance. Accepts 'lat,lon' or a place name like 'UIC', 'Pilsen'."""
    lat, lon = _resolve_location(location)
    loc = LocationInput(latitude=lat, longitude=lon)
    crimes = get_recent_crimes(loc)
    return [crime.model_dump() for crime in crimes]


if __name__ == "__main__":
    mcp.run()
