import logging
import re

import httpx

logger = logging.getLogger(__name__)

PLATFORM_SIGNATURES = {
    "squarespace": [
        re.compile(r'<meta\s+[^>]*content="Squarespace"', re.I),
        re.compile(r"static\.squarespace\.com", re.I),
        re.compile(r"squarespace-cdn\.com", re.I),
    ],
    "wordpress": [
        re.compile(r'<meta\s+name="generator"\s+content="WordPress', re.I),
        re.compile(r"wp-content/", re.I),
        re.compile(r"wp-includes/", re.I),
    ],
    "wix": [
        re.compile(r"wix\.com", re.I),
        re.compile(r"static\.wixstatic\.com", re.I),
        re.compile(r"wixpress\.com", re.I),
    ],
    "shopify": [
        re.compile(r"cdn\.shopify\.com", re.I),
        re.compile(r"Shopify\.theme", re.I),
    ],
    "toast": [
        re.compile(r"toasttab\.com", re.I),
        re.compile(r"ws\.toasttab\.com", re.I),
    ],
    "bentobox": [
        re.compile(r"getbento\.com", re.I),
        re.compile(r"bentobox", re.I),
    ],
    "popmenu": [
        re.compile(r"popmenu\.com", re.I),
    ],
}

# Minimum HTML length to consider a page "has content" (not just a JS shell)
_MIN_CONTENT_LENGTH = 2000


def _detect_platform_from_html(html: str) -> str:
    for platform, patterns in PLATFORM_SIGNATURES.items():
        for pattern in patterns:
            if pattern.search(html):
                return platform
    return "custom"


def _looks_like_js_shell(html: str) -> bool:
    """Detect if the HTML is mostly a JS shell with no real content."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(strip=True)
    return len(text) < 500


async def _fetch_with_httpx(url: str) -> str:
    """Fast lightweight fetch — works for static sites."""
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=15.0,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text


async def _fetch_with_browser(url: str) -> str:
    """Headless browser fetch — handles JS-rendered sites and bot protection."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        try:
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 720},
                java_script_enabled=True,
            )
            # Hide webdriver flag
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            """)
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            # Brief wait for JS to render content
            await page.wait_for_timeout(1500)

            # Try clicking content-revealing elements (location pickers, menu links, tabs)
            for selector in [
                # Location/store pickers (multi-location ordering sites)
                "button:has-text('Schedule')",
                "button:has-text('Order')",
                "a:has-text('Order Now')",
                "a:has-text('Order Here')",
                # Menu links
                "a:has-text('Full Menu')",
                "a:has-text('View Menu')",
                "a:has-text('See Menu')",
                "a:has-text('Menu')",
                "a:has-text('menu')",
                "button:has-text('Menu')",
                "button:has-text('View Menu')",
                "[data-menu]",
                "[role='tab']:has-text('Menu')",
            ]:
                try:
                    link = page.locator(selector).first
                    if await link.is_visible(timeout=1000):
                        await link.click()
                        await page.wait_for_load_state("domcontentloaded", timeout=8000)
                        await page.wait_for_timeout(1500)
                        break
                except Exception:
                    continue
            html = await page.content()
            return html
        finally:
            await browser.close()


async def fetch_light(url: str) -> tuple[str, str] | None:
    """Lightweight fetch — httpx only, no browser fallback.

    Use for speculative/fallback URLs where browser cost isn't justified.
    Returns (platform_type, html) or None if fetch fails.
    """
    try:
        html = await _fetch_with_httpx(url)
    except (httpx.HTTPStatusError, httpx.RequestError):
        return None

    if _looks_like_js_shell(html):
        return None

    platform = _detect_platform_from_html(html)
    return platform, html


async def detect_platform(url: str) -> tuple[str, str]:
    """Fetch a website and detect its platform.

    Strategy:
    1. Try fast httpx fetch first
    2. If blocked (403/5xx) or page is a JS shell → fall back to headless browser

    Returns (platform_type, html_content).
    """
    html = None

    # Try lightweight fetch first
    try:
        html = await _fetch_with_httpx(url)
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status in (404, 410):
            # Page doesn't exist — no point trying browser
            raise
        if status == 403 or status >= 500:
            logger.info(f"httpx blocked for {url} ({status}), trying browser")
        else:
            raise
    except httpx.RequestError as e:
        logger.info(f"httpx failed for {url} ({e}), trying browser")

    # Fall back to browser if httpx failed or returned a JS shell
    if html is None or _looks_like_js_shell(html):
        reason = "JS shell" if html else "fetch failed"
        logger.info(f"Using headless browser for {url} ({reason})")
        try:
            html = await _fetch_with_browser(url)
        except Exception as e:
            if html is None:
                raise
            logger.warning(f"Browser also failed for {url}: {e}, using httpx result")

    platform = _detect_platform_from_html(html)
    return platform, html
