import asyncio
import logging
from datetime import datetime, timedelta, timezone

from geoalchemy2.functions import ST_MakePoint, ST_SetSRID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.restaurant import MenuItem, Restaurant
from app.services.places import PlacesService
from app.services.scraper.pipeline import ScrapingPipeline

logger = logging.getLogger(__name__)


class DiscoveryService:
    """Discovers restaurants via Google Places and scrapes their menus."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.places = PlacesService()
        self.pipeline = ScrapingPipeline(db)

    async def discover_and_scrape(
        self,
        lat: float,
        lng: float,
        radius_meters: int = 5000,
        food_type: str | None = None,
    ) -> int:
        """Discover restaurants and scrape menus. Returns count of new restaurants."""
        # Step 1: Find restaurants via Google Places
        places = await self.places.search_nearby_restaurants(
            lat=lat, lng=lng, radius_meters=radius_meters, food_type=food_type
        )
        logger.info(f"Found {len(places)} restaurants from Google Places")

        new_count = 0
        scrape_tasks = []

        for place in places:
            # Check if already in DB
            existing = await self.db.execute(
                select(Restaurant).where(
                    Restaurant.google_place_id == place.place_id
                )
            )
            restaurant = existing.scalar_one_or_none()

            if restaurant:
                # Check if menu needs refresh
                if self._menu_is_fresh(restaurant):
                    continue
            else:
                # Create new restaurant
                restaurant = Restaurant(
                    google_place_id=place.place_id,
                    name=place.name,
                    address=place.address,
                    location=ST_SetSRID(
                        ST_MakePoint(place.lng, place.lat), 4326
                    ),
                    website_url=place.website_url,
                    phone=place.phone,
                    rating=place.rating,
                    price_level=place.price_level,
                    photos=place.photos,
                )
                self.db.add(restaurant)
                await self.db.flush()
                new_count += 1

            # Queue for scraping if has website
            if place.website_url:
                scrape_tasks.append((restaurant, place.website_url))

        await self.db.commit()

        # Step 2: Scrape menus concurrently (limited concurrency)
        semaphore = asyncio.Semaphore(settings.max_concurrent_scrapes)

        async def scrape_one(restaurant: Restaurant, url: str):
            async with semaphore:
                await self._scrape_and_save(restaurant, url)

        await asyncio.gather(
            *[scrape_one(r, url) for r, url in scrape_tasks],
            return_exceptions=True,
        )

        logger.info(
            f"Discovery complete: {new_count} new restaurants, "
            f"{len(scrape_tasks)} menus scraped"
        )
        return new_count

    async def _scrape_and_save(self, restaurant: Restaurant, url: str) -> None:
        """Scrape a restaurant's menu and save items to DB."""
        result = await self.pipeline.scrape_menu(url)

        if not result.items:
            return

        # Update restaurant platform type
        restaurant.platform_type = result.platform_type
        restaurant.menu_last_scraped_at = datetime.now(timezone.utc)

        # Clear old menu items and add new ones
        await self.db.execute(
            select(MenuItem)
            .where(MenuItem.restaurant_id == restaurant.id)
        )

        # Delete existing items
        from sqlalchemy import delete
        await self.db.execute(
            delete(MenuItem).where(MenuItem.restaurant_id == restaurant.id)
        )

        # Add new items
        for item_data in result.items:
            menu_item = MenuItem(
                restaurant_id=restaurant.id,
                name=item_data["name"],
                description=item_data.get("description"),
                price=item_data.get("price"),
                category=item_data.get("category"),
            )
            self.db.add(menu_item)

        await self.db.commit()
        logger.info(
            f"Saved {len(result.items)} menu items for '{restaurant.name}' "
            f"(pattern: {result.used_pattern})"
        )

    @staticmethod
    def _menu_is_fresh(restaurant: Restaurant) -> bool:
        if not restaurant.menu_last_scraped_at:
            return False
        age = datetime.now(timezone.utc) - restaurant.menu_last_scraped_at
        return age < timedelta(days=settings.menu_cache_days)
