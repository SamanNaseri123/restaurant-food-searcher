"""US metro area definitions and grid generation for restaurant discovery.

Each metro is defined by a bounding box. Grid points are generated at a
configurable spacing (default 5km for budget mode, 2-3km for full coverage).

Usage:
    from app.data.metro_grids import METROS, generate_grid, get_metros_by_rank

    grid = generate_grid(METROS["new_york"], spacing_km=5.0)
    # Returns: [(40.50, -74.25, "new_york_0_0"), (40.545, -74.25, "new_york_1_0"), ...]
"""
from dataclasses import dataclass


@dataclass
class MetroDefinition:
    name: str           # slug, e.g. "new_york"
    display_name: str   # human-readable
    rank: int           # population rank (1 = largest US metro)
    sw_lat: float       # bounding box southwest corner
    sw_lng: float
    ne_lat: float       # bounding box northeast corner
    ne_lng: float
    default_spacing_km: float = 5.0  # default grid spacing


def generate_grid(
    metro: MetroDefinition,
    spacing_km: float | None = None,
) -> list[tuple[float, float, str]]:
    """Generate evenly-spaced grid points filling a metro's bounding box.

    Args:
        metro: Metro definition with bounding box
        spacing_km: Override spacing (default uses metro's default_spacing_km)

    Returns:
        List of (lat, lng, label) tuples
    """
    spacing = spacing_km or metro.default_spacing_km

    # 1 degree latitude ≈ 111 km everywhere
    lat_step = spacing / 111.0
    # 1 degree longitude varies by latitude; use center latitude for approximation
    center_lat = (metro.sw_lat + metro.ne_lat) / 2
    import math
    lng_step = spacing / (111.0 * math.cos(math.radians(center_lat)))

    points = []
    lat = metro.sw_lat
    row = 0
    while lat <= metro.ne_lat:
        lng = metro.sw_lng
        col = 0
        while lng <= metro.ne_lng:
            label = f"{metro.name}_{row}_{col}"
            points.append((round(lat, 4), round(lng, 4), label))
            lng += lng_step
            col += 1
        lat += lat_step
        row += 1

    return points


def get_metros_by_rank(
    start_rank: int = 1,
    end_rank: int = 50,
) -> list[MetroDefinition]:
    """Get metros ordered by population rank within the given range."""
    return sorted(
        [m for m in METROS.values() if start_rank <= m.rank <= end_rank],
        key=lambda m: m.rank,
    )


# ---------------------------------------------------------------------------
# Top ~40 US metro areas by population, with approximate bounding boxes
# covering the main urbanized area. Bounding boxes are intentionally generous
# to capture suburban restaurants.
#
# Population ranks from US Census 2020 MSA estimates.
# Bounding boxes approximate the core urbanized extent (not the full MSA).
# ---------------------------------------------------------------------------

