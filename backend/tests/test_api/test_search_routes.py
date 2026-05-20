import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.schemas import AutocompleteResponse, SearchResponse
from app.main import app


client = TestClient(app)


class TestSearchRoutes:
    """Tests for search API endpoints."""

    def test_should_require_query_parameter(self):
        # Act
        response = client.get("/api/v1/search?lat=40.7&lng=-74.0")

        # Assert
        assert response.status_code == 422  # Missing required 'q' param

    def test_should_require_lat_lng(self):
        # Act
        response = client.get("/api/v1/search?q=pizza")

        # Assert
        assert response.status_code == 422

    def test_should_reject_invalid_radius(self):
        # Act - radius too large
        response = client.get("/api/v1/search?q=pizza&lat=40.7&lng=-74.0&radius=50000")

        # Assert
        assert response.status_code == 422

    def test_should_reject_empty_query(self):
        # Act
        response = client.get("/api/v1/search?q=&lat=40.7&lng=-74.0")

        # Assert
        assert response.status_code == 422

    def test_health_endpoint(self):
        # Act
        response = client.get("/health")

        # Assert
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_should_reject_invalid_lat(self):
        # Act - lat out of range
        response = client.get("/api/v1/search?q=pizza&lat=100&lng=-74.0")

        # Assert
        assert response.status_code == 422

    @pytest.mark.skipif(True, reason="Requires running PostgreSQL database")
    def test_should_return_404_for_nonexistent_restaurant(self):
        # Act
        fake_id = uuid4()
        response = client.get(f"/api/v1/restaurants/{fake_id}")

        # Assert
        assert response.status_code == 404

    def test_autocomplete_should_require_query(self):
        # Act
        response = client.get("/api/v1/autocomplete")

        # Assert
        assert response.status_code == 422
