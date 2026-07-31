import base64
from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.models import Opportunity
from app.database.session import get_engine, get_session_factory
from app.main import app


def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "research.db"))
    monkeypatch.setenv("DASHBOARD_ADMIN_TOKEN", "research-admin")
    monkeypatch.setenv("DASHBOARD_READONLY_PUBLIC", "false")
    get_settings.cache_clear()
    get_engine.cache_clear()
    return TestClient(app)


def add_opportunity():
    with get_session_factory()() as db:
        row = Opportunity(
            symbol="SOXL", timeframe="60m", direction="LONG",
            opportunity_type="PULLBACK_RESTRENGTH",
            strategy_name="pullback_restrength", strategy_version="1.0.0",
            status="ACTIVE", score=80, confidence=90,
            detected_at=datetime.now(timezone.utc), bar_time=datetime.now(timezone.utc),
            entry_reference_price=Decimal("20"), feature_snapshot_json={},
            strategy_snapshot_json={}, decision_snapshot_json={},
            notification_status="PENDING",
        )
        db.add(row)
        db.commit()
        return row.id


def test_research_api_requires_admin(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as value:
        assert value.get("/api/research").status_code == 401


def test_research_list_detail_timeline(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as value:
        add_opportunity()
        headers = {"X-Dashboard-Token": "research-admin"}
        listing = value.get("/api/research", headers=headers).json()
        assert listing["total"] == 1
        workspace_id = listing["items"][0]["id"]
        assert value.get("/api/research/%s" % workspace_id, headers=headers).status_code == 200
        assert value.get(
            "/api/research/%s/timeline" % workspace_id, headers=headers,
        ).json()["total"] >= 1


def test_research_note_attachment_similarity(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as value:
        add_opportunity()
        headers = {"X-Dashboard-Token": "research-admin"}
        workspace_id = value.get("/api/research", headers=headers).json()["items"][0]["id"]
        note = value.post(
            "/api/research/%s/notes" % workspace_id, headers=headers,
            json={"content": "观察成交量", "note_type": "OBSERVATION"},
        )
        assert note.status_code == 200
        attachment = value.post(
            "/api/research/%s/attachments" % workspace_id, headers=headers,
            json={"filename": "note.md", "content_base64": base64.b64encode(b"note").decode()},
        )
        assert attachment.status_code == 200
        assert value.get(
            "/api/research/%s/similarity" % workspace_id, headers=headers,
        ).status_code == 200


def test_research_dashboard(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as value:
        response = value.get(
            "/dashboard/research", headers={"X-Dashboard-Token": "research-admin"},
            follow_redirects=False,
        )
        assert response.status_code == 200 and "Trade Companion" in response.text
