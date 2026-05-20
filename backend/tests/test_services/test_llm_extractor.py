import pytest

from app.services.scraper.llm_extractor import LLMExtractor


class TestLLMExtractorHelpers:
    """Tests for LLM extractor utility methods (no API calls)."""

    def test_should_clean_html_by_removing_scripts(self):
        # Arrange
        html = """
        <html>
        <head><script>var x = 1;</script><style>.foo{}</style></head>
        <body>
            <nav>Navigation</nav>
            <div class="menu">
                <h3>Pad Thai</h3>
                <p>$14.99</p>
            </div>
            <footer>Footer content</footer>
        </body>
        </html>
        """

        # Act
        cleaned = LLMExtractor._clean_html(html)

        # Assert
        assert "var x = 1" not in cleaned
        assert ".foo{}" not in cleaned
        assert "Navigation" not in cleaned
        assert "Footer content" not in cleaned
        assert "Pad Thai" in cleaned
        assert "14.99" in cleaned

    def test_should_normalize_valid_price(self):
        assert LLMExtractor._normalize_price(14.99) == 14.99
        assert LLMExtractor._normalize_price("14.99") == 14.99
        assert LLMExtractor._normalize_price(0) == 0.0

    def test_should_return_none_for_invalid_price(self):
        assert LLMExtractor._normalize_price(None) is None
        assert LLMExtractor._normalize_price("free") is None

    def test_should_clean_html_preserving_menu_content(self):
        # Arrange
        html = """
        <div class="menu-section" id="entrees">
            <h2>Entrees</h2>
            <div class="item" data-price="15.99">
                <h3>Chicken Tikka Masala</h3>
                <p>Tender chicken in creamy tomato sauce</p>
            </div>
        </div>
        """

        # Act
        cleaned = LLMExtractor._clean_html(html)

        # Assert
        assert "Chicken Tikka Masala" in cleaned
        assert "Tender chicken" in cleaned
