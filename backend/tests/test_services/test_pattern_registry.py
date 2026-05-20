import pytest

from app.services.scraper.pattern_registry import PatternRegistry


class TestPatternRegistry:
    """Tests for CSS selector pattern matching and price parsing."""

    def test_should_extract_items_with_valid_selectors(self):
        # Arrange
        html = """
        <div class="menu">
            <div class="menu-item">
                <h3 class="item-name">Pad Thai</h3>
                <span class="price">$14.99</span>
                <p class="description">Classic Thai noodles with peanuts</p>
            </div>
            <div class="menu-item">
                <h3 class="item-name">Green Curry</h3>
                <span class="price">$16.50</span>
                <p class="description">Spicy coconut curry</p>
            </div>
            <div class="menu-item">
                <h3 class="item-name">Spring Rolls</h3>
                <span class="price">$8.00</span>
                <p class="description">Crispy vegetable rolls</p>
            </div>
        </div>
        """
        selectors = {
            "menu_item": ".menu-item",
            "item_name": ".item-name",
            "item_price": ".price",
            "item_description": ".description",
        }
        registry = PatternRegistry(db=None)

        # Act
        items = registry.try_extract_with_selectors(html, selectors)

        # Assert
        assert items is not None
        assert len(items) == 3
        assert items[0]["name"] == "Pad Thai"
        assert items[0]["price"] == 14.99
        assert items[0]["description"] == "Classic Thai noodles with peanuts"

    def test_should_return_none_when_no_items_found(self):
        # Arrange
        html = "<html><body><h1>About Us</h1><p>We are a restaurant.</p></body></html>"
        selectors = {"menu_item": ".menu-item", "item_name": ".item-name"}
        registry = PatternRegistry(db=None)

        # Act
        items = registry.try_extract_with_selectors(html, selectors)

        # Assert
        assert items is None

    def test_should_return_none_when_fewer_than_3_items(self):
        # Arrange
        html = """
        <div class="menu-item">
            <h3 class="item-name">Pad Thai</h3>
        </div>
        <div class="menu-item">
            <h3 class="item-name">Curry</h3>
        </div>
        """
        selectors = {"menu_item": ".menu-item", "item_name": ".item-name"}
        registry = PatternRegistry(db=None)

        # Act
        items = registry.try_extract_with_selectors(html, selectors)

        # Assert
        assert items is None

    def test_should_parse_price_with_dollar_sign(self):
        assert PatternRegistry._parse_price("$14.99") == 14.99

    def test_should_parse_price_without_dollar_sign(self):
        assert PatternRegistry._parse_price("14.99") == 14.99

    def test_should_parse_price_with_comma(self):
        assert PatternRegistry._parse_price("$1,299.00") == 1299.00

    def test_should_return_none_for_empty_price(self):
        assert PatternRegistry._parse_price(None) is None
        assert PatternRegistry._parse_price("") is None

    def test_should_handle_item_container_alias(self):
        # Arrange
        html = """
        <div class="dish">
            <span class="name">Item 1</span>
        </div>
        <div class="dish">
            <span class="name">Item 2</span>
        </div>
        <div class="dish">
            <span class="name">Item 3</span>
        </div>
        """
        selectors = {
            "item_container": ".dish",
            "item_name": ".name",
        }
        registry = PatternRegistry(db=None)

        # Act
        items = registry.try_extract_with_selectors(html, selectors)

        # Assert
        assert items is not None
        assert len(items) == 3
