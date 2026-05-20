"""Extract menu items using price-pattern heuristics.

Scans HTML for price patterns ($XX.XX) near text to identify menu items
without any LLM calls. Works on any site that displays prices.
"""
import logging
import re

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

# Matches prices like $12, $12.99, $1,299.00
_PRICE_RE = re.compile(r"\$\s*(\d{1,4}(?:,\d{3})*(?:\.\d{1,2})?)")
# Also matches bare decimal prices like 22.95 (must have decimal to avoid matching random numbers)
_BARE_PRICE_RE = re.compile(r"(?<!\d)(\d{1,3}\.\d{2})(?!\d)")

# Elements that commonly contain menu items
_ITEM_TAGS = {"div", "li", "tr", "article", "section", "p", "span"}

# Min/max reasonable price for a menu item
_MIN_PRICE = 1.0
_MAX_PRICE = 500.0

# Things that are NOT menu items
_BLACKLIST_PATTERNS = re.compile(
    r"(gift\s*card|merchandise|merch|shipping|delivery\s*fee|service\s*charge|"
    r"tax|gratuity|tip|reservation|booking|private\s*event|catering|"
    r"minimum\s*order|subtotal|total|checkout)",
    re.I,
)


def extract_from_heuristics(html: str) -> list[dict] | None:
    """Extract menu items by finding price patterns near food-like text.

    Returns items or None if fewer than 3 found.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove noise
    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "iframe", "noscript"]):
        tag.decompose()

    items = []
    seen_names = set()

    # Strategy 1: Find elements that contain exactly one price
    for element in soup.find_all(_ITEM_TAGS):
        text = element.get_text(strip=True)
        if not text or len(text) < 3 or len(text) > 500:
            continue

        # Try $-prefixed prices first, then bare decimals
        prices = _PRICE_RE.findall(text)
        if len(prices) != 1:
            prices = _BARE_PRICE_RE.findall(text)
        if len(prices) != 1:
            continue

        price_val = _parse_price_str(prices[0])
        if price_val is None or price_val < _MIN_PRICE or price_val > _MAX_PRICE:
            continue

        # Extract the name (text before the price)
        name = _extract_name_from_text(text)
        if not name or len(name) < 2 or len(name) > 150:
            continue

        if _BLACKLIST_PATTERNS.search(name):
            continue

        # Split name from description if they're concatenated
        description = _extract_description(element, name)
        name, split_desc = _split_name_description(name)
        if split_desc and not description:
            description = split_desc

        if not name or len(name) < 2:
            continue

        # Deduplicate
        name_key = name.lower().strip()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Check this isn't a deeply nested child (avoid double-counting)
        if _has_price_ancestor(element):
            continue

        items.append({
            "name": name,
            "description": description,
            "price": price_val,
            "category": None,
        })

    # Strategy 2: Look for table rows with name + price columns
    if len(items) < 3:
        table_items = _extract_from_tables(soup)
        # Merge, avoiding duplicates
        for item in table_items:
            name_key = item["name"].lower().strip()
            if name_key not in seen_names:
                seen_names.add(name_key)
                items.append(item)

    if len(items) >= 3:
        logger.info(f"Heuristic extractor found {len(items)} items")
        return items

    return None


def _split_name_description(name: str) -> tuple[str, str | None]:
    """Split a name that might have a description concatenated.

    E.g. 'Sushi Combo - A5pcs Sushi (Salmon, Tuna)' -> ('Sushi Combo - A', '5pcs Sushi (Salmon, Tuna)')
    E.g. 'EdamameSpicy soy beans' -> ('Edamame', 'Spicy soy beans')
    """
    # Pattern: CamelCase smush — uppercase letter after lowercase (e.g. "EdamameSteamed")
    match = re.search(r"([a-z)0-9])([A-Z][a-z])", name)
    if match and match.start() > 2:
        split_at = match.start() + 1
        title = name[:split_at].strip()
        desc = name[split_at:].strip()
        if len(title) >= 2 and len(desc) >= 5:
            return title, desc

    # Pattern: text followed by digits starting a new phrase (e.g. "Combo - A5pcs")
    match = re.search(r"([A-Za-z) ]{3,})(\d+\s*pcs|\d+\s*pieces|\d+\s*oz)", name, re.I)
    if match:
        title = name[: match.start(2)].strip()
        desc = name[match.start(2) :].strip()
        if len(title) >= 2 and len(desc) >= 3:
            return title, desc

    return name, None


def _extract_name_from_text(text: str) -> str | None:
    """Extract the menu item name from text that contains a price."""
    # Remove the price part (try both patterns)
    name = _PRICE_RE.sub("", text).strip()
    name = _BARE_PRICE_RE.sub("", name).strip()
    # Remove common separators
    name = re.sub(r"[\.\-–—]{2,}$", "", name).strip()
    name = re.sub(r"^\s*[\.\-–—]+\s*", "", name).strip()
    # Remove trailing dots/dashes (price leader dots)
    name = re.sub(r"[\s\.\-–—]+$", "", name).strip()

    if not name:
        return None

    # If the remaining text is too long, it probably includes a description
    # Take just the first line
    lines = [l.strip() for l in name.split("\n") if l.strip()]
    if lines:
        return lines[0]

    return name


def _extract_description(element: Tag, name: str) -> str | None:
    """Try to find a description near the name element."""
    # Strategy 1: Look for child elements with descriptive text
    for child in element.children:
        if isinstance(child, Tag):
            child_text = child.get_text(strip=True)
            if (
                child_text
                and child_text != name
                and not _PRICE_RE.search(child_text)
                and 10 < len(child_text) < 300
            ):
                return child_text

    # Strategy 2: If the element has multi-line text, split name from description
    full_text = element.get_text(separator="\n", strip=True)
    lines = [l.strip() for l in full_text.split("\n") if l.strip()]
    # Find lines that aren't the name and don't contain prices
    desc_lines = []
    for line in lines:
        if line == name or _PRICE_RE.search(line):
            continue
        if 5 < len(line) < 300 and not line.startswith("$"):
            desc_lines.append(line)
    if desc_lines:
        return " ".join(desc_lines)[:500]

    # Strategy 3: Check next sibling element
    next_sib = element.find_next_sibling()
    if next_sib and isinstance(next_sib, Tag):
        sib_text = next_sib.get_text(strip=True)
        if (
            sib_text
            and not _PRICE_RE.search(sib_text)
            and 10 < len(sib_text) < 300
            and sib_text != name
        ):
            return sib_text

    return None


def _has_price_ancestor(element: Tag) -> bool:
    """Check if any ancestor (up to 3 levels) also contains a price.

    This prevents extracting from deeply nested elements when the
    parent is already being processed.
    """
    parent = element.parent
    for _ in range(3):
        if parent is None or parent.name in ("body", "html", "[document]"):
            break
        if parent.name in _ITEM_TAGS:
            parent_text = parent.get_text(strip=True)
            parent_prices = _PRICE_RE.findall(parent_text)
            if len(parent_prices) == 1:
                return True
        parent = parent.parent
    return False


def _extract_from_tables(soup: BeautifulSoup) -> list[dict]:
    """Extract menu items from HTML tables."""
    items = []

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            # Find the cell with a price
            price_cell = None
            name_cell = None
            for cell in cells:
                cell_text = cell.get_text(strip=True)
                if _PRICE_RE.search(cell_text):
                    price_cell = cell
                elif cell_text and len(cell_text) > 2 and not price_cell:
                    name_cell = cell

            if not price_cell or not name_cell:
                continue

            name = name_cell.get_text(strip=True)
            price_text = price_cell.get_text(strip=True)
            price_match = _PRICE_RE.search(price_text) or _BARE_PRICE_RE.search(price_text)

            if not name or not price_match or _BLACKLIST_PATTERNS.search(name):
                continue

            price_val = _parse_price_str(price_match.group(1))
            if price_val and _MIN_PRICE <= price_val <= _MAX_PRICE:
                items.append({
                    "name": name,
                    "description": None,
                    "price": price_val,
                    "category": None,
                })

    return items


def _parse_price_str(price_str: str) -> float | None:
    try:
        return float(price_str.replace(",", ""))
    except (ValueError, TypeError):
        return None
