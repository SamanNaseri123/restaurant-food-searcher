"""Premium feature: save favorite menu items and restaurants.

All endpoints require an active premium subscription (trial or lifetime).
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    FavoriteItemRequest,
    FavoriteItemResponse,
    FavoriteRestaurantRequest,
    FavoriteRestaurantResponse,
    MenuItemResult,
)
from app.core.auth import require_premium
from app.core.database import get_db
from app.models.favorite import FavoriteItem, FavoriteRestaurant
from app.models.restaurant import MenuItem, Restaurant
from app.models.user import User

router = APIRouter(prefix="/api/v1/favorites", tags=["favorites"])


# --- Favorite menu items ---

@router.post("/items", response_model=FavoriteItemResponse)
async def add_favorite_item(
    req: FavoriteItemRequest,
    user: User = Depends(require_premium),
    db: AsyncSession = Depends(get_db),
):
    """Save a menu item to favorites. Premium only."""
    # Check item exists
    result = await db.execute(select(MenuItem).where(MenuItem.id == req.menu_item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Menu item not found")

    # Check if already favorited
    existing = await db.execute(
        select(FavoriteItem).where(
            FavoriteItem.user_id == user.id,
            FavoriteItem.menu_item_id == req.menu_item_id,
        )
    )
    fav = existing.scalar_one_or_none()
    if fav:
        # Update note if provided
        if req.note is not None:
            fav.note = req.note
            await db.commit()
            await db.refresh(fav)
    else:
        fav = FavoriteItem(
            user_id=user.id,
            menu_item_id=req.menu_item_id,
            note=req.note,
        )
        db.add(fav)
        await db.commit()
        await db.refresh(fav)

    return FavoriteItemResponse(
        id=fav.id,
        menu_item_id=fav.menu_item_id,
        note=fav.note,
        created_at=fav.created_at,
        item=MenuItemResult(
            id=item.id,
            name=item.name,
            description=item.description,
            price=item.price,
            category=item.category,
        ),
    )


@router.get("/items", response_model=list[FavoriteItemResponse])
async def list_favorite_items(
    user: User = Depends(require_premium),
    db: AsyncSession = Depends(get_db),
):
    """List all favorited menu items. Premium only."""
    result = await db.execute(
        select(FavoriteItem, MenuItem)
        .join(MenuItem, MenuItem.id == FavoriteItem.menu_item_id)
        .where(FavoriteItem.user_id == user.id)
        .order_by(FavoriteItem.created_at.desc())
    )
    return [
        FavoriteItemResponse(
            id=fav.id,
            menu_item_id=fav.menu_item_id,
            note=fav.note,
            created_at=fav.created_at,
            item=MenuItemResult(
                id=item.id,
                name=item.name,
                description=item.description,
                price=item.price,
                category=item.category,
            ),
        )
        for fav, item in result.all()
    ]


@router.delete("/items/{favorite_id}")
async def delete_favorite_item(
    favorite_id: UUID,
    user: User = Depends(require_premium),
    db: AsyncSession = Depends(get_db),
):
    """Remove a menu item from favorites. Premium only."""
    result = await db.execute(
        delete(FavoriteItem)
        .where(FavoriteItem.id == favorite_id)
        .where(FavoriteItem.user_id == user.id)
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Favorite not found")
    return {"status": "deleted"}


# --- Favorite restaurants ---

@router.post("/restaurants", response_model=FavoriteRestaurantResponse)
async def add_favorite_restaurant(
    req: FavoriteRestaurantRequest,
    user: User = Depends(require_premium),
    db: AsyncSession = Depends(get_db),
):
    """Save a restaurant to favorites. Premium only."""
    result = await db.execute(
        select(Restaurant).where(Restaurant.id == req.restaurant_id)
    )
    restaurant = result.scalar_one_or_none()
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    existing = await db.execute(
        select(FavoriteRestaurant).where(
            FavoriteRestaurant.user_id == user.id,
            FavoriteRestaurant.restaurant_id == req.restaurant_id,
        )
    )
    fav = existing.scalar_one_or_none()
    if fav:
        if req.note is not None:
            fav.note = req.note
            await db.commit()
            await db.refresh(fav)
    else:
        fav = FavoriteRestaurant(
            user_id=user.id,
            restaurant_id=req.restaurant_id,
            note=req.note,
        )
        db.add(fav)
        await db.commit()
        await db.refresh(fav)

    return FavoriteRestaurantResponse(
        id=fav.id,
        restaurant_id=fav.restaurant_id,
        note=fav.note,
        created_at=fav.created_at,
        restaurant=None,  # Skip populating to keep response light
    )


@router.delete("/restaurants/{favorite_id}")
async def delete_favorite_restaurant(
    favorite_id: UUID,
    user: User = Depends(require_premium),
    db: AsyncSession = Depends(get_db),
):
    """Remove a restaurant from favorites. Premium only."""
    result = await db.execute(
        delete(FavoriteRestaurant)
        .where(FavoriteRestaurant.id == favorite_id)
        .where(FavoriteRestaurant.user_id == user.id)
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Favorite not found")
    return {"status": "deleted"}
