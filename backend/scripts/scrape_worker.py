"""Standalone scraping worker — runs separately from the API server.

Discovers restaurants via Google Places and scrapes their menus directly,
bypassing the API server to avoid crashes under heavy load.

Usage:
    # Single location
    python scripts/scrape_worker.py --lat 32.7157 --lng -117.1611 --radius 3000

    # Metro grid (budget mode — free extraction only, no photos, core food types)
    python scripts/scrape_worker.py --grid new_york --free-only --monthly-budget 8000

    # Metro grid (full coverage — all methods, all food types, tight spacing)
    python scripts/scrape_worker.py --grid san_diego --spacing 2.5 --food-types all --include-photos

    # List available metros
    python scripts/scrape_worker.py --list-metros

    # Retry failed restaurants with LLM (after onboarding premium users)
    python scripts/scrape_worker.py --retry-failures --error-type free_only_skip

    # Dry-run: show failure counts without processing
    python scripts/scrape_worker.py --retry-failures --dry-run
"""
import argparse
import asyncio
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.db_bootstrap import ensure_extensions, ensure_search_trigger
from app.data.metro_grids import (
    FOOD_TYPES_CORE,
    FOOD_TYPES_FULL,
    METROS,
    generate_grid,
    get_metros_by_rank,
)
from app.models.restaurant import Base, MenuItem, Restaurant, ScrapeCheckpoint, ScrapeFailure
from app.services.places import PlacesService
from app.services.scraper.pipeline import ScrapingPipeline

from geoalchemy2.functions import ST_MakePoint, ST_SetSRID

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger(__name__)


async def _init_db(engine) -> None:
    """Create extensions, tables, and the menu search-vector trigger.

    Mirrors the API's startup bootstrap. Without the trigger, every menu item
    the worker inserts gets a NULL search_vector and search silently returns
    nothing — so the worker must set it up, not just call create_all().
    """
    async with engine.begin() as conn:
        await ensure_extensions(conn)
        await conn.run_sync(Base.metadata.create_all)
        await ensure_search_trigger(conn)

# --- San Diego hand-curated grid (kept for backwards compatibility) ---
# This is the original high-quality grid with named neighborhoods.
# For all other metros, grids are auto-generated from bounding boxes.

