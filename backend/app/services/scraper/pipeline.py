import logging
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.scraper.heuristic_extractor import extract_from_heuristics
from app.services.scraper.image_menu_extractor import extract_from_menu_images
from app.services.scraper.llm_extractor import LLMExtractor
from app.services.scraper.pattern_registry import PatternRegistry
from app.services.scraper.pdf_extractor import extract_from_pdf_url
from app.services.scraper.platform_detector import detect_platform, fetch_light
from app.services.scraper.wayback_fetcher import fetch_from_wayback
from app.services.scraper.platform_extractors import extract_from_platform
from app.services.scraper.structured_data_extractor import extract_from_structured_data

logger = logging.getLogger(__name__)

# Patterns that indicate a link points to a menu page
_MENU_LINK_RE = re.compile(
    r"\b(menu|food|dining|eat|carte|speisekarte|dishes|full.?menu|"
    r"lunch|dinner|brunch|breakfast|drinks?|cocktails?|wine.?list|"
    r"appetizers?|entrees?|starters?)\b",
    re.I,
)

# Fallback paths only used if no menu links found in HTML (kept short to save time/cost)
_FALLBACK_PATHS = ["/menu", "/menus", "/food-menu", "/our-menu"]

# External domains that are known menu/ordering platforms — treat as valid menu links
_MENU_PLATFORM_DOMAINS = {
    "menoves-online.com",
    "order.toasttab.com",
    "www.toasttab.com",
    "order.online",
    "www.clover.com",
    "squareup.com",
    "square.site",
    "order.mealkeyway.com",
    "www.doordash.com",
    "www.ubereats.com",
    "www.grubhub.com",
    "www.seamless.com",
    "www.postmates.com",
    "www.caviar.com",
    "www.olo.com",
    "direct.chownow.com",
    "www.chownow.com",
    "ordering.chownow.com",
    "www.popmenu.com",
    "restaurant.eatstreet.com",
    "www.beyondmenu.com",
    "www.bfresco.com",
    "www.menufy.com",
    "order.spoton.com",
    "getbento.com",
    "www.getbento.com",
    "order.slice.com",
    "slicelife.com",
    "www.happydinermenu.com",
    "www.allmenus.com",
}


@dataclass
class ScrapeResult:
    items: list[dict]
    platform_type: str
    used_pattern: bool  # True if any free method was used, False if LLM was used
    extraction_method: str  # "structured_data", "platform", "pattern", "heuristic", "llm", "none"


def _find_menu_links(html: str, base_url: str) -> list[str]:
    """Scan HTML for links that likely point to menu pages.

    Returns deduplicated, absolute URLs sorted by relevance.
    """
    soup = BeautifulSoup(html, "html.parser")
    base_domain = urlparse(base_url).netloc
    scored_urls: dict[str, int] = {}

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue

        # Build absolute URL
        url = urljoin(base_url, href)
        parsed = urlparse(url)

        # Skip non-http
        if parsed.scheme not in ("http", "https", ""):
            continue

        # Check if external link
        is_external = parsed.netloc and parsed.netloc != base_domain
        is_known_platform = parsed.netloc in _MENU_PLATFORM_DOMAINS

        # Score by link text + href path
        link_text = a.get_text(strip=True).lower()
        href_lower = href.lower()
        score = 0

        # PDF links on a menu page are almost certainly the menu
        is_pdf = href_lower.endswith(".pdf")
        if is_pdf:
            score += 15

        # Check link text
        text_has_menu = _MENU_LINK_RE.search(link_text)
        if text_has_menu:
            score += 10
        # Check href/path
        if _MENU_LINK_RE.search(href_lower):
            score += 5
        # Check aria-label, title
        for attr in ("aria-label", "title"):
            val = a.get(attr, "")
            if val and _MENU_LINK_RE.search(val.lower()):
                score += 3

        # Boost exact "menu" matches and common button labels
        if link_text in ("menu", "our menu", "view menu", "full menu", "see menu",
                         "see menu & order online", "order online", "order now",
                         "view our menu", "browse menu", "view", "download menu",
                         "download", "see our menu", "food menu"):
            score += 20
        if "/menu" in href_lower and href_lower.count("/") <= 3:
            score += 10

        # For external links: allow if link text/href indicates a menu, or known platform
        if is_external:
            if is_known_platform:
                score += 8  # Boost known platforms
            elif score >= 10:
                pass  # Link text/href clearly says menu — trust the restaurant's own links
            else:
                continue  # No menu signal — skip random external links

        # Skip links to same page
        clean_url = url.split("?")[0].split("#")[0].rstrip("/")
        clean_base = base_url.split("?")[0].split("#")[0].rstrip("/")
        if clean_url == clean_base:
            continue

        if score > 0:
            # Deduplicate by cleaned URL
            if clean_url not in scored_urls or scored_urls[clean_url] < score:
                scored_urls[clean_url] = score

    # Scan raw HTML for menu URLs in JSON data, scripts, and data attributes.
    # Many SPAs embed URLs in JSON, not in <a> tags. This catches:
    #   - Popmenu: "/san-diego-menu" in JSON props
    #   - Toast: "menulandingpageurl":"https://..."
    #   - Generic: "/menu/dinner", "/menu/lunch" as route paths
    import re as _re
    # Pattern 1: paths containing "-menu" (e.g. /san-diego-menu)
    # Pattern 2: paths starting with /menu/ (e.g. /menu/dinner)
    # Pattern 3: full URLs with menu in path
    for pattern in [
        r'["\']((?:/|https?://[^"\']+/)[\w-]+-menu(?:/[\w-]*)?)["\']',
        r'["\'](/menu/[\w-]+(?:/[\w-]*)?)["\']',
        r'"(https?://[^"]+/menu[^"]*)"',
    ]:
        for match in _re.finditer(pattern, html, _re.I):
            raw = match.group(1)
            url = urljoin(base_url, raw) if raw.startswith("/") else raw
            clean = url.split("?")[0].split("#")[0].rstrip("/")
            clean_base = base_url.split("?")[0].split("#")[0].rstrip("/")
            if clean != clean_base and clean not in scored_urls:
                # Higher score for same-domain URLs
                parsed = urlparse(clean)
                if parsed.netloc == base_domain:
                    scored_urls[clean] = 15
                elif parsed.netloc:
                    scored_urls[clean] = 10

    # Sort by score descending, return top 8
    sorted_urls = sorted(scored_urls.items(), key=lambda x: -x[1])
    return [url for url, _ in sorted_urls[:8]]


