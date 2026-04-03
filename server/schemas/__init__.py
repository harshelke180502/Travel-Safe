"""
Schemas module for SafeTravel MCP server.

Contains data schemas and validation definitions.
"""

from server.schemas.models import (
    LocationInput,
    RouteInput,
    IncidentReportInput,
)

__all__ = [
    "LocationInput",
    "RouteInput",
    "IncidentReportInput",
]
