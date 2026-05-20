"""Authentication core: password hashing, JWT, FastAPI dependencies."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.user import Subscription, User

# OAuth2 scheme — clients send `Authorization: Bearer <token>`
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


# --- Password hashing ---

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its bcrypt hash."""
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


# --- JWT ---

def create_access_token(user_id: UUID, expires_minutes: int | None = None) -> str:
    """Create a signed JWT for a user."""
    expires = expires_minutes or settings.jwt_expires_minutes
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=expires),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict | None:
    """Decode and verify a JWT. Returns payload dict or None if invalid."""
    try:
        return jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError:
        return None


# --- FastAPI dependencies ---

async def get_current_user_optional(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Get the current user if authenticated, else None.

    Use for endpoints that work for both anonymous and authenticated users.
    """
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        return None
    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if user and user.is_active:
        return user
    return None


async def get_current_user(
    user: User | None = Depends(get_current_user_optional),
) -> User:
    """Require an authenticated user. Raises 401 if not logged in."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_active_subscription(
    user_id: UUID, db: AsyncSession
) -> Subscription | None:
    """Fetch the user's currently active subscription, if any."""
    result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .where(Subscription.is_active == 1)
        .order_by(Subscription.created_at.desc())
    )
    return result.scalars().first()


async def require_premium(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Require an authenticated user with an active premium subscription.

    Premium = active trial OR lifetime subscription.
    Raises 403 if user is logged in but not premium.
    Raises 401 if not logged in.
    """
    sub = await get_active_subscription(user.id, db)
    if not sub or not sub.is_currently_premium():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Premium subscription required",
        )
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Require an authenticated admin user."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user
