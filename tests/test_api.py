import sys
import os
import json
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["API_KEY"] = "test-api-key-placeholder"
os.environ["ENABLE_BACKGROUND_TASKS"] = "False"

from app import app


@pytest.fixture
def client():
    """Flask test client."""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestPublicEndpoints:
    """Kimlik doğrulaması gerektirmeyen endpoint'ler."""

    def test_index_page(self, client):
        """Ana sayfa yüklenmeli."""
        response = client.get("/")
        assert response.status_code == 200

    def test_api_stats(self, client):
        """İstatistik API'si çalışmalı."""
        response = client.get("/api/stats")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, dict)

    def test_api_leagues(self, client):
        """Ligler API'si çalışmalı."""
        response = client.get("/api/leagues")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, list)

    def test_api_seasons(self, client):
        """Sezonlar API'si çalışmalı."""
        response = client.get("/api/seasons")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, list)

    def test_teams_search_short_query(self, client):
        """Kısa sorgu ile takım arama boş liste dönmeli."""
        response = client.get("/api/teams/search?q=A")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data == []

    def test_teams_search_empty(self, client):
        """Boş sorgu ile takım arama boş liste dönmeli."""
        response = client.get("/api/teams/search?q=")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data == []


class TestProtectedEndpoints:
    """Kimlik doğrulaması gerektiren POST endpoint'ler."""

    def test_fetch_no_api_key(self, client):
        """API key olmadan fetch 401 dönmeli."""
        response = client.post("/api/fetch")
        assert response.status_code == 401
        data = json.loads(response.data)
        assert "error" in data

    def test_fetch_wrong_api_key(self, client):
        """Yanlış API key ile fetch 401 dönmeli."""
        response = client.post("/api/fetch", headers={"X-API-Key": "wrong-key"})
        assert response.status_code == 401

    def test_model_train_no_api_key(self, client):
        """API key olmadan model eğitimi 401 dönmeli."""
        response = client.post("/api/model/train")
        assert response.status_code == 401

    def test_prediction_delete_no_api_key(self, client):
        """API key olmadan tahmin silme 401 dönmeli."""
        response = client.post("/api/predictions/delete", json={"id": 1})
        assert response.status_code == 401

    def test_prediction_update_no_api_key(self, client):
        """API key olmadan tahmin güncelleme 401 dönmeli."""
        response = client.post("/api/predictions/update", json={"id": 1, "home_score": 2, "away_score": 1})
        assert response.status_code == 401

    def test_autoresearch_start_no_api_key(self, client):
        """API key olmadan auto research başlatma 401 dönmeli."""
        response = client.post("/api/autoresearch/start")
        assert response.status_code == 401

    def test_weekly_refresh_no_api_key(self, client):
        """API key olmadan haftalık yenileme 401 dönmeli."""
        response = client.post("/api/weekly/refresh")
        assert response.status_code == 401

    def test_import_no_api_key(self, client):
        """API key olmadan import 401 dönmeli."""
        response = client.post("/api/import")
        assert response.status_code == 401
