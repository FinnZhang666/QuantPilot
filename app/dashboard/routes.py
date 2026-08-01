from pathlib import Path
from urllib.parse import parse_qs
import secrets

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.config import Settings, get_settings
from app.dashboard.auth import is_admin

router = APIRouter(tags=["公司工作台"])
ROOT = Path(__file__).resolve().parent


def _template(name: str) -> str:
    html = (ROOT / "templates" / name).read_text(encoding="utf-8")
    static_root = ROOT / "static"
    fingerprints = [
        path.stat().st_mtime_ns for path in static_root.rglob("*") if path.is_file()
    ]
    return html.replace("__ASSET_VERSION__", str(max(fingerprints, default=0)))


@router.get("/dashboard/login", response_class=HTMLResponse)
def login_page():
    return _template("login.html")


@router.post("/dashboard/login")
async def login(request: Request, settings: Settings = Depends(get_settings)):
    values = parse_qs((await request.body()).decode("utf-8"))
    token = values.get("token", [""])[0]
    if (
        not settings.dashboard_admin_token or
        not secrets.compare_digest(token, settings.dashboard_admin_token)
    ):
        return HTMLResponse(
            _template("login.html").replace(
                "<!--ERROR-->", '<p class="error">管理员Token无效。</p>',
            ),
            status_code=401,
        )
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie("dashboard_admin", token, httponly=True, samesite="strict")
    return response


@router.post("/dashboard/logout")
def logout():
    response = RedirectResponse("/dashboard/login", status_code=303)
    response.delete_cookie("dashboard_admin")
    return response


def _page(request: Request, settings: Settings, page: str):
    if not settings.dashboard_readonly_public and not is_admin(request, settings):
        return RedirectResponse("/dashboard/login", status_code=303)
    html = _template("dashboard.html")
    return HTMLResponse(html.replace("__PAGE__", page))


@router.get("/dashboard")
def home(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "home")


@router.get("/dashboard/opportunities")
def opportunities(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "opportunities")


@router.get("/dashboard/opportunities/{opportunity_id}")
def opportunity_detail(opportunity_id: int, request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "opportunity-detail")


@router.get("/dashboard/trade-plans")
def trade_plans(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "trade-plans")


@router.get("/dashboard/trade-plans/{plan_id}")
def trade_plan_detail(plan_id: str, request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "trade-plan-detail")


@router.get("/dashboard/positions")
def user_positions(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "positions")


@router.get("/dashboard/positions/{position_id}")
def user_position_detail(position_id: int, request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "position-detail")


@router.get("/dashboard/trade-reviews")
def trade_reviews(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "trade-reviews")


@router.get("/dashboard/trade-reviews/{review_id}")
def trade_review_detail(review_id: int, request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "trade-review-detail")


@router.get("/dashboard/companion")
def companion(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "companion")


@router.get("/dashboard/companion/{analysis_id}")
def companion_detail(analysis_id: int, request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "companion-detail")


@router.get("/dashboard/ai-companion")
def ai_companion(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "companion")


@router.get("/dashboard/ai-companion/{analysis_id}")
def ai_companion_detail(analysis_id: int, request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "companion-detail")


@router.get("/dashboard/portfolios")
def portfolios(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "portfolios")


@router.get("/dashboard/portfolios/{portfolio_id}")
def portfolio_detail(portfolio_id: int, request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "portfolio-detail")


@router.get("/dashboard/holdings/{holding_id}")
def holding_detail(holding_id: int, request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "holding-detail")


@router.get("/dashboard/market-snapshots")
def market_snapshots(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "market-snapshots")


@router.get("/dashboard/market-monitor", include_in_schema=False)
def market_monitor(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "market-monitor")


@router.get("/dashboard/market-snapshots/{symbol}")
def market_snapshot_detail(symbol: str, request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "market-snapshot-detail")


@router.get("/dashboard/symbols/{symbol}")
def symbol_overview(symbol: str, request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "symbol-overview")


@router.get("/dashboard/telegram-preview")
def telegram_preview(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "telegram-preview")


@router.get("/dashboard/watchlists/{portfolio_id}/snapshot")
def watchlist_snapshot(portfolio_id: int, request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "watchlist-snapshot")


@router.get("/dashboard/runtime")
def runtime(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "runtime")


@router.get("/dashboard/strategies")
def strategies(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "strategies")


@router.get("/dashboard/strategies/{strategy_name}")
def strategy_detail(strategy_name: str, request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "strategy-detail")


@router.get("/dashboard/paper-positions", include_in_schema=False)
def paper_positions(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "paper-positions")


@router.get("/dashboard/paper-positions/{position_id}", include_in_schema=False)
def paper_position_detail(
    position_id: int, request: Request, settings: Settings = Depends(get_settings),
):
    return _page(request, settings, "paper-position-detail")


@router.get("/dashboard/strategy-scoreboard", include_in_schema=False)
def strategy_scoreboard(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "strategy-scoreboard")


@router.get("/dashboard/trading-performance", include_in_schema=False)
def trading_performance(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "strategy-scoreboard")


@router.get("/dashboard/strategy-lab/parameters", include_in_schema=False)
def strategy_parameters(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "strategy-parameters")


@router.get("/dashboard/data-quality")
def data_quality(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "data-quality")


@router.get("/dashboard/reports")
def reports(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "reports")


@router.get("/dashboard/development")
def development(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "development")


@router.get("/dashboard/development/{issue_id}")
def development_detail(issue_id: int, request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "development-detail")


@router.get("/dashboard/market-regime")
def market_regime(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "market-regime")


@router.get("/dashboard/candidates")
def candidates(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "candidates")


@router.get("/dashboard/candidates/{entry_id}")
def candidate_detail(entry_id: int, request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "candidate-detail")


@router.get("/dashboard/reviews")
def reviews(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "reviews")


@router.get("/dashboard/reviews/{review_id}")
def review_detail(review_id: int, request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "review-detail")


@router.get("/dashboard/ai-reviews")
def ai_reviews(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "ai-reviews")


@router.get("/dashboard/ai-reviews/{analysis_id}")
def ai_review_detail(analysis_id: int, request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "ai-review-detail")


@router.get("/dashboard/system")
def system(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "system")


@router.get("/dashboard/system-monitor", include_in_schema=False)
def system_monitor(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "system-monitor")


@router.get("/dashboard/runtime-logs", include_in_schema=False)
def runtime_logs(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "runtime-logs")


@router.get("/dashboard/product/feedback", include_in_schema=False)
def product_feedback(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "product-feedback")


@router.get("/dashboard/product/behavior", include_in_schema=False)
def product_behavior(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "product-behavior")


@router.get("/dashboard/product/bot-statistics", include_in_schema=False)
def bot_statistics(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "bot-statistics")


@router.get("/dashboard/product/user-intelligence", include_in_schema=False)
def user_intelligence(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "user-intelligence")


@router.get("/dashboard/research")
def research(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "research")


@router.get("/dashboard/research/{workspace_id}")
def research_detail(
    workspace_id: int, request: Request, settings: Settings = Depends(get_settings),
):
    return _page(request, settings, "research-detail")