METROS: dict[str, MetroDefinition] = {
    # --- Top 10 ---
    "new_york": MetroDefinition(
        "new_york", "New York City", 1,
        40.4961, -74.2557, 40.9176, -73.7004, 2.5,
    ),
    "los_angeles": MetroDefinition(
        "los_angeles", "Los Angeles", 2,
        33.7037, -118.6682, 34.3373, -117.6462, 3.0,
    ),
    "chicago": MetroDefinition(
        "chicago", "Chicago", 3,
        41.6445, -87.9401, 42.0230, -87.5244, 2.5,
    ),
    "dallas": MetroDefinition(
        "dallas", "Dallas-Fort Worth", 4,
        32.6200, -97.5000, 33.0200, -96.5000, 3.0,
    ),
    "houston": MetroDefinition(
        "houston", "Houston", 5,
        29.5200, -95.7800, 30.1100, -95.0100, 3.0,
    ),
    "washington_dc": MetroDefinition(
        "washington_dc", "Washington D.C.", 6,
        38.7900, -77.2200, 39.0000, -76.9100, 2.5,
    ),
    "philadelphia": MetroDefinition(
        "philadelphia", "Philadelphia", 7,
        39.8700, -75.2800, 40.0900, -74.9600, 2.5,
    ),
    "miami": MetroDefinition(
        "miami", "Miami", 8,
        25.7000, -80.4500, 26.2200, -80.0500, 3.0,
    ),
    "atlanta": MetroDefinition(
        "atlanta", "Atlanta", 9,
        33.6500, -84.5500, 33.9500, -84.2000, 3.0,
    ),
    "boston": MetroDefinition(
        "boston", "Boston", 10,
        42.2300, -71.1900, 42.4000, -70.9900, 2.5,
    ),

    # --- 11-20 ---
    "phoenix": MetroDefinition(
        "phoenix", "Phoenix", 11,
        33.2900, -112.3300, 33.7200, -111.7900, 3.0,
    ),
    "san_francisco": MetroDefinition(
        "san_francisco", "San Francisco Bay Area", 12,
        37.2500, -122.5200, 37.8100, -121.8000, 3.0,
    ),
    "riverside": MetroDefinition(
        "riverside", "Riverside-San Bernardino", 13,
        33.8500, -117.6500, 34.1500, -117.1500, 3.0,
    ),
    "detroit": MetroDefinition(
        "detroit", "Detroit", 14,
        42.2500, -83.3000, 42.4700, -82.9000, 2.5,
    ),
    "seattle": MetroDefinition(
        "seattle", "Seattle", 15,
        47.4000, -122.4500, 47.7500, -122.2000, 2.5,
    ),
    "minneapolis": MetroDefinition(
        "minneapolis", "Minneapolis-St. Paul", 16,
        44.8500, -93.4500, 45.0700, -93.1000, 3.0,
    ),
    "san_diego": MetroDefinition(
        "san_diego", "San Diego", 17,
        32.5400, -117.3200, 33.2000, -116.9000, 3.0,
    ),
    "tampa": MetroDefinition(
        "tampa", "Tampa-St. Petersburg", 18,
        27.7500, -82.7500, 28.1000, -82.3500, 3.0,
    ),
    "denver": MetroDefinition(
        "denver", "Denver", 19,
        39.6000, -105.1000, 39.8500, -104.7500, 3.0,
    ),
    "st_louis": MetroDefinition(
        "st_louis", "St. Louis", 20,
        38.5000, -90.4500, 38.7500, -90.1500, 3.0,
    ),

    # --- 21-30 ---
    "orlando": MetroDefinition(
        "orlando", "Orlando", 21,
        28.3500, -81.5500, 28.6500, -81.2000, 3.0,
    ),
    "charlotte": MetroDefinition(
        "charlotte", "Charlotte", 22,
        35.1000, -80.9800, 35.3500, -80.7000, 3.0,
    ),
    "san_antonio": MetroDefinition(
        "san_antonio", "San Antonio", 23,
        29.3000, -98.6500, 29.5800, -98.3500, 3.0,
    ),
    "portland": MetroDefinition(
        "portland", "Portland", 24,
        45.4000, -122.8000, 45.6000, -122.5000, 3.0,
    ),
    "sacramento": MetroDefinition(
        "sacramento", "Sacramento", 25,
        38.4500, -121.5500, 38.7000, -121.3000, 3.0,
    ),
    "pittsburgh": MetroDefinition(
        "pittsburgh", "Pittsburgh", 26,
        40.3500, -80.1000, 40.5200, -79.8500, 2.5,
    ),
    "las_vegas": MetroDefinition(
        "las_vegas", "Las Vegas", 27,
        35.9800, -115.3500, 36.2800, -115.0000, 3.0,
    ),
    "austin": MetroDefinition(
        "austin", "Austin", 28,
        30.1500, -97.8800, 30.4500, -97.5500, 3.0,
    ),
    "cincinnati": MetroDefinition(
        "cincinnati", "Cincinnati", 29,
        39.0500, -84.6500, 39.2200, -84.3500, 3.0,
    ),
    "kansas_city": MetroDefinition(
        "kansas_city", "Kansas City", 30,
        38.9500, -94.7500, 39.1800, -94.4500, 3.0,
    ),

    # --- 31-40 ---
    "columbus": MetroDefinition(
        "columbus", "Columbus OH", 31,
        39.8800, -83.1500, 40.1000, -82.8000, 3.0,
    ),
    "indianapolis": MetroDefinition(
        "indianapolis", "Indianapolis", 32,
        39.6500, -86.3000, 39.8800, -85.9500, 3.0,
    ),
    "cleveland": MetroDefinition(
        "cleveland", "Cleveland", 33,
        41.3500, -81.8500, 41.5500, -81.5500, 3.0,
    ),
    "nashville": MetroDefinition(
        "nashville", "Nashville", 34,
        36.0500, -86.9000, 36.2500, -86.6500, 3.0,
    ),
    "virginia_beach": MetroDefinition(
        "virginia_beach", "Virginia Beach-Norfolk", 35,
        36.7500, -76.3500, 36.9500, -76.0500, 3.0,
    ),
    "providence": MetroDefinition(
        "providence", "Providence", 36,
        41.7500, -71.5000, 41.8800, -71.3500, 2.5,
    ),
    "milwaukee": MetroDefinition(
        "milwaukee", "Milwaukee", 37,
        42.9000, -88.0500, 43.1000, -87.8500, 2.5,
    ),
    "jacksonville": MetroDefinition(
        "jacksonville", "Jacksonville", 38,
        30.2000, -81.8000, 30.4500, -81.5000, 3.0,
    ),
    "memphis": MetroDefinition(
        "memphis", "Memphis", 39,
        35.0000, -90.1500, 35.2200, -89.8500, 3.0,
    ),
    "raleigh": MetroDefinition(
        "raleigh", "Raleigh-Durham", 40,
        35.7000, -78.8500, 35.9500, -78.5500, 3.0,
    ),
}

# Food type lists for different budget tiers
FOOD_TYPES_CORE = [
    None, "mexican", "italian", "chinese", "japanese", "thai",
    "indian", "american", "seafood", "pizza", "burger", "sushi",
]

FOOD_TYPES_FULL = FOOD_TYPES_CORE + [
    "korean", "vietnamese", "bbq", "mediterranean", "breakfast", "cafe",
    "ramen", "pho", "tacos", "wings", "ethiopian", "peruvian",
    "greek", "middle eastern", "french", "caribbean", "hawaiian",
    "vegan", "bakery", "ice cream", "deli", "steakhouse",
]
