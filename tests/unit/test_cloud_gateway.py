from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.cloud_gateway import CloudGatewayMiddleware, SnapshotCache
from app.core.config import Settings


def cloud_app(tmp_path):
    inner = FastAPI()

    @inner.get("/dashboard")
    def dashboard():
        return {"page": "ok"}

    settings = Settings(
        app_role="cloud_web",
        quant_node_base_url="",
        cloud_cache_directory=str(tmp_path / "cache"),
        telegram_enabled=False,
        universe_auto_update_enabled=False,
    )
    inner.add_middleware(CloudGatewayMiddleware, settings=settings)
    return inner


def test_cloud_health_stays_200_when_quant_node_offline(tmp_path):
    with TestClient(cloud_app(tmp_path)) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["cloud_web"] == "HEALTHY"
    assert response.json()["quant_node"] == "OFFLINE"


def test_cloud_dashboard_shell_still_loads(tmp_path):
    with TestClient(cloud_app(tmp_path)) as client:
        assert client.get("/dashboard").status_code == 200


def test_cloud_fails_closed_for_mutation_and_internal_api(tmp_path):
    with TestClient(cloud_app(tmp_path)) as client:
        assert client.post("/api/qmr/run").status_code == 405
        assert client.get("/internal/qmr/run").status_code == 404


def test_uncached_api_is_safe_when_node_offline(tmp_path):
    with TestClient(cloud_app(tmp_path)) as client:
        response = client.get("/api/dashboard/summary")
    assert response.status_code == 503
    assert response.headers["X-Quant-Node-Status"] == "OFFLINE"
    assert response.json()["data_freshness"] == "UNAVAILABLE"


def test_snapshot_cache_is_atomic_and_reports_age(tmp_path):
    cache = SnapshotCache(str(tmp_path / "cache"), max_stale_seconds=60)
    recorded_at = cache.store("GET:/example", 200, {"value": 7})
    cached = cache.load("GET:/example")
    assert cached["payload"] == {"value": 7}
    assert cached["recorded_at"] == recorded_at
    assert cached["age_seconds"] >= 0
