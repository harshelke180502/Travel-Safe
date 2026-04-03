"""
CLI client for SafeTravel MCP server.

Provides a minimal command-line interface for executing MCP tool calls.
Uses keyword matching to route natural language inputs to appropriate tools.
"""

import json
import re
import sys
from typing import Optional

import typer

from server.schemas import LocationInput, RouteInput, IncidentReportInput
from server.tools import (
    get_recent_crimes,
    get_bus_status,
    get_stops,
    report_incident,
    assess_route_safety,
)

app = typer.Typer(
    name="SafeTravel",
    help="Travel safety assistant using MCP tools"
)

# Default hardcoded inputs
DEFAULT_LOCATION = LocationInput(latitude=41.8781, longitude=-87.6298)
DEFAULT_DESTINATION = LocationInput(latitude=41.8820, longitude=-87.6315)
DEFAULT_ROUTE = "Route 36"
LOCATION_MAP = {
    # Central / Downtown
    "downtown":                 (41.8781, -87.6298),
    "loop":                     (41.8781, -87.6298),
    "the loop":                 (41.8781, -87.6298),
    "millennium park":          (41.8827, -87.6233),
    "grant park":               (41.8765, -87.6194),
    "navy pier":                (41.8917, -87.6078),
    "union station":            (41.8786, -87.6400),

    # Near North / North Side
    "river north":              (41.8926, -87.6341),
    "gold coast":               (41.9044, -87.6295),
    "magnificent mile":         (41.8962, -87.6254),
    "old town":                 (41.9107, -87.6362),
    "lincoln park":             (41.9214, -87.6513),
    "lakeview":                 (41.9435, -87.6459),
    "wrigleyville":             (41.9474, -87.6556),
    "wicker park":              (41.9086, -87.6771),
    "bucktown":                 (41.9178, -87.6770),
    "logan square":             (41.9217, -87.7036),
    "humboldt park":            (41.9000, -87.7226),
    "andersonville":            (41.9810, -87.6557),
    "uptown":                   (41.9655, -87.6537),
    "rogers park":              (42.0085, -87.6683),

    # West Side
    "west loop":                (41.8828, -87.6480),
    "greektown":                (41.8791, -87.6484),
    "ukrainian village":        (41.8951, -87.6728),
    "pilsen":                   (41.8557, -87.6614),
    "little village":           (41.8286, -87.7148),

    # South Side
    "south loop":               (41.8665, -87.6266),
    "bronzeville":              (41.8344, -87.6152),
    "hyde park":                (41.7943, -87.5907),
    "woodlawn":                 (41.7742, -87.5986),
    "chatham":                  (41.7487, -87.6098),
    "englewood":                (41.7788, -87.6468),
    "south shore":              (41.7601, -87.5696),
    "chinatown":                (41.8526, -87.6324),
    "bridgeport":               (41.8441, -87.6527),

    # Airports & Transit Hubs
    "o'hare":                   (41.9742, -87.9073),
    "o'hare airport":           (41.9742, -87.9073),
    "midway":                   (41.7868, -87.7428),
    "midway airport":           (41.7868, -87.7428),

    # Universities
    "uic":                      (41.8708, -87.6505),
    "university of illinois chicago": (41.8708, -87.6505),
    "depaul":                   (41.9256, -87.6553),
    "depaul university":        (41.9256, -87.6553),
    "university of chicago":    (41.7886, -87.5987),
    "uchicago":                 (41.7886, -87.5987),
    "northwestern":             (42.0565, -87.6753),
    "loyola":                   (42.0012, -87.6584),
}


def extract_route(text: str) -> str:
    """
    Extract route number from text.
    
    Patterns:
        - "route 22" → "Route 22"
        - "route 18" → "Route 18"
        - "route 151" → "Route 151"
    
    Returns default route if extraction fails.
    """
    # Match "route <number>" pattern
    match = re.search(r"route\s+(\d+)", text, re.IGNORECASE)
    if match:
        route_number = match.group(1)
        return f"Route {route_number}"
    
    return DEFAULT_ROUTE


def extract_description(text: str) -> str:
    """
    Extract incident description from text.
    
    Takes everything after "report" keyword.
    Returns default description if extraction fails.
    """
    # Split on "report" keyword
    match = re.search(r"report\s+(.*)", text, re.IGNORECASE)
    if match:
        description = match.group(1).strip()
        if description:
            return description
    
    return "Incident reported via SafeTravel"


