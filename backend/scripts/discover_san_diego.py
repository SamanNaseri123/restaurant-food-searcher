"""Systematically discover all restaurants in San Diego.

Covers the city with overlapping searches across neighborhoods and food types.
Google Places returns max 20 per search, so we use multiple grid points + food types.
"""
import asyncio
import logging
import sys
import time

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

API_BASE = "http://127.0.0.1:8000/api/v1"

# San Diego neighborhoods with approximate centers
# Grid covers ~400 sq miles of metro area
SD_GRID = [
    # Downtown / Core
    (32.7157, -117.1611, "Downtown"),
    (32.7220, -117.1630, "Little Italy"),
    (32.7185, -117.1530, "East Village"),
    (32.7145, -117.1700, "Harbor"),
    # Gaslamp / Barrio Logan
    (32.7095, -117.1610, "Gaslamp"),
    (32.6990, -117.1490, "Barrio Logan"),
    # Hillcrest / North Park / University Heights
    (32.7490, -117.1630, "Hillcrest"),
    (32.7475, -117.1290, "North Park"),
    (32.7500, -117.1100, "University Heights"),
    # Normal Heights / Kensington
    (32.7620, -117.1100, "Normal Heights"),
    (32.7600, -117.0980, "Kensington"),
    # Mission Hills / Old Town
    (32.7530, -117.1790, "Mission Hills"),
    (32.7535, -117.1970, "Old Town"),
    # Mission Valley / Fashion Valley
    (32.7680, -117.1560, "Mission Valley"),
    (32.7650, -117.1700, "Fashion Valley"),
    # Ocean Beach / Point Loma
    (32.7470, -117.2490, "Ocean Beach"),
    (32.7330, -117.2410, "Point Loma"),
    (32.7190, -117.2320, "Shelter Island"),
    # Pacific Beach / Mission Beach
    (32.7945, -117.2535, "Pacific Beach"),
    (32.7700, -117.2520, "Mission Beach"),
    # La Jolla
    (32.8425, -117.2720, "La Jolla"),
    (32.8530, -117.2590, "La Jolla UTC"),
    (32.8710, -117.2330, "University City"),
    # Clairemont / Kearny Mesa
    (32.8100, -117.2050, "Clairemont"),
    (32.8180, -117.1570, "Kearny Mesa"),
    (32.8350, -117.1500, "Convoy District"),
    # Mira Mesa / Scripps Ranch
    (32.8680, -117.1540, "Mira Mesa"),
    (32.8950, -117.1080, "Scripps Ranch"),
    # Rancho Bernardo / Poway
    (33.0150, -117.0870, "Rancho Bernardo"),
    (32.9625, -117.0360, "Poway"),
    # Del Mar / Carmel Valley
    (32.9595, -117.2655, "Del Mar"),
    (32.9400, -117.2300, "Carmel Valley"),
    (32.9210, -117.2100, "Sorrento Valley"),
    # Chula Vista / National City
    (32.6401, -117.0842, "Chula Vista"),
    (32.6600, -117.0950, "National City"),
    (32.6170, -117.0490, "Chula Vista East"),
    # Encinitas / Carlsbad (north county)
    (33.0370, -117.2920, "Encinitas"),
    (33.0990, -117.3190, "Carlsbad"),
    # El Cajon / La Mesa / Santee
    (32.7948, -116.9625, "El Cajon"),
    (32.7678, -117.0231, "La Mesa"),
    (32.8384, -116.9739, "Santee"),
    # Coronado
    (32.6859, -117.1831, "Coronado"),
    # Imperial Beach / San Ysidro
    (32.5840, -117.1130, "Imperial Beach"),
    (32.5470, -117.0420, "San Ysidro"),
    # Tierrasanta / Allied Gardens
    (32.8100, -117.0880, "Tierrasanta"),
    (32.7700, -117.0750, "Allied Gardens"),
    # South Park / Golden Hill
    (32.7280, -117.1340, "South Park"),
    (32.7200, -117.1380, "Golden Hill"),
]

# Food types to search (increases coverage per location)
FOOD_TYPES = [
    None,           # Generic "restaurants"
    "mexican",
    "italian",
    "chinese",
    "japanese",
    "thai",
    "indian",
    "korean",
    "vietnamese",
    "american",
    "seafood",
    "pizza",
    "burger",
    "sushi",
    "bbq",
    "mediterranean",
    "breakfast",
    "cafe",
]


async def discover_batch(client: httpx.AsyncClient, lat: float, lng: float, food_type: str | None, name: str):
    """Trigger discovery for one location + food type."""
    body = {"lat": lat, "lng": lng, "radius_meters": 3000}
    if food_type:
        body["food_type"] = food_type

    try:
        resp = await client.post(f"{API_BASE}/discover", json=body, timeout=10.0)
        resp.raise_for_status()
        label = f"{name} ({food_type or 'all'})"
        logger.info(f"Started: {label}")
    except Exception as e:
        logger.error(f"Failed to start {name} ({food_type}): {e}")


async def run_discovery():
    total_searches = len(SD_GRID) * len(FOOD_TYPES)
    logger.info(f"Starting San Diego discovery: {len(SD_GRID)} locations x {len(FOOD_TYPES)} food types = {total_searches} searches")
    logger.info("Each search returns up to 20 restaurants. Running sequentially to avoid overloading the server.")

    async with httpx.AsyncClient() as client:
        # Check server is up
        try:
            resp = await client.get("http://127.0.0.1:8000/health", timeout=5.0)
            resp.raise_for_status()
        except Exception:
            logger.error("Server not running on port 8000! Start it first.")
            sys.exit(1)

        completed = 0
        start_time = time.time()

        for lat, lng, name in SD_GRID:
            for food_type in FOOD_TYPES:
                await discover_batch(client, lat, lng, food_type, name)
                completed += 1

                # Small delay to avoid hammering Google Places API rate limits
                # Scraping runs in the background on the server
                await asyncio.sleep(3)

                if completed % 20 == 0:
                    elapsed = time.time() - start_time
                    rate = completed / elapsed * 3600
                    logger.info(
                        f"Progress: {completed}/{total_searches} ({completed/total_searches*100:.1f}%) "
                        f"- {rate:.0f} searches/hr"
                    )
                    # Every 20 searches, pause a bit longer to let scraping catch up
                    await asyncio.sleep(15)

    elapsed = time.time() - start_time
    logger.info(f"Discovery complete! {completed} searches in {elapsed/60:.1f} minutes")


if __name__ == "__main__":
    asyncio.run(run_discovery())
