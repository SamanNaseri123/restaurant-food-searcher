import pytest

from app.services.scraper.heuristic_extractor import extract_from_heuristics


class TestHeuristicExtractor:

    def test_should_extract_items_with_prices(self):
        html = '''<html><body>
        <div class="menu">
            <div class="item">Cheeseburger $12.99</div>
            <div class="item">Caesar Salad $9.50</div>
            <div class="item">Fish Tacos $14.00</div>
            <div class="item">Onion Rings $7.25</div>
        </div>
        </body></html>'''

        items = extract_from_heuristics(html)

        assert items is not None
        assert len(items) >= 3
        names = [i["name"] for i in items]
        assert "Cheeseburger" in names
        assert items[0]["price"] is not None

    def test_should_return_none_with_no_prices(self):
        html = "<html><body><p>Welcome to our restaurant!</p></body></html>"
        assert extract_from_heuristics(html) is None

    def test_should_ignore_non_food_items(self):
        html = '''<html><body>
        <div>Gift Card $50.00</div>
        <div>Delivery Fee $3.99</div>
        <div>Burger $12.00</div>
        </body></html>'''

        items = extract_from_heuristics(html)
        if items:
            names = [i["name"].lower() for i in items]
            assert "gift card" not in names
            assert "delivery fee" not in names

    def test_should_extract_from_table(self):
        html = '''<html><body>
        <table>
            <tr><td>Margherita Pizza</td><td>$14.99</td></tr>
            <tr><td>Pepperoni Pizza</td><td>$16.99</td></tr>
            <tr><td>Hawaiian Pizza</td><td>$15.99</td></tr>
            <tr><td>Veggie Pizza</td><td>$14.99</td></tr>
        </table>
        </body></html>'''

        items = extract_from_heuristics(html)

        assert items is not None
        assert len(items) >= 3

    def test_should_return_none_with_fewer_than_3_items(self):
        html = '''<html><body>
        <div>Burger $12.00</div>
        <div>Fries $5.00</div>
        </body></html>'''

        assert extract_from_heuristics(html) is None