def extract_location(text: str) -> LocationInput:
    """
    Extract location from text.
    
    Priority:
    1. Two floats in text → treat as latitude, longitude
    2. Keyword in LOCATION_MAP → use mapped coordinates
    3. Default → use DEFAULT_LOCATION
    
    Examples:
        - "crime at 41.8781 -87.6298" → LocationInput(41.8781, -87.6298)
        - "crime at downtown" → LocationInput(downtown coordinates)
        - "crime nearby" → DEFAULT_LOCATION
    
    Returns:
        LocationInput object
    """
    text_lower = text.lower()
    
    # Try to extract two floats (latitude, longitude)
    floats = re.findall(r"-?\d+\.\d+", text)
    if len(floats) >= 2:
        try:
            latitude = float(floats[0])
            longitude = float(floats[1])
            
            # Validate coordinates are within valid ranges
            if -90 <= latitude <= 90 and -180 <= longitude <= 180:
                return LocationInput(latitude=latitude, longitude=longitude)
        except (ValueError, IndexError):
            pass
    
    # Check for location keywords in LOCATION_MAP
    for keyword, (lat, lon) in LOCATION_MAP.items():
        if keyword in text_lower:
            return LocationInput(latitude=lat, longitude=lon)
    
    # Fall back to default location
    return DEFAULT_LOCATION


def extract_origin_destination(text: str) -> tuple:
    """
    Extract origin and destination from route safety query.
    
    Supports two formats:
    A. "from X to Y" → origin=X, destination=Y
    B. "near X" → origin=destination=X
    
    Examples:
        - "is route 22 safe from uic to downtown"
          → origin = uic, destination = downtown
        
        - "is route 22 safe near navy pier"
          → origin = navy pier, destination = navy pier
    
    Args:
        text: User query text
    
    Returns:
        Tuple of (origin: LocationInput, destination: LocationInput)
    
    Raises:
        ValueError: If locations cannot be parsed
    """
    text_lower = text.lower()
    
    # Pattern 1: "from X to Y"
    # Matches: "from <any chars> to <any chars>" followed by optional keywords or end
    from_to_match = re.search(
        r"from\s+(.+?)\s+to\s+(.+?)(?:\s+(?:safe|on|route|with|using|\?)|$)",
        text_lower
    )
    
    if from_to_match:
        origin_str = from_to_match.group(1).strip()
        destination_str = from_to_match.group(2).strip()
        
        try:
            origin = extract_location(origin_str)
            destination = extract_location(destination_str)
            return (origin, destination)
        except Exception as e:
            raise ValueError(f"Failed to parse 'from {origin_str} to {destination_str}': {str(e)}")
    
    # Pattern 2: "near X"
    # Matches: "near <any chars>" followed by optional keywords or end
    near_match = re.search(
        r"near\s+(.+?)(?:\s+(?:safe|on|route|with|using|\?)|$)",
        text_lower
    )
    
    if near_match:
        location_str = near_match.group(1).strip()
        try:
            location = extract_location(location_str)
            return (location, location)
        except Exception as e:
            raise ValueError(f"Failed to parse 'near {location_str}': {str(e)}")
    
    # No specific location pattern found
    raise ValueError(
        "Could not extract origin and destination. "
        "Use 'from X to Y' or 'near X' format. "
        "Example: 'is route 22 safe from uic to downtown?'"
    )


def format_output(data) -> str:
    """Format Pydantic model or response as pretty JSON."""
    if hasattr(data, "model_dump"):
        return json.dumps(data.model_dump(), indent=2)
    elif isinstance(data, list):
        return json.dumps(
            [item.model_dump() if hasattr(item, "model_dump") else item for item in data],
            indent=2
        )
    else:
        return json.dumps(data, indent=2, default=str)


def handle_crimes_query(input_text: str) -> None:
    """Handle 'crime' keyword - get recent crimes."""
    location = extract_location(input_text)
    typer.echo(f"🔍 Checking for nearby crimes at {location.latitude}, {location.longitude}...")
    typer.echo(f"📍 Using location: ({location.latitude}, {location.longitude})")
    try:
        crimes = get_recent_crimes(location, limit=5)
        typer.echo(f"\n📍 Crimes near location ({location.latitude}, {location.longitude}):")
        typer.echo(format_output(crimes))
    except Exception as e:
        typer.echo(f"❌ Error: {str(e)}", err=True)


