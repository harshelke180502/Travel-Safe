"""
Stop tools for SafeTravel MCP server.

Uses CTA Bus Tracker API for live stop data.
"""

import os
import re
import sys
from typing import List

import requests
from dotenv import load_dotenv
from pydantic import BaseModel

from server.schemas import RouteInput

load_dotenv()

CTA_DIRECTIONS_API_URL = "https://www.ctabustracker.com/bustime/api/v2/getdirections"
CTA_STOPS_API_URL = "https://www.ctabustracker.com/bustime/api/v2/getstops"
API_TIMEOUT = 10


class StopInfo(BaseModel):
    """Bus stop information."""
    stop_id: str
    name: str
    lat: float
    lon: float


def _extract_route_number(route_str: str) -> str:
    match = re.search(r"(\d+)", route_str)
    return match.group(1) if match else ""


def _get_directions(api_key: str, route_number: str) -> List[str]:
    response = requests.get(
        CTA_DIRECTIONS_API_URL,
        params={"key": api_key, "rt": route_number, "format": "json"},
        timeout=API_TIMEOUT,
    )

   
    
    print(f"[stops] getdirections URL: {response.url}", file=sys.stderr)
    print(f"[stops] getdirections status: {response.status_code}", file=sys.stderr)
    response.raise_for_status()

    # root = ET.fromstring(response.text)

    # # Debug
    # print(f"[stops] raw XML: {response.text}", file=sys.stderr)

    # # 🔍 check errors
    # error = root.find(".//error/msg")
    # if error is not None:
    #     raise RuntimeError(error.text)

    # # ✅ extract directions
    
    # directions = [d.text for d in root.findall(".//dir") if d.text]
    # print(f"[stops] directions extracted: {directions}", file=sys.stderr)

    # return directions

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"CTA directions API returned non-JSON response: {response.text[:300]}"
        ) from exc
    print(f"[stops] getdirections raw response: {data}", file=sys.stderr)

    bustime_response = data.get("bustime-response", {}) if isinstance(data, dict) else {}

    errors = data.get("error") if isinstance(data, dict) else None
    if not errors:
        errors = bustime_response.get("error")
    if errors:
        raise RuntimeError(errors[0].get("msg", "Unknown CTA directions error"))

    directions_data = bustime_response.get("directions") or []
    if not isinstance(directions_data, list):
        directions_data = [directions_data]

    return [str(item["dir"]) for item in directions_data if isinstance(item, dict) and item.get("dir")]


def _get_stops_for_direction(api_key: str, route_number: str, direction: str) -> List[dict]:
    response = requests.get(
        CTA_STOPS_API_URL,
        params={"key": api_key, "rt": route_number, "dir": direction, "format": "json"},
        timeout=API_TIMEOUT,
    )

    # headers = {
    # "Cache-Control": "no-cache",
    # "Pragma": "no-cache"
    # }

    # response = requests.get(
    # CTA_STOPS_API_URL,
    # params={"key": api_key, "rt": route_number, "dir": direction, "format": "json"},
    # headers=headers,
    # timeout=API_TIMEOUT,
    # )
    print(f"[stops] getstops URL: {response.url}", file=sys.stderr)
    print(f"[stops] getstops status: {response.status_code}", file=sys.stderr)
    response.raise_for_status()

    # root = ET.fromstring(response.text)

    # # Debug
    # print(f"[stops] raw XML: {response.text}", file=sys.stderr)

    # # 🔍 check errors
    # error = root.find(".//error/msg")
    # if error is not None:
    #     raise RuntimeError(error.text)

    # stops = []

    # for s in root.findall(".//stops"):
    #     stop_id = s.findtext("stpid")
    #     if not stop_id:
    #         continue  # skip invalid entries

    #     lat = s.findtext("lat")
    #     lon = s.findtext("lon")
    #     if not lat or not lon:
    #         continue  # skip bad coordinates

    #     stops.append({
    #         "stpid": stop_id.strip(),
    #         "stpnm": (s.findtext("stpnm") or "").strip(),
    #         "lat": float(lat),
    #         "lon": float(lon),
    #     })

    # return stops

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"CTA stops API returned non-JSON response ({direction}): {response.text[:300]}"
        ) from exc
    print(f"[stops] getstops raw response: {data}", file=sys.stderr)

    bustime_response = data.get("bustime-response", {}) if isinstance(data, dict) else {}

    errors = data.get("error") if isinstance(data, dict) else None
    if not errors:
        errors = bustime_response.get("error")
    if errors:
        raise RuntimeError(errors[0].get("msg", f"Unknown CTA stops error ({direction})"))

    stops_data = bustime_response.get("stops") or []
    if not isinstance(stops_data, list):
        stops_data = [stops_data]

    return [s for s in stops_data if isinstance(s, dict)]


def get_stops(route_input: RouteInput) -> List[StopInfo]:
    """Get all bus stops on a given route using CTA Bus Tracker API."""
    api_key = os.getenv("CTA_API_KEY")
    if not api_key:
        raise RuntimeError("CTA_API_KEY is not set")

    route_number = _extract_route_number(route_input.route)
    if not route_number:
        raise ValueError(f"Could not extract route number from '{route_input.route}'")

    directions = _get_directions(api_key, route_number)
    if not directions:
        raise RuntimeError(f"No directions found for route {route_number}")

    stop_infos: List[StopInfo] = []
    seen_ids: set = set()

    for direction in directions:
        for stop in _get_stops_for_direction(api_key, route_number, direction):
            stop_id = str(stop.get("stpid", "")).strip()
            if not stop_id or stop_id in seen_ids:
                continue
            lat, lon = stop.get("lat"), stop.get("lon")
            if lat is None or lon is None:
                continue
            stop_infos.append(StopInfo(
                stop_id=stop_id,
                name=str(stop.get("stpnm", "")).strip(),
                lat=float(lat),
                lon=float(lon),
            ))
            seen_ids.add(stop_id)

    print(f"[stops] {len(stop_infos)} stops returned for {route_input.route}", file=sys.stderr)
    return stop_infos
