"""
OpenCode Space — Production ASGI Gateway & Reverse Proxy
=========================================================
Technology Stack & Design:
  - Framework: FastAPI 0.115+ / Starlette ASGI Engine
  - Async I/O: Python 3.11+ / 3.12+ Async Context Lifespan & httpx.AsyncClient
  - Protocol Support: Full HTTP/1.1, Server-Sent Events (SSE) Streaming, & Full-Duplex WebSockets
  - Resilience: Automatic connection pool management (1000 max, 200 keep-alive), exponential retries on transient errors, header sanitization, & zero-port-leakage URL rewriting.

Port Architecture (All listening on 127.0.0.1 internally):
  Port 4096  — Main FastAPI Gateway (External HF Space Port)
  Port 4097  — OpenCode Server Engine
  Port 8098  — Open WebUI Platform
  Port 20128 — OmniRoute Multi-LLM Gateway
  Port 8096  — Jellyfin Media Server
  Port 8080  — TG-Drive Direct 5G Streaming Server

Public URL Routing Matrix:
  /           → Landing Hub (index.html)
  /server/    → OpenCode Server (4097)
  /openwebui/ → Open WebUI (8098)  [Path Stripped & Re-anchored]
  /omniroute/ → OmniRoute (20128)  [Path Stripped & Re-anchored]
  /jellyfin/  → Jellyfin Media (8096)
  /tg-stream/ → TG Streaming Engine (8080)
  /health     → Service Health & Diagnostic API
"""

import os
import re
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Callable, Optional, Dict, Any

import httpx
import aiohttp
from fastapi import FastAPI, Request, Response, WebSocket
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("GatewayProxy")

# Port Definitions
WEBUI_PORT     = int(os.environ.get("WEBUI_PORT", 8098))
OMNIROUTE_PORT = int(os.environ.get("OMNIROUTE_PORT", 20128))
OPENCODE_PORT  = int(os.environ.get("OPENCODE_PORT", 4097))
JELLYFIN_PORT  = int(os.environ.get("JELLYFIN_PORT", 8096))
TG_PORT        = int(os.environ.get("TG_PORT", 8080))
GATEWAY_PORT   = int(os.environ.get("PORT", 4096))

PUBLIC_HOST   = os.environ.get("PUBLIC_HOST", "jishnupg-opencode-cli.hf.space")
PUBLIC_ORIGIN = f"https://{PUBLIC_HOST}"

# Internal Port Leakage Protection
_INTERNAL_PORTS = {GATEWAY_PORT, WEBUI_PORT, OMNIROUTE_PORT, OPENCODE_PORT, JELLYFIN_PORT, TG_PORT}
_PORT_STRIP_RE  = re.compile(r"(https?://[^/:]+):(" + "|".join(str(p) for p in _INTERNAL_PORTS) + r")")

_PORT_PREFIX_MAP = {
    GATEWAY_PORT:   "",
    OMNIROUTE_PORT: "/omniroute",
    WEBUI_PORT:     "/openwebui",
    OPENCODE_PORT:  "/server",
    JELLYFIN_PORT:  "/jellyfin",
    TG_PORT:        "/tg-stream",
}

def _fix_location_header(location: str) -> str:
    """Strip internal ports from HTTP Location headers and re-anchor to public paths."""
    if not location:
        return location

    def _replace_port(match: re.Match[str]) -> str:
        port = int(match.group(2))
        prefix = _PORT_PREFIX_MAP.get(port, "")
        return f"{PUBLIC_ORIGIN}{prefix}"

    return _PORT_STRIP_RE.sub(_replace_port, location)


# ── Global Async HTTP Client with Lifespan Manager ─────────────────────────
http_client: Optional[httpx.AsyncClient] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    logger.info("Initializing Gateway Connection Pool...")
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(120.0, connect=10.0),
        follow_redirects=False,
        limits=httpx.Limits(max_connections=1000, max_keepalive_connections=200, keepalive_expiry=30.0),
    )
    yield
    logger.info("Closing Gateway Connection Pool...")
    if http_client:
        await http_client.aclose()


app = FastAPI(title="OpenCode Space ASGI Gateway", lifespan=lifespan, docs_url=None, redoc_url=None)


# ── Header Sanitization Helpers ─────────────────────────────────────────────
_HOP_BY_HOP_HEADERS = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
    "content-length", "content-encoding"
}

