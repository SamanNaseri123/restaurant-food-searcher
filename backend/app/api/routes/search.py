from enum import Enum
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    AutocompleteResponse,
    RestaurantDetailResponse,
    SearchResponse,
)
from app.core.config import settings
from app.core.database import get_db
from app.services.search import SearchService

router = APIRouter(prefix="/api/v1", tags=["search"])


class SortBy(str, Enum):
    relevance = "relevance"   # Best menu match first (default)
    distance = "distance"     # Closest first
    rating = "rating"         # Highest rated first
    price_low = "price_low"   # Cheapest matched items first
    price_high = "price_high" # Most expensive matched items first


@router.get("/search", response_model=SearchResponse)
async def search_menu_items(
    q: str = Query(..., min_length=1, max_length=200, description="Food item to search for"),
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
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
