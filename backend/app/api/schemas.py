from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class MenuItemResult(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    price: float | None = None
    category: str | None = None


class RestaurantResult(BaseModel):
    id: UUID
    name: str
    address: str | None = None
    lat: float
    lng: float
    website_url: str | None = None
    phone: str | None = None
    rating: float | None = None
    price_level: int | None = None
    photos: list[str] = []
    distance_miles: float | None = None
    matched_items: list[MenuItemResult] = []
    total_matched_items: int = 0  # Total matches in this restaurant (for "+N more" UI)


class SearchResponse(BaseModel):
    query: str
    lat: float
    lng: float
    radius_miles: float
    total_results: int
    restaurants: list[RestaurantResult]


class RestaurantDetailResponse(BaseModel):
    id: UUID
    name: str
    address: str | None = None
    lat: float
    lng: float
    website_url: str | None = None
    phone: str | None = None
    rating: float | None = None
    price_level: int | None = None
    photos: list[str] = []
    menu_items: list[MenuItemResult] = []
    menu_last_scraped_at: datetime | None = None


class AutocompleteResponse(BaseModel):
    suggestions: list[str]


class DiscoverRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    radius_meters: int = Field(default=5000, ge=100, le=25000)
    food_type: str | None = None  # e.g., "thai", "italian" to narrow discovery


# --- Auth & Premium ---

class SignupRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=100)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class UserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str | None = None
    is_admin: bool = False
    created_at: datetime


class SubscriptionResponse(BaseModel):
    tier: str  # "free", "trial", "lifetime"
    is_premium: bool
    started_at: datetime | None = None
    expires_at: datetime | None = None  # null for lifetime
    days_remaining: int | None = None  # for trial


class MeResponse(BaseModel):
    user: UserResponse
    subscription: SubscriptionResponse


class RedeemAppleReceiptRequest(BaseModel):
    """iOS app sends Apple's receipt after a successful purchase."""
    receipt_data: str = Field(..., min_length=1)
    transaction_id: str | None = None  # Apple's original_transaction_id


class AdminGrantLifetimeRequest(BaseModel):
    """Admin endpoint to manually grant lifetime access (testing/comping users)."""
    user_email: str


class FavoriteItemRequest(BaseModel):
    menu_item_id: UUID
    note: str | None = Field(default=None, max_length=500)


class FavoriteItemResponse(BaseModel):
    id: UUID
    menu_item_id: UUID
    note: str | None = None
    created_at: datetime
    item: MenuItemResult | None = None


class FavoriteRestaurantRequest(BaseModel):
    restaurant_id: UUID
    note: str | None = Field(default=None, max_length=500)


class FavoriteRestaurantResponse(BaseModel):
    id: UUID
    restaurant_id: UUID
    note: str | None = None
    created_at: datetime
    restaurant: RestaurantResult | None = None
