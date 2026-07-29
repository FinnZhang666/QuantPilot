from pathlib import Path
from urllib.parse import parse_qs
import secrets

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.config import Settings, get_settings
from app.dashboard.auth import is_admin

router = APIRouter(tags=["公司工作台"])
ROOT = Path(__file__).resolve().parent


@router.get("/dashboard/login", response_class=HTMLResponse)
def login_page():
    return (ROOT / "templates" / "login.html").read_text(encoding="utf-8")


@router.post("/dashboard/login")
async def login(request: Request, settings: Settings = Depends(get_settings)):
    values = parse_qs((await request.body()).decode("utf-8"))
    token = values.get("token", [""])[0]
    if (
        not settings.dashboard_admin_token or
        not secrets.compare_digest(token, settings.dashboard_admin_token)
    ):
        return HTMLResponse(
            (ROOT / "templates" / "login.html").read_text(encoding="utf-8").replace(
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
    html = (ROOT / "templates" / "dashboard.html").read_text(encoding="utf-8")
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


@router.get("/dashboard/runtime")
def runtime(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "runtime")


@router.get("/dashboard/strategies")
def strategies(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "strategies")


@router.get("/dashboard/strategies/{strategy_name}")
def strategy_detail(strategy_name: str, request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "strategy-detail")


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


@router.get("/dashboard/research")
def research(request: Request, settings: Settings = Depends(get_settings)):
    return _page(request, settings, "research")


@router.get("/dashboard/research/{workspace_id}")
def research_detail(
    workspace_id: int, request: Request, settings: Settings = Depends(get_settings),
):
    return _page(request, settings, "research-detail")
