from dataclasses import dataclass

import httpx

from app.core.config import settings


@dataclass
class PlaceResult:
    place_id: str
    name: str
    address: str
    lat: float
    lng: float
    rating: float | None
    price_level: int | None
    website_url: str | None
    phone: str | None
    photos: list[str]


class PlacesService:
    BASE_URL = "https://places.googleapis.com/v1/places"

    def __init__(self, include_photos: bool = True):
        self.api_key = settings.google_places_api_key
        self.include_photos = include_photos

    async def search_nearby_restaurants(
        self,
        lat: float,
        lng: float,
        radius_meters: int = 5000,
        food_type: str | None = None,
    ) -> list[PlaceResult]:
        """Search for restaurants near a location using Google Places API (New)."""
        text_query = f"{food_type} restaurants" if food_type else "restaurants"

        fields = (
            "places.id,places.displayName,places.formattedAddress,"
            "places.location,places.rating,places.priceLevel,"
            "places.websiteUri,places.nationalPhoneNumber"
        )
        if self.include_photos:
            fields += ",places.photos"

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": fields,
        }

        body = {
            "textQuery": text_query,
            "locationBias": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
                    "radius": float(radius_meters),
                }
            },
            "maxResultCount": 20,
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.BASE_URL}:searchText",
                headers=headers,
                json=body,
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()

        return [self._parse_place(p) for p in data.get("places", [])]

    def _parse_place(self, place: dict) -> PlaceResult:
        location = place.get("location", {})
        price_raw = place.get("priceLevel")
        price_map = {
            "PRICE_LEVEL_FREE": 0,
            "PRICE_LEVEL_INEXPENSIVE": 1,
            "PRICE_LEVEL_MODERATE": 2,
            "PRICE_LEVEL_EXPENSIVE": 3,
            "PRICE_LEVEL_VERY_EXPENSIVE": 4,
        }

        photo_names = []
        for photo in place.get("photos", [])[:3]:
            name = photo.get("name", "")
            if name:
                photo_names.append(
                    f"https://places.googleapis.com/v1/{name}/media"
                    f"?maxWidthPx=400&key={self.api_key}"
                )

        return PlaceResult(
            place_id=place.get("id", ""),
            name=place.get("displayName", {}).get("text", "Unknown"),
            address=place.get("formattedAddress", ""),
            lat=location.get("latitude", 0),
            lng=location.get("longitude", 0),
            rating=place.get("rating"),
            price_level=price_map.get(price_raw) if price_raw else None,
            website_url=place.get("websiteUri"),
            phone=place.get("nationalPhoneNumber"),
            photos=photo_names,
        )
