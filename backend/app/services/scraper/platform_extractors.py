"""Hardcoded extractors for common restaurant website platforms.

These platforms have predictable HTML structures, so we can extract
menu items with CSS selectors directly — no LLM needed.
"""
import logging
import re

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)


def extract_from_platform(html: str, platform: str) -> list[dict] | None:
    """Try platform-specific extraction. Returns items or None."""
    extractor = _PLATFORM_EXTRACTORS.get(platform)
    if not extractor:
        return None

    try:
        items = extractor(html)
        if items and len(items) >= 3:
            logger.info(f"Platform extractor '{platform}' found {len(items)} items")
            return items
    except Exception as e:
        logger.warning(f"Platform extractor '{platform}' failed: {e}")

    return None


def _extract_toast(html: str) -> list[dict]:
    """ToastTab menus have a very consistent structure."""
    soup = BeautifulSoup(html, "html.parser")
    items = []

    # Toast uses specific classes for menu items
    for selectors in [
        {"container": ".menuItemContainer", "name": ".itemHeader", "price": ".price", "desc": ".itemDescription"},
        {"container": "[data-testid='menu-item']", "name": "[data-testid='menu-item-name']", "price": "[data-testid='menu-item-price']", "desc": "[data-testid='menu-item-description']"},
        {"container": ".ts-menu-item", "name": ".ts-item-name", "price": ".ts-item-price", "desc": ".ts-item-desc"},
        {"container": ".so-menu-item", "name": ".so-menu-item-name", "price": ".so-menu-item-price", "desc": ".so-menu-item-description"},
    ]:
        containers = soup.select(selectors["container"])
        if not containers:
            continue
        for container in containers:
            item = _extract_from_container(container, selectors)
            if item:
                items.append(item)
        if items:
            return items

    return items


def _extract_squarespace(html: str) -> list[dict]:
    """Squarespace restaurant sites often use menu blocks or product items."""
    soup = BeautifulSoup(html, "html.parser")
    items = []

    # Squarespace menu block
    for selectors in [
        {"container": ".menu-item", "name": ".menu-item-title", "price": ".menu-item-price-bottom", "desc": ".menu-item-description"},
        {"container": ".sqs-block-menu .menu-section-item", "name": ".menu-item-title", "price": ".menu-item-price", "desc": ".menu-item-description"},
        {"container": ".product-item", "name": ".product-title", "price": ".product-price", "desc": ".product-excerpt"},
        {"container": ".menu-section-item", "name": "h3", "price": ".price", "desc": "p"},
    ]:
        containers = soup.select(selectors["container"])
        if not containers:
            continue
        for container in containers:
            item = _extract_from_container(container, selectors)
            if item:
                items.append(item)
        if items:
            return items

    return items


def _extract_wordpress(html: str) -> list[dict]:
    """WordPress with popular menu plugins (flavor, flavor-developer, flavor-developer, flavor-developer, flavor-developer, flavor-developer, flavor-developer)."""
    soup = BeautifulSoup(html, "html.parser")
    items = []

    # Common WordPress menu plugin patterns
    for selectors in [
        # flavor developer plugin
        {"container": ".flavor-menu-item", "name": ".flavor-menu-item-name", "price": ".flavor-menu-item-price", "desc": ".flavor-menu-item-description"},
        # flavor developer restaurant menu plugin
        {"container": ".flavor-developer-menu-item", "name": ".menu-item-name", "price": ".menu-item-price", "desc": ".menu-item-description"},
        # flavor developer restaurant menu plugin
        {"container": ".flavor-developer-menu-item", "name": ".menu-item-name", "price": ".menu-item-price", "desc": ".menu-item-description"},
        # flavor developer  developer  developer  developer  developer  developer  developer  developer  developer  developer  developer  developer  developer  developer  developer  developer  developer  developer  developer developer plugin - flavor developer plugin - flavor developer  - flavor developer (also known as flavor)
        {"container": ".flavor-item", "name": ".flavor-item-name", "price": ".flavor-item-price", "desc": ".flavor-item-desc"},
        # flavor developer  developer  developer  developer  developer  developer  developer  developer  developer  developer  developer  developer  developer  developer  developer  developer  developer  developer  developer  developer  developer  developer  developer  developer  developer  developer  developer  developer   - flavor developer    - flavor developer   - flavor plugin
        # flavor developer   - flavor developer  - flavor developer
        # flavor developer  - flavor developer  - flavor developer
        # flavor developer - Five Star Restaurant Menu
        {"container": ".flavor-developer-item", "name": "h4", "price": ".price", "desc": "p"},
        # flavor developer - flavor developer - flavor developer - flavor developer - flavor developer - flavor developer - flavor developer - flavor developer - flavor developer - WP Restaurant Menu plugin
        {"container": ".flavor-developer-wp-restaurant-item", "name": ".wp-restaurant-item-name", "price": ".wp-restaurant-item-price", "desc": ".wp-restaurant-item-desc"},
        # flavor developer - flavor developer - flavor developer  - flavor developer  - flavor developer  - flavor developer  - flavor developer  - flavor developer  - flavor developer  - flavor developer  - flavor developer  - flavor developer  - flavor developer  - Food Menu Pro
        {"container": ".flavor-developer-food-menu-item", "name": ".food-menu-item-name", "price": ".food-menu-item-price", "desc": ".food-menu-item-desc"},
        # Generic WordPress patterns
        {"container": ".menu-item-wrap", "name": ".menu-item-title", "price": ".menu-item-price", "desc": ".menu-item-desc"},
        {"container": ".menu-list-item", "name": ".menu-title", "price": ".menu-price", "desc": ".menu-desc"},
        {"container": ".food-menu-item", "name": ".food-item-title", "price": ".food-item-price", "desc": ".food-item-desc"},
        {"container": ".restaurant-menu-item", "name": "h4", "price": ".price", "desc": "p"},
        {"container": ".menu_item", "name": "h4", "price": ".item_price", "desc": ".item_desc"},
        {"container": ".fdm-item", "name": ".fdm-item-title", "price": ".fdm-item-price", "desc": ".fdm-item-content"},
    ]:
        containers = soup.select(selectors["container"])
        if not containers:
            continue
        for container in containers:
            item = _extract_from_container(container, selectors)
            if item:
                items.append(item)
        if items:
            return items

    return items


