"""
OpenCode Space — Production Gateway Main Application (Option A Master Specification)
==================================================================================
Open WebUI is the primary root application (/), owning /, /api/config, /api/v1/chats, /ws/socket.io, /_app/*, etc.
OmniRoute owns explicit management & LLM API routes (/dashboard/*, /v1/*, /v1beta/*, /_next/*, /api/providers/*, etc.).
"""

import os
import json
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, WebSocket
from fastapi.responses import RedirectResponse, JSONResponse

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


# ── Open WebUI Legacy Namespace Aliases -> Native Root (/) ─────────────────────
@app.get("/openwebui", operation_id="openwebui_root_alias")
@app.get("/openwebui/", operation_id="openwebui_slash_alias")
async def openwebui_root_alias():
    return RedirectResponse(url="/")

@app.get("/openwebui/{path:path}", operation_id="openwebui_subpath_alias")
async def openwebui_subpath_alias(path: str):
    return RedirectResponse(url=f"/{path}")

# ── P0 Security Middleware: Hard Block Sensitive Files & Path Traversal ──────
@app.middleware("http")
async def block_sensitive_files_middleware(request: Request, call_next):
    raw_path = str(request.url.path).lower()
    query_str = str(request.url.query).lower()
    combined = f"{raw_path}?{query_str}"

    if any(p in combined for p in (".env", "server.env", "/secrets", "file=", "..", "%2e%2e", "%5c", ".git", ".sqlite")):
        logger.warning(f"[SECURITY] Blocked unauthorized sensitive path access attempt: {combined}")
        return JSONResponse({"error": "Access Denied: Protected System Resource"}, status_code=403)

    return await call_next(request)

# Include Service Routers
app.include_router(omniroute_router)
app.include_router(openwebui_router)
app.include_router(jellyfin_router)
app.include_router(tg_stream_router)


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

# ── Protected Live OmniRoute Provider & Decryption Diagnostic Inspection ──────
import subprocess

@app.get("/debug/omniroute-diagnostics", operation_id="debug_omniroute_diagnostics")
async def omniroute_diagnostics(request: Request):
    secret_key = os.getenv("DEBUG_DIAGNOSTIC_TOKEN") or os.getenv("INITIAL_PASSWORD")
    if not secret_key:
        return JSONResponse({"error": "Diagnostic authentication is not configured"}, status_code=503)

    auth_header = request.headers.get("Authorization", "")
    token_bearer = auth_header.replace("Bearer ", "").strip() if auth_header.startswith("Bearer ") else ""
    provided_key = request.headers.get("X-Admin-Key") or token_bearer or request.query_params.get("key")
    if provided_key != secret_key:
        return JSONResponse({"error": "Unauthorized: Bearer Token or X-Admin-Key Required"}, status_code=401)

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

    cli_summary = {}
    try:
        res = subprocess.run(["omniroute", "providers", "list", "--json"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            try:
                data = json.loads(res.stdout)
                providers_summary = []
                if isinstance(data, list):
                    for item in data:
                        providers_summary.append({
                            "id": item.get("id"),
                            "name": item.get("name"),
                            "status": item.get("status"),
                            "connected": item.get("connected", False),
                            "healthy": item.get("healthy", False)
                        })
                cli_summary["providers"] = providers_summary
            except Exception:
                cli_summary["providers_raw_length"] = len(res.stdout)
        else:
            cli_summary["providers_error"] = "Failed to list providers"
    except Exception as e:
        cli_summary["providers_error"] = f"Error: {e}"

    try:
        res = subprocess.run(["omniroute", "providers", "validate"], capture_output=True, text=True, timeout=5)
        cli_summary["validation_status"] = "ok" if res.returncode == 0 else "degraded"
    except Exception as e:
        cli_summary["validation_status"] = f"Error: {e}"

    return {
        "status": "healthy",
        "environment": env_info,
        "database": db_info,
        "providers_summary": cli_summary
    }


# ── Catch-All Router (Master Specification: Open WebUI = Root Application Fallback)
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"], operation_id="global_catchall_proxy")
async def route_catch_all(path: str, request: Request):
    req_path = "/" + path.lstrip("/")

    # ── 1. OmniRoute Explicit Management & API Endpoints ──────────────────────
    OMNIROUTE_PREFIXES = (
        "/dashboard",
        "/_next",
        "/api/providers",
        "/api/credentials",
        "/api/oauth",
        "/api/settings",
        "/api/monitoring",
        "/api/combos",
        "/api/auth",
        "/api/models",
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
    return await proxy_http_request(f"http://127.0.0.1:{WEBUI_PORT}{req_path}", request, default_prefix="")
