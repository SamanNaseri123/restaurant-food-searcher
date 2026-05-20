import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.scraper.pipeline import ScrapingPipeline, ScrapeResult

# Patch paths for free extractors
_STRUCTURED = "app.services.scraper.pipeline.extract_from_structured_data"
_PLATFORM = "app.services.scraper.pipeline.extract_from_platform"
_HEURISTIC = "app.services.scraper.pipeline.extract_from_heuristics"
_DETECT = "app.services.scraper.pipeline.detect_platform"


def _no_free_extractors():
    """Context manager that disables all free extractors."""
    return (
        patch(_STRUCTURED, return_value=None),
        patch(_PLATFORM, return_value=None),
        patch(_HEURISTIC, return_value=None),
    )


class TestScrapingPipeline:
    """Tests for the scraping pipeline orchestration."""

    @pytest.mark.asyncio
    async def test_should_use_pattern_when_available(self, mock_db):
        pipeline = ScrapingPipeline(mock_db)
        fake_items = [
            {"name": "Pad Thai", "price": 14.99, "description": "Noodles", "category": "entree"},
            {"name": "Green Curry", "price": 16.50, "description": "Curry", "category": "entree"},
            {"name": "Spring Rolls", "price": 8.00, "description": "Rolls", "category": "appetizer"},
        ]

        p1, p2, p3 = _no_free_extractors()
        with p1, p2, p3, patch.object(
            pipeline.pattern_registry, "get_pattern", new_callable=AsyncMock
        ) as mock_pattern, patch(
            _DETECT, new_callable=AsyncMock
        ) as mock_detect, patch.object(
            pipeline.pattern_registry, "try_extract_with_selectors"
        ) as mock_extract:
            mock_detect.return_value = ("squarespace", "<html>...</html>")
            mock_pattern.return_value = {"menu_item": ".item"}
            mock_extract.return_value = fake_items

            result = await pipeline.scrape_menu("https://example.com")

            assert result.used_pattern is True
            assert len(result.items) == 3
            assert result.platform_type == "squarespace"
            assert result.extraction_method == "pattern"

    @pytest.mark.asyncio
    async def test_should_fallback_to_llm_when_no_pattern(self, mock_db):
        pipeline = ScrapingPipeline(mock_db)
        fake_items = [
            {"name": "Burger", "price": 12.00, "description": None, "category": "entree"},
            {"name": "Fries", "price": 5.00, "description": None, "category": "side"},
            {"name": "Shake", "price": 7.00, "description": None, "category": "drink"},
        ]

        p1, p2, p3 = _no_free_extractors()
        with p1, p2, p3, patch.object(
            pipeline.pattern_registry, "get_pattern", new_callable=AsyncMock
        ) as mock_pattern, patch(
            _DETECT, new_callable=AsyncMock
        ) as mock_detect, patch.object(
            pipeline.llm_extractor, "extract_menu_items", new_callable=AsyncMock
        ) as mock_llm, patch.object(
            pipeline.llm_extractor, "learn_selectors", new_callable=AsyncMock
        ) as mock_learn, patch.object(
            pipeline.pattern_registry, "save_pattern", new_callable=AsyncMock
        ):
            mock_detect.return_value = ("custom", "<html>...</html>")
            mock_pattern.return_value = None
            mock_llm.return_value = fake_items
            mock_learn.return_value = {"menu_item": ".dish"}

            result = await pipeline.scrape_menu("https://example.com")

            assert result.used_pattern is False
            assert result.extraction_method == "llm"
            assert len(result.items) == 3
            mock_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_return_empty_when_fetch_fails(self, mock_db):
        pipeline = ScrapingPipeline(mock_db)

        with patch(_DETECT, new_callable=AsyncMock) as mock_detect, patch(
            "app.services.scraper.pipeline.fetch_from_wayback",
            new_callable=AsyncMock,
            return_value=None,
        ):
            mock_detect.side_effect = Exception("Connection refused")

            result = await pipeline.scrape_menu("https://down-site.com")

            assert result.items == []
            assert result.platform_type == "unknown"
            assert result.extraction_method == "none"

    @pytest.mark.asyncio
    async def test_should_learn_selectors_after_llm_extraction(self, mock_db):
        pipeline = ScrapingPipeline(mock_db)
        learned_selectors = {"menu_item": ".dish", "item_name": ".title"}

        p1, p2, p3 = _no_free_extractors()
        with p1, p2, p3, patch.object(
            pipeline.pattern_registry, "get_pattern", new_callable=AsyncMock
        ) as mock_pattern, patch(
            _DETECT, new_callable=AsyncMock
        ) as mock_detect, patch.object(
            pipeline.llm_extractor, "extract_menu_items", new_callable=AsyncMock
        ) as mock_llm, patch.object(
            pipeline.llm_extractor, "learn_selectors", new_callable=AsyncMock
        ) as mock_learn, patch.object(
            pipeline.pattern_registry, "save_pattern", new_callable=AsyncMock
        ) as mock_save:
            mock_detect.return_value = ("wordpress", "<html>...</html>")
            mock_pattern.return_value = None
            mock_llm.return_value = [{"name": "Item", "price": 10}]
            mock_learn.return_value = learned_selectors

            await pipeline.scrape_menu("https://example.com")

            mock_save.assert_called_once_with(
                platform_type="wordpress",
                detection_rule="platform:wordpress",
                selectors=learned_selectors,
            )

    @pytest.mark.asyncio
    async def test_should_prefer_structured_data_over_llm(self, mock_db):
        pipeline = ScrapingPipeline(mock_db)
        schema_items = [
            {"name": "Tacos", "price": 12.0, "description": "Corn tortillas", "category": "entree"},
            {"name": "Burrito", "price": 14.0, "description": "Flour tortilla", "category": "entree"},
            {"name": "Chips", "price": 6.0, "description": "With salsa", "category": "appetizer"},
        ]

        with patch(_STRUCTURED, return_value=schema_items), patch(
            _DETECT, new_callable=AsyncMock
        ) as mock_detect, patch.object(
            pipeline.llm_extractor, "extract_menu_items", new_callable=AsyncMock
        ) as mock_llm:
            mock_detect.return_value = ("custom", "<html>...</html>")

            result = await pipeline.scrape_menu("https://example.com")

            assert result.extraction_method == "structured_data"
            assert result.used_pattern is True
            assert len(result.items) == 3
            mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_prefer_heuristic_over_llm(self, mock_db):
        pipeline = ScrapingPipeline(mock_db)
        heuristic_items = [
            {"name": "Wings", "price": 11.0, "description": None, "category": None},
            {"name": "Nachos", "price": 13.0, "description": None, "category": None},
            {"name": "Sliders", "price": 9.0, "description": None, "category": None},
        ]

        with patch(_STRUCTURED, return_value=None), patch(
            _PLATFORM, return_value=None
        ), patch(_HEURISTIC, return_value=heuristic_items), patch(
            _DETECT, new_callable=AsyncMock
        ) as mock_detect, patch.object(
            pipeline.pattern_registry, "get_pattern", new_callable=AsyncMock, return_value=None
        ), patch.object(
            pipeline.llm_extractor, "extract_menu_items", new_callable=AsyncMock
        ) as mock_llm:
            mock_detect.return_value = ("custom", "<html>...</html>")

            result = await pipeline.scrape_menu("https://example.com")

            assert result.extraction_method == "heuristic"
            assert result.used_pattern is True
            mock_llm.assert_not_called()
