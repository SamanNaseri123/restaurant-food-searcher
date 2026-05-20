import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class Restaurant(Base):
    __tablename__ = "restaurants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    google_place_id = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(500), nullable=False)
    address = Column(Text)
    location = Column(Geometry("POINT", srid=4326), nullable=False)
    website_url = Column(Text)
    phone = Column(String(50))
    rating = Column(Float)
    price_level = Column(Integer)
    photos = Column(JSONB, default=list)
    platform_type = Column(String(50))  # squarespace, wordpress, wix, custom
    menu_last_scraped_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    menu_items = relationship(
        "MenuItem", back_populates="restaurant", cascade="all, delete-orphan"
    )

    __table_args__ = ()


class MenuItem(Base):
    __tablename__ = "menu_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    restaurant_id = Column(
        UUID(as_uuid=True), ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String(500), nullable=False)
    description = Column(Text)
    price = Column(Float)
    category = Column(String(100))  # appetizer, entree, dessert, drink, etc.
    search_vector = Column(TSVECTOR, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    restaurant = relationship("Restaurant", back_populates="menu_items")

    __table_args__ = (
        Index(
            "idx_menu_items_search",
            "search_vector",
            postgresql_using="gin",
        ),
        Index("idx_menu_items_restaurant", "restaurant_id"),
    )


class ScrapingPattern(Base):
    __tablename__ = "scraping_patterns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    platform_type = Column(String(50), nullable=False, index=True)
    detection_rule = Column(Text, nullable=False)
    selectors = Column(JSONB, nullable=False)
    success_count = Column(Integer, default=1)
    last_used_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ScrapeFailure(Base):
    """Tracks failed scraping attempts for future retry when new solutions are found."""
    __tablename__ = "scrape_failures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    restaurant_id = Column(
        UUID(as_uuid=True), ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False
    )
    website_url = Column(Text, nullable=False)
    error_type = Column(String(50), nullable=False, index=True)  # See error types below
    error_detail = Column(Text)
    platform_type = Column(String(50))
    attempts = Column(Integer, default=1)
    last_attempt_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved = Column(Integer, default=0)  # 0=unresolved, 1=resolved
    extractor_version = Column(Integer, default=1)  # version of extractors when failure was logged
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    restaurant = relationship("Restaurant")

    __table_args__ = (
        Index("idx_scrape_failures_error_type", "error_type"),
        Index("idx_scrape_failures_unresolved", "resolved", "error_type"),
    )


class ScrapeCheckpoint(Base):
    """Tracks progress through a metro grid scrape for resume capability."""
    __tablename__ = "scrape_checkpoints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    metro_name = Column(String(100), nullable=False, unique=True, index=True)
    grid_index = Column(Integer, nullable=False, default=0)
    food_type_index = Column(Integer, nullable=False, default=0)
    total_grid_points = Column(Integer, nullable=False)
    total_food_types = Column(Integer, nullable=False)
    searches_this_run = Column(Integer, default=0)  # for budget tracking
    free_only = Column(Integer, default=0)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)


class SearchCache(Base):
    __tablename__ = "search_cache"

    query_hash = Column(String(64), primary_key=True)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    radius = Column(Integer, nullable=False)
    results = Column(JSONB, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
