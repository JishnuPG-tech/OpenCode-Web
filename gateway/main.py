"""
OpenCode Space — Production Gateway Main Application
=====================================================
Assembles Service Routers into a unified FastAPI ASGI Gateway:
  1. Lightweight Public Readiness: /health/live (HTTP 200 {"status": "alive"})
  2. Open WebUI (gateway.openwebui) -> / (Root Fallback, 8098)
  3. OmniRoute Gateway (gateway.omniroute) -> /v1, /v1beta, /dashboard, /api/providers, /api/oauth, /live-ws
  4. Jellyfin Media Server (gateway.jellyfin) -> /jellyfin (8096)
  5. TG-Drive Direct Streamer (gateway.tg_stream) -> /tg_stream (8080)
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse

from gateway.utils import (
    get_http_client,
    proxy_http_request,
    WEBUI_PORT,
    JELLYFIN_PORT,
    TG_PORT,
    OMNIROUTE_PORT,
)
from gateway.openwebui import router as openwebui_router, fixup_webui_html
from gateway.omniroute import router as omniroute_router, omniroute_main_route
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
app.include_router(openwebui_router)
app.include_router(omniroute_router)
app.include_router(jellyfin_router)
app.include_router(tg_stream_router)


# ── Lightweight Platform Readiness Endpoint ──────────────────────────────────
@app.get("/health/live")
@app.head("/health/live")
async def health_live():
    """
    Lightweight platform readiness check required for Hugging Face Spaces.
    Must return immediately with HTTP 200 without blocking on downstream initialization.
    """
    return JSONResponse(content={"status": "alive"}, status_code=200)


# ── Root Landing & Diagnostic Routes ─────────────────────────────────────────
@app.api_route("/favicon.ico", methods=["GET", "HEAD"])
async def favicon():
    return Response(content=b"", status_code=204)

@app.get("/health")
@app.get("/debug/status")
async def health_check():
    client = get_http_client()
    services = {
        "openwebui": f"http://127.0.0.1:{WEBUI_PORT}/",
        "jellyfin":  f"http://127.0.0.1:{JELLYFIN_PORT}/",
        "tg_stream": f"http://127.0.0.1:{TG_PORT}/",
        "omniroute": f"http://127.0.0.1:{OMNIROUTE_PORT}/",
    }
    results = {}
    for name, url in services.items():
        try:
            r = await client.get(url, timeout=2.0)
            results[name] = {"status": "ok", "code": r.status_code}
        except Exception as exc:
            results[name] = {"status": "starting", "message": str(exc)}
    return {"gateway": "healthy", "upstreams": results}


# ── Catch-All Referer & Subpath Fallback Router ──────────────────────────────
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def route_catch_all(path: str, request: Request):
    referer = request.headers.get("referer", "").lower()
    req_path = request.url.path.lower()

    # ── 1. OmniRoute Explicit Management & API Endpoints ──────────────────────
    if req_path in ("/omniroute", "/omniroute/"):
        return RedirectResponse(url="/dashboard", status_code=307)

    OMNIROUTE_PREFIXES = (
        "/dashboard",
        "/omniroute",
        "/_next",
        "/api/providers",
        "/api/credentials",
        "/api/oauth",
        "/api/settings",
        "/api/monitoring",
        "/api/combos",
        "/api/auth",
        "/api/models",
        "/api/keys",
        "/api/stats",
        "/api/health",
        "/api/system",
        "/api/logs",
        "/api/users",
        "/api/vector",
        "/api/chats",
        "/api/tokens",
        "/api/cloud-agent-credentials",
    )

    OMNIROUTE_EXACT = (
        "/login",
        "/forgot-password",
        "/reset-password",
        "/reset",
        "/register",
        "/signup",
        "/auth",
        "/home",
        "/callback",
    )

    if (
        any(req_path == p or req_path.startswith(p + "/") for p in OMNIROUTE_PREFIXES)
        or req_path in OMNIROUTE_EXACT
    ):
        logger.info(f"[ROUTER] {req_path} -> OmniRoute ({OMNIROUTE_PORT})")
        extra = {
            "Host": PUBLIC_HOST,
            "X-Forwarded-Host": PUBLIC_HOST,
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Port": "443",
        }
        return await proxy_http_request(f"http://127.0.0.1:{OMNIROUTE_PORT}{req_path}", request, default_prefix="", extra_headers=extra)

    # ── 2. Jellyfin Media Server Namespace ────────────────────────────────────
    if req_path == "/jellyfin" or req_path.startswith("/jellyfin/"):
        logger.info(f"[ROUTER] {req_path} -> Jellyfin ({JELLYFIN_PORT})")
        sub_p = "/" if req_path == "/jellyfin" else req_path[len("/jellyfin"):]
        return await proxy_http_request(f"http://127.0.0.1:{JELLYFIN_PORT}{sub_p}", request, default_prefix="/jellyfin", extra_headers={"X-Forwarded-Prefix": "/jellyfin"})

    # ── 3. Telegram Streamer Namespace ────────────────────────────────────────
    if req_path in ("/tg-stream", "/tg_stream") or req_path.startswith("/tg-stream/") or req_path.startswith("/tg_stream/"):
        logger.info(f"[ROUTER] {req_path} -> Telegram ({TG_PORT})")
        if req_path in ("/tg-stream", "/tg_stream"):
            sub_p = "/"
        elif req_path.startswith("/tg-stream/"):
            sub_p = req_path[len("/tg-stream"):]
        else:
            sub_p = req_path[len("/tg_stream"):]
        return await proxy_http_request(f"http://127.0.0.1:{TG_PORT}{sub_p}", request, default_prefix="/tg-stream")

    # ── 4. Primary Root Application Fallback -> Open WebUI (:8098) ────────────
    logger.info(f"[ROUTER] {req_path} -> Open WebUI ({WEBUI_PORT})")
    return await proxy_http_request(f"http://127.0.0.1:{WEBUI_PORT}{req_path}", request, default_prefix="", html_fixup=fixup_webui_html)
