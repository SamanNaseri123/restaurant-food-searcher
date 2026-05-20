"""Authentication routes: signup, login, current user, admin grants."""
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    AdminGrantLifetimeRequest,
    LoginRequest,
    MeResponse,
    SignupRequest,
    SubscriptionResponse,
    TokenResponse,
    UserResponse,
)
from app.core.auth import (
    create_access_token,
    get_active_subscription,
    get_current_user,
    hash_password,
    require_admin,
    verify_password,
)
from app.core.config import settings
from app.core.database import get_db
from app.models.user import (
    SOURCE_ADMIN,
    TIER_FREE,
    Subscription,
    User,
    make_lifetime_subscription,
    make_trial_subscription,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(email: str) -> str:
    email = email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid email address",
        )
    return email


def _build_subscription_response(sub: Subscription | None) -> SubscriptionResponse:
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


@router.post("/signup", response_model=MeResponse)
async def signup(req: SignupRequest, db: AsyncSession = Depends(get_db)):
    """Create a new user account and start their 7-day free trial."""
    email = _validate_email(req.email)

    # Check if email is taken
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email=email,
        password_hash=hash_password(req.password),
        display_name=req.display_name,
    )
    db.add(user)
    await db.flush()  # populate user.id

    trial = make_trial_subscription(user.id, days=settings.trial_days)
    db.add(trial)
    await db.commit()
    await db.refresh(user)
    await db.refresh(trial)

    return MeResponse(
        user=UserResponse(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            is_admin=bool(user.is_admin),
            created_at=user.created_at,
        ),
        subscription=_build_subscription_response(trial),
    )


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Exchange email/password for a JWT access token."""
    email = req.email.strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    token = create_access_token(user.id)
    return TokenResponse(
        access_token=token,
        expires_in_minutes=settings.jwt_expires_minutes,
    )


@router.get("/me", response_model=MeResponse)
async def me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current user's profile and subscription status."""
    sub = await get_active_subscription(user.id, db)
    return MeResponse(
        user=UserResponse(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            is_admin=bool(user.is_admin),
            created_at=user.created_at,
        ),
        subscription=_build_subscription_response(sub),
    )


@router.post("/admin/grant-lifetime", response_model=MeResponse)
async def admin_grant_lifetime(
    req: AdminGrantLifetimeRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin endpoint: manually grant lifetime premium to any user.

    Used for testing and comping users before payment processing is wired up.
    """
    email = req.user_email.strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    target = result.scalar_one_or_none()

    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    # Deactivate any existing subscriptions
    existing = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == target.id)
        .where(Subscription.is_active == 1)
    )
    for sub in existing.scalars():
        sub.is_active = 0

    new_sub = make_lifetime_subscription(
        target.id, source=SOURCE_ADMIN, external_id=f"admin:{admin.email}"
    )
    db.add(new_sub)
    await db.commit()
    await db.refresh(new_sub)

    return MeResponse(
        user=UserResponse(
            id=target.id,
            email=target.email,
            display_name=target.display_name,
            is_admin=bool(target.is_admin),
            created_at=target.created_at,
        ),
        subscription=_build_subscription_response(new_sub),
    )
