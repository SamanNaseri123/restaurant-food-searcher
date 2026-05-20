import pytest
from unittest.mock import AsyncMock, patch

from app.services.scraper.platform_detector import (
    detect_platform,
    _detect_platform_from_html,
    PLATFORM_SIGNATURES,
)


class TestPlatformDetector:
    """Tests for website platform detection."""

    @pytest.mark.asyncio
    async def test_should_detect_squarespace_from_meta_tag(self):
        html = '<html><head><meta content="Squarespace"></head><body>' + ("x" * 600) + "</body></html>"

        with patch("app.services.scraper.platform_detector._fetch_with_httpx", new_callable=AsyncMock, return_value=html):
            platform, content = await detect_platform("https://example.com")

        assert platform == "squarespace"
        assert content == html

    @pytest.mark.asyncio
    async def test_should_detect_wordpress_from_wp_content(self):
        html = '<html><body><link href="/wp-content/themes/theme.css">' + ("x" * 600) + "</body></html>"

        with patch("app.services.scraper.platform_detector._fetch_with_httpx", new_callable=AsyncMock, return_value=html):
            platform, _ = await detect_platform("https://example.com")

        assert platform == "wordpress"

    @pytest.mark.asyncio
    async def test_should_detect_wix_from_static_url(self):
        html = '<html><body><img src="https://static.wixstatic.com/image.jpg">' + ("x" * 600) + "</body></html>"

        with patch("app.services.scraper.platform_detector._fetch_with_httpx", new_callable=AsyncMock, return_value=html):
            platform, _ = await detect_platform("https://example.com")

        assert platform == "wix"

    @pytest.mark.asyncio
    async def test_should_return_custom_for_unknown_platform(self):
        html = "<html><body><h1>My Restaurant</h1>" + ("x" * 600) + "</body></html>"

        with patch("app.services.scraper.platform_detector._fetch_with_httpx", new_callable=AsyncMock, return_value=html):
            platform, _ = await detect_platform("https://example.com")

        assert platform == "custom"

    @pytest.mark.asyncio
    async def test_should_detect_toast_platform(self):
        html = '<html><body><script src="https://ws.toasttab.com/menu.js"></script>' + ("x" * 600) + "</body></html>"

        with patch("app.services.scraper.platform_detector._fetch_with_httpx", new_callable=AsyncMock, return_value=html):
            platform, _ = await detect_platform("https://example.com")

        assert platform == "toast"

    def test_should_have_signatures_for_major_platforms(self):
        expected_platforms = {"squarespace", "wordpress", "wix", "toast", "popmenu"}
        assert expected_platforms.issubset(set(PLATFORM_SIGNATURES.keys()))

    def test_detect_platform_from_html_directly(self):
        assert _detect_platform_from_html('<meta content="Squarespace">') == "squarespace"
        assert _detect_platform_from_html("wp-content/themes") == "wordpress"
        assert _detect_platform_from_html("static.wixstatic.com") == "wix"
        assert _detect_platform_from_html("<html>plain</html>") == "custom"

    @pytest.mark.asyncio
    async def test_should_fallback_to_browser_on_js_shell(self):
        js_shell = "<html><body><div id='app'></div></body></html>"
        browser_html = '<html><body><link href="/wp-content/x">' + ("x" * 600) + "</body></html>"

        with (
            patch("app.services.scraper.platform_detector._fetch_with_httpx", new_callable=AsyncMock, return_value=js_shell),
            patch("app.services.scraper.platform_detector._fetch_with_browser", new_callable=AsyncMock, return_value=browser_html),
        ):
            platform, content = await detect_platform("https://example.com")

        assert platform == "wordpress"
        assert content == browser_html

    @pytest.mark.asyncio
    async def test_should_fallback_to_browser_on_403(self):
        import httpx as httpx_lib

        browser_html = "<html><body>Full content here " + ("x" * 600) + "</body></html>"

        async def raise_403(url):
            resp = httpx_lib.Response(403, request=httpx_lib.Request("GET", url))
            raise httpx_lib.HTTPStatusError("Forbidden", request=resp.request, response=resp)

        with (
            patch("app.services.scraper.platform_detector._fetch_with_httpx", side_effect=raise_403),
            patch("app.services.scraper.platform_detector._fetch_with_browser", new_callable=AsyncMock, return_value=browser_html),
        ):
            platform, content = await detect_platform("https://example.com")

        assert content == browser_html
