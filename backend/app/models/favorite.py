"""User favorites — premium feature for saving menu items and restaurants."""
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class FavoriteItem(Base):
    """A menu item a user has saved. Premium feature."""
    __tablename__ = "favorite_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    menu_item_id = Column(
        UUID(as_uuid=True), ForeignKey("menu_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    note = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "menu_item_id", name="uq_user_menu_item"),
    )


class FavoriteRestaurant(Base):
    """A restaurant a user has saved. Premium feature."""
    __tablename__ = "favorite_restaurants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    restaurant_id = Column(
        UUID(as_uuid=True), ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
    )
    note = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "restaurant_id", name="uq_user_restaurant"),
    )