SD_GRID = [
    (32.7157, -117.1611, "Downtown"), (32.7220, -117.1630, "Little Italy"),
    (32.7185, -117.1530, "East Village"), (32.7145, -117.1700, "Harbor"),
    (32.7095, -117.1610, "Gaslamp"), (32.7250, -117.1530, "East Village N"),
    (32.7120, -117.1530, "East Village S"), (32.7180, -117.1450, "Sherman Heights"),
    (32.6990, -117.1490, "Barrio Logan"), (32.6920, -117.1430, "Logan Heights"),
    (32.7490, -117.1630, "Hillcrest"), (32.7440, -117.1520, "Hillcrest E"),
    (32.7475, -117.1290, "North Park"), (32.7410, -117.1290, "North Park S"),
    (32.7530, -117.1290, "North Park N"), (32.7500, -117.1100, "University Heights"),
    (32.7620, -117.1100, "Normal Heights"), (32.7600, -117.0980, "Kensington"),
    (32.7530, -117.1790, "Mission Hills"), (32.7535, -117.1970, "Old Town"),
    (32.7560, -117.2070, "Midway District"), (32.7280, -117.1340, "South Park"),
    (32.7200, -117.1380, "Golden Hill"), (32.7350, -117.1450, "Balboa Park S"),
    (32.7300, -117.1550, "Bankers Hill"), (32.7680, -117.1560, "Mission Valley"),
    (32.7650, -117.1700, "Fashion Valley"), (32.7720, -117.1420, "Mission Valley E"),
    (32.7600, -117.1800, "Linda Vista S"), (32.7470, -117.2490, "Ocean Beach"),
    (32.7400, -117.2450, "Ocean Beach S"), (32.7330, -117.2410, "Point Loma"),
    (32.7190, -117.2320, "Shelter Island"), (32.7260, -117.2260, "Point Loma Village"),
    (32.7945, -117.2535, "Pacific Beach"), (32.7850, -117.2500, "Pacific Beach S"),
    (32.8020, -117.2530, "Pacific Beach N"), (32.7700, -117.2520, "Mission Beach"),
    (32.8425, -117.2720, "La Jolla"), (32.8350, -117.2710, "La Jolla S"),
    (32.8500, -117.2700, "La Jolla N"), (32.8530, -117.2590, "La Jolla UTC"),
    (32.8620, -117.2520, "La Jolla Colony"), (32.8710, -117.2330, "University City"),
    (32.8780, -117.2230, "University City N"), (32.8650, -117.2130, "Governor Dr"),
    (32.8100, -117.2050, "Clairemont"), (32.8180, -117.2130, "Clairemont Mesa W"),
    (32.8200, -117.1900, "Clairemont Mesa E"), (32.8050, -117.1850, "Clairemont S"),
    (32.8180, -117.1570, "Kearny Mesa"), (32.8250, -117.1570, "Kearny Mesa N"),
    (32.8120, -117.1430, "Kearny Mesa E"), (32.8350, -117.1500, "Convoy District"),
    (32.8400, -117.1400, "Convoy E"), (32.7900, -117.1800, "Linda Vista"),
    (32.7950, -117.1950, "Bay Ho"), (32.7850, -117.2100, "Bay Park"),
    (32.7780, -117.2050, "Morena"), (32.8680, -117.1540, "Mira Mesa"),
    (32.8750, -117.1700, "Mira Mesa W"), (32.8600, -117.1400, "Mira Mesa S"),
    (32.8950, -117.1080, "Scripps Ranch"), (32.8900, -117.1300, "Scripps Ranch W"),
    (32.9050, -117.0950, "Scripps Ranch N"), (33.0150, -117.0870, "Rancho Bernardo"),
    (33.0050, -117.1050, "Rancho Bernardo W"), (32.9800, -117.0700, "Rancho Penasquitos"),
    (32.9625, -117.0360, "Poway"), (32.9550, -117.0550, "Poway W"),
    (32.9450, -117.0700, "Sabre Springs"), (32.9595, -117.2655, "Del Mar"),
    (32.9500, -117.2600, "Del Mar Heights"), (32.9400, -117.2300, "Carmel Valley"),
    (32.9350, -117.2450, "Carmel Valley W"), (32.9210, -117.2100, "Sorrento Valley"),
    (32.9130, -117.2250, "Torrey Hills"), (33.0370, -117.2920, "Encinitas"),
    (33.0200, -117.2850, "Encinitas S"), (33.0550, -117.2900, "Leucadia"),
    (33.0750, -117.3050, "Carlsbad S"), (33.0990, -117.3190, "Carlsbad"),
    (33.1200, -117.3250, "Carlsbad N"), (33.0800, -117.2700, "Carlsbad E"),
    (33.1300, -117.3100, "Carlsbad Village"), (32.9910, -117.2710, "Solana Beach"),
    (33.0050, -117.2200, "Rancho Santa Fe"), (32.6401, -117.0842, "Chula Vista"),
    (32.6300, -117.0650, "Chula Vista S"), (32.6500, -117.0600, "Chula Vista E"),
    (32.6700, -117.0900, "Chula Vista N"), (32.6200, -117.1000, "Chula Vista W"),
    (32.6600, -117.0950, "National City"), (32.6650, -117.1100, "National City W"),
    (32.6170, -117.0490, "Chula Vista East"), (32.5840, -117.1130, "Imperial Beach"),
    (32.5470, -117.0420, "San Ysidro"), (32.5550, -117.0700, "Otay Mesa"),
    (32.5700, -117.0250, "Otay Mesa E"), (32.7948, -116.9625, "El Cajon"),
    (32.7850, -116.9800, "El Cajon W"), (32.8050, -116.9500, "El Cajon N"),
    (32.7678, -117.0231, "La Mesa"), (32.7750, -117.0100, "La Mesa N"),
    (32.7600, -117.0350, "La Mesa W"), (32.8384, -116.9739, "Santee"),
    (32.8500, -116.9550, "Santee N"), (32.8250, -116.9900, "Santee W"),
    (32.7500, -116.9500, "Spring Valley"), (32.7350, -116.9700, "Spring Valley W"),
    (32.6900, -116.9700, "Bonita"), (32.8100, -117.0880, "Tierrasanta"),
    (32.8000, -117.0700, "Tierrasanta S"), (32.7700, -117.0750, "Allied Gardens"),
    (32.7750, -117.0550, "College Area"), (32.7650, -117.0600, "College Area S"),
    (32.7550, -117.1000, "City Heights"), (32.7450, -117.1050, "City Heights W"),
    (32.7400, -117.0800, "City Heights E"), (32.7300, -117.0900, "Chollas Creek"),
    (32.6859, -117.1831, "Coronado"), (32.6780, -117.1750, "Coronado S"),
    (33.1190, -117.0860, "Escondido"), (33.1300, -117.1050, "Escondido W"),
    (33.1100, -117.0650, "Escondido E"), (33.1430, -117.1660, "San Marcos"),
    (33.1350, -117.1900, "San Marcos W"), (33.1960, -117.3790, "Oceanside"),
    (33.1850, -117.3500, "Oceanside E"), (33.2000, -117.3400, "Oceanside N"),
    (33.2100, -117.3250, "Camp Pendleton Gate"), (33.2000, -117.2430, "Vista"),
    (33.1850, -117.2600, "Vista W"), (32.7430, -117.0300, "Lemon Grove"),
    (32.7200, -117.0500, "Encanto"), (32.7050, -117.0700, "Paradise Hills"),
    (32.7150, -117.0200, "Valencia Park"), (32.9700, -117.0100, "Poway E"),
    (33.0250, -117.0650, "Rancho Bernardo E"), (33.0400, -117.1000, "4S Ranch"),
    (32.9900, -117.0400, "Poway N"),
]

