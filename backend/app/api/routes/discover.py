from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import DiscoverRequest
from app.core.database import get_db
from app.services.discovery import DiscoveryService

router = APIRouter(prefix="/api/v1", tags=["discovery"])


@router.post("/discover")
async def discover_restaurants(
    request: DiscoverRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    service = DiscoveryService(db)
    background_tasks.add_task(
        service.discover_and_scrape,
        lat=request.lat,
        lng=request.lng,
        radius_meters=request.radius_meters,
        food_type=request.food_type,
    )
    return {
        "status": "discovery_started",
        "message": "Restaurant discovery and menu scraping started in background",
    }
