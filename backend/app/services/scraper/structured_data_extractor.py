"""Extract menu items from JSON-LD / Schema.org structured data.

Many restaurant sites embed Menu/MenuItem schema markup that Google uses
for rich results. We can parse this for free — no LLM needed.
"""
import json
import logging
import re

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def extract_from_structured_data(html: str) -> list[dict] | None:
    """Extract menu items from JSON-LD or microdata in the page.

    Returns a list of menu item dicts, or None if no structured data found.
    """
    items = _extract_from_jsonld(html)
    if items:
        return items

    items = _extract_from_microdata(html)
    if items:
        return items

    return None


def _extract_from_jsonld(html: str) -> list[dict] | None:
    """Parse JSON-LD script tags for Menu/MenuItem schema."""
    soup = BeautifulSoup(html, "html.parser")
    items = []

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        # Handle both single objects and arrays
        if isinstance(data, list):
            for obj in data:
                items.extend(_extract_menu_from_schema(obj))
        elif isinstance(data, dict):
            items.extend(_extract_menu_from_schema(data))

    return items if len(items) >= 3 else None


def _extract_menu_from_schema(obj: dict) -> list[dict]:
    """Recursively extract menu items from a Schema.org object."""
    items = []
    obj_type = obj.get("@type", "")

    # Direct MenuItem
    if obj_type in ("MenuItem", "MenuItemOffer"):
        item = _schema_to_item(obj)
        if item:
            items.append(item)
        return items

    # Menu or MenuSection containing items
    if obj_type in ("Menu", "MenuSection", "ItemList"):
        section_name = obj.get("name", "")
        category = _guess_category(section_name)

        # Check hasMenuSection
        for section in obj.get("hasMenuSection", []):
            if isinstance(section, dict):
                sub_items = _extract_menu_from_schema(section)
                # Apply parent category if items don't have one
                for item in sub_items:
                    if not item.get("category") and category:
                        item["category"] = category
                items.extend(sub_items)

        # Check hasMenuItem
        for menu_item in obj.get("hasMenuItem", []):
            if isinstance(menu_item, dict):
                item = _schema_to_item(menu_item)
                if item:
                    if not item.get("category") and category:
                        item["category"] = category
                    items.append(item)

        # Check itemListElement
        for element in obj.get("itemListElement", []):
            if isinstance(element, dict):
                inner = element.get("item", element)
                if isinstance(inner, dict):
                    items.extend(_extract_menu_from_schema(inner))

    # Restaurant with menu
    if obj_type in ("Restaurant", "FoodEstablishment"):
        menu = obj.get("hasMenu") or obj.get("menu")
        if isinstance(menu, dict):
            items.extend(_extract_menu_from_schema(menu))
        elif isinstance(menu, list):
            for m in menu:
                if isinstance(m, dict):
                    items.extend(_extract_menu_from_schema(m))

    # Check @graph
    for graph_item in obj.get("@graph", []):
        if isinstance(graph_item, dict):
            items.extend(_extract_menu_from_schema(graph_item))

    return items


def _schema_to_item(obj: dict) -> dict | None:
    """Convert a Schema.org MenuItem to our dict format."""
    name = obj.get("name", "").strip()
    if not name:
        return None

    price = _extract_price_from_schema(obj)

    return {
        "name": name,
        "description": (obj.get("description") or "").strip() or None,
        "price": price,
        "category": _guess_category(obj.get("menuAddOn", obj.get("@type", ""))),
    }


def _extract_price_from_schema(obj: dict) -> float | None:
    """Extract price from various Schema.org price representations."""
    # Direct price field
    price = obj.get("price")
    if price is not None:
        return _parse_price(price)

    # Offers
    offers = obj.get("offers") or obj.get("offer")
    if isinstance(offers, dict):
        price = offers.get("price") or offers.get("lowPrice")
        if price is not None:
            return _parse_price(price)
    elif isinstance(offers, list):
        for offer in offers:
            if isinstance(offer, dict):
                price = offer.get("price") or offer.get("lowPrice")
                if price is not None:
                    return _parse_price(price)

    return None


def _parse_price(value) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _extract_from_microdata(html: str) -> list[dict] | None:
    """Extract from HTML microdata (itemprop attributes)."""
    soup = BeautifulSoup(html, "html.parser")
    items = []

    # Look for elements with itemprop="menuItem" or itemtype containing MenuItem
    for el in soup.find_all(attrs={"itemtype": re.compile(r"MenuItem", re.I)}):
        name_el = el.find(attrs={"itemprop": "name"})
        desc_el = el.find(attrs={"itemprop": "description"})
        price_el = el.find(attrs={"itemprop": "price"})

        name = (name_el.get_text(strip=True) if name_el else "").strip()
        if not name:
            continue

        items.append({
            "name": name,
            "description": (desc_el.get_text(strip=True) if desc_el else None),
            "price": _parse_price(price_el.get_text(strip=True) if price_el else None),
            "category": None,
        })

    return items if len(items) >= 3 else None


def _guess_category(text: str) -> str | None:
    """Guess a menu category from section name text."""
    if not text:
        return None
    text_lower = text.lower()
    categories = {
        "appetizer": ["appetizer", "starter", "small plate", "shareables", "apps"],
        "entree": ["entree", "entrée", "main", "dinner", "platter", "large plate"],
        "salad": ["salad"],
        "soup": ["soup"],
        "side": ["side", "accompaniment"],
        "dessert": ["dessert", "sweet", "postre"],
        "drink": ["drink", "beverage", "cocktail", "wine", "beer", "bebida"],
        "breakfast": ["breakfast", "brunch", "morning"],
        "lunch": ["lunch", "midday"],
        "taco": ["taco"],
        "burrito": ["burrito"],
        "sandwich": ["sandwich", "sub", "wrap"],
        "pizza": ["pizza"],
        "pasta": ["pasta", "noodle"],
    }
    for category, keywords in categories.items():
        if any(kw in text_lower for kw in keywords):
            return category
    return None