# Bump this when extraction methods are improved. Failures logged with an older
# version will be auto-retried on the next grid run. Do NOT bump for pipeline
# logistics changes (caching, error handling, etc.) — only for extraction improvements.
#
# Changelog:
#   1 - Initial extractors (structured data, platform, pattern, heuristic, LLM)
#   2 - Added PDF extractor, image menu extractor, link discovery, vision OCR,
#       bare price matching, external menu platform links, 2-level crawl
#   3 - Location URL construction for multi-location ordering platforms (Toast etc),
#       LLM tries richest page first, no browser on 404, lighter fallback fetching
#   4 - Wayback Machine fallback for bot-blocked sites, JSON/script URL pattern scanning
#       for *-menu and /menu/* paths, LLM capped at 3 pages per restaurant
EXTRACTOR_VERSION = 4


def _classify_failure(result, url: str) -> str:
    """Classify why scraping failed for future retry prioritization."""
    if result.extraction_method == "free_exhausted":
        return "free_only_skip"
    if result.platform_type == "unknown":
        return "bot_blocked"
    if result.platform_type == "custom" and result.extraction_method == "none":
        return "js_spa_empty"
    return "extraction_fail"


def get_grid(metro_name: str, spacing_km: float | None = None) -> list[tuple[float, float, str]]:
    """Get grid points for a metro. Uses hand-curated grid for San Diego,
    auto-generated from bounding box for all others."""
    if metro_name == "san_diego" and spacing_km is None:
        return SD_GRID

    metro = METROS.get(metro_name)
    if not metro:
        available = ", ".join(sorted(METROS.keys()))
        raise ValueError(f"Unknown metro: {metro_name}. Available: {available}")

    return generate_grid(metro, spacing_km=spacing_km)


# --- Checkpoint helpers ---

async def _load_checkpoint(db, metro_name: str) -> ScrapeCheckpoint | None:
    result = await db.execute(
        select(ScrapeCheckpoint).where(ScrapeCheckpoint.metro_name == metro_name)
    )
    return result.scalar_one_or_none()


async def _save_checkpoint(db, metro_name: str, grid_idx: int, food_idx: int,
                           total_grid: int, total_food: int, searches: int, free_only: bool):
    existing = await _load_checkpoint(db, metro_name)
    if existing:
        existing.grid_index = grid_idx
        existing.food_type_index = food_idx
        existing.searches_this_run = searches
        existing.updated_at = datetime.now(timezone.utc)
    else:
        db.add(ScrapeCheckpoint(
            metro_name=metro_name,
            grid_index=grid_idx,
            food_type_index=food_idx,
            total_grid_points=total_grid,
            total_food_types=total_food,
            searches_this_run=searches,
            free_only=1 if free_only else 0,
        ))
    await db.commit()