def _build_upstream_headers(request: Request, extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    headers = {k: v for k, v in request.headers.items() if k.lower() not in {"host", "content-length"}}
    headers["X-Forwarded-Host"]  = PUBLIC_HOST
    headers["X-Forwarded-Proto"] = "https"
    headers["X-Forwarded-Port"]  = "443"
    headers["X-Real-IP"]         = request.client.host if request.client else "127.0.0.1"
    if extra_headers:
        headers.update(extra_headers)
    return headers

def _build_downstream_headers(resp_headers: httpx.Headers, override_location: Optional[str] = None) -> Dict[str, str]:
    headers = {}
    for key, value in resp_headers.items():
        lk = key.lower()
        if lk in _HOP_BY_HOP_HEADERS:
            continue
        if lk == "location":
            value = _fix_location_header(value)
            if override_location:
                value = override_location
        headers[key] = value
    return headers


# ── Core Resilient HTTP Proxy Engine ───────────────────────────────────────
async def proxy_http_request(
    target_url: str,
    request: Request,
    extra_headers: Optional[Dict[str, str]] = None,
    html_fixup: Optional[Callable[[str], str]] = None,
) -> Response:
    """
    Forward an HTTP request to upstream service with automatic retries & streaming support.
    """
    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=httpx.Timeout(120.0), follow_redirects=False)

    headers = _build_upstream_headers(request, extra_headers)
    body    = await request.body()
    method  = request.method
    params  = dict(request.query_params)

    # Perform up to 3 attempts with exponential backoff for transient upstream delays
    resp: Optional[httpx.Response] = None
    last_exc: Optional[Exception] = None

    for attempt in range(1, 4):
        try:
            req = http_client.build_request(
                method=method,
                url=target_url,
                headers=headers,
                params=params,
                content=body,
            )
            resp = await http_client.send(req, stream=True)
            if resp.status_code in (502, 503) and attempt < 3:
                await resp.aclose()
                await asyncio.sleep(0.1 * attempt)
                continue
            break
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
            last_exc = exc
            if attempt < 3:
                await asyncio.sleep(0.1 * attempt)
                continue
            return Response(
                content=f"<h2>502 Gateway Error — Upstream Service Starting</h2><p>{exc}</p>",
                status_code=502,
                media_type="text/html",
            )

    if resp is None:
        return Response(content=f"<h2>502 Bad Gateway</h2><p>{last_exc}</p>", status_code=502, media_type="text/html")

    res_headers = _build_downstream_headers(resp.headers)
    content_type = resp.headers.get("content-type", "")
    status_code  = resp.status_code

    # Check if streaming response (eventsource or binary video stream)
    is_stream = "text/event-stream" in content_type or "video/" in content_type or "audio/" in content_type or resp.headers.get("transfer-encoding") == "chunked"

    if is_stream:
        async def stream_generator():
            try:
                async for chunk in resp.aiter_bytes():
                    yield chunk
            finally:
                await resp.aclose()

        return StreamingResponse(
            stream_generator(),
            status_code=status_code,
            headers=res_headers,
            media_type=content_type or None,
        )

    # Non-streaming response body read
    try:
        content = await resp.aread()
    finally:
        await resp.aclose()

    # Rewrite HTML references ONLY for text/html (protect JS/CSS/JSON bundles)
    if "text/html" in content_type and html_fixup and content:
        try:
            text = content.decode("utf-8", errors="replace")
            text = html_fixup(text)
            content = text.encode("utf-8")
        except Exception:
            pass

    return Response(
        content=content,
        status_code=status_code,
        headers=res_headers,
        media_type=content_type or None,
    )


# ── Full-Duplex ASGI WebSocket Proxy Engine ──────────────────────────────────
async def proxy_websocket_stream(websocket: WebSocket, target_ws_url: str):
    """
    Transparent full-duplex ASGI WebSocket proxy between browser client and upstream.
    """
    await websocket.accept()
    skip_headers = {"host", "sec-websocket-key", "sec-websocket-version", "sec-websocket-extensions"}
    forward_headers = {k: v for k, v in websocket.headers.items() if k.lower() not in skip_headers}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(target_ws_url, headers=forward_headers) as upstream_ws:
                async def downstream_to_upstream():
                    async for msg in upstream_ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await websocket.send_text(msg.data)
                        elif msg.type == aiohttp.WSMsgType.BINARY:
                            await websocket.send_bytes(msg.data)
                        elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
                            break

                async def upstream_to_downstream():
                    while True:
                        try:
                            msg = await websocket.receive()
                            if "text" in msg:
                                await upstream_ws.send_str(msg["text"])
                            elif "bytes" in msg:
                                await upstream_ws.send_bytes(msg["bytes"])
                            elif msg.get("type") == "websocket.disconnect":
                                break
                        except Exception:
                            break

                await asyncio.gather(downstream_to_upstream(), upstream_to_downstream(), return_exceptions=True)
    except Exception as exc:
        logger.warning(f"WebSocket Proxy Exception for {target_ws_url}: {exc}")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# GATEWAY ROUTING MATRIX
