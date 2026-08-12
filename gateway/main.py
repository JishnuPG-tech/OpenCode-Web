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

# ── P0 Security Middleware: Hard Block Sensitive Files & Path Traversal ──────
from fastapi.responses import JSONResponse

@app.middleware("http")
async def block_sensitive_files_middleware(request: Request, call_next):
    raw_path = str(request.url.path).lower()
    query_str = str(request.url.query).lower()
    combined = f"{raw_path}?{query_str}"

    if any(p in combined for p in (".env", "server.env", "/secrets", "file=", "..", "%2e%2e", "%5c", ".git", ".sqlite")):
        if not raw_path.startswith("/api/credentials"):
            logger.warning(f"[SECURITY] Blocked unauthorized sensitive path access attempt: {combined}")
            return JSONResponse({"error": "Access Denied: Protected System Resource"}, status_code=403)

    return await call_next(request)

# Include Service Routers
app.include_router(omniroute_router)
app.include_router(openwebui_router)
app.include_router(jellyfin_router)
app.include_router(tg_stream_router)


# ── Root Direct Handler for OmniRoute Landing Page (Approach A) ────────────────
@app.api_route("/", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"], operation_id="root_landing_proxy")
async def root_proxy(request: Request):
    extra = {
        "Host": PUBLIC_HOST,
        "X-Forwarded-Host": PUBLIC_HOST,
        "X-Forwarded-Proto": "https",
        "X-Forwarded-Port": "443"
    }
    return await proxy_http_request(f"http://127.0.0.1:{OMNIROUTE_PORT}/", request, default_prefix="", extra_headers=extra)

@app.api_route("/favicon.ico", methods=["GET", "HEAD"], operation_id="root_favicon_proxy")
async def favicon():
    return Response(content=b"", status_code=204)

# ── Dedicated Open WebUI Socket.IO WebSocket Handler ──────────────────────────
@app.websocket("/ws/socket.io")
async def handle_openwebui_socketio_root(websocket: WebSocket):
    target = f"ws://127.0.0.1:{WEBUI_PORT}/ws/socket.io"
    await proxy_websocket_stream(websocket, target)

@app.websocket("/ws/socket.io/{path:path}")
async def handle_openwebui_socketio_subpath(websocket: WebSocket, path: str = ""):
    target = f"ws://127.0.0.1:{WEBUI_PORT}/ws/socket.io/{path}"
    await proxy_websocket_stream(websocket, target)

@app.websocket("/openwebui/ws/socket.io")
async def handle_openwebui_socketio_owui_root(websocket: WebSocket):
    target = f"ws://127.0.0.1:{WEBUI_PORT}/ws/socket.io"
    await proxy_websocket_stream(websocket, target)

@app.websocket("/openwebui/ws/socket.io/{path:path}")
async def handle_openwebui_socketio_owui_subpath(websocket: WebSocket, path: str = ""):
    target = f"ws://127.0.0.1:{WEBUI_PORT}/ws/socket.io/{path}"
    await proxy_websocket_stream(websocket, target)

# ── Health Watchdog System ───────────────────────────────────────────────────
@app.get("/health/live", operation_id="health_live_check")
async def health_liveness():
    return {"status": "alive"}

@app.get("/health/ready", operation_id="health_ready_check")
@app.get("/health/services", operation_id="health_services_check")
@app.get("/health", operation_id="health_root_check")
@app.get("/debug/status", operation_id="health_debug_status_check")
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

# ── Live OmniRoute Provider & Decryption Diagnostic Inspection Endpoint ────────
import subprocess

@app.get("/debug/omniroute-diagnostics", operation_id="debug_omniroute_diagnostics")
async def omniroute_diagnostics():
    env_info = {
        "DATA_DIR": os.getenv("DATA_DIR", ""),
        "PORT": os.getenv("PORT", ""),
        "NEXT_PUBLIC_BASE_URL": os.getenv("NEXT_PUBLIC_BASE_URL", ""),
        "STORAGE_ENCRYPTION_KEY_PRESENT": bool(os.getenv("STORAGE_ENCRYPTION_KEY")),
        "STORAGE_ENCRYPTION_KEY_LEN": len(os.getenv("STORAGE_ENCRYPTION_KEY", "")),
    }
    
    db_info = {}
    for p in ["/root/.omniroute/storage.sqlite", "/data/omniroute/storage.sqlite"]:
        if os.path.exists(p):
            db_info[p] = {
                "exists": True,
                "size_bytes": os.path.getsize(p)
            }
        else:
            db_info[p] = {"exists": False}

    cli_results = {}
    try:
        res = subprocess.run(["omniroute", "providers", "list", "--json"], capture_output=True, text=True, timeout=5)
        cli_results["providers_list"] = res.stdout if res.returncode == 0 else res.stderr
    except Exception as e:
        cli_results["providers_list"] = f"Error: {e}"

    try:
        res = subprocess.run(["omniroute", "providers", "validate"], capture_output=True, text=True, timeout=5)
        cli_results["providers_validate"] = res.stdout if res.returncode == 0 else res.stderr
    except Exception as e:
        cli_results["providers_validate"] = f"Error: {e}"

    return {
        "environment": env_info,
        "database": db_info,
        "omniroute_cli": cli_results
    }


# ── Catch-All Router (Approach A Master Specification) ──────────────────────
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"], operation_id="global_catchall_proxy")
async def route_catch_all(path: str, request: Request):
    req_path = request.url.path.lower()
    referer  = request.headers.get("referer", "").lower()

    # ── 1. Open WebUI Namespace Isolation ─────────────────────────────────────
    if req_path == "/openwebui" or req_path.startswith("/openwebui/"):
        logger.info(f"[ROUTER] {req_path} -> Open WebUI (8098)")
        sub_p = path.replace("openwebui/", "", 1).replace("openwebui", "", 1)
        return await proxy_http_request(f"http://127.0.0.1:{WEBUI_PORT}/{sub_p}", request, default_prefix="/openwebui", html_fixup=fixup_webui_html)

    # ── 2. OmniRoute Primary Root Endpoints ───────────────────────────────────
    OMNIROUTE_EXACT = {
        "/login", "/forgot-password", "/reset-password", "/reset",
        "/register", "/signup", "/auth", "/home", "/callback",
        "/live-ws", "/health", "/debug"
    }

    OMNIROUTE_PREFIXES = (
        "/omniroute", "/dashboard", "/_next", "/v1", "/v1beta",
        "/api", "/static", "/favicon", "/manifest.json"
    )

    is_omniroute = (
        req_path in OMNIROUTE_EXACT
        or any(
            req_path == prefix or req_path.startswith(prefix + "/")
            for prefix in OMNIROUTE_PREFIXES
        )
    )

    if is_omniroute:
        logger.info(f"[ROUTER] {req_path} -> OmniRoute (20128)")
        sub_p = path.replace("omniroute/", "", 1).replace("omniroute", "", 1)
        extra = {
            "Host": PUBLIC_HOST,
            "X-Forwarded-Host": PUBLIC_HOST,
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Port": "443"
        }
        return await proxy_http_request(f"http://127.0.0.1:{OMNIROUTE_PORT}/{sub_p}", request, default_prefix="", extra_headers=extra)

    # ── 3. Jellyfin Media Server ──────────────────────────────────────────────
    if req_path.startswith("/jellyfin") or "/jellyfin" in referer:
        logger.info(f"[ROUTER] {req_path} -> Jellyfin (8096)")
        sub_p = path.replace("jellyfin/", "", 1).replace("jellyfin", "", 1)
        return await proxy_http_request(f"http://127.0.0.1:{JELLYFIN_PORT}/{sub_p}", request, default_prefix="/jellyfin", extra_headers={"X-Forwarded-Prefix": "/jellyfin"})

    # ── 4. Telegram Streamer ──────────────────────────────────────────────────
    if req_path.startswith("/tg-stream") or req_path.startswith("/tg_stream") or "/tg" in referer:
        logger.info(f"[ROUTER] {req_path} -> Telegram Streamer (8080)")
        sub_p = path.replace("tg-stream/", "", 1).replace("tg_stream/", "", 1)
        return await proxy_http_request(f"http://127.0.0.1:{TG_PORT}/{sub_p}", request, default_prefix="/tg-stream")

    # ── 5. Clean 404 Fallback for Unknown Traffic ─────────────────────────────
    logger.warning(f"[ROUTER] {req_path} -> 404 Not Found")
    return Response(content="Not Found", status_code=404)
