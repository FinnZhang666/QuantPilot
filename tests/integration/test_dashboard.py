from datetime import datetime, timezone
from decimal import Decimal
import re

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.models import Opportunity
from app.database.session import get_engine, get_session_factory
from app.main import app


def dashboard_client(monkeypatch, tmp_path, public=False):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "dashboard.db"))
    monkeypatch.setenv("DASHBOARD_ADMIN_TOKEN", "secret-dashboard-token")
    monkeypatch.setenv("DASHBOARD_READONLY_PUBLIC", "true" if public else "false")
    get_settings.cache_clear()
    get_engine.cache_clear()
    client = TestClient(app)
    client.__enter__()
    return client


def login(client):
    return client.post(
        "/dashboard/login", data={"token": "secret-dashboard-token"},
        follow_redirects=False,
    )


def add_opportunity():
    with get_session_factory()() as db:
        row = Opportunity(
            symbol="SOXL", timeframe="1m", direction="LONG",
            opportunity_type="PULLBACK_RESTRENGTH",
            strategy_name="pullback_restrength", strategy_version="1.0.0",
            status="DETECTED", score=83, confidence=90,
            detected_at=datetime.now(timezone.utc), bar_time=datetime.now(timezone.utc),
            entry_reference_price=Decimal("10.25"),
            feature_snapshot_json={"ema_20": "ok"},
            strategy_snapshot_json={"signal_type": "CANDIDATE_BUY"},
            notification_status="PENDING",
        )
        db.add(row)
        db.commit()
        return row.id


def test_dashboard_login_and_all_pages(monkeypatch, tmp_path):
    client = dashboard_client(monkeypatch, tmp_path)
    try:
        assert client.get("/dashboard", follow_redirects=False).status_code == 303
        assert login(client).status_code == 303
        for path in (
            "/dashboard", "/dashboard/opportunities", "/dashboard/runtime",
            "/dashboard/market-regime", "/dashboard/candidates",
            "/dashboard/strategies", "/dashboard/data-quality",
            "/dashboard/reports", "/dashboard/development",
        ):
            response = client.get(path)
            assert response.status_code == 200
            assert "Trade Companion" in response.text
    finally:
        client.__exit__(None, None, None)


def test_empty_summary_and_data_quality(monkeypatch, tmp_path):
    client = dashboard_client(monkeypatch, tmp_path, public=True)
    try:
        summary = client.get("/api/dashboard/summary")
        assert summary.status_code == 200
        assert summary.json()["today"]["opportunities"] == 0
        assert summary.json()["database"]["core_counts"]["covered_symbols"] == 0
        assert summary.json()["database"]["core_counts"]["active_candidates"] == 0
        quality = client.get("/api/dashboard/data-quality")
        assert quality.status_code == 200 and quality.json()["items"] == []
        strategies = client.get("/api/dashboard/strategy-summary").json()
        assert strategies["items"] == []
    finally:
        client.__exit__(None, None, None)


def test_opportunity_filter_and_detail(monkeypatch, tmp_path):
    client = dashboard_client(monkeypatch, tmp_path, public=True)
    try:
        opportunity_id = add_opportunity()
        filtered = client.get("/api/opportunities", params={
            "symbol": "SOXL", "timeframe": "1m", "direction": "LONG",
            "strategy_name": "pullback_restrength", "min_score": 80,
        })
        assert filtered.status_code == 200 and filtered.json()["total"] == 1
        assert client.get("/api/opportunities", params={"min_score": 84}).json()["total"] == 0
        detail = client.get("/api/opportunities/%s" % opportunity_id).json()
        assert detail["feature_snapshot"]["ema_20"] == "ok"
        assert client.get("/dashboard/opportunities/%s" % opportunity_id).status_code == 200
    finally:
        client.__exit__(None, None, None)


def test_runtime_write_requires_admin(monkeypatch, tmp_path):
    client = dashboard_client(monkeypatch, tmp_path, public=True)
    try:
        assert client.get("/api/runtime/status").status_code == 200
        assert client.post("/api/runtime/start").status_code == 401
        assert client.post("/api/runtime/stop").status_code == 401
    finally:
        client.__exit__(None, None, None)


def test_issue_crud_filters_and_auth(monkeypatch, tmp_path):
    client = dashboard_client(monkeypatch, tmp_path, public=True)
    try:
        payload = {
            "title": "检查数据延迟", "description": "SOXL一分钟数据延迟需要调查",
            "source_type": "ADMIN", "priority": "HIGH", "category": "DATA",
        }
        assert client.post("/api/development/issues", json=payload).status_code == 401
        headers = {"X-Dashboard-Token": "secret-dashboard-token"}
        created = client.post("/api/development/issues", json=payload, headers=headers)
        assert created.status_code == 200
        issue_id = created.json()["id"]
        changed = client.patch(
            "/api/development/issues/%s" % issue_id,
            json={"status": "INVESTIGATING"}, headers=headers,
        )
        assert changed.json()["status"] == "INVESTIGATING"
        filtered = client.get("/api/development/issues", params={
            "status": "INVESTIGATING", "source_type": "ADMIN", "priority": "HIGH",
        })
        assert filtered.json()["total"] == 1
        assert client.get("/api/development/issues/%s" % issue_id).status_code == 200
    finally:
        client.__exit__(None, None, None)


