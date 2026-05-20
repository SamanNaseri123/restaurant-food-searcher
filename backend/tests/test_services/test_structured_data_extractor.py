import pytest

from app.services.scraper.structured_data_extractor import extract_from_structured_data


class TestStructuredDataExtractor:

    def test_should_extract_from_jsonld_menu(self):
        html = '''<html><head>
        <script type="application/ld+json">
        {
            "@type": "Menu",
            "hasMenuSection": [
                {
                    "@type": "MenuSection",
                    "name": "Appetizers",
                    "hasMenuItem": [
                        {"@type": "MenuItem", "name": "Nachos", "offers": {"price": "12.99"}, "description": "Loaded nachos"},
                        {"@type": "MenuItem", "name": "Wings", "offers": {"price": "11.50"}, "description": "Buffalo wings"},
                        {"@type": "MenuItem", "name": "Soup", "offers": {"price": "8.00"}, "description": "Daily soup"}
                    ]
                }
            ]
        }
        </script></head><body></body></html>'''

        items = extract_from_structured_data(html)

        assert items is not None
        assert len(items) == 3
        assert items[0]["name"] == "Nachos"
        assert items[0]["price"] == 12.99
        assert items[0]["description"] == "Loaded nachos"

    def test_should_extract_from_restaurant_with_menu(self):
        html = '''<html><head>
        <script type="application/ld+json">
        {
            "@type": "Restaurant",
            "name": "Test Restaurant",
            "hasMenu": {
                "@type": "Menu",
                "hasMenuItem": [
                    {"@type": "MenuItem", "name": "Burger", "price": "15"},
                    {"@type": "MenuItem", "name": "Fries", "price": "6"},
                    {"@type": "MenuItem", "name": "Shake", "price": "8"}
                ]
            }
        }
        </script></head><body></body></html>'''

        items = extract_from_structured_data(html)

        assert items is not None
        assert len(items) == 3

    def test_should_return_none_when_no_structured_data(self):
        html = "<html><body><h1>No schema here</h1></body></html>"
        assert extract_from_structured_data(html) is None

    def test_should_return_none_when_fewer_than_3_items(self):
        html = '''<html><head>
        <script type="application/ld+json">
        {"@type": "Menu", "hasMenuItem": [
            {"@type": "MenuItem", "name": "Solo Item", "price": "10"}
        ]}
        </script></head><body></body></html>'''

        assert extract_from_structured_data(html) is None

    def test_should_handle_category_from_section_name(self):
        html = '''<html><head>
        <script type="application/ld+json">
        {
            "@type": "Menu",
            "hasMenuSection": [{
                "@type": "MenuSection",
                "name": "Desserts",
                "hasMenuItem": [
                    {"@type": "MenuItem", "name": "Cake", "price": "9"},
                    {"@type": "MenuItem", "name": "Pie", "price": "8"},
                    {"@type": "MenuItem", "name": "Ice Cream", "price": "7"}
                ]
            }]
        }
        </script></head><body></body></html>'''

        items = extract_from_structured_data(html)
        assert items is not None
        assert items[0]["category"] == "dessert"
