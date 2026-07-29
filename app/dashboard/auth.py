import secrets
from typing import Optional

from fastapi import Depends, HTTPException, Request

from app.core.config import Settings, get_settings


def supplied_token(request: Request) -> str:
    return request.headers.get("X-Dashboard-Token") or request.cookies.get("dashboard_admin") or ""


def is_admin(request: Request, settings: Settings) -> bool:
    expected = settings.dashboard_admin_token
    return bool(expected and secrets.compare_digest(supplied_token(request), expected))


def require_admin(
    request: Request, settings: Settings = Depends(get_settings),
) -> None:
    if not is_admin(request, settings):
        raise HTTPException(401, "管理员Token无效或未提供。")


def require_read(
    request: Request, settings: Settings = Depends(get_settings),
) -> None:
    if settings.dashboard_readonly_public:
        return
    require_admin(request, settings)
