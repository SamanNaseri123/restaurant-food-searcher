import pytest

from app.services.scraper.pipeline import _find_menu_links


class TestMenuLinkDiscovery:

    def test_should_find_menu_links_from_nav(self):
        html = '''<html><body>
        <nav>
            <a href="/">Home</a>
            <a href="/about">About</a>
            <a href="/full-menu">Menu</a>
            <a href="/catering">Catering</a>
            <a href="/contact">Contact</a>
        </nav>
        </body></html>'''

        urls = _find_menu_links(html, "https://example.com")
        assert len(urls) >= 1
        assert "https://example.com/full-menu" in urls

    def test_should_find_menu_links_with_varied_text(self):
        html = '''<html><body>
        <a href="/our-food">Our Food</a>
        <a href="/drinks-list">Drinks</a>
        <a href="/lunch-specials">Lunch Menu</a>
        <a href="/dinner">Dinner</a>
        </body></html>'''

        urls = _find_menu_links(html, "https://example.com")
        assert len(urls) >= 3

    def test_should_rank_exact_menu_links_higher(self):
        html = '''<html><body>
        <a href="/food-and-culture">Food & Culture Blog</a>
        <a href="/menu">Menu</a>
        <a href="/lunch-specials">Lunch</a>
        </body></html>'''

        urls = _find_menu_links(html, "https://example.com")
        assert urls[0] == "https://example.com/menu"

    def test_should_allow_external_links_with_menu_text(self):
        html = '''<html><body>
        <a href="https://other-site.com/menu">External Menu</a>
        <a href="/our-menu">Our Menu</a>
        </body></html>'''

        urls = _find_menu_links(html, "https://example.com")
        # Both should be found — external link has clear "menu" text
        assert len(urls) == 2

    def test_should_skip_external_links_without_menu_text(self):
        html = '''<html><body>
        <a href="https://instagram.com/restaurant">Follow Us</a>
        <a href="https://yelp.com/biz/restaurant">Yelp Reviews</a>
        <a href="/our-menu">Our Menu</a>
        </body></html>'''

        urls = _find_menu_links(html, "https://example.com")
        assert all("instagram" not in u and "yelp" not in u for u in urls)

    def test_should_ignore_same_page_links(self):
        html = '''<html><body>
        <a href="https://example.com/">Home</a>
        <a href="/menu">Menu</a>
        </body></html>'''

        urls = _find_menu_links(html, "https://example.com/")
        assert "https://example.com" not in urls

    def test_should_return_empty_when_no_menu_links(self):
        html = '''<html><body>
        <a href="/about">About Us</a>
        <a href="/contact">Contact</a>
        <a href="/gallery">Photo Gallery</a>
        </body></html>'''

        urls = _find_menu_links(html, "https://example.com")
        assert len(urls) == 0

    def test_should_handle_relative_urls(self):
        html = '''<html><body>
        <a href="menu.html">View Menu</a>
        <a href="../food">Food</a>
        </body></html>'''

        urls = _find_menu_links(html, "https://example.com/pages/home")
        assert any("menu" in u.lower() for u in urls)