async def _mark_complete(db, metro_name: str):
    existing = await _load_checkpoint(db, metro_name)
    if existing:
        existing.completed_at = datetime.now(timezone.utc)
        await db.commit()


async def _reset_checkpoint(db, metro_name: str):
    await db.execute(
        delete(ScrapeCheckpoint).where(ScrapeCheckpoint.metro_name == metro_name)
    )
    await db.commit()


# --- Core scraping functions ---

async def discover_and_scrape(
    lat: float, lng: float, radius_meters: int,
    food_type: str | None, label: str,
    session_factory: async_sessionmaker,
    places: PlacesService,
    semaphore: asyncio.Semaphore,
    stats: dict,
    free_only: bool = False,
):
    """Discover restaurants at one location and scrape their menus."""
    async with session_factory() as db:
        try:
            place_results = await places.search_nearby_restaurants(
                lat=lat, lng=lng, radius_meters=radius_meters, food_type=food_type,
            )
        except Exception as e:
            logger.error(f"[{label}] Places API failed: {e}")
            stats["places_errors"] += 1
            return

        stats["places_calls"] += 1
        new_restaurants = 0

        for place in place_results:
            existing = await db.execute(
                select(Restaurant).where(Restaurant.google_place_id == place.place_id)
            )
            restaurant = existing.scalar_one_or_none()

            if restaurant:
                if restaurant.menu_last_scraped_at:
                    age = datetime.now(timezone.utc) - restaurant.menu_last_scraped_at
                    if age < timedelta(days=settings.menu_cache_days):
                        continue

                failure_check = await db.execute(
                    select(ScrapeFailure).where(
                        ScrapeFailure.restaurant_id == restaurant.id,
                        ScrapeFailure.resolved == 0,
                        ScrapeFailure.extractor_version >= EXTRACTOR_VERSION,
                    )
                )
                if failure_check.scalar_one_or_none():
                    continue
            else:
                restaurant = Restaurant(
                    google_place_id=place.place_id,
                    name=place.name,
                    address=place.address,
                    location=ST_SetSRID(ST_MakePoint(place.lng, place.lat), 4326),
                    website_url=place.website_url,
                    phone=place.phone,
                    rating=place.rating,
                    price_level=place.price_level,
                    photos=place.photos,
                )
                db.add(restaurant)
                await db.flush()
                new_restaurants += 1

            if place.website_url:
                async with semaphore:
                    await _scrape_restaurant(db, restaurant, place.website_url, stats, free_only)

        await db.commit()
        stats["new_restaurants"] += new_restaurants
        logger.info(f"[{label}] +{new_restaurants} new, {len(place_results)} from Places")


async def _log_failure(db, restaurant, url, error_type, error_detail, platform=None):
    """Log a scrape failure for future retry."""
    existing = await db.execute(
        select(ScrapeFailure).where(
            ScrapeFailure.restaurant_id == restaurant.id,
            ScrapeFailure.resolved == 0,
        )
    )
    failure = existing.scalar_one_or_none()

    if failure:
        failure.error_type = error_type
        failure.error_detail = error_detail[:1000] if error_detail else None
        failure.platform_type = platform
        failure.attempts += 1
        failure.last_attempt_at = datetime.now(timezone.utc)
        failure.extractor_version = EXTRACTOR_VERSION
    else:
        db.add(ScrapeFailure(
            restaurant_id=restaurant.id,
            website_url=url,
            error_type=error_type,
            error_detail=error_detail[:1000] if error_detail else None,
            platform_type=platform,
            extractor_version=EXTRACTOR_VERSION,
        ))
    await db.flush()


