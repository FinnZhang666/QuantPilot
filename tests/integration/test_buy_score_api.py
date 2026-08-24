from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.session import get_engine
from app.main import app


HEADERS = {"X-Dashboard-Token": "buy-score-test"}


def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "buy-score-api.db"))
    monkeypatch.setenv("DASHBOARD_ADMIN_TOKEN", "buy-score-test")
    monkeypatch.setenv("DASHBOARD_READONLY_PUBLIC", "false")
    get_settings.cache_clear(); get_engine.cache_clear()
    return TestClient(app)


def test_buy_score_api_auth_empty_validation_and_404(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        assert api.get("/qmr/buy-scores").status_code == 401
        assert api.get("/qmr/buy-scores", headers=HEADERS).json()["total"] == 0
        assert api.get("/qmr/ranking", headers=HEADERS).json()["total"] == 0
        assert api.get("/qmr/MU/buy-score", headers=HEADERS).status_code == 404
        assert api.get("/qmr/buy-scores", headers=HEADERS, params={"status": "BUY"}).status_code == 422


def test_buy_score_internal_default_dry_run_is_hidden(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        assert "/internal/buy-scores/run" not in api.get("/openapi.json").json()["paths"]
        response = api.post("/internal/buy-scores/run", headers=HEADERS)
        assert response.status_code == 200
        assert response.json()["created"] == 0


def test_buy_score_dashboard_routes_render(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        assert api.get("/dashboard/qmr", follow_redirects=False).status_code in (302, 303, 307)
        assert api.get("/dashboard/qmr", headers=HEADERS).status_code == 200
        assert api.get("/dashboard/qmr/MU", headers=HEADERS).status_code == 200