# ══════════════════════════════════════════════════════════════════════════════

# ── 0. Landing Page & Health Check ───────────────────────────────────────────
@app.api_route("/", methods=["GET", "HEAD"])
async def gateway_root(request: Request):
    if request.method == "HEAD":
        return Response(status_code=200)
    for index_path in ("/index.html", "/app/index.html"):
        if os.path.exists(index_path):
            return FileResponse(index_path, media_type="text/html")
    return HTMLResponse(
        "<h1>OpenCode Space Gateway</h1>"
        "<p>Services: "
        "<a href='/server/'>OpenCode Server</a> | "
        "<a href='/openwebui/'>Open WebUI</a> | "
        "<a href='/omniroute/'>OmniRoute AI Gateway</a> | "
        "<a href='/jellyfin/'>Jellyfin Media</a>"
        "</p>"
    )

@app.api_route("/favicon.ico", methods=["GET", "HEAD"])
async def favicon():
    return Response(content=b"", status_code=204)

@app.get("/health")
@app.get("/debug/status")
async def health_check():
    """Diagnostic health check for all upstream services."""
    services = {
        "opencode":  f"http://127.0.0.1:{OPENCODE_PORT}/",
        "openwebui": f"http://127.0.0.1:{WEBUI_PORT}/",
        "omniroute": f"http://127.0.0.1:{OMNIROUTE_PORT}/",
        "jellyfin":  f"http://127.0.0.1:{JELLYFIN_PORT}/",
        "tg_stream": f"http://127.0.0.1:{TG_PORT}/",
    }
    results = {}
    if http_client:
        for name, url in services.items():
            try:
                r = await http_client.get(url, timeout=3.0)
                results[name] = {"status": "ok", "code": r.status_code}
            except Exception as exc:
                results[name] = {"status": "error", "message": str(exc)}
    return {"gateway": "healthy", "upstreams": results}


# ── 1. Open WebUI Route (/openwebui/) ────────────────────────────────────────
def _fixup_webui_html(html: str) -> str:
    html = html.replace('href="/', 'href="/openwebui/')
    html = html.replace("href='/", "href='/openwebui/")
    html = html.replace('src="/', 'src="/openwebui/')
    html = html.replace("src='/", "src='/openwebui/")
    html = html.replace('action="/', 'action="/openwebui/')
    return html

