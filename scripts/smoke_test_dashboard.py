import os
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient


def main():
    with TemporaryDirectory() as directory:
        os.environ["DATABASE_URL"] = "sqlite:///" + directory + "/dashboard-smoke.db"
        os.environ["DASHBOARD_ADMIN_TOKEN"] = "dashboard-smoke-token"
        os.environ["DASHBOARD_READONLY_PUBLIC"] = "false"
        from app.core.config import get_settings
        from app.database.session import get_engine
        get_settings.cache_clear()
        get_engine.cache_clear()
        from app.main import app
        with TestClient(app) as client:
            assert client.get("/dashboard", follow_redirects=False).status_code == 303
            response = client.post(
                "/dashboard/login", data={"token": "dashboard-smoke-token"},
                follow_redirects=False,
            )
            assert response.status_code == 303
            for path in (
                "/dashboard", "/dashboard/opportunities", "/dashboard/runtime",
                "/dashboard/market-regime", "/dashboard/candidates",
                "/dashboard/strategies", "/dashboard/data-quality",
                "/dashboard/reports", "/dashboard/development",
            ):
                assert client.get(path).status_code == 200
            assert client.get("/api/dashboard/summary").status_code == 200
            assert client.get("/api/dashboard/data-quality").status_code == 200
            assert client.get("/api/market-regime/current").status_code == 200
            assert client.get("/api/candidate-pool").status_code == 200
            assert "dashboard-smoke-token" not in client.get("/dashboard").text
    print("Sprint 09 Dashboard Smoke Test通过")
    print("- 空数据库页面：通过")
    print("- 管理员登录：通过")
    print("- 九个主页面：通过")
    print("- Token泄露检查：通过")
    print("- 订单接口：未连接")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
