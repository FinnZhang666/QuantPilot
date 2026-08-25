"""Read-only Cloud Web gateway for a private Windows Quant Node.

The gateway deliberately sits in front of the existing API routers. In cloud_web
mode GET requests are forwarded server-side, while every mutation and /internal
path fails closed. Successful JSON responses are cached on disk so the dashboard
shell remains useful during a temporary Quant Node outage.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

import httpx
from fastapi.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import Settings

LOGGER = logging.getLogger(__name__)
LOCAL_PATHS = {"/health", "/api/cloud/status"}


class SnapshotCache:
    def __init__(self, directory: str, max_stale_seconds: int):
        self.directory = Path(directory)
        self.max_stale_seconds = max_stale_seconds

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.directory / f"{digest}.json"

    def store(self, key: str, status_code: int, payload: Any) -> str:
        self.directory.mkdir(parents=True, exist_ok=True)
        recorded_at = datetime.now(timezone.utc).isoformat()
        body = {"recorded_at": recorded_at, "status_code": status_code, "payload": payload}
        target = self._path(key)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, target)
        return recorded_at

    def load(self, key: str) -> Optional[Dict[str, Any]]:
        target = self._path(key)
        try:
            body = json.loads(target.read_text(encoding="utf-8"))
            recorded = datetime.fromisoformat(body["recorded_at"])
            if recorded.tzinfo is None:
                recorded = recorded.replace(tzinfo=timezone.utc)
            age = max(0, int((datetime.now(timezone.utc) - recorded).total_seconds()))
            if age > self.max_stale_seconds:
                return None
            body["age_seconds"] = age
            return body
        except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def latest_timestamp(self) -> Optional[str]:
        timestamps = []
        if not self.directory.exists():
            return None
        for path in self.directory.glob("*.json"):
            try:
                timestamps.append(json.loads(path.read_text(encoding="utf-8"))["recorded_at"])
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return max(timestamps, default=None)


class CloudGatewayMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings):
        self.app = app
        self.settings = settings
        self.cache = SnapshotCache(
            settings.cloud_cache_directory, settings.cloud_cache_max_stale_seconds,
        )
        self.base_url = settings.quant_node_base_url.rstrip("/")
        self._validate_base_url()

    def _validate_base_url(self) -> None:
        if not self.base_url:
            return
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("QUANT_NODE_BASE_URL必须是有效的HTTP(S)地址。")
        # The production design uses Tailscale. Loopback remains allowed for tests.
        host = parsed.hostname
        if not (host.startswith("100.") or host in {"127.0.0.1", "localhost"}):
            raise ValueError("QUANT_NODE_BASE_URL必须指向Tailscale或loopback地址。")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self.settings.app_role != "cloud_web":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        method = scope.get("method", "GET").upper()
        if path == "/health" or path == "/api/cloud/status":
            await self._send_cloud_health(scope, receive, send)
            return
        if path.startswith("/internal"):
            await JSONResponse({"detail": "Cloud Web不公开内部管理接口。"}, 404)(scope, receive, send)
            return
        if path.startswith("/api/"):
            if method not in {"GET", "HEAD"}:
                await JSONResponse({"detail": "Cloud Web仅允许只读请求。"}, 405)(scope, receive, send)
                return
            await self._proxy(scope, receive, send)
            return
        await self.app(scope, receive, send)

    def _target(self, scope: Scope) -> str:
        query = scope.get("query_string", b"").decode("ascii", errors="ignore")
        suffix = scope.get("path", "") + (f"?{query}" if query else "")
        return self.base_url + suffix

    async def _fetch(self, scope: Scope) -> httpx.Response:
        if not self.base_url:
            raise httpx.ConnectError("Quant Node URL is not configured")
        headers = {"Accept": "application/json"}
        if self.settings.quant_node_api_token:
            headers["X-Dashboard-Token"] = self.settings.quant_node_api_token
        async with httpx.AsyncClient(
            timeout=self.settings.quant_node_timeout_seconds, follow_redirects=False,
        ) as client:
            return await client.get(self._target(scope), headers=headers)

    async def _proxy(self, scope: Scope, receive: Receive, send: Send) -> None:
        key = self._target(scope)
        try:
            upstream = await self._fetch(scope)
            payload = upstream.json()
            if 200 <= upstream.status_code < 300:
                timestamp = self.cache.store(key, upstream.status_code, payload)
            else:
                timestamp = datetime.now(timezone.utc).isoformat()
            response = JSONResponse(payload, status_code=upstream.status_code, headers={
                "X-Quant-Node-Status": "HEALTHY",
                "X-Data-Freshness": "AVAILABLE",
                "X-Source-Timestamp": timestamp,
            })
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            cached = self.cache.load(key)
            LOGGER.warning("Quant Node unavailable; serving cache when possible: %s", type(exc).__name__)
            if cached is None:
                response = JSONResponse({
                    "detail": "Quant Node OFFLINE，当前数据不可用。",
                    "quant_node": "OFFLINE", "data_freshness": "UNAVAILABLE",
                }, status_code=503, headers={
                    "X-Quant-Node-Status": "OFFLINE", "X-Data-Freshness": "UNAVAILABLE",
                })
            else:
                response = JSONResponse(cached["payload"], status_code=cached["status_code"], headers={
                    "X-Quant-Node-Status": "OFFLINE", "X-Data-Freshness": "STALE",
                    "X-Source-Timestamp": cached["recorded_at"],
                    "X-Cache-Age-Seconds": str(cached["age_seconds"]),
                })
        await response(scope, receive, send)

    async def _send_cloud_health(self, scope: Scope, receive: Receive, send: Send) -> None:
        quant_node = "OFFLINE"
        try:
            fake_scope: Scope = {"path": "/health", "query_string": b""}  # type: ignore[typeddict-item]
            upstream = await self._fetch(fake_scope)
            quant_node = "HEALTHY" if upstream.status_code < 500 else "DEGRADED"
        except httpx.HTTPError:
            pass
        payload = {
            "status": "OK" if quant_node == "HEALTHY" else "WARNING",
            "cloud_web": "HEALTHY",
            "quant_node": quant_node,
            "cache": "AVAILABLE" if self.cache.latest_timestamp() else "EMPTY",
            "last_successful_sync": self.cache.latest_timestamp(),
            "data_freshness": "AVAILABLE" if quant_node == "HEALTHY" else (
                "STALE" if self.cache.latest_timestamp() else "UNAVAILABLE"
            ),
            "real_trading": "DISABLED",
        }
        response = JSONResponse(payload, status_code=200, headers={
            "X-Quant-Node-Status": quant_node,
            "Cache-Control": "no-store",
        })
        await response(scope, receive, send)
