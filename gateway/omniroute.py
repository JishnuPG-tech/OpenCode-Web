"""
OmniRoute AI Gateway Router
===========================
Routes OmniRoute compatibility APIs & Live WebSockets.
OmniRoute is mounted at the root origin (/), owning /dashboard/*, /api/*, /_next/*, etc.
"""

import logging
from fastapi import APIRouter, Request, WebSocket
from gateway.utils import (
    OMNIROUTE_PORT,
    OMNIROUTE_API_PORT,
    OMNIROUTE_WS_PORT,
    PUBLIC_HOST,
    proxy_http_request,
    proxy_websocket_stream,
)

logger = logging.getLogger("OmniRouteGateway")
router = APIRouter(tags=["OmniRoute"])

# ── 1. OpenAI & Gemini Compatibility APIs (Dedicated API Port 20129) ──────────
@router.api_route("/v1", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def omniroute_v1_api(request: Request, path: str = ""):
    target = f"http://127.0.0.1:{OMNIROUTE_API_PORT}/v1/{path}" if path else f"http://127.0.0.1:{OMNIROUTE_API_PORT}/v1"
    return await proxy_http_request(target, request, default_prefix="")

@router.api_route("/v1beta/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def omniroute_v1beta_api(request: Request, path: str = ""):
    target = f"http://127.0.0.1:{OMNIROUTE_API_PORT}/v1beta/{path}"
    return await proxy_http_request(target, request, default_prefix="")

# ── 2. OmniRoute Live Monitoring WebSocket (Dedicated WS Port 20132) ──────────
@router.websocket("/live-ws")
@router.websocket("/live-ws/{path:path}")
@router.websocket("/omniroute/live-ws")
@router.websocket("/omniroute/live-ws/{path:path}")
async def omniroute_live_ws(websocket: WebSocket, path: str = ""):
    target_ws = f"ws://127.0.0.1:{OMNIROUTE_WS_PORT}/live-ws/{path}" if path else f"ws://127.0.0.1:{OMNIROUTE_WS_PORT}/live-ws"
    await proxy_websocket_stream(websocket, target_ws)