async def _scrape_restaurant(db, restaurant, url, stats, free_only=False):
    """Scrape one restaurant's menu."""
    pipeline = ScrapingPipeline(db, free_only=free_only)

    try:
        result = await asyncio.wait_for(pipeline.scrape_menu(url), timeout=120)
    except asyncio.TimeoutError:
        logger.warning(f"Scraping timed out for {url}")
        stats["scrape_timeouts"] += 1
        await _log_failure(db, restaurant, url, "timeout", "Scraping timed out after 120s")
        return
    except Exception as e:
        logger.warning(f"Scraping failed for {url}: {e}")
        stats["scrape_errors"] += 1
        await _log_failure(db, restaurant, url, "exception", str(e))
        return

    if not result.items:
        stats["no_menu"] += 1
        error_type = _classify_failure(result, url)
        await _log_failure(db, restaurant, url, error_type, f"platform={result.platform_type}", result.platform_type)
        return

    # Success
    await db.execute(
        update(ScrapeFailure)
        .where(ScrapeFailure.restaurant_id == restaurant.id, ScrapeFailure.resolved == 0)
        .values(resolved=1)
    )

    stats[f"method_{result.extraction_method}"] = stats.get(f"method_{result.extraction_method}", 0) + 1
    restaurant.platform_type = result.platform_type
    restaurant.menu_last_scraped_at = datetime.now(timezone.utc)

    await db.execute(delete(MenuItem).where(MenuItem.restaurant_id == restaurant.id))
    for item_data in result.items:
        db.add(MenuItem(
            restaurant_id=restaurant.id,
            name=item_data["name"],
            description=item_data.get("description"),
            price=item_data.get("price"),
            category=item_data.get("category"),
        ))

    await db.commit()
    stats["menus_scraped"] += 1
    stats["items_scraped"] += len(result.items)
    logger.info(f"  [{result.extraction_method}] {restaurant.name}: {len(result.items)} items")


# --- Grid runner ---

async def run_grid(
    grid_name: str,
    food_types: list,
    radius: int,
    concurrency: int,
    free_only: bool = False,
    include_photos: bool = True,
    monthly_budget: int | None = None,
    spacing_km: float | None = None,
    reset_checkpoint: bool = False,
):
    """Run discovery across a grid of locations with checkpoint/resume."""
    grid = get_grid(grid_name, spacing_km=spacing_km)

    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    await _init_db(engine)

    # Handle checkpoint
    async with session_factory() as db:
        if reset_checkpoint:
            await _reset_checkpoint(db, grid_name)
            logger.info(f"Checkpoint reset for {grid_name}")

        checkpoint = await _load_checkpoint(db, grid_name)

    start_gi = 0
    start_fi = 0
    searches_done = 0
    if checkpoint and not checkpoint.completed_at:
        start_gi = checkpoint.grid_index
        start_fi = checkpoint.food_type_index
        searches_done = checkpoint.searches_this_run or 0
        logger.info(f"Resuming {grid_name} from grid[{start_gi}] food[{start_fi}] ({searches_done} searches done)")

    places = PlacesService(include_photos=include_photos)
    semaphore = asyncio.Semaphore(concurrency)

    total_searches = len(grid) * len(food_types)
    stats = {
        "places_calls": 0, "places_errors": 0,
        "new_restaurants": 0, "menus_scraped": 0,
        "items_scraped": 0, "no_menu": 0,
        "scrape_errors": 0, "scrape_timeouts": 0,
    }

    mode = "FREE-ONLY" if free_only else "FULL"
    logger.info(
        f"Starting {grid_name} [{mode}]: {len(grid)} points x {len(food_types)} food types = {total_searches} searches"
        + (f" (budget: {monthly_budget})" if monthly_budget else "")
    )
    start_time = time.time()

    completed = searches_done
    for gi, (lat, lng, name) in enumerate(grid):
        if gi < start_gi:
            continue
        for fi, food_type in enumerate(food_types):
            if gi == start_gi and fi < start_fi:
                continue

            # Budget check
            if monthly_budget and stats["places_calls"] >= monthly_budget:
                logger.info(f"Monthly budget reached ({monthly_budget} searches). Stopping.")
                async with session_factory() as db:
                    await _save_checkpoint(db, grid_name, gi, fi, len(grid), len(food_types), completed, free_only)
                await engine.dispose()
                return

            label = f"{name}/{food_type or 'all'}"
            await discover_and_scrape(
                lat, lng, radius, food_type, label,
                session_factory, places, semaphore, stats, free_only,
            )
            completed += 1

            # Save checkpoint every 5 searches
            if completed % 5 == 0:
                async with session_factory() as db:
                    await _save_checkpoint(db, grid_name, gi, fi + 1, len(grid), len(food_types), completed, free_only)

            if completed % 10 == 0:
                elapsed = time.time() - start_time
                rate = stats["places_calls"] / elapsed * 3600 if elapsed > 0 else 0
                logger.info(
                    f"\n--- Progress: {completed}/{total_searches} ({completed/total_searches*100:.1f}%) "
                    f"| {rate:.0f} searches/hr ---\n"
                    f"  Restaurants: {stats['new_restaurants']} new | "
                    f"Menus: {stats['menus_scraped']} scraped, {stats['items_scraped']} items\n"
                    f"  Methods: {', '.join(f'{k}={v}' for k, v in stats.items() if k.startswith('method_'))}\n"
                    f"  Errors: {stats['places_errors']} places, {stats['scrape_errors']} scrape, "
                    f"{stats['scrape_timeouts']} timeout, {stats['no_menu']} no menu"
                )

    # Mark complete
    async with session_factory() as db:
        await _save_checkpoint(db, grid_name, len(grid), 0, len(grid), len(food_types), completed, free_only)
        await _mark_complete(db, grid_name)

    elapsed = time.time() - start_time
    logger.info(
        f"\n{'='*60}\n"
        f"DISCOVERY COMPLETE: {grid_name}\n"
        f"{'='*60}\n"
        f"  Time: {elapsed/60:.1f} minutes\n"
        f"  Places API calls: {stats['places_calls']}\n"
        f"  New restaurants: {stats['new_restaurants']}\n"
        f"  Menus scraped: {stats['menus_scraped']}\n"
        f"  Total menu items: {stats['items_scraped']}\n"
        f"  Extraction methods: {', '.join(f'{k}={v}' for k, v in stats.items() if k.startswith('method_'))}\n"
        f"  Errors: {stats['places_errors']} places, {stats['scrape_errors']} scrape, "
        f"{stats['scrape_timeouts']} timeout, {stats['no_menu']} no menu\n"
        f"{'='*60}"
    )
    await engine.dispose()


