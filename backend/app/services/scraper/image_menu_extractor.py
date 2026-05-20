"""Extract menu items from images embedded on restaurant pages.

Some restaurants display their menu as images (photos of physical menus,
designed graphics, etc.) directly on their website instead of text or PDF.
We detect likely menu images by size/aspect ratio and use Claude vision to read them.
"""
import base64
import io
import json
import logging
import re
from urllib.parse import urljoin

import anthropic
import httpx
from bs4 import BeautifulSoup

from app.core.config import settings

logger = logging.getLogger(__name__)

# Menu images tend to be tall (portrait) and large
_MIN_AREA = 400_000  # minimum width*height to consider
_MIN_HEIGHT = 600


_VISION_PROMPT = """Extract all menu items from this restaurant menu image.

Return a JSON array where each item has:
- "name": string (dish name)
- "description": string or null (dish description)
- "price": number or null (price in dollars, no $ sign)
- "category": string or null (e.g., "appetizer", "entree", "dessert", "drink", "side", "soup", "salad")

Rules:
- Only extract actual food/drink items, not section headers or restaurant info
- If a price has a range like "$12-15", use the lower price (12)
- Include descriptions when visible (ingredients, preparation details)
- If the image is NOT a menu (it's a food photo, logo, etc.), return an empty array []

Return ONLY the JSON array, no other text."""


def find_menu_images(html: str, base_url: str) -> list[tuple[str, int]]:
    """Find images on the page that are likely menu photos.

    Returns list of (url, confidence_score) tuples, best candidates first.
    Only returns images above the minimum confidence threshold.

    Scoring is based purely on free metadata signals — no API calls:
    - Filename: "menu" in name = strong signal
    - Alt text: menu-related keywords
    - Dimensions: portrait/tall images (menus are usually vertical)
    - Context: surrounding HTML text mentions menu/prices
    - Page URL: being on a /menu page
    """
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[tuple[str, int]] = []
    seen_urls: set[str] = set()

    is_menu_page = any(kw in base_url.lower() for kw in ["/menu", "/food", "/dining"])

    for img in soup.find_all("img"):
        src = img.get("data-src") or img.get("src") or ""
        if not src:
            continue

        url = urljoin(base_url, src)
        clean_url = url.split("?")[0]
        if clean_url in seen_urls:
            continue
        seen_urls.add(clean_url)

        src_lower = src.lower()
        if any(skip in src_lower for skip in ["logo", "icon", "favicon", "avatar", "banner", "hero",
                                               "map", "yelp", "google", "facebook", "instagram",
                                               "twitter", "tripadvisor", "doordash"]):
            continue

        w, h = _get_dimensions(img)
        if w is None or h is None:
            continue

        area = w * h
        if area < _MIN_AREA or h < _MIN_HEIGHT:
            continue

        score = 0

        # --- Filename signals (strongest free signal) ---
        filename = src_lower.split("/")[-1]
        if "menu" in filename:
            score += 30
        if any(kw in filename for kw in ["price", "food-list", "carte", "speisekarte"]):
            score += 25
        # "screenshot" of a menu is common
        if "screenshot" in filename and is_menu_page:
            score += 15

        # Negative filename signals — food photos, gallery, ambiance
        if any(kw in filename for kw in ["food", "dish", "plate", "gallery", "interior",
                                         "ambiance", "event", "team", "staff", "chef",
                                         "dog", "pet", "flyer", "promo", "coupon"]):
            score -= 20

        # --- Alt text signals ---
        alt = (img.get("alt") or "").lower()
        if any(kw in alt for kw in ["menu", "food menu", "dinner menu", "lunch menu", "price list"]):
            score += 25
        if any(kw in alt for kw in ["photo", "gallery", "ambiance", "interior"]):
            score -= 15

        # --- Aspect ratio (menus are portrait/tall) ---
        aspect = h / w if w > 0 else 0
        if aspect > 1.3:
            score += 15  # Strongly portrait = menu-like
        elif aspect > 1.0:
            score += 5
        elif aspect < 0.7:
            score -= 10  # Wide landscape = food photo

        # --- Size signals ---
        if area > 1_500_000:
            score += 5

        # --- Context: surrounding HTML ---
        parent = img.parent
        for _ in range(3):
            if parent is None:
                break
            parent_text = parent.get_text(strip=True).lower()[:300]
            if any(kw in parent_text for kw in ["menu", "price", "appetizer", "entree",
                                                 "dessert", "our food", "what we serve"]):
                score += 10
                break
            parent = parent.parent

        # --- Page context ---
        if is_menu_page:
            score += 10

        # Only include candidates above minimum threshold
        if score >= _MIN_CONFIDENCE:
            candidates.append((url, score))

    candidates.sort(key=lambda x: -x[1])
    return candidates[:5]


