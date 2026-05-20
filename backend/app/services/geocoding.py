"""Address geocoding — converts a free-text address/place into coordinates.

Uses the Google Geocoding API (`maps.googleapis.com`). This is a current,
supported API (unlike the legacy Places API) and shares the same key as the
Places integration. Keep this separate from `places.py`: geocoding answers
"where is this address?", Places answers "what restaurants are near here?".
"""
import logging
from dataclasses import dataclass

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


@dataclass
class GeocodeResult:
    lat: float
    lng: float
    formatted_address: str


async def geocode_address(address: str) -> GeocodeResult | None:
    """Resolve an address/place string to coordinates.

    Returns None if the address cannot be resolved (no match, or the API
    rejects the request) — callers should treat that as a 404, not a crash.
    """
    params = {"address": address, "key": settings.google_places_api_key}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(_GEOCODE_URL, params=params, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        logger.warning(f"Geocoding request failed for {address!r}: {e}")
        return None

    status = data.get("status")
    results = data.get("results") or []
    if status != "OK" or not results:
        # ZERO_RESULTS, REQUEST_DENIED, OVER_QUERY_LIMIT, etc.
        logger.info(f"Geocoding returned {status!r} for {address!r}")
        return None

    top = results[0]
    loc = top["geometry"]["location"]
    return GeocodeResult(
        lat=loc["lat"],
        lng=loc["lng"],
        formatted_address=top.get("formatted_address", address),
    )
