"""Subscription routes: redeem Apple/Google receipts, check status."""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    MeResponse,
    RedeemAppleReceiptRequest,
    SubscriptionResponse,
    UserResponse,
)
from app.core.auth import get_active_subscription, get_current_user
from app.core.database import get_db
from app.models.user import (
    SOURCE_APPLE,
    Subscription,
    User,
    make_lifetime_subscription,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/subscriptions", tags=["subscriptions"])


def _build_subscription_response(sub: Subscription | None) -> SubscriptionResponse:
    from datetime import datetime, timezone
    from app.models.user import TIER_FREE
    if not sub:
        return SubscriptionResponse(tier=TIER_FREE, is_premium=False)
    days_remaining = None
    if sub.expires_at:
        delta = sub.expires_at - datetime.now(timezone.utc)
        days_remaining = max(0, delta.days)
    return SubscriptionResponse(
        tier=sub.tier,
        is_premium=sub.is_currently_premium(),
        started_at=sub.started_at,
        expires_at=sub.expires_at,
        days_remaining=days_remaining,
    )


@router.post("/redeem-apple", response_model=MeResponse)
async def redeem_apple_receipt(
    req: RedeemAppleReceiptRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Redeem an Apple In-App Purchase receipt for a lifetime subscription.

    The iOS app calls this after a successful StoreKit transaction.
    Receipt validation against Apple's servers is stubbed for now — to enable
    real validation you need:
        1. Apple Developer Program enrollment ($99/yr)
        2. App Store Connect product setup (lifetime IAP)
        3. Real receipt verification call to Apple's verifyReceipt endpoint
        4. Or RevenueCat integration (recommended)

    For now this just stores the receipt data and grants lifetime access.
    DO NOT deploy to production without real receipt validation.
    """
    if not req.receipt_data or len(req.receipt_data) < 10:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid receipt data",
        )

    # TODO: When ready for real payments, replace this stub with:
    #   - Call to https://buy.itunes.apple.com/verifyReceipt
    #   - Parse and validate the receipt
    #   - Check the product_id matches your lifetime IAP product
    #   - Use original_transaction_id to detect duplicate redemptions
    logger.warning(
        f"STUB: Granting lifetime to {user.email} from unverified receipt "
        f"(transaction_id={req.transaction_id})"
    )

    # Check if this transaction was already redeemed (basic dedup)
    if req.transaction_id:
        existing = await db.execute(
            select(Subscription).where(
                Subscription.external_id == req.transaction_id
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Receipt already redeemed",
            )

    # Deactivate any existing subscriptions for this user
    existing_subs = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .where(Subscription.is_active == 1)
    )
    for sub in existing_subs.scalars():
        sub.is_active = 0

    new_sub = make_lifetime_subscription(
        user.id,
        source=SOURCE_APPLE,
        external_id=req.transaction_id,
        receipt_data=req.receipt_data[:5000],  # Truncate for storage
    )
    db.add(new_sub)
    await db.commit()
    await db.refresh(new_sub)

    return MeResponse(
        user=UserResponse(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            is_admin=bool(user.is_admin),
            created_at=user.created_at,
        ),
        subscription=_build_subscription_response(new_sub),
    )


@router.get("/status", response_model=SubscriptionResponse)
async def subscription_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Quick endpoint to check current subscription status."""
    sub = await get_active_subscription(user.id, db)
    return _build_subscription_response(sub)