def handle_bus_query(input_text: str) -> None:
    """Handle 'bus' keyword - get bus status."""
    route = extract_route(input_text)
    typer.echo(f"🚌 Checking bus status for {route}...")
    try:
        buses = get_bus_status(RouteInput(route=route))
        typer.echo(f"\n🚌 Buses on {route}:")
        typer.echo(format_output(buses))
    except Exception as e:
        typer.echo(f"❌ Error: {str(e)}", err=True)


def handle_stop_query(input_text: str) -> None:
    """Handle 'stop' keyword - get bus stops."""
    route = extract_route(input_text)
    typer.echo(f"🛑 Getting stops for {route}...")
    try:
        stops = get_stops(RouteInput(route=route))
        typer.echo(f"\n🛑 Stops on {route}:")
        typer.echo(format_output(stops))
    except Exception as e:
        typer.echo(f"❌ Error: {str(e)}", err=True)


def handle_report_query(input_text: str) -> None:
    """Handle 'report' keyword - report an incident."""
    location = extract_location(input_text)
    description = extract_description(input_text)
    typer.echo(f"📝 Reporting incident at {location.latitude}, {location.longitude}...")
    typer.echo(f"📍 Using location: ({location.latitude}, {location.longitude})")
    try:
        incident = IncidentReportInput(
            location=location,
            description=description
        )
        response = report_incident(incident)
        typer.echo("\n✅ Incident Report:")
        typer.echo(format_output(response))
    except Exception as e:
        typer.echo(f"❌ Error: {str(e)}", err=True)


def handle_safety_query(input_text: str) -> None:
    """Handle 'safe' keyword - assess route safety."""
    route = extract_route(input_text)
    
    try:
        origin, destination = extract_origin_destination(input_text)
        typer.echo(f"🛡️  Assessing route safety...")
        typer.echo(f"📍 Origin: ({origin.latitude}, {origin.longitude})")
        typer.echo(f"📍 Destination: ({destination.latitude}, {destination.longitude})")
        typer.echo(f"🚌 Route: {route}\n")
        
        assessment = assess_route_safety(
            origin=origin,
            destination=destination,
            route=route
        )
        typer.echo("🛡️  Safety Assessment:")
        typer.echo(format_output(assessment))
    except ValueError as e:
        typer.echo(f"⚠️  {str(e)}", err=True)
        typer.echo(
            "\n💡 Hint: Use one of these formats:\n"
            "  - 'is route 22 safe from uic to downtown?'\n"
            "  - 'is route 36 safe near navy pier?'",
            err=True
        )
    except Exception as e:
        typer.echo(f"❌ Error: {str(e)}", err=True)


@app.command()
def query(text: str = typer.Argument(..., help="Natural language query")) -> None:
    """
    Query SafeTravel with a natural language instruction.
    
    Examples:
        - "Check crimes nearby"
        - "What buses are running on route 22?"
        - "Get bus stops for route 18"
        - "Report suspicious activity near 5th street"
        - "Is route 151 safe?"
    """
    text_lower = text.lower()
    
    typer.echo(f"\n📋 Query: {text}\n")
    
    # Route based on keywords
    if "crime" in text_lower:
        handle_crimes_query(text)
    elif "bus" in text_lower:
        handle_bus_query(text)
    elif "stop" in text_lower:
        handle_stop_query(text)
    elif "report" in text_lower:
        handle_report_query(text)
    elif "safe" in text_lower or "safety" in text_lower:
        handle_safety_query(text)
    else:
        typer.echo("❓ Unknown query. Try keywords like:", err=True)
        typer.echo("  - 'crime' (nearby crimes)", err=True)
        typer.echo("  - 'bus' (bus status, e.g. 'bus route 22')", err=True)
        typer.echo("  - 'stop' (bus stops, e.g. 'stops on route 18')", err=True)
        typer.echo("  - 'report' (incident report, e.g. 'report hazard')", err=True)
        typer.echo("  - 'safe' (safety assessment, e.g. 'safe on route 151')", err=True)


@app.command()
def status() -> None:
    """Show system status and default configuration."""
    typer.echo("\n🛡️  SafeTravel MCP System Status\n")
    typer.echo(f"Default Location: {DEFAULT_LOCATION.latitude}, {DEFAULT_LOCATION.longitude}")
    typer.echo(f"Default Destination: {DEFAULT_DESTINATION.latitude}, {DEFAULT_DESTINATION.longitude}")
    typer.echo(f"Default Route: {DEFAULT_ROUTE}")
    typer.echo("\n✅ System ready for queries")


def main() -> None:
    """Entry point for the CLI client."""
    app()


if __name__ == "__main__":
    main()

