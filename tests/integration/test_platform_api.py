from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.session import get_engine
from app.main import app


def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "platform.db"))
    monkeypatch.setenv("DASHBOARD_READONLY_PUBLIC", "true")
    monkeypatch.setenv("DASHBOARD_ADMIN_TOKEN", "admin-secret")
    monkeypatch.setenv("BACKUP_DIRECTORY", str(tmp_path / "backups"))
    get_settings.cache_clear()
    get_engine.cache_clear()
    return TestClient(app)


def test_platform_health_version_runtime_api(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as value:
        assert value.get("/health").status_code == 200
        assert value.get("/runtime").status_code == 200
        assert value.get("/api/platform/health").status_code == 200
        version = value.get("/api/platform/version").json()
        assert version["product"] == "Trade Companion"
        assert version["sprint"] == "36"
        openapi = value.get("/openapi.json").json()
        assert openapi["info"]["title"] == "Trade Companion"
        assert "AI 辅助" in openapi["info"]["description"]


def test_platform_admin_api_and_secret_mask(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as value:
        assert value.get("/api/platform/config").status_code == 401
        response = value.get("/api/platform/config", headers={"X-Dashboard-Token": "admin-secret"})
        assert response.status_code == 200
        assert "admin-secret" not in response.text


def test_platform_backup_api(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as value:
        headers = {"X-Dashboard-Token": "admin-secret"}
        result = value.post("/api/platform/backups", headers=headers)
        assert result.status_code == 200 and result.json()["valid"]
        assert value.get("/api/platform/backups", headers=headers).json()["items"]


def test_system_dashboard_page(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as value:
        response = value.get("/dashboard/system")
        assert response.status_code == 200 and "公司工作台" in response.text
        assert "Trade Companion" in response.text
