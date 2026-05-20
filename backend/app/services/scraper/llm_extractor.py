import json
import logging
import re

import anthropic
from bs4 import BeautifulSoup

from app.core.config import settings

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Extract all menu items from this restaurant website HTML.

Return a JSON array where each item has:
- "name": string (dish name)
- "description": string or null (dish description)
- "price": number or null (price in dollars, no $ sign)
- "category": string or null (e.g., "appetizer", "entree", "dessert", "drink", "side", "soup", "salad")

Rules:
- Only extract actual food/drink items, not section headers or restaurant info
- If a price has a range like "$12-15", use the lower price (12)
- Ignore items that are clearly not food (merchandise, gift cards, etc.)
- If no menu items are found, return an empty array []

HTML content:
{html}

Return ONLY the JSON array, no other text."""

CSS_LEARNING_PROMPT = """Analyze this restaurant website HTML and identify CSS selectors that could be used to extract menu items.

Return a JSON object with these keys:
- "menu_item": CSS selector for individual menu item containers
- "item_name": CSS selector for the item name within a container
- "item_price": CSS selector for the price within a container
- "item_description": CSS selector for the description within a container

Only return selectors you are confident about. If you can't identify a selector, set it to null.

HTML content (first 3000 chars):
{html}

Return ONLY the JSON object, no other text."""


class LLMExtractor:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def extract_menu_items(self, html: str) -> list[dict]:
        """Use Claude to extract menu items from HTML."""
        cleaned = self._clean_html(html)

        # Skip if page has too little content — not worth an API call
        if len(cleaned) < 200:
            logger.info("Skipping LLM: page has too little text content")
            return []

        # Truncate to avoid huge token costs
        if len(cleaned) > 15000:
            cleaned = cleaned[:15000]

        try:
            response = await self.client.messages.create(
                model=settings.llm_model,
                max_tokens=8192,
                temperature=0,
                messages=[
                    {
                        "role": "user",
                        "content": EXTRACTION_PROMPT.format(html=cleaned),
                    }
                ],
            )

            text = response.content[0].text.strip()
            # Extract JSON from response (handle markdown code blocks)
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

            items = json.loads(text)
            if not isinstance(items, list):
                return []

            return [
                {
                    "name": item.get("name", ""),
                    "description": item.get("description"),
                    "price": self._normalize_price(item.get("price")),
                    "category": item.get("category"),
                }
                for item in items
                if item.get("name")
            ]

        except (json.JSONDecodeError, anthropic.APIError) as e:
            logger.error(f"LLM extraction failed: {e}")
            return []

    async def learn_selectors(self, html: str) -> dict | None:
        """Use Claude to learn CSS selectors for a website pattern."""
        cleaned = self._clean_html(html)[:3000]

        try:
            response = await self.client.messages.create(
                model=settings.llm_model,
                max_tokens=1024,
                temperature=0,
                messages=[
                    {
                        "role": "user",
                        "content": CSS_LEARNING_PROMPT.format(html=cleaned),
                    }
                ],
            )

            text = response.content[0].text.strip()
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

            selectors = json.loads(text)
            if not isinstance(selectors, dict):
                return None

            # Only return if we got at least the item container selector
            if selectors.get("menu_item"):
                return selectors
            return None

        except (json.JSONDecodeError, anthropic.APIError) as e:
            logger.error(f"LLM selector learning failed: {e}")
            return None

    @staticmethod
    def _clean_html(html: str) -> str:
        """Strip non-content elements to reduce token usage."""
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup.find_all(["script", "style", "nav", "footer", "header", "iframe", "noscript"]):
            tag.decompose()

        for tag in soup.find_all(True):
            attrs_to_keep = {"class", "id", "data-item", "data-menu", "data-price"}
            tag.attrs = {k: v for k, v in tag.attrs.items() if k in attrs_to_keep}

        return soup.get_text(separator="\n", strip=True)

    @staticmethod
    def _normalize_price(price) -> float | None:
        if price is None:
            return None
        try:
            return float(price)
        except (ValueError, TypeError):
            return None
