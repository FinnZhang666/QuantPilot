import re
from pathlib import Path

from app.core.config import Settings
from app.main import app
from app.version import PRODUCT, SPRINT, VERSION


ROOT = Path(__file__).resolve().parents[2]


def test_release_version_is_frozen():
    assert (PRODUCT, VERSION, SPRINT) == ("Trade Companion", "1.0.0-beta.1", "40")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "1.0.0b1"' in pyproject


def test_env_example_exactly_covers_settings_without_real_secrets():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    keys = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", text, re.MULTILINE))
    assert keys == {name.upper() for name in Settings.model_fields}
    for secret in ("TELEGRAM_BOT_TOKEN", "AI_REVIEW_API_KEY", "AI_COMPANION_API_KEY",
                   "DASHBOARD_ADMIN_TOKEN"):
        assert re.search(r"^%s=$" % secret, text, re.MULTILINE)


def test_release_documents_exist_and_use_product_name():
    names = ("INSTALLATION.md", "DEPLOYMENT.md", "RELEASE_CHECKLIST.md",
             "KNOWN_ISSUES.md", "BACKUP_AND_RECOVERY.md")
    for name in names:
        text = (ROOT / "docs" / name).read_text(encoding="utf-8")
        assert "Trade Companion" in text and len(text) > 300


def test_windows_service_entry_points_are_explicit_and_safe():
    required = (
        "scripts/run_dashboard_service.py",
        "scripts/run_paper_runtime_worker.py",
        "scripts/run_telegram_runtime_worker.py",
        "scripts/windows/start-trade-companion.ps1",
        "scripts/windows/stop-trade-companion.ps1",
        "scripts/windows/restart-trade-companion.ps1",
        "docs/WINDOWS_SERVICE_PLAN.md",
    )
    for name in required:
        assert (ROOT / name).is_file()
    start = (ROOT / "scripts/windows/start-trade-companion.ps1").read_text(encoding="utf-8")
    stop = (ROOT / "scripts/windows/stop-trade-companion.ps1").read_text(encoding="utf-8")
    plan = (ROOT / "docs/WINDOWS_SERVICE_PLAN.md").read_text(encoding="utf-8")
    assert "-WindowStyle Hidden" in start
    assert "refusing to stop" in stop
    assert "does not register Windows services" in plan


def test_release_includes_phase4_migrations():
    versions = ROOT / "alembic" / "versions"
    assert any("0022" in path.name for path in versions.glob("*.py"))
    assert any("0023" in path.name for path in versions.glob("*.py"))
    assert any("0024" in path.name for path in versions.glob("*.py"))
    assert any("0025" in path.name for path in versions.glob("*.py"))
    assert any("0026" in path.name for path in versions.glob("*.py"))
    assert not any(re.match(r"002[7-9]", path.name) for path in versions.glob("*.py"))


def test_readme_known_limitations_are_current():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "当前已包含 Strategy、Backtest、Dashboard" in text
    assert "当前不含Moomoo模拟下单、策略、回测、前端" not in text


def test_public_openapi_phase4_surface_and_internal_hidden():
    paths = app.openapi()["paths"]
    assert len(paths) == 181
    assert sum(len(operations) for operations in paths.values()) == 190
    assert not any(path.startswith("/internal") for path in paths)


def test_dashboard_release_routes_remain_available():
    paths = {route.path for route in app.routes}
    required = {
        "/dashboard", "/dashboard/market-snapshots", "/dashboard/symbols/{symbol}",
        "/dashboard/portfolios", "/dashboard/trade-reviews", "/dashboard/companion",
        "/dashboard/telegram-preview", "/docs", "/health",
    }
    assert required <= paths


def test_environment_check_is_availability_only():
    source = (ROOT / "scripts" / "check_environment.py").read_text(encoding="utf-8")
    assert "find_spec" in source
    assert "import_module" not in source