def test_tokens_not_leaked(monkeypatch, tmp_path):
    client = dashboard_client(monkeypatch, tmp_path)
    try:
        login(client)
        for path in ("/dashboard", "/api/dashboard/summary", "/api/runtime/status"):
            response = client.get(path)
            assert "secret-dashboard-token" not in response.text
            assert "telegram_bot_token" not in response.text
    finally:
        client.__exit__(None, None, None)


def test_dashboard_product_shell_and_all_routes(monkeypatch, tmp_path):
    client = dashboard_client(monkeypatch, tmp_path)
    try:
        login(client)
        paths = (
            "/dashboard", "/dashboard/opportunities", "/dashboard/trade-plans",
            "/dashboard/positions", "/dashboard/portfolios",
            "/dashboard/market-snapshots", "/dashboard/telegram-preview",
            "/dashboard/trade-reviews", "/dashboard/companion",
            "/dashboard/market-regime", "/dashboard/candidates",
            "/dashboard/reviews", "/dashboard/ai-reviews", "/dashboard/research",
            "/dashboard/runtime", "/dashboard/strategies",
            "/dashboard/data-quality", "/dashboard/reports",
            "/dashboard/development", "/dashboard/system",
            "/dashboard/symbols/QQQ", "/dashboard/holdings/1",
            "/dashboard/market-monitor", "/dashboard/paper-positions",
            "/dashboard/strategy-scoreboard", "/dashboard/strategy-lab/parameters",
            "/dashboard/product/feedback", "/dashboard/product/behavior",
            "/dashboard/product/bot-statistics",
            "/dashboard/product/user-intelligence",
            "/dashboard/system-monitor", "/dashboard/runtime-logs",
        )
        for path in paths:
            response = client.get(path)
            assert response.status_code == 200
            assert "Trade Companion" in response.text
            assert "branding/trade-companion-logo.png" in response.text
            assert "ui.js" in response.text
    finally:
        client.__exit__(None, None, None)


def test_telegram_preview_uses_safe_html_renderer(monkeypatch, tmp_path):
    client = dashboard_client(monkeypatch, tmp_path)
    try:
        source = client.get("/dashboard/static/dashboard.js").text
        assert "safeTelegramHtml(x.text)" in source
        assert "esc(x.text)" not in source
        assert "?language=${encodeURIComponent(locale)}" in source
    finally:
        client.__exit__(None, None, None)


def test_dashboard_navigation_is_grouped_and_has_no_placeholder_links(monkeypatch, tmp_path):
    client = dashboard_client(monkeypatch, tmp_path)
    try:
        login(client)
        html = client.get("/dashboard").text
        assert html.count('class="nav-group"') >= 7
        assert 'id="sidebar-toggle"' in html
        assert 'id="mobile-menu"' in html
        assert 'href="#"' not in html
        for target in (
            "/dashboard/market-regime", "/dashboard/market-monitor",
            "/dashboard/candidates", "/dashboard/trade-plans",
            "/dashboard/paper-positions", "/dashboard/trade-reviews",
            "/dashboard/strategy-scoreboard", "/dashboard/companion",
            "/dashboard/ai-reviews", "/dashboard/telegram-preview",
            "/dashboard/product/feedback", "/dashboard/product/behavior",
            "/dashboard/product/bot-statistics",
            "/dashboard/product/user-intelligence", "/dashboard/strategies",
            "/dashboard/strategy-lab/parameters", "/dashboard/research",
            "/dashboard/system", "/dashboard/system-monitor",
            "/dashboard/runtime-logs",
        ):
            assert 'href="%s"' % target in html
        assert 'href="/dashboard/opportunities"' not in html
        assert 'href="/dashboard/positions"' not in html
    finally:
        client.__exit__(None, None, None)


def test_dashboard_language_and_accessibility_assets(monkeypatch, tmp_path):
    client = dashboard_client(monkeypatch, tmp_path)
    try:
        login(client)
        html = client.get("/dashboard").text
        script = client.get("/dashboard/static/ui.js").text
        login_html = client.get("/dashboard/login").text
        assert 'id="language-select"' in html
        assert 'value="zh-CN"' in html and 'value="en-US"' in html
        assert 'tc-dashboard-language' in script
        assert '"zh-CN"' in script and '"en-US"' in script
        assert 'aria-label="主导航"' in html
        assert 'aria-label="刷新页面"' in html
        assert 'for="admin-token"' in login_html
        assert 'id="toggle-password"' in login_html
        assert "QuantPilot" not in login_html
    finally:
        client.__exit__(None, None, None)


