"""
Main MCP server implementation for SafeTravel.

Orchestrates the MCP server, tools, and safety mechanisms.
"""

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


@mcp.tool()
def get_recent_crimes_tool(lat: float, lon: float) -> list:
    """Get recent crimes near a given location."""
    location = LocationInput(latitude=lat, longitude=lon)
    crimes = get_recent_crimes(location)
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
    """Report a travel safety incident at a location (lat,lon or keyword)."""
    # Parse "lat,lon" string into coordinates
    parts = location.split(",")
    if len(parts) == 2:
        lat = float(parts[0].strip())
        lon = float(parts[1].strip())
    else:
        raise ValueError(
            f"Invalid location format '{location}'. Expected 'lat,lon' (e.g. '41.8781,-87.6298')."
        )

    loc_input = LocationInput(latitude=lat, longitude=lon)
    incident = IncidentReportInput(location=loc_input, description=description)
    result = report_incident(incident)
    return result.model_dump()


if __name__ == "__main__":
    mcp.run()