# Minimum confidence score to attempt vision extraction on an image.
# Set high to avoid wasting money on food photos/ads.
# Only images with strong filename/alt text signals ("menu" in name) will pass.
# Score guide: "menu" in filename = 30, portrait aspect = 15, on /menu page = 10
# So an image needs at least a filename match OR multiple weaker signals.
_MIN_CONFIDENCE = 25


async def extract_from_menu_images(html: str, base_url: str) -> list[dict] | None:
    """Find and extract menu items from images on the page.

    Returns items or None if no menu images found or extraction fails.
    """
    candidates = find_menu_images(html, base_url)
    if not candidates:
        return None

    logger.info(f"Found {len(candidates)} potential menu images on {base_url}")
    for url, score in candidates:
        fname = url.split("/")[-1][:60]
        logger.info(f"  score={score:>3}  {fname}")

    all_items: list[dict] = []
    seen_names: set[str] = set()

    for img_url, score in candidates:
        items = await _extract_from_image_url(img_url)
        if not items:
            continue

        # Post-validation: real menus have prices
        items_with_price = sum(1 for i in items if i.get("price") is not None)
        price_ratio = items_with_price / len(items) if items else 0

        if price_ratio < 0.3 and items_with_price < 3:
            fname = img_url.split("/")[-1][:60]
            logger.info(f"Skipping image {fname}: only {items_with_price}/{len(items)} items have prices (not a real menu)")
            continue

        for item in items:
            name_key = item["name"].lower().strip()
            if name_key not in seen_names:
                seen_names.add(name_key)
                all_items.append(item)

    if len(all_items) >= 3:
        logger.info(f"Image menu extractor found {len(all_items)} items")
        return all_items

    return None


async def _extract_from_image_url(url: str) -> list[dict] | None:
    """Download an image and extract menu items with vision."""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            img_bytes = resp.content
            content_type = resp.headers.get("content-type", "image/jpeg")
    except Exception as e:
        logger.warning(f"Failed to download image {url}: {e}")
        return None

    # Determine media type
    if "png" in content_type:
        media_type = "image/png"
    elif "webp" in content_type:
        media_type = "image/webp"
    else:
        media_type = "image/jpeg"

    b64 = base64.b64encode(img_bytes).decode("utf-8")

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    try:
        response = await client.messages.create(
            model=settings.llm_model,
            max_tokens=8192,
            temperature=0,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                    {"type": "text", "text": _VISION_PROMPT},
                ],
            }],
        )

        text = response.content[0].text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        items = json.loads(text)
        if not isinstance(items, list):
            return None

        return [
            {
                "name": item.get("name", ""),
                "description": item.get("description"),
                "price": _safe_float(item.get("price")),
                "category": item.get("category"),
            }
            for item in items
            if item.get("name")
        ]
    except (json.JSONDecodeError, anthropic.APIError) as e:
        logger.error(f"Vision extraction failed for {url}: {e}")
        return None


def _get_dimensions(img) -> tuple[int | None, int | None]:
    """Extract image dimensions from HTML attributes."""
    # Try data-image-dimensions (Squarespace)
    dims = img.get("data-image-dimensions", "")
    if "x" in dims:
        parts = dims.split("x")
        try:
            return int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            pass

    # Try width/height attributes
    w = img.get("width")
    h = img.get("height")
    if w and h:
        try:
            return int(w), int(h)
        except ValueError:
            pass

    return None, None


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
