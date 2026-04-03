"""
Pydantic schemas for SafeTravel MCP server.

Defines data models with explicit validation for all inputs.
"""

from pydantic import BaseModel, Field


class LocationInput(BaseModel):
    """
    Geographic location input schema.
    
    Validates latitude and longitude coordinates.
    """
    latitude: float = Field(
        ...,
        ge=-90,
        le=90,
        description="Latitude coordinate between -90 and 90"
    )
    longitude: float = Field(
        ...,
        ge=-180,
        le=180,
        description="Longitude coordinate between -180 and 180"
    )

    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "example": {
                "latitude": 40.7128,
                "longitude": -74.0060
            }
        }


class RouteInput(BaseModel):
    """
    Route input schema.
    
    Validates that route is a non-empty string.
    """
    route: str = Field(
        ...,
        min_length=1,
        description="Route name or destination (non-empty)"
    )

    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "example": {
                "route": "New York to Boston"
            }
        }


class IncidentReportInput(BaseModel):
    """
    Incident report input schema.
    
    Combines location data with incident description.
    Validates that description is non-empty and not just whitespace.
    """
    location: LocationInput = Field(
        ...,
        description="Geographic location of the incident"
    )
    description: str = Field(
        ...,
        min_length=1,
        description="Incident description (non-empty, non-whitespace)"
    )

    def validate_description_not_whitespace(self) -> None:
        """Ensure description is not just whitespace."""
        if not self.description.strip():
            raise ValueError("Description cannot be empty or contain only whitespace")

    def model_post_init(self, __context):
        """Run validation after model initialization."""
        self.validate_description_not_whitespace()

    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "example": {
                "location": {
                    "latitude": 40.7128,
                    "longitude": -74.0060
                },
                "description": "Hazardous road conditions reported"
            }
        }
