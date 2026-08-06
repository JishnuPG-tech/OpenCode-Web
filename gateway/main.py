"""
OpenCode Space — Production Gateway Main Application
=====================================================
Assembles 5 Modular Service Routers into a unified FastAPI ASGI Gateway:
  1. OpenCode CLI Server (gateway.opencode)
  2. Open WebUI (gateway.openwebui)
  3. OmniRoute AI Gateway (gateway.omniroute)
  4. Jellyfin Media Server (gateway.jellyfin)
  5. TG-Drive Direct Streamer (gateway.tg_stream)
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, FileResponse

from gateway.utils import (
    get_http_client,
    proxy_http_request,
    OPENCODE_PORT,
    WEBUI_PORT,
    OMNIROUTE_PORT,
    JELLYFIN_PORT,
    TG_PORT,
)
from gateway.opencode import router as opencode_router, fixup_opencode_html
from gateway.openwebui import router as openwebui_router, fixup_webui_html
from gateway.omniroute import router as omniroute_router, fixup_omniroute_html
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
app.include_router(opencode_router)
app.include_router(openwebui_router)
app.include_router(omniroute_router)
app.include_router(jellyfin_router)
app.include_router(tg_stream_router)


# ── Root Landing & Diagnostic Routes ─────────────────────────────────────────
@app.api_route("/favicon.ico", methods=["GET", "HEAD"])
async def favicon():
    return Response(content=b"", status_code=204)

@app.get("/health")
@app.get("/debug/status")
async def health_check():
    client = get_http_client()
    services = {
        "opencode":  f"http://127.0.0.1:{OPENCODE_PORT}/",
        "openwebui": f"http://127.0.0.1:{WEBUI_PORT}/",
        "omniroute": f"http://127.0.0.1:{OMNIROUTE_PORT}/",
        "jellyfin":  f"http://127.0.0.1:{JELLYFIN_PORT}/",
        "tg_stream": f"http://127.0.0.1:{TG_PORT}/",
    }
    results = {}
    for name, url in services.items():
        try:
            r = await client.get(url, timeout=3.0)
            results[name] = {"status": "ok", "code": r.status_code}
        except Exception as exc:
            results[name] = {"status": "error", "message": str(exc)}
    return {"gateway": "healthy", "upstreams": results}


# ── Catch-All Referer & Subpath Fallback Router ──────────────────────────────
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def route_catch_all(path: str, request: Request):
    referer = request.headers.get("referer", "").lower()
    req_path = request.url.path.lower()

    OMNIROUTE_EXPLICIT_PREFIXES = (
        "/omniroute", "/v1", "/_next", "/dashboard", "/api-keys",
        "/providers", "/models", "/keys", "/settings", "/logs",
        "/stats", "/system", "/login", "/users"
    )

    is_omniroute_req = (
        "/omniroute" in referer or 
        "/dashboard" in referer or 
        req_path.startswith("/omniroute") or 
        any(req_path.startswith(p) for p in OMNIROUTE_EXPLICIT_PREFIXES)
    )

    if is_omniroute_req:
        return await proxy_http_request(f"http://127.0.0.1:{OMNIROUTE_PORT}/{path}", request, default_prefix="/omniroute", html_fixup=fixup_omniroute_html)
    elif "/server" in referer or req_path.startswith("/server") or req_path.startswith("/opencode"):
        return await proxy_http_request(f"http://127.0.0.1:{OPENCODE_PORT}/{path}", request, default_prefix="/server", html_fixup=fixup_opencode_html)
    elif "/jellyfin" in referer or req_path.startswith("/jellyfin"):
        return await proxy_http_request(f"http://127.0.0.1:{JELLYFIN_PORT}/{path}", request, default_prefix="/jellyfin", extra_headers={"X-Forwarded-Prefix": "/jellyfin"})
    elif "/tg_stream" in referer or req_path.startswith("/tg_stream"):
        return await proxy_http_request(f"http://127.0.0.1:{TG_PORT}/{path}", request, default_prefix="/tg_stream")
    elif req_path.startswith("/_app") or req_path == "/sw.js" or req_path.startswith("/api/") or req_path.startswith("/static/"):
        return await proxy_http_request(f"http://127.0.0.1:{WEBUI_PORT}/{path}", request)

    # Strict 404 for unknown endpoints
    return Response(content="<h1>404 Not Found</h1><p>The requested endpoint does not exist on this gateway.</p>", status_code=404, media_type="text/html")
