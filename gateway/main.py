"""
OpenCode Space — Production Gateway Main Application (Approach A)
==================================================================
OmniRoute is mounted as the primary root application (/), owning /dashboard/*, /api/*, /_next/*, etc.
Open WebUI is cleanly namespace-isolated under /openwebui/.
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.responses import RedirectResponse

from gateway.utils import (
    get_http_client,
    proxy_http_request,
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


# ── Root Direct Handler for OmniRoute Landing Page ───────────────────────────
@app.api_route("/", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def root_proxy(request: Request):
    extra = {
        "Host": PUBLIC_HOST,
        "X-Forwarded-Host": PUBLIC_HOST,
        "X-Forwarded-Proto": "https",
        "X-Forwarded-Port": "443"
    }
    return await proxy_http_request(f"http://127.0.0.1:{OMNIROUTE_PORT}/", request, default_prefix="", extra_headers=extra)

@app.api_route("/favicon.ico", methods=["GET", "HEAD"])
async def favicon():
    return Response(content=b"", status_code=204)

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


# ── Catch-All Router (OmniRoute Native at Root /, Open WebUI at /openwebui/) ──
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def route_catch_all(path: str, request: Request):
    req_path = request.url.path.lower()
    referer  = request.headers.get("referer", "").lower()
    has_owui_scope = request.cookies.get("OWUI_SCOPE") == "1"

    # Context-aware Open WebUI detection
    is_owui_path = req_path.startswith("/openwebui") or req_path.startswith("/_app")
    if not is_owui_path and (has_owui_scope or "/openwebui" in referer):
        if req_path in ("/api/config", "/api/version", "/manifest.json", "/favicon.ico") or req_path.startswith(("/api/v1/", "/ws/", "/socket.io/", "/static/", "/assets/")):
            is_owui_path = True

    # Open WebUI routing
    if is_owui_path:
        sub_p = path.replace("openwebui/", "", 1).replace("openwebui", "", 1)
        resp = await proxy_http_request(f"http://127.0.0.1:{WEBUI_PORT}/{sub_p}", request, default_prefix="/openwebui", html_fixup=fixup_webui_html)
        if req_path.startswith("/openwebui"):
            resp.set_cookie("OWUI_SCOPE", "1", path="/", samesite="lax")
        return resp

    # Jellyfin
    if req_path.startswith("/jellyfin") or "/jellyfin" in referer:
        sub_p = path.replace("jellyfin/", "", 1).replace("jellyfin", "", 1)
        return await proxy_http_request(f"http://127.0.0.1:{JELLYFIN_PORT}/{sub_p}", request, default_prefix="/jellyfin", extra_headers={"X-Forwarded-Prefix": "/jellyfin"})

    # Telegram Streamer
    if req_path.startswith("/tg-stream") or req_path.startswith("/tg_stream") or "/tg" in referer:
        sub_p = path.replace("tg-stream/", "", 1).replace("tg_stream/", "", 1)
        return await proxy_http_request(f"http://127.0.0.1:{TG_PORT}/{sub_p}", request, default_prefix="/tg-stream")

    # Handle legacy /omniroute links by proxying natively to root
    if req_path.startswith("/omniroute"):
        sub_p = path.replace("omniroute/", "", 1).replace("omniroute", "", 1)
        extra = {
            "Host": PUBLIC_HOST,
            "X-Forwarded-Host": PUBLIC_HOST,
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Port": "443"
        }
        return await proxy_http_request(f"http://127.0.0.1:{OMNIROUTE_PORT}/{sub_p}", request, default_prefix="", extra_headers=extra)

    # Default native root traffic (OmniRoute dashboard, /api/*, /_next/*, /dashboard/*, /login, /callback) -> OmniRoute (:20128)
    extra = {
        "Host": PUBLIC_HOST,
        "X-Forwarded-Host": PUBLIC_HOST,
        "X-Forwarded-Proto": "https",
        "X-Forwarded-Port": "443"
    }
    return await proxy_http_request(f"http://127.0.0.1:{OMNIROUTE_PORT}/{path}", request, default_prefix="", extra_headers=extra)
