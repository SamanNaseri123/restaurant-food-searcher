"""User and subscription models for premium feature gating."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class User(Base):
    """A registered user account."""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    # Optional external IDs from third-party auth (Apple Sign In, etc.)
    apple_user_id = Column(String(255), unique=True, nullable=True, index=True)
    google_user_id = Column(String(255), unique=True, nullable=True, index=True)
    display_name = Column(String(100), nullable=True)
    is_active = Column(Integer, default=1)  # 0=disabled, 1=active
    is_admin = Column(Integer, default=0)   # 0=user, 1=admin
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    subscriptions = relationship(
        "Subscription", back_populates="user", cascade="all, delete-orphan"
    )


# Subscription tier values
TIER_FREE = "free"          # No active subscription (paywall enforced)
TIER_TRIAL = "trial"        # 7-day free trial after signup
TIER_LIFETIME = "lifetime"  # One-time purchase, never expires

# Source values — where the subscription came from
SOURCE_TRIAL = "trial"      # Auto-granted on signup
SOURCE_APPLE = "apple"      # Apple In-App Purchase
SOURCE_GOOGLE = "google"    # Google Play
SOURCE_ADMIN = "admin"      # Manually granted (testing/comp)


class Subscription(Base):
    """Tracks a user's premium subscription state.

    A user can have multiple historical subscriptions, but only ONE should be
    `is_active = 1` at a time. Use `get_active_subscription(user_id)` to fetch.
    """
    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    tier = Column(String(20), nullable=False)        # See TIER_* constants above
    source = Column(String(20), nullable=False)      # See SOURCE_* constants
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)  # NULL = lifetime
    is_active = Column(Integer, default=1, index=True)
    # External transaction reference (Apple original_transaction_id, etc.)
    external_id = Column(String(255), nullable=True, index=True)
    # Raw receipt or webhook payload for audit/debugging
    receipt_data = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user = relationship("User", back_populates="subscriptions")

    def is_currently_premium(self) -> bool:
        """Returns True if this subscription grants premium access right now."""
        if not self.is_active:
            return False
        if self.tier == TIER_LIFETIME:
            return True
        if self.tier == TIER_TRIAL:
            if self.expires_at is None:
                return False
            return self.expires_at > datetime.now(timezone.utc)
        return False


def make_trial_subscription(user_id: uuid.UUID, days: int = 7) -> Subscription:
    """Create a 7-day free trial subscription for a new user."""
    return Subscription(
        user_id=user_id,
        tier=TIER_TRIAL,
        source=SOURCE_TRIAL,
        expires_at=datetime.now(timezone.utc) + timedelta(days=days),
        is_active=1,
    )


def make_lifetime_subscription(
    user_id: uuid.UUID,
    source: str,
    external_id: str | None = None,
    receipt_data: str | None = None,
) -> Subscription:
    """Create a lifetime subscription (one-time purchase, never expires)."""
    return Subscription(
        user_id=user_id,
        tier=TIER_LIFETIME,
        source=source,
        expires_at=None,
        is_active=1,
        external_id=external_id,
        receipt_data=receipt_data,
    )
