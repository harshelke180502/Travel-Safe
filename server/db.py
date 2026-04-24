"""
PostgreSQL connection and incident persistence for SafeTravel.
"""

import os
from datetime import datetime
from typing import List

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def _connect():
    return psycopg2.connect(DATABASE_URL)


def init_db() -> None:
    """Create the incidents table if it does not exist."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS incidents (
                    id          SERIAL PRIMARY KEY,
                    timestamp   TIMESTAMPTZ NOT NULL,
                    latitude    DOUBLE PRECISION NOT NULL,
                    longitude   DOUBLE PRECISION NOT NULL,
                    description TEXT NOT NULL
                )
            """)
        conn.commit()


def save_incident(
    timestamp: str,
    latitude: float,
    longitude: float,
    description: str,
) -> None:
    """Insert one incident row."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO incidents (timestamp, latitude, longitude, description)
                VALUES (%s, %s, %s, %s)
                """,
                (timestamp, latitude, longitude, description),
            )
        conn.commit()


def load_recent_incidents() -> List[dict]:
    """Return all incidents as a list of dicts with datetime timestamps."""
    with _connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT timestamp, latitude, longitude, description FROM incidents ORDER BY timestamp DESC"
            )
            rows = cur.fetchall()

    return [
        {
            "timestamp": row["timestamp"] if isinstance(row["timestamp"], datetime)
                         else datetime.fromisoformat(str(row["timestamp"])),
            "latitude": float(row["latitude"]),
            "longitude": float(row["longitude"]),
            "description": row["description"],
        }
        for row in rows
    ]
