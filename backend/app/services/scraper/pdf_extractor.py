"""Extract menu items from PDF menus.

Many restaurants link to PDF menus. We download the PDF, extract text,
then use price-pattern heuristics to find menu items.

For image-based PDFs (no extractable text), falls back to converting
pages to images and using Claude's vision to read them.
"""
import base64
import io
import logging
import json
import re

import anthropic
import httpx
import pdfplumber

from app.core.config import settings

logger = logging.getLogger(__name__)

_PRICE_RE = re.compile(r"\$?\s*(\d{1,3}\.\d{2})")

_BLACKLIST = re.compile(
    r"(gift\s*card|delivery|service\s*charge|tax|gratuity|tip|"
    r"reservation|private\s*event|catering|minimum|subtotal|total|"
    r"checkout|all rights|copyright|follow us|instagram|facebook)",
    re.I,
)

_MIN_PRICE = 1.0
_MAX_PRICE = 500.0


async def extract_from_pdf_url(url: str, free_only: bool = False) -> list[dict] | None:
    """Download a PDF and extract menu items from it.

    Returns list of items or None if extraction fails.
    """
    try:
        pdf_bytes = await _download_pdf(url)
    except Exception as e:
        logger.warning(f"Failed to download PDF {url}: {e}")
        return None

    text = _extract_text_from_pdf(pdf_bytes)
    if text and len(text) >= 50:
        items = _parse_menu_from_text(text)
        if items and len(items) >= 3:
            logger.info(f"PDF text extractor found {len(items)} items from {url}")
            return items

    # Text extraction failed — likely an image-based PDF.
    if free_only:
        logger.info(f"PDF has no extractable text, skipping vision OCR (free_only=True): {url}")
        return None

    logger.info(f"PDF has no extractable text, trying vision OCR: {url}")
    items = await _extract_from_pdf_with_vision(pdf_bytes)
    if items and len(items) >= 3:
        logger.info(f"PDF vision extractor found {len(items)} items from {url}")
        return items

    return None


async def _download_pdf(url: str) -> bytes:
    """Download PDF content."""
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=20.0,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        },
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


def _extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from PDF preserving layout."""
    lines = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text(layout=True)
                if text:
                    lines.append(text)
    except Exception as e:
        logger.warning(f"PDF parsing failed: {e}")
        return ""

    return "\n".join(lines)


def _parse_menu_from_text(text: str) -> list[dict]:
    """Parse menu items from extracted PDF text using line-by-line analysis."""
    items = []
    seen_names = set()
    lines = text.split("\n")
    current_category = None

    for i, line in enumerate(lines):
        line = line.strip()
        if not line or len(line) < 3:
            continue

        # Detect category headers (ALL CAPS lines without prices)
        if (
            line.isupper()
            and len(line) > 3
            and len(line) < 40
            and not _PRICE_RE.search(line)
            and not _BLACKLIST.search(line)
        ):
            current_category = _normalize_category(line)
            continue

        # Find lines with prices
        price_match = _PRICE_RE.search(line)
        if not price_match:
            continue

        price_val = float(price_match.group(1))
        if price_val < _MIN_PRICE or price_val > _MAX_PRICE:
            continue

        # Extract name (text before the price)
        name = line[: price_match.start()].strip()
        # Clean up dots/dashes used as price leaders
        name = re.sub(r"[\s.\-–—]+$", "", name).strip()
        # Remove leading bullets/numbers
        name = re.sub(r"^[\d.)\-•*]+\s*", "", name).strip()

        if not name or len(name) < 2 or len(name) > 150:
            continue
        if _BLACKLIST.search(name):
            continue

        name_key = name.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Look for description on next line (if it has no price)
        description = None
        if i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if (
                next_line
                and not _PRICE_RE.search(next_line)
                and not next_line.isupper()
                and 5 < len(next_line) < 300
            ):
                description = next_line

        items.append({
            "name": name,
            "description": description,
            "price": price_val,
            "category": current_category,
        })

    return items


def _normalize_category(text: str) -> str | None:
    """Map a section header to a standard category."""
    text_lower = text.lower().strip()
    categories = {
        "appetizer": ["appetizer", "starter", "small plate", "aperitivo", "antojitos", "botanas"],
        "entree": ["entree", "entrée", "main", "platter", "large plate", "plato fuerte"],
        "salad": ["salad", "ensalada"],
        "soup": ["soup", "sopa"],
        "side": ["side", "accompaniment", "guarnicion"],
        "dessert": ["dessert", "postre", "sweet"],
        "drink": ["drink", "beverage", "cocktail", "wine", "beer", "bebida", "margarita"],
        "breakfast": ["breakfast", "brunch", "desayuno"],
        "lunch": ["lunch", "almuerzo"],
        "taco": ["taco"],
        "burrito": ["burrito"],
        "sandwich": ["sandwich", "torta"],
        "pizza": ["pizza"],
        "pasta": ["pasta"],
        "seafood": ["seafood", "mariscos", "pescado"],
        "sushi": ["sushi", "sashimi", "roll"],
    }
    for category, keywords in categories.items():
        if any(kw in text_lower for kw in keywords):
            return category
    return text_lower if len(text_lower) < 30 else None


_VISION_PROMPT = """Extract all menu items from this restaurant menu image.

Return a JSON array where each item has:
- "name": string (dish name)
- "description": string or null (dish description)
- "price": number or null (price in dollars, no $ sign)
- "category": string or null (e.g., "appetizer", "entree", "dessert", "drink", "side", "soup", "salad", "taco", "burrito", "seafood", "pasta")

Rules:
- Only extract actual food/drink items, not section headers or restaurant info
- If a price has a range like "$12-15", use the lower price (12)
- Ignore items that are clearly not food (merchandise, gift cards, etc.)
- Include descriptions when visible (ingredients, preparation details)
- If no menu items are found, return an empty array []

Return ONLY the JSON array, no other text."""


async def _extract_from_pdf_with_vision(pdf_bytes: bytes) -> list[dict] | None:
    """Convert PDF pages to images and use Claude vision to extract menu items."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        logger.warning("pypdfium2 not installed, cannot do vision PDF extraction")
        return None

    # Convert PDF pages to images
    images = []
    try:
        pdf = pdfium.PdfDocument(pdf_bytes)
        # Limit to first 5 pages to control costs
        for i in range(min(len(pdf), 5)):
            page = pdf[i]
            # Render at 150 DPI for good quality without huge size
            bitmap = page.render(scale=150 / 72)
            pil_image = bitmap.to_pil()

            # Convert to JPEG bytes
            buf = io.BytesIO()
            pil_image.save(buf, format="JPEG", quality=80)
            images.append(buf.getvalue())
        pdf.close()
    except Exception as e:
        logger.warning(f"Failed to convert PDF to images: {e}")
        return None

    if not images:
        return None

    # Send images to Claude vision
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    # Build content with all page images
    content = []
    for img_bytes in images:
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
        })
    content.append({"type": "text", "text": _VISION_PROMPT})

    try:
        response = await client.messages.create(
            model=settings.llm_model,
            max_tokens=8192,
            temperature=0,
            messages=[{"role": "user", "content": content}],
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
        logger.error(f"Vision PDF extraction failed: {e}")
        return None


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
