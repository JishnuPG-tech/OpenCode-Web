"""
OpenCode Space — Production Gateway Main Application (Approach A)
==================================================================
OmniRoute is mounted as the primary root application (/), owning /dashboard/*, /api/*, /_next/*, etc.
Open WebUI is cleanly namespace-isolated under /openwebui/.
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, WebSocket
from fastapi.responses import RedirectResponse

from gateway.utils import (
    get_http_client,
    proxy_http_request,
    proxy_websocket_stream,
    WEBUI_PORT,
    OMNIROUTE_PORT,
    OMNIROUTE_API_PORT,
    JELLYFIN_PORT,
    TG_PORT,
    PUBLIC_HOST,
)
from gateway.openwebui import router as openwebui_router, fixup_webui_html
from gateway.omniroute import router as omniroute_router
from gateway.jellyfin import router as jellyfin_router
from gateway.tg_stream import router as tg_stream_router

logger = logging.getLogger("GatewayMain")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Gateway Connection Pool...")
    client = get_http_client()
    yield
    logger.info("Closing Gateway Connection Pool...")
    if not client.is_closed:
        await client.aclose()


app = FastAPI(title="OpenCode Space Gateway", lifespan=lifespan, docs_url=None, redoc_url=None)

# Include Service Routers
app.include_router(omniroute_router)
app.include_router(openwebui_router)
app.include_router(jellyfin_router)
app.include_router(tg_stream_router)


# ── Root Direct Handler for Open WebUI Landing Page ───────────────────────────
@app.api_route("/", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def root_proxy(request: Request):
    return await proxy_http_request(f"http://127.0.0.1:{WEBUI_PORT}/", request, default_prefix="")

@app.api_route("/favicon.ico", methods=["GET", "HEAD"])
async def favicon():
    return Response(content=b"", status_code=204)

# ── Dedicated Open WebUI Socket.IO WebSocket Handler ──────────────────────────
@app.websocket("/ws/socket.io")
@app.websocket("/ws/socket.io/{path:path}")
@app.websocket("/openwebui/ws/socket.io")
@app.websocket("/openwebui/ws/socket.io/{path:path}")
async def handle_openwebui_socketio(websocket: WebSocket, path: str = ""):
    target = f"ws://127.0.0.1:{WEBUI_PORT}/ws/socket.io"
    if path:
        target = f"{target}/{path}"
    await proxy_websocket_stream(websocket, target)

# ── Health Watchdog System ───────────────────────────────────────────────────
@app.get("/health/live")
async def health_liveness():
    return {"status": "alive"}

@app.get("/health/ready")
@app.get("/health/services")
@app.get("/health")
@app.get("/debug/status")
async def health_services():
    client = get_http_client()
    services = {
        "redis":               "http://127.0.0.1:6379",
        "omniroute":           f"http://127.0.0.1:{OMNIROUTE_PORT}/dashboard",
        "omniroute_api":       f"http://127.0.0.1:{OMNIROUTE_API_PORT}/v1/models",
        "openwebui":           f"http://127.0.0.1:{WEBUI_PORT}/api/config",
        "jellyfin":            f"http://127.0.0.1:{JELLYFIN_PORT}/health",
        "telegram":            f"http://127.0.0.1:{TG_PORT}/",
    }
    results = {}
    for name, url in services.items():
        if name == "redis":
            results[name] = "healthy"
            continue
        try:
            r = await client.get(url, timeout=3.0)
            results[name] = "healthy" if r.status_code < 500 else f"unhealthy ({r.status_code})"
        except Exception as exc:
            results[name] = f"error ({exc})"
    return {
        "status": "healthy",
        "gateway": "healthy",
        "services": results
    }


# ── Catch-All Router (Open WebUI Native at Root /, OmniRoute at /omniroute and /dashboard) ──
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def route_catch_all(path: str, request: Request):
    req_path = request.url.path.lower()
    referer  = request.headers.get("referer", "").lower()

    # ── OmniRoute Core Application & API Endpoints ──────────────────────────────
    omniroute_paths = (
        "/omniroute", "/dashboard", "/_next", "/v1", "/v1beta",
        "/api/providers", "/api/combos", "/api/oauth", "/api/credentials",
        "/api/settings", "/api/monitoring", "/login", "/home", "/callback", "/live-ws"
    )
    if any(req_path.startswith(p) for p in omniroute_paths):
        sub_p = path.replace("omniroute/", "", 1).replace("omniroute", "", 1)
        extra = {
            "Host": PUBLIC_HOST,
            "X-Forwarded-Host": PUBLIC_HOST,
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Port": "443"
        }
        return await proxy_http_request(f"http://127.0.0.1:{OMNIROUTE_PORT}/{sub_p}", request, default_prefix="", extra_headers=extra)

    # Jellyfin Media Server
    if req_path.startswith("/jellyfin") or "/jellyfin" in referer:
        sub_p = path.replace("jellyfin/", "", 1).replace("jellyfin", "", 1)
        return await proxy_http_request(f"http://127.0.0.1:{JELLYFIN_PORT}/{sub_p}", request, default_prefix="/jellyfin", extra_headers={"X-Forwarded-Prefix": "/jellyfin"})

    # Telegram Streamer
    if req_path.startswith("/tg-stream") or req_path.startswith("/tg_stream") or "/tg" in referer:
        sub_p = path.replace("tg-stream/", "", 1).replace("tg_stream/", "", 1)
        return await proxy_http_request(f"http://127.0.0.1:{TG_PORT}/{sub_p}", request, default_prefix="/tg-stream")

    # Default root traffic (Open WebUI native at /, /api/config, /ws/socket.io, /_app/*, /static/*, /assets/*)
    sub_p = path.replace("openwebui/", "", 1).replace("openwebui", "", 1)
    return await proxy_http_request(f"http://127.0.0.1:{WEBUI_PORT}/{sub_p}", request, default_prefix="")
