"""Tests for auth core: password hashing, JWT, premium gating logic."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.core.auth import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import (
    SOURCE_TRIAL,
    TIER_LIFETIME,
    TIER_TRIAL,
    Subscription,
    make_lifetime_subscription,
    make_trial_subscription,
)


class TestPasswordHashing:
    def test_should_hash_and_verify_password(self):
        password = "correcthorsebatterystaple"
        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(password, hashed) is True

    def test_should_reject_wrong_password(self):
        hashed = hash_password("rightpassword")
        assert verify_password("wrongpassword", hashed) is False

    def test_should_handle_invalid_hash_gracefully(self):
        assert verify_password("password", "not-a-real-hash") is False
        assert verify_password("password", "") is False


class TestJWT:
    def test_should_create_and_decode_token(self):
        user_id = uuid4()
        token = create_access_token(user_id)
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == str(user_id)

    def test_should_reject_invalid_token(self):
        assert decode_token("not-a-jwt") is None
        assert decode_token("") is None

    def test_should_reject_expired_token(self):
        # Create a token that expired 1 minute ago
        token = create_access_token(uuid4(), expires_minutes=-1)
        assert decode_token(token) is None


class TestSubscriptionLogic:
    def test_lifetime_is_always_premium(self):
        sub = make_lifetime_subscription(uuid4(), source="apple")
        assert sub.is_currently_premium() is True

    def test_active_trial_is_premium(self):
        sub = make_trial_subscription(uuid4(), days=7)
        assert sub.is_currently_premium() is True

    def test_expired_trial_is_not_premium(self):
        sub = Subscription(
            user_id=uuid4(),
            tier=TIER_TRIAL,
            source=SOURCE_TRIAL,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            is_active=1,
        )
        assert sub.is_currently_premium() is False

    def test_inactive_subscription_is_not_premium(self):
        sub = make_lifetime_subscription(uuid4(), source="apple")
        sub.is_active = 0
        assert sub.is_currently_premium() is False

    def test_trial_factory_sets_correct_tier(self):
        sub = make_trial_subscription(uuid4(), days=14)
        assert sub.tier == TIER_TRIAL
        assert sub.source == SOURCE_TRIAL
        assert sub.expires_at is not None
        # Should be roughly 14 days from now
        delta = sub.expires_at - datetime.now(timezone.utc)
        assert 13 < delta.days <= 14

    def test_lifetime_factory_has_no_expiry(self):
        sub = make_lifetime_subscription(uuid4(), source="apple", external_id="txn_123")
        assert sub.tier == TIER_LIFETIME
        assert sub.expires_at is None
        assert sub.external_id == "txn_123"
