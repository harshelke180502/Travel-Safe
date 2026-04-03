"""
Incident reporting tools for SafeTravel MCP server.

Implements incident logging and reporting operations.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from server.schemas import IncidentReportInput


class IncidentReportResponse(BaseModel):
    """Response from incident report submission."""
    success: bool
    message: str
    timestamp: str


def report_incident(incident: IncidentReportInput) -> IncidentReportResponse:
    """
    Report a travel safety incident and log it persistently.
    
    Args:
        incident: IncidentReportInput with location and description
    
    Returns:
        IncidentReportResponse with success status and message
    
    Raises:
        IOError: If unable to write to incidents.log
        PermissionError: If insufficient permissions to write log file
    """
    # Generate timestamp
    timestamp = datetime.utcnow().isoformat()
    
    # Extract location data
    latitude = incident.location.latitude
    longitude = incident.location.longitude
    description = incident.description.strip()
    
    # Prepare log entry (CSV format)
    log_entry = f"{timestamp},{latitude},{longitude},{description}\n"
    
    # Get log file path
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    log_file = data_dir / "incidents.log"
    
    # Safely append to log file
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except IOError as e:
        return IncidentReportResponse(
            success=False,
            message=f"Failed to write incident log: {str(e)}",
            timestamp=timestamp
        )
    except PermissionError as e:
        return IncidentReportResponse(
            success=False,
            message=f"Permission denied writing to incident log: {str(e)}",
            timestamp=timestamp
        )
    
    return IncidentReportResponse(
        success=True,
        message=f"Incident reported successfully at {timestamp}",
        timestamp=timestamp
    )
