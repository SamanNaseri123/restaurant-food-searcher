from enum import Enum
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    AutocompleteResponse,
    RestaurantDetailResponse,
    SearchResponse,
)
from app.core.database import get_db
from app.services.geocoding import geocode_address
from app.services.search import SearchService

router = APIRouter(prefix="/api/v1", tags=["search"])


class SortBy(str, Enum):
    relevance = "relevance"   # Best menu match first (default)
    distance = "distance"     # Closest first
    rating = "rating"         # Highest rated first
    price_low = "price_low"   # Cheapest matched items first
    price_high = "price_high" # Most expensive matched items first


# Default search location — La Jolla, San Diego. The database currently only
# holds San Diego restaurants, so a search with no location defaults here
# instead of failing or returning nothing.
_DEFAULT_LAT = 32.8755
_DEFAULT_LNG = -117.2295


@router.get("/search", response_model=SearchResponse)
async def search_menu_items(
    q: str = Query(..., min_length=1, max_length=200, description="Food item to search for"),
    address: str | None = Query(
        default=None,
        max_length=300,
        description="Address or place to search near, e.g. 'La Jolla, CA'. "
        "Geocoded server-side; when given, it overrides lat/lng.",
    ),
    lat: float = Query(
        default=_DEFAULT_LAT, ge=-90, le=90,
        description="Latitude. Defaults to La Jolla, San Diego.",
    ),
    lng: float = Query(
        default=_DEFAULT_LNG, ge=-180, le=180,
        description="Longitude. Defaults to La Jolla, San Diego.",
    ),
    radius: int = Query(
        default=5000,
        ge=100,
        le=25000,
        description="Search radius in meters",
    ),
    sort: SortBy = Query(default=SortBy.relevance, description="Sort order for results"),
    limit: int = Query(default=20, ge=1, le=100, description="Max results to return"),
    db: AsyncSession = Depends(get_db),
):
    """Search menu items near a location.

    Location resolution: a free-text `address` (geocoded) if given, otherwise
    `lat`/`lng` — which default to La Jolla, San Diego. So the only required
    parameter is `q`.
    """
    if address:
        geo = await geocode_address(address)
        if geo is None:
            raise HTTPException(status_code=404, detail=f"Could not resolve address: {address!r}")
        lat, lng = geo.lat, geo.lng

    service = SearchService(db)
    return await service.search(
        query=q, lat=lat, lng=lng, radius_meters=radius,
        sort_by=sort.value, limit=limit,
    )


@router.get("/restaurants/{restaurant_id}", response_model=RestaurantDetailResponse)
async def get_restaurant(
    restaurant_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    service = SearchService(db)
    return await service.get_restaurant_detail(restaurant_id)


@router.get("/autocomplete", response_model=AutocompleteResponse)
async def autocomplete(
    q: str = Query(..., min_length=1, max_length=100),
    db: AsyncSession = Depends(get_db),
):
    service = SearchService(db)
    return await service.autocomplete(q)