# --- Single location ---

async def run_single(lat, lng, radius, food_type, concurrency, free_only=False, include_photos=True):
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    await _init_db(engine)

    places = PlacesService(include_photos=include_photos)
    semaphore = asyncio.Semaphore(concurrency)
    stats = {
        "places_calls": 0, "places_errors": 0,
        "new_restaurants": 0, "menus_scraped": 0,
        "items_scraped": 0, "no_menu": 0,
        "scrape_errors": 0, "scrape_timeouts": 0,
    }
    await discover_and_scrape(
        lat, lng, radius, food_type, f"{lat},{lng}",
        session_factory, places, semaphore, stats, free_only,
    )
    logger.info(f"Done: {stats['new_restaurants']} restaurants, {stats['items_scraped']} menu items")
    await engine.dispose()


# --- Retry failures ---

async def run_retry_failures(error_type, concurrency, dry_run=False):
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    await _init_db(engine)

    async with session_factory() as db:
        query = select(ScrapeFailure, Restaurant).join(
            Restaurant, ScrapeFailure.restaurant_id == Restaurant.id
        ).where(ScrapeFailure.resolved == 0)
        if error_type:
            query = query.where(ScrapeFailure.error_type == error_type)
        result = await db.execute(query)
        failures = result.all()

        logger.info(f"Found {len(failures)} failed restaurants" + (f" (type={error_type})" if error_type else ""))
        from collections import Counter
        type_counts = Counter(f.error_type for f, _ in failures)
        for t, c in type_counts.most_common():
            logger.info(f"  {t}: {c}")

    if dry_run:
        logger.info("Dry run — not processing.")
        await engine.dispose()
        return

    semaphore = asyncio.Semaphore(concurrency)
    stats = {
        "places_calls": 0, "places_errors": 0,
        "new_restaurants": 0, "menus_scraped": 0,
        "items_scraped": 0, "no_menu": 0,
        "scrape_errors": 0, "scrape_timeouts": 0,
    }

    for failure, restaurant in failures:
        async with session_factory() as db:
            r = await db.execute(select(Restaurant).where(Restaurant.id == restaurant.id))
            rest = r.scalar_one_or_none()
            if rest and failure.website_url:
                async with semaphore:
                    await _scrape_restaurant(db, rest, failure.website_url, stats)

    logger.info(
        f"Retry complete: {stats['menus_scraped']} newly scraped, "
        f"{stats['items_scraped']} items, {stats['no_menu']} still failing"
    )
    await engine.dispose()


# --- List metros ---