def test_dashboard_version_uses_central_source(monkeypatch, tmp_path):
    client = dashboard_client(monkeypatch, tmp_path, public=True)
    try:
        version = client.get("/api/platform/version").json()
        openapi = client.get("/openapi.json").json()
        script = client.get("/dashboard/static/dashboard.js").text
        html = client.get("/dashboard").text
        assert version["product"] == openapi["info"]["title"] == "Trade Companion"
        assert version["version"] == openapi["info"]["version"] == "1.0.0-rc2"
        assert version["sprint"] == "40"
        assert version["migration"] in {"0022", "unknown"}
        assert "/api/platform/version" in script
        assert 'id="footer-version"' in html
        assert "1.0.0-rc1" not in html + script
    finally:
        client.__exit__(None, None, None)


def test_dashboard_responsive_and_component_system(monkeypatch, tmp_path):
    client = dashboard_client(monkeypatch, tmp_path, public=True)
    try:
        css = client.get("/dashboard/static/dashboard.css").text
        script = client.get("/dashboard/static/dashboard.js").text
        for breakpoint in ("1280px", "900px", "600px"):
            assert breakpoint in css
        assert ".sidebar-collapsed" in css
        assert ".table-wrap" in css and "position:sticky" in css
        assert ":focus-visible" in css
        assert ".button.disabled" in css and "pointer-events:none" in css
        assert "telegram-phone" in css and "telegram-preview-layout" in css
        assert "暂无交易计划" in script
        assert "暂无持仓计划" in script
        assert "暂无复盘记录" in script
        assert "暂无 AI 分析" in script
    finally:
        client.__exit__(None, None, None)


def test_product_architecture_primary_navigation(monkeypatch, tmp_path):
    client = dashboard_client(monkeypatch, tmp_path, public=True)
    try:
        html = client.get("/dashboard").text
        script = client.get("/dashboard/static/ui.js").text
        for label in (
            "🏠 工作台", "📈 市场", "📊 策略", "🤖 AI",
            "📱 产品运营", "🧪 Strategy Lab", "⚙ 更多",
        ):
            assert label in html + script
        for label in ("市场监控", "我的持仓", "策略成绩榜", "用户反馈", "系统监控"):
            assert label in html
        assert 'data-nav="opportunities"' not in html
        assert 'data-nav="positions"' not in html
    finally:
        client.__exit__(None, None, None)


def test_product_architecture_is_presentation_only(monkeypatch, tmp_path):
    client = dashboard_client(monkeypatch, tmp_path, public=True)
    try:
        script = client.get("/dashboard/static/dashboard.js").text
        for function_name in (
            "marketMonitor", "strategyScoreboard", "productFeedback", "systemMonitor",
        ):
            assert "function %s" % function_name in script
        assert "Telegram Runtime 未接入" in script
        assert "不发送消息" in script
        assert "/api/development/issues?source_type=USER_FEEDBACK" in script
        assert "/api/platform/version" in script
        assert "place_order" not in script
        assert "sendMessage" not in script
    finally:
        client.__exit__(None, None, None)


def test_every_sidebar_route_is_registered_protected_and_renders(monkeypatch, tmp_path):
    client = dashboard_client(monkeypatch, tmp_path)
    try:
        public_html = client.get("/dashboard/login").text
        assert "Trade Companion" in public_html
        assert login(client).status_code == 303
        html = client.get("/dashboard").text
        paths = sorted(set(re.findall(
            r'<a href="(/dashboard(?:/[^"]*)?)" data-nav=', html,
        )))
        route_paths = {route.path: route.name for route in app.routes}
        assert paths
        for path in paths:
            assert path in route_paths, "Sidebar route is not registered: %s" % path
            response = client.get(path)
            assert response.status_code == 200, path
            assert response.headers["content-type"].startswith("text/html")
            assert 'data-page="' in response.text
            assert '{"detail":"Not Found"}' not in response.text
        client.cookies.clear()
        for path in paths:
            response = client.get(path, follow_redirects=False)
            assert response.status_code == 303, path
            assert response.headers["location"] == "/dashboard/login"
    finally:
        client.__exit__(None, None, None)


def test_part_d_dashboard_ui_contract(monkeypatch, tmp_path):
    client = dashboard_client(monkeypatch, tmp_path, public=True)
    try:
        html = client.get("/dashboard").text
        script = client.get("/dashboard/static/dashboard.js").text
        ui = client.get("/dashboard/static/ui.js").text
        css = client.get("/dashboard/static/dashboard.css").text
        assert html.count("nav-group-toggle") == 7
        assert "tc-nav-group-" in ui and 'aria-expanded' in ui
        assert "homeFinal" in script and "pageFailure" in script
        assert "retry-page" in script
        assert "My Positions" in script
        assert "user holdings and broker data are not substituted" in script
        assert "Strategy Lab" in script and "Parameter experiments" in script
        assert "Safe Log View" in script
        assert "Telegram Runtime is unavailable" in script
        assert "min-height:66px" in css
        assert 'href="#"' not in html
        assert "sendMessage" not in script and "place_order" not in script
    finally:
        client.__exit__(None, None, None)
