"""
OmniRoute AI Gateway Router
===========================
Routes OmniRoute endpoints cleanly without interfering with Open WebUI, Jellyfin, or TG-Streamer.
Handles:
  - /omniroute/*          Dashboard & frontend routes     → port 20128
  - /v1/*                 OpenAI API compatibility        → port 20129
  - /v1beta/*             Gemini API compatibility        → port 20129
  - /omniroute/live-ws/*  Live monitoring WebSocket       → port 20132
  - /api/monitoring/*     OmniRoute health endpoints      → port 20128
  - /api/providers et al  OmniRoute management APIs       → port 20128
"""

import logging
from fastapi import APIRouter, Request, WebSocket
from fastapi.responses import RedirectResponse
from gateway.utils import (
    OMNIROUTE_PORT,
    OMNIROUTE_API_PORT,
    OMNIROUTE_WS_PORT,
    proxy_http_request,
    proxy_websocket_stream,
)

logger = logging.getLogger("OmniRouteGateway")
router = APIRouter(tags=["OmniRoute"])

# ── 1. OmniRoute Dashboard Pages (Port 20128) ─────────────────────────────────
@router.api_route("/omniroute", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/omniroute/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def omniroute_main_route(request: Request, path: str = ""):
    extra = {
        "Host": f"127.0.0.1:{OMNIROUTE_PORT}",
        "X-Forwarded-Host": f"127.0.0.1:{OMNIROUTE_PORT}",
        "X-Forwarded-Proto": "http"
    }
    # Strip /omniroute prefix when proxying to OmniRoute backend on port 20128
    target = f"http://127.0.0.1:{OMNIROUTE_PORT}/{path}" if path else f"http://127.0.0.1:{OMNIROUTE_PORT}/"
    return await proxy_http_request(
        target,
        request,
        default_prefix="/omniroute",
        extra_headers=extra
    )

# ── 2. OpenAI & Gemini Compatibility APIs (Dedicated API Port 20129) ──────────
@router.api_route("/v1", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def omniroute_v1_api(request: Request, path: str = ""):
    target = f"http://127.0.0.1:{OMNIROUTE_API_PORT}/v1/{path}" if path else f"http://127.0.0.1:{OMNIROUTE_API_PORT}/v1"
    return await proxy_http_request(target, request, default_prefix="")

@router.api_route("/v1beta/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def omniroute_v1beta_api(request: Request, path: str = ""):
    target = f"http://127.0.0.1:{OMNIROUTE_API_PORT}/v1beta/{path}"
    return await proxy_http_request(target, request, default_prefix="")

# ── 3. OmniRoute Live Monitoring WebSocket (Dedicated WS Port 20132) ──────────
@router.websocket("/omniroute/live-ws")
@router.websocket("/omniroute/live-ws/{path:path}")
async def omniroute_live_ws(websocket: WebSocket, path: str = ""):
    target_ws = f"ws://127.0.0.1:{OMNIROUTE_WS_PORT}/live-ws/{path}" if path else f"ws://127.0.0.1:{OMNIROUTE_WS_PORT}/live-ws"
    await proxy_websocket_stream(websocket, target_ws)

# ── 4. OmniRoute Monitoring / Health Endpoints ────────────────────────────────
@router.api_route("/api/monitoring/{path:path}", methods=["GET", "HEAD", "OPTIONS"])
async def omniroute_monitoring(request: Request, path: str = ""):
    target = f"http://127.0.0.1:{OMNIROUTE_PORT}/api/monitoring/{path}"
    return await proxy_http_request(target, request, default_prefix="")

# ── 3. Next.js Static Asset Routing ──────────────────────────────────────────
@router.api_route("/_next/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/omniroute/_next/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def omniroute_assets(request: Request, path: str = ""):
    extra = {
        "Host": f"127.0.0.1:{OMNIROUTE_PORT}",
        "X-Forwarded-Host": f"127.0.0.1:{OMNIROUTE_PORT}",
        "X-Forwarded-Proto": "http"
    }
    target = f"http://127.0.0.1:{OMNIROUTE_PORT}/omniroute/_next/{path}"
    res = await proxy_http_request(target, request, default_prefix="/omniroute", extra_headers=extra)
    if res.status_code == 404:
        alt_target = f"http://127.0.0.1:{OMNIROUTE_PORT}/_next/{path}"
        alt_res = await proxy_http_request(alt_target, request, default_prefix="/omniroute", extra_headers=extra)
        if alt_res.status_code != 404:
            return alt_res
    return res

# ── 4. OAuth & Health Endpoints ──────────────────────────────────────────────
@router.api_route("/authorize", methods=["GET", "POST", "OPTIONS"])
async def omniroute_authorize(request: Request):
    target = f"http://127.0.0.1:{OMNIROUTE_PORT}/authorize"
    return await proxy_http_request(target, request, default_prefix="/omniroute")

# ── 5. Specific OmniRoute Backend Management APIs ─────────────────────────────
OMNIROUTE_API_PREFIXES = (
    "/api/providers",
    "/api/combos",
    "/api/circuit-breakers",
    "/api/settings",
    "/api/usage",
    "/api/system",
    "/api/skills",
    "/api/tunnels",
    "/api/version-manager",
    "/api/tools",
    "/api/mcp",
    "/api/a2a",
    "/api/webhooks",
    "/api/token-health",
    "/api/synced-available-models",
    "/api/shutdown",
    "/api/storage",
    "/api/sync",
    "/api/telemetry",
    "/api/translator",
    "/api/upstream-proxy",
)

# Dynamically register explicit route handlers for OmniRoute management APIs
# This prevents capturing non-OmniRoute routes (such as Open WebUI's /api/config or /api/v1)
for prefix in OMNIROUTE_API_PREFIXES:
    sub_path = prefix.replace("/api/", "")
    
    def _create_route(s_path: str):
        @router.api_route(
            f"/api/{s_path}",
            methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
            include_in_schema=False
        )
        @router.api_route(
            f"/api/{s_path}/{{path:path}}",
            methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
            include_in_schema=False
        )
        async def omniroute_api_handler(request: Request, path: str = ""):
            target_path = f"/api/{s_path}/{path}" if path else f"/api/{s_path}"
            target = f"http://127.0.0.1:{OMNIROUTE_PORT}{target_path}"
            return await proxy_http_request(target, request, default_prefix="/omniroute")
        return omniroute_api_handler

    _create_route(sub_path)