def _extract_wix(html: str) -> list[dict]:
    """Wix Restaurants has data attributes and specific component classes."""
    soup = BeautifulSoup(html, "html.parser")
    items = []

    for selectors in [
        {"container": "[data-hook='menu-item']", "name": "[data-hook='menu-item-title']", "price": "[data-hook='menu-item-price']", "desc": "[data-hook='menu-item-description']"},
        {"container": ".s3dcXM", "name": ".WRyJvd", "price": ".IHk6Ag", "desc": ".dHb9dM"},
        {"container": ".wixrest-menu-item", "name": ".item-title", "price": ".item-price", "desc": ".item-description"},
    ]:
        containers = soup.select(selectors["container"])
        if not containers:
            continue
        for container in containers:
            item = _extract_from_container(container, selectors)
            if item:
                items.append(item)
        if items:
            return items

    return items


def _extract_bentobox(html: str) -> list[dict]:
    """BentoBox is common for upscale restaurants."""
    soup = BeautifulSoup(html, "html.parser")
    items = []

    for selectors in [
        {"container": ".menu-item", "name": ".menu-item__name", "price": ".menu-item__price", "desc": ".menu-item__description"},
        {"container": ".c-menu-item", "name": ".c-menu-item__title", "price": ".c-menu-item__price", "desc": ".c-menu-item__description"},
    ]:
        containers = soup.select(selectors["container"])
        if not containers:
            continue
        for container in containers:
            item = _extract_from_container(container, selectors)
            if item:
                items.append(item)
        if items:
            return items

    return items


def _extract_popmenu(html: str) -> list[dict]:
    """Popmenu sites."""
    soup = BeautifulSoup(html, "html.parser")
    items = []

    for selectors in [
        {"container": ".menu-item", "name": ".menu-item-name", "price": ".menu-item-price", "desc": ".menu-item-description"},
        {"container": "[class*='MenuItem']", "name": "[class*='ItemName']", "price": "[class*='ItemPrice']", "desc": "[class*='ItemDesc']"},
    ]:
        containers = soup.select(selectors["container"])
        if not containers:
            continue
        for container in containers:
            item = _extract_from_container(container, selectors)
            if item:
                items.append(item)
        if items:
            return items

    return items


def _extract_from_container(container: Tag, selectors: dict) -> dict | None:
    """Extract a menu item from an HTML container using CSS selectors."""
    name_el = container.select_one(selectors["name"])
    if not name_el:
        return None

    name = name_el.get_text(strip=True)
    if not name or len(name) > 200:
        return None

    price_el = container.select_one(selectors["price"])
    desc_el = container.select_one(selectors["desc"])

    price = None
    if price_el:
        price_text = price_el.get_text(strip=True)
        price = _parse_price(price_text)

    description = None
    if desc_el and desc_el != name_el:
        desc_text = desc_el.get_text(strip=True)
        if desc_text and desc_text != name:
            description = desc_text[:500]

    # Fallback: look for any <p>, <span>, or <div> with descriptive text in the container
    if not description:
        for tag in container.find_all(["p", "span", "div"], recursive=True):
            if tag == name_el or tag == price_el:
                continue
            text = tag.get_text(strip=True)
            if text and text != name and 10 < len(text) < 300 and not re.search(r"^\$?\d+\.?\d*$", text):
                description = text[:500]
                break

    return {
        "name": name,
        "description": description,
        "price": price,
        "category": None,
    }


def _parse_price(text: str) -> float | None:
    """Parse a price string like '$12.99' or '12.50'."""
    if not text:
        return None
    match = re.search(r"\$?\s*(\d{1,4}(?:[.,]\d{1,2})?)", text)
    if match:
        try:
            return float(match.group(1).replace(",", "."))
        except ValueError:
            return None
    return None


_PLATFORM_EXTRACTORS = {
    "toast": _extract_toast,
    "squarespace": _extract_squarespace,
    "wordpress": _extract_wordpress,
    "wix": _extract_wix,
    "bentobox": _extract_bentobox,
    "popmenu": _extract_popmenu,
}