class ScrapingPipeline:
    """Orchestrates the menu scraping process.

    Extraction priority (cheapest first):
    1. JSON-LD / Schema.org structured data (free, most reliable)
    2. Platform-specific CSS extractors (free, hardcoded for Toast/Squarespace/etc.)
    3. Learned CSS patterns from Pattern Registry (free, learned from prior LLM runs)
    4. Price-pattern heuristics (free, finds $XX.XX near text)
    5. LLM extraction (costs ~$0.003-0.005, last resort)

    If landing page has no menu, discovers menu links from the page's <a> tags
    instead of blindly guessing paths.
    """

    def __init__(self, db: AsyncSession, free_only: bool = False):
        self.db = db
        self.free_only = free_only
        self.pattern_registry = PatternRegistry(db)
        self.llm_extractor = None if free_only else LLMExtractor()

    async def _fetch(self, url: str) -> tuple[str, str] | None:
        """Fetch a URL with full browser fallback. Tries Wayback on failure."""
        try:
            return await detect_platform(url)
        except Exception as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            # Try Wayback Machine as last resort
            wayback_html = await fetch_from_wayback(url)
            if wayback_html:
                from app.services.scraper.platform_detector import _detect_platform_from_html
                return _detect_platform_from_html(wayback_html), wayback_html
            return None

    @staticmethod
    async def _fetch_light(url: str) -> tuple[str, str] | None:
        """Lightweight fetch — httpx only, no browser. For speculative/fallback URLs."""
        return await fetch_light(url)

    async def _try_free_extraction(self, html: str, platform_type: str) -> tuple[list[dict], str] | None:
        """Try all free extraction methods in priority order.

        Returns (items, method_name) or None.
        """
        # 1. Structured data (JSON-LD / Schema.org)
        items = extract_from_structured_data(html)
        if items:
            return items, "structured_data"

        # 2. Platform-specific hardcoded extractors
        items = extract_from_platform(html, platform_type)
        if items:
            return items, "platform"

        # 3. Learned CSS patterns from registry
        pattern = await self.pattern_registry.get_pattern(platform_type)
        if pattern:
            items = self.pattern_registry.try_extract_with_selectors(html, pattern)
            if items:
                return items, "pattern"

        # 4. Price-pattern heuristics
        items = extract_from_heuristics(html)
        if items:
            return items, "heuristic"

        return None

    async def _discover_menu_urls(self, html: str, website_url: str) -> tuple[list[str], bool]:
        """Find menu page URLs by scanning links in the HTML.

        Returns (urls, is_discovered). If is_discovered=True, these are real links
        found on the page (worth using browser). If False, they're guessed fallback
        paths (use lightweight httpx-only fetch to save time).
        """
        urls = _find_menu_links(html, website_url)
        if urls:
            logger.info(f"Found {len(urls)} menu links on {website_url}")
            return urls, True

        logger.info(f"No menu links found on {website_url}, trying fallback paths")
        fallbacks = [
            urljoin(website_url.rstrip("/") + "/", path.lstrip("/"))
            for path in _FALLBACK_PATHS
        ]
        return fallbacks, False

    async def scrape_menu(self, website_url: str) -> ScrapeResult:
        """Scrape menu items from a restaurant website."""
        # Step 1: Fetch landing page
        result = await self._fetch(website_url)

        # If blocked, try Wayback Machine before giving up
        if not result:
            logger.info(f"Live fetch failed for {website_url}, trying Wayback Machine")
            wayback_html = await fetch_from_wayback(website_url)
            if wayback_html:
                from app.services.scraper.platform_detector import _detect_platform_from_html
                platform_type = _detect_platform_from_html(wayback_html)
                result = (platform_type, wayback_html)

        if not result:
            return ScrapeResult(items=[], platform_type="unknown", used_pattern=False, extraction_method="none")

        platform_type, html = result
        logger.info(f"Detected platform '{platform_type}' for {website_url}")

        # Step 2: Try free extraction on landing page
        free_result = await self._try_free_extraction(html, platform_type)
        if free_result:
            items, method = free_result
            logger.info(f"[FREE:{method}] Extracted {len(items)} items from {website_url}")
            return ScrapeResult(items=items, platform_type=platform_type, used_pattern=True, extraction_method=method)

        # Step 3: Discover menu links from the page
        menu_urls, urls_are_discovered = await self._discover_menu_urls(html, website_url)
        # Use full fetch (with browser) for discovered links, light fetch for fallback guesses
        fetch_fn = self._fetch if urls_are_discovered else self._fetch_light

        # Step 3a: Try PDF links first — collect items from ALL PDFs (lunch + dinner + drinks)
        pdf_urls = [u for u in menu_urls if u.lower().endswith(".pdf")]
        all_pdf_items: list[dict] = []
        seen_names: set[str] = set()
        for pdf_url in pdf_urls[:5]:  # Cap at 5 PDFs
            items = await extract_from_pdf_url(pdf_url, free_only=self.free_only)
            if items:
                for item in items:
                    name_key = item["name"].lower().strip()
                    if name_key not in seen_names:
                        seen_names.add(name_key)
                        all_pdf_items.append(item)
        if len(all_pdf_items) >= 3:
            logger.info(f"[PDF] Extracted {len(all_pdf_items)} items from {len(pdf_urls)} PDFs")
            return ScrapeResult(items=all_pdf_items, platform_type=platform_type, used_pattern=True, extraction_method="pdf")

        # Step 3b: Try HTML menu pages with free extraction
        # Cache all fetched pages to avoid re-fetching in later steps
        fetched_pages: list[tuple[str, str]] = [(website_url, html)]
        second_level_urls: list[str] = []

        for menu_url in menu_urls:
            if menu_url.lower().endswith(".pdf"):
                continue

            result = await fetch_fn(menu_url)
            if not result:
                continue

            _, menu_html = result
            fetched_pages.append((menu_url, menu_html))

            # If this is an ordering platform with a location picker (no menu items),
            # scan for location names and try them as URL subpaths
            if not self._html_has_prices(menu_html):
                location_urls = self._find_location_urls(menu_html, menu_url)
                for loc_url in location_urls[:3]:
                    loc_result = await fetch_fn(loc_url)
                    if loc_result:
                        fetched_pages.append((loc_url, loc_result[1]))

            free_result = await self._try_free_extraction(menu_html, platform_type)
            if free_result:
                items, method = free_result
                logger.info(f"[FREE:{method}] Extracted {len(items)} items from {menu_url}")
                return ScrapeResult(items=items, platform_type=platform_type, used_pattern=True, extraction_method=method)

            # No items — scan for deeper links (PDFs, sub-menu pages)
            deeper_links = _find_menu_links(menu_html, menu_url)
            for link in deeper_links:
                if link not in menu_urls and link not in second_level_urls:
                    second_level_urls.append(link)

        # Step 3c: Try second-level discovered links (PDFs first, then HTML)
        if second_level_urls:
            logger.info(f"Found {len(second_level_urls)} second-level menu links")
            pdf_urls_2 = [u for u in second_level_urls if u.lower().endswith(".pdf")]
            all_pdf_items_2: list[dict] = []
            seen_names_2: set[str] = set()
            for pdf_url in pdf_urls_2[:5]:
                items = await extract_from_pdf_url(pdf_url, free_only=self.free_only)
                if items:
                    for item in items:
                        name_key = item["name"].lower().strip()
                        if name_key not in seen_names_2:
                            seen_names_2.add(name_key)
                            all_pdf_items_2.append(item)
            if len(all_pdf_items_2) >= 3:
                logger.info(f"[PDF] Extracted {len(all_pdf_items_2)} items from {len(pdf_urls_2)} second-level PDFs")
                return ScrapeResult(items=all_pdf_items_2, platform_type=platform_type, used_pattern=True, extraction_method="pdf")

            for link_url in second_level_urls:
                if link_url.lower().endswith(".pdf"):
                    continue
                result = await self._fetch(link_url)
                if not result:
                    continue
                _, link_html = result
                fetched_pages.append((link_url, link_html))
                free_result = await self._try_free_extraction(link_html, platform_type)
                if free_result:
                    items, method = free_result
                    logger.info(f"[FREE:{method}] Extracted {len(items)} items from {link_url}")
                    return ScrapeResult(items=items, platform_type=platform_type, used_pattern=True, extraction_method=method)

        # Step 4: Check for menu images on cached pages (PAID — vision API)
        if not self.free_only:
            for page_url, page_html in fetched_pages:
                items = await extract_from_menu_images(page_html, page_url)
                if items:
                    logger.info(f"[IMAGE] Extracted {len(items)} items from menu images on {page_url}")
                    return ScrapeResult(items=items, platform_type=platform_type, used_pattern=False, extraction_method="image")

        # Step 5: LLM as last resort (PAID — Anthropic API)
        if not self.free_only:
            logger.info(f"Free extraction failed for {website_url}, falling back to LLM")
            pages_by_content = sorted(fetched_pages, key=lambda p: len(p[1]), reverse=True)
            for page_url, page_html in pages_by_content[:3]:
                items = await self.llm_extractor.extract_menu_items(page_html)
                if items:
                    logger.info(f"[LLM] Extracted {len(items)} items from {page_url}")
                    await self._learn_and_save(page_html, platform_type)
                    return ScrapeResult(items=items, platform_type=platform_type, used_pattern=False, extraction_method="llm")

            logger.warning(f"No menu items found for {website_url} (all methods exhausted)")
            return ScrapeResult(items=[], platform_type=platform_type, used_pattern=False, extraction_method="none")

        # Free-only mode: all free methods exhausted
        logger.info(f"Free methods exhausted for {website_url} (free_only=True, skipping LLM)")
        return ScrapeResult(items=[], platform_type=platform_type, used_pattern=False, extraction_method="free_exhausted")

    @staticmethod
    def _html_has_prices(html: str) -> bool:
        """Quick check if HTML contains price patterns (indicates a menu page)."""
        import re
        text = BeautifulSoup(html, "html.parser").get_text()
        return bool(re.search(r"\$\d+\.\d{2}", text))

    @staticmethod
    def _find_location_urls(html: str, base_url: str) -> list[str]:
        """Find location names on ordering platform pages and construct location URLs.

        Many ordering platforms (Toast, ChowNow, etc.) use slugified location names:
        order.example.com/sorrento-valley, order.example.com/downtown, etc.
        """
        soup = BeautifulSoup(html, "html.parser")
        location_urls = []

        # Look for h2/h3 elements that might be location names
        for tag in soup.find_all(["h2", "h3", "h4"]):
            text = tag.get_text(strip=True)
            if not text or len(text) > 50 or len(text) < 3:
                continue
            # Skip generic headings
            if text.lower() in ("menu", "locations", "find a location", "hours", "contact"):
                continue
            # Slugify: "Sorrento Valley" -> "sorrento-valley"
            slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
            if slug and len(slug) > 2:
                loc_url = f"{base_url.rstrip('/')}/{slug}"
                if loc_url not in location_urls:
                    location_urls.append(loc_url)

        return location_urls

    async def _learn_and_save(self, html: str, platform_type: str) -> None:
        """Learn CSS selectors from successful LLM extraction for future free use.

        Only learns if we don't already have a pattern for this platform (saves an API call).
        """
        existing = await self.pattern_registry.get_pattern(platform_type)
        if existing:
            return  # Already have a pattern for this platform

        selectors = await self.llm_extractor.learn_selectors(html)
        if selectors:
            await self.pattern_registry.save_pattern(
                platform_type=platform_type,
                detection_rule=f"platform:{platform_type}",
                selectors=selectors,
            )
            logger.info(f"Learned new pattern for platform '{platform_type}'")