def list_metros():
    print(f"\n{'Metro':<25} {'Rank':>4} {'Grid pts (5km)':>14} {'Searches (core)':>16} {'Searches (full)':>16}")
    print("-" * 80)
    for metro in get_metros_by_rank(1, 50):
        grid = generate_grid(metro, spacing_km=5.0)
        core = len(grid) * len(FOOD_TYPES_CORE)
        full = len(grid) * len(FOOD_TYPES_FULL)
        print(f"{metro.display_name:<25} {metro.rank:>4} {len(grid):>14} {core:>16} {full:>16}")

    # San Diego hand-curated
    core = len(SD_GRID) * len(FOOD_TYPES_CORE)
    full = len(SD_GRID) * len(FOOD_TYPES_FULL)
    print(f"{'San Diego (curated)':<25} {'17':>4} {len(SD_GRID):>14} {core:>16} {full:>16}")
    print()
    total_core = sum(len(generate_grid(m, 5.0)) * len(FOOD_TYPES_CORE) for m in METROS.values())
    print(f"Total core searches across all metros: {total_core}")
    print(f"At free tier (8,000/month): ~{total_core // 8000 + 1} months")


# --- CLI ---

def main():
    parser = argparse.ArgumentParser(
        description="Restaurant discovery & menu scraping worker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Budget mode (free extraction, no photos, core food types)
  %(prog)s --grid new_york --free-only --monthly-budget 8000

  # Full coverage for a metro
  %(prog)s --grid san_diego --spacing 2.5 --food-types all --include-photos

  # Single location
  %(prog)s --lat 32.8755 --lng -117.2295 --radius 5000

  # List available metros
  %(prog)s --list-metros

  # Retry failed restaurants with LLM
  %(prog)s --retry-failures --error-type free_only_skip

  # Preview retry counts
  %(prog)s --retry-failures --dry-run
        """,
    )

    # Mode selection
    parser.add_argument("--grid", type=str, help="Metro name (e.g. new_york, san_diego)")
    parser.add_argument("--lat", type=float, help="Latitude for single-point search")
    parser.add_argument("--lng", type=float, help="Longitude for single-point search")
    parser.add_argument("--retry-failures", action="store_true", help="Retry previously failed restaurants")
    parser.add_argument("--list-metros", action="store_true", help="List available metros and exit")

    # Grid options
    parser.add_argument("--spacing", type=float, default=None, help="Grid spacing in km (default: 5km budget, 3km full)")
    parser.add_argument("--radius", type=int, default=5000, help="Search radius in meters (default: 5000)")
    parser.add_argument("--food-types", type=str, default="core",
                       help="'core' (12 types, default), 'all' (34 types), or a single type name")

    # Cost controls
    parser.add_argument("--free-only", action="store_true", help="Skip LLM/vision, use free extraction only")
    parser.add_argument("--include-photos", action="store_true", help="Include photos in Places API (costs more)")
    parser.add_argument("--monthly-budget", type=int, default=None,
                       help="Max Google Places searches before stopping (free tier = 8000)")

    # Resume/retry
    parser.add_argument("--concurrency", type=int, default=3, help="Max concurrent scrapes")
    parser.add_argument("--error-type", type=str, default=None, help="Filter retry by error type")
    parser.add_argument("--dry-run", action="store_true", help="Show counts without processing")
    parser.add_argument("--reset-checkpoint", action="store_true", help="Clear checkpoint and start metro from scratch")

    args = parser.parse_args()

    if args.list_metros:
        list_metros()
        return

    if args.retry_failures:
        asyncio.run(run_retry_failures(args.error_type, args.concurrency, args.dry_run))
        return

    # Resolve food types
    if args.food_types == "core":
        food_types = FOOD_TYPES_CORE
    elif args.food_types == "all":
        food_types = FOOD_TYPES_FULL
    else:
        food_types = [args.food_types if args.food_types != "none" else None]

    if args.grid:
        asyncio.run(run_grid(
            args.grid, food_types, args.radius, args.concurrency,
            free_only=args.free_only,
            include_photos=args.include_photos,
            monthly_budget=args.monthly_budget,
            spacing_km=args.spacing,
            reset_checkpoint=args.reset_checkpoint,
        ))
    elif args.lat and args.lng:
        asyncio.run(run_single(
            args.lat, args.lng, args.radius,
            food_types[0] if len(food_types) == 1 else None,
            args.concurrency, args.free_only, args.include_photos,
        ))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
