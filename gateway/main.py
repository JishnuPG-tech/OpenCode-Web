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

# ── Health & Diagnostics ──────────────────────────────────────────────────────
@app.get("/health")
@app.get("/debug/status")
async def health_check():
    client = get_http_client()
    services = {
        "omniroute_dashboard": f"http://127.0.0.1:{OMNIROUTE_PORT}/dashboard",
        "omniroute_api":       f"http://127.0.0.1:{OMNIROUTE_API_PORT}/v1/models",
        "openwebui":           f"http://127.0.0.1:{WEBUI_PORT}/api/config",
        "jellyfin":            f"http://127.0.0.1:{JELLYFIN_PORT}/health",
        "tg_stream":           f"http://127.0.0.1:{TG_PORT}/",
    }
    results = {}
    for name, url in services.items():
        try:
            r = await client.get(url, timeout=3.0)
            results[name] = {"status": "ok", "code": r.status_code}
        except Exception as exc:
            results[name] = {"status": "error", "message": str(exc)}
    return {"gateway": "healthy", "upstreams": results}


# ── Catch-All Router (OmniRoute Native at Root /, Open WebUI at /openwebui/) ──
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def route_catch_all(path: str, request: Request):
    req_path = request.url.path.lower()
    referer  = request.headers.get("referer", "").lower()

    # Open WebUI explicit subpath or referer
    if req_path.startswith("/openwebui") or "/openwebui" in referer:
        sub_p = path.replace("openwebui/", "", 1).replace("openwebui", "", 1)
        return await proxy_http_request(f"http://127.0.0.1:{WEBUI_PORT}/{sub_p}", request, default_prefix="/openwebui", html_fixup=fixup_webui_html)

    # Jellyfin
    if req_path.startswith("/jellyfin") or "/jellyfin" in referer:
        sub_p = path.replace("jellyfin/", "", 1).replace("jellyfin", "", 1)
        return await proxy_http_request(f"http://127.0.0.1:{JELLYFIN_PORT}/{sub_p}", request, default_prefix="/jellyfin", extra_headers={"X-Forwarded-Prefix": "/jellyfin"})

    # Telegram Streamer
    if req_path.startswith("/tg-stream") or req_path.startswith("/tg_stream") or "/tg" in referer:
        sub_p = path.replace("tg-stream/", "", 1).replace("tg_stream/", "", 1)
        return await proxy_http_request(f"http://127.0.0.1:{TG_PORT}/{sub_p}", request, default_prefix="/tg-stream")

    # Handle legacy /omniroute links by redirecting or proxying natively to root
    if req_path.startswith("/omniroute"):
        sub_p = path.replace("omniroute/", "", 1).replace("omniroute", "", 1)
        extra = {
            "Host": PUBLIC_HOST,
            "X-Forwarded-Host": PUBLIC_HOST,
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Port": "443"
        }
        return await proxy_http_request(f"http://127.0.0.1:{OMNIROUTE_PORT}/{sub_p}", request, default_prefix="", extra_headers=extra)

    # Default all native root traffic (OmniRoute dashboard, /api/*, /_next/*, /dashboard/*, /login, /callback) -> OmniRoute (:20128)
    extra = {
        "Host": PUBLIC_HOST,
        "X-Forwarded-Host": PUBLIC_HOST,
        "X-Forwarded-Proto": "https",
        "X-Forwarded-Port": "443"
    }
    return await proxy_http_request(f"http://127.0.0.1:{OMNIROUTE_PORT}/{path}", request, default_prefix="", extra_headers=extra)
