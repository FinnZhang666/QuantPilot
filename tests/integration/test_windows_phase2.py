import platform

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.session import get_engine
from app.main import app
from app.platform import health as platform_health


def phase2_client(monkeypatch, tmp_path, public=True):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "phase2.db"))
    monkeypatch.setenv("DASHBOARD_READONLY_PUBLIC", "true" if public else "false")
    monkeypatch.setenv("DASHBOARD_ADMIN_TOKEN", "phase2-admin")
    monkeypatch.setenv("REALTIME_RUNTIME_ENABLED", "false")
    monkeypatch.setenv("TELEGRAM_ENABLED", "false")
    monkeypatch.setenv("AI_COMPANION_ENABLED", "false")
    monkeypatch.setenv("MOOMOO_ENABLED", "false")
    get_settings.cache_clear()
    get_engine.cache_clear()
    return TestClient(app)


@pytest.mark.parametrize("system", ["Windows", "Linux", "Darwin"])
def test_process_memory_probe_is_cross_platform(monkeypatch, system):
    monkeypatch.setattr(platform_health.platform, "system", lambda: system)
    assert platform_health._process_memory_mb() >= 0


def test_windows_platform_health_runtime_and_version(monkeypatch, tmp_path):
    with phase2_client(monkeypatch, tmp_path) as client:
        health = client.get("/api/platform/health")
        runtime = client.get("/api/platform/runtime")
        version = client.get("/api/platform/version")
        assert health.status_code == runtime.status_code == version.status_code == 200
        assert health.json()["platform"]["os"] == platform.system()
        assert health.json()["platform"]["python"] == platform.python_version()
        assert runtime.json()["runtime"] == "STOPPED"
        assert health.json()["telegram"] == "DISABLED"
        assert health.json()["opend"] == "DISCONNECTED"


def test_public_readonly_dashboard_api_matrix(monkeypatch, tmp_path):
    with phase2_client(monkeypatch, tmp_path) as client:
        public_reads = (
            "/api/dashboard/summary", "/api/dashboard/strategy-summary",
            "/api/dashboard/data-quality", "/api/reviews",
            "/api/reviews/statistics", "/api/platform/version",
            "/api/platform/health", "/api/platform/runtime",
            "/api/runtime/status", "/api/market-regime/current",
            "/api/candidate-pool", "/api/opportunities",
            "/api/trade-plans", "/api/user-positions",
            "/api/user-positions/statistics", "/api/companion-analyses",
            "/api/market-snapshots", "/api/portfolios", "/api/review",
            "/api/ai-review", "/api/research",
        )
        for path in public_reads:
            response = client.get(path)
            assert response.status_code == 200, (path, response.status_code, response.text)

        admin_only = (
            ("post", "/api/runtime/start", None),
            ("post", "/api/candidate-pool/build", None),
            ("post", "/api/market-regime/evaluate", None),
            ("post", "/api/review/run", None),
            ("post", "/api/ai-review/run", {"limit": 1}),
            ("get", "/api/platform/config", None),
            ("get", "/api/platform/backups", None),
        )
        for method, path, payload in admin_only:
            response = getattr(client, method)(path, json=payload) if payload else getattr(client, method)(path)
            assert response.status_code == 401, (path, response.status_code, response.text)


def test_private_mode_keeps_read_api_authenticated(monkeypatch, tmp_path):
    with phase2_client(monkeypatch, tmp_path, public=False) as client:
        for path in (
            "/api/dashboard/summary", "/api/reviews/statistics",
            "/api/platform/health", "/api/platform/runtime",
        ):
            assert client.get(path).status_code == 401


def test_empty_database_dashboard_has_zero_statistics(monkeypatch, tmp_path):
    with phase2_client(monkeypatch, tmp_path) as client:
        summary = client.get("/api/dashboard/summary")
        statistics = client.get("/api/reviews/statistics")
        assert summary.status_code == statistics.status_code == 200
        assert summary.json()["today"]["opportunities"] == 0
        assert summary.json()["today"]["reviews_completed"] == 0
        assert next(
            row for row in summary.json()["services"] if row["service_name"] == "opend"
        )["status"] == "DISCONNECTED"
        assert statistics.json()["system"]["total_reviews"] == 0
        assert statistics.json()["user"]["closed_positions"] == 0


def test_openapi_path_contract_is_preserved(monkeypatch, tmp_path):
    with phase2_client(monkeypatch, tmp_path) as client:
        schema = client.get("/openapi.json")
        assert schema.status_code == 200
        assert len(schema.json()["paths"]) == 170