@app.api_route("/openwebui", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@app.api_route("/openwebui/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def route_openwebui(request: Request, path: str = ""):
    target = f"http://127.0.0.1:{WEBUI_PORT}/{path}"
    return await proxy_http_request(target, request, html_fixup=_fixup_webui_html)

@app.websocket("/openwebui/ws")
@app.websocket("/openwebui/ws/")
@app.websocket("/openwebui/socket.io")
async def route_openwebui_ws(websocket: WebSocket):
    await proxy_websocket_stream(websocket, f"ws://127.0.0.1:{WEBUI_PORT}/ws")


# ── 2. OmniRoute AI Gateway Route (/omniroute/) ──────────────────────────────
def _fixup_omniroute_html(html: str) -> str:
    html = html.replace('href="/', 'href="/omniroute/')
    html = html.replace("href='/", "href='/omniroute/")
    html = html.replace('src="/', 'src="/omniroute/')
    html = html.replace("src='/", "src='/omniroute/")
    html = html.replace('action="/', 'action="/omniroute/')
    html = html.replace('"/_next/', '"/omniroute/_next/')
    html = html.replace("'/_next/", "'/omniroute/_next/")
    html = html.replace('"basePath":""', '"basePath":"/omniroute"')
    html = html.replace('"basePath": ""', '"basePath": "/omniroute"')
    return html

@app.api_route("/omniroute", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@app.api_route("/omniroute/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def route_omniroute(request: Request, path: str = ""):
    target = f"http://127.0.0.1:{OMNIROUTE_PORT}/{path}"
    return await proxy_http_request(target, request, html_fixup=_fixup_omniroute_html)


# ── 3. OpenCode CLI Server Route (/server/) ──────────────────────────────────
def _fixup_opencode_html(html: str) -> str:
    html = html.replace('href="/', 'href="/server/')
    html = html.replace("href='/", "href='/server/")
    html = html.replace('src="/', 'src="/server/')
    html = html.replace("src='/", "src='/server/")
    html = html.replace('ws://"+location.host+"/ws', 'ws://"+location.host+"/server/ws')
    html = html.replace("ws://'+location.host+'/ws", "ws://'+location.host+'/server/ws")
    return html

@app.api_route("/server", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@app.api_route("/server/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def route_opencode(request: Request, path: str = ""):
    target = f"http://127.0.0.1:{OPENCODE_PORT}/{path}"
    return await proxy_http_request(target, request, html_fixup=_fixup_opencode_html)

@app.websocket("/server/ws")
@app.websocket("/ws")
async def route_opencode_ws(websocket: WebSocket):
    await proxy_websocket_stream(websocket, f"ws://127.0.0.1:{OPENCODE_PORT}/ws")


# ── Direct OpenCode Endpoints (session, project, config, etc.) ───────────────
OPENCODE_DIRECT_PATHS = ["session", "project", "config", "permission", "question", "file", "find", "events", "event", "command", "provider", "model", "mcp", "api"]

def _create_direct_route(prefix: str):
    @app.api_route(f"/{prefix}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
    @app.api_route(f"/{prefix}/{{path:path}}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
    async def direct_endpoint(request: Request, path: str = ""):
        full_path = f"{prefix}/{path}" if path else prefix
        target = f"http://127.0.0.1:{OPENCODE_PORT}/{full_path}"
        return await proxy_http_request(target, request, html_fixup=_fixup_opencode_html)

for p in OPENCODE_DIRECT_PATHS:
    _create_direct_route(p)


# ── 4. Jellyfin Media Server Route (/jellyfin/) ───────────────────────────────
@app.api_route("/jellyfin", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@app.api_route("/jellyfin/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@app.api_route("/Jellyfin", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@app.api_route("/Jellyfin/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def route_jellyfin(request: Request, path: str = ""):
    target = f"http://127.0.0.1:{JELLYFIN_PORT}/{path}"
    return await proxy_http_request(target, request, extra_headers={"X-Forwarded-Prefix": "/jellyfin"})


# ── 5. TG-Drive Direct Streamer Route (/tg-stream/) ─────────────────────────
@app.api_route("/tg-stream", methods=["GET", "HEAD", "OPTIONS"])
@app.api_route("/tg-stream/{path:path}", methods=["GET", "HEAD", "OPTIONS"])
async def route_tg_stream(request: Request, path: str = ""):
    target = f"http://127.0.0.1:{TG_PORT}/{path}"
    return await proxy_http_request(target, request)


# ── 6. Catch-All Referer Router (Sub-resource Fallback Engine) ────────────────
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def route_catch_all(path: str, request: Request):
    referer = request.headers.get("referer", "").lower()

    if "/openwebui" in referer:
        return await proxy_http_request(f"http://127.0.0.1:{WEBUI_PORT}/{path}", request, html_fixup=_fixup_webui_html)
    elif "/omniroute" in referer or "/dashboard" in referer or "/login" in referer:
        return await proxy_http_request(f"http://127.0.0.1:{OMNIROUTE_PORT}/{path}", request, html_fixup=_fixup_omniroute_html)
    elif "/server" in referer:
        return await proxy_http_request(f"http://127.0.0.1:{OPENCODE_PORT}/{path}", request, html_fixup=_fixup_opencode_html)
    elif "/jellyfin" in referer:
        return await proxy_http_request(f"http://127.0.0.1:{JELLYFIN_PORT}/{path}", request, extra_headers={"X-Forwarded-Prefix": "/jellyfin"})

    # Fallback default: Open WebUI
    return await proxy_http_request(f"http://127.0.0.1:{WEBUI_PORT}/{path}", request, html_fixup=_fixup_webui_html)
