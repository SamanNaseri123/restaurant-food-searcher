from datetime import datetime, timezone

from bs4 import BeautifulSoup
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.restaurant import ScrapingPattern


class PatternRegistry:
    """Stores and retrieves learned CSS selector patterns for menu scraping."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_pattern(self, platform_type: str) -> dict | None:
        """Get the best-performing pattern for a platform type."""
        stmt = (
            select(ScrapingPattern)
            .where(ScrapingPattern.platform_type == platform_type)
            .order_by(ScrapingPattern.success_count.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        pattern = result.scalar_one_or_none()

        if pattern:
            # Update last_used_at
            await self.db.execute(
                update(ScrapingPattern)
                .where(ScrapingPattern.id == pattern.id)
                .values(
                    last_used_at=datetime.now(timezone.utc),
                    success_count=pattern.success_count + 1,
                )
            )
            await self.db.commit()
            return pattern.selectors

        return None

    async def save_pattern(
        self,
        platform_type: str,
        detection_rule: str,
        selectors: dict,
    ) -> None:
        """Save a new scraping pattern or increment an existing one."""
        # Check if a similar pattern already exists
        stmt = select(ScrapingPattern).where(
            ScrapingPattern.platform_type == platform_type,
            ScrapingPattern.detection_rule == detection_rule,
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.success_count += 1
            existing.selectors = selectors
            existing.last_used_at = datetime.now(timezone.utc)
        else:
            new_pattern = ScrapingPattern(
                platform_type=platform_type,
                detection_rule=detection_rule,
                selectors=selectors,
            )
            self.db.add(new_pattern)

        await self.db.commit()

    def try_extract_with_selectors(
        self, html: str, selectors: dict
    ) -> list[dict] | None:
        """Try to extract menu items using CSS selectors.

        Returns list of dicts with name, description, price, category
        or None if extraction fails.
        """
        soup = BeautifulSoup(html, "html.parser")
        items = []

        # Try the item container selector
        item_selector = selectors.get("menu_item", selectors.get("item_container"))
        if not item_selector:
            return None

        containers = soup.select(item_selector)
        if not containers:
            return None

        name_sel = selectors.get("item_name") or "h3, h4, .item-name, .name"
        price_sel = selectors.get("item_price") or ".price, .item-price"
        desc_sel = selectors.get("item_description") or ".description, .item-desc, p"

        for container in containers:
            name_el = container.select_one(name_sel)
            if not name_el:
                continue

            name = name_el.get_text(strip=True)
            if not name or len(name) < 2:
                continue

            price_el = container.select_one(price_sel)
            price_text = price_el.get_text(strip=True) if price_el else None
            price = self._parse_price(price_text)

            desc_el = container.select_one(desc_sel)
            description = desc_el.get_text(strip=True) if desc_el else None

            items.append({
                "name": name,
                "description": description,
                "price": price,
                "category": None,  # Can be inferred from section headers
            })

        return items if len(items) >= 3 else None  # Minimum 3 items to consider valid

    @staticmethod
    def _parse_price(price_text: str | None) -> float | None:
        if not price_text:
            return None
        import re

        match = re.search(r"[\d]+\.?\d*", price_text.replace(",", ""))
        if match:
            return float(match.group())
        return None
