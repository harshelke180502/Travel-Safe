"""
Incident reporting tools for SafeTravel MCP server.

Writes incidents to PostgreSQL; falls back to incidents.log if DB is unavailable.
"""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from server.schemas import IncidentReportInput


class IncidentReportResponse(BaseModel):
    """Response from incident report submission."""
    success: bool
    message: str
    timestamp: str


def report_incident(incident: IncidentReportInput) -> IncidentReportResponse:
    """
    Persist a travel safety incident to PostgreSQL.

    Falls back to appending incidents.log if the database is unavailable.
    """
    timestamp = datetime.utcnow().isoformat()
    latitude = incident.location.latitude
    longitude = incident.location.longitude
    description = incident.description.strip()

    # Primary: write to PostgreSQL
    try:
        from server.db import save_incident
        save_incident(timestamp, latitude, longitude, description)
        return IncidentReportResponse(
            success=True,
            message=f"Incident saved to database at {timestamp}",
            timestamp=timestamp,
        )
    except Exception:
        pass  # fall through to log-file fallback

    # Fallback: append to incidents.log
    try:
        data_dir = Path(__file__).parent.parent / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        log_file = data_dir / "incidents.log"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"{timestamp},{latitude},{longitude},{description}\n")
        return IncidentReportResponse(
            success=True,
            message=f"Incident saved to log (DB unavailable) at {timestamp}",
            timestamp=timestamp,
        )
    except Exception as log_err:
        return IncidentReportResponse(
            success=False,
            message=f"Failed to save incident: {log_err}",
            timestamp=timestamp,
        )
