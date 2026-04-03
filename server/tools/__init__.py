"""
Tools module for SafeTravel MCP server.

Contains tool implementations for the MCP server.
"""

from server.tools.crimes import get_recent_crimes, CrimeRecord
from server.tools.buses import get_bus_status, BusStatus
from server.tools.stops import get_stops, StopInfo
from server.tools.incidents import report_incident, IncidentReportResponse
from server.tools.safety import assess_route_safety, SafetyAssessmentResponse

__all__ = [
    "get_recent_crimes",
    "CrimeRecord",
    "get_bus_status",
    "BusStatus",
    "get_stops",
    "StopInfo",
    "report_incident",
    "IncidentReportResponse",
    "assess_route_safety",
    "SafetyAssessmentResponse",
]
