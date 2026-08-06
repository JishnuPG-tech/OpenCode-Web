"""
OpenCode Space — FastAPI Reverse-Proxy Gateway
================================================
Architecture (all on 127.0.0.1 inside the container):
  Port 4096  — this FastAPI app  (HF-Space external port)
  Port 4097  — opencode serve
  Port 8096  — Jellyfin
  Port 8098  — Open WebUI
  Port 20128 — OmniRoute
  Port 8080  — TG-Drive Streamer

Public URL prefix mapping:
  /          → landing hub (index.html)
  /server/   → opencode (4097)
  /openwebui/→ Open WebUI (8098)  — STRIP prefix before upstream
  /omniroute/→ OmniRoute  (20128) — STRIP prefix before upstream
  /jellyfin/ → Jellyfin   (8096)
  /tg-stream/→ TG Streamer(8080)
"""

import os
import re
import asyncio
from fastapi import FastAPI, Request, Response, WebSocket
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
import httpx
import aiohttp

app = FastAPI(title="OpenCode Space Gateway", docs_url=None, redoc_url=None)

# ── Port constants ──────────────────────────────────────────────────────────
WEBUI_PORT     = 8098
OMNIROUTE_PORT = 20128
OPENCODE_PORT  = 4097
JELLYFIN_PORT  = 8096
TG_PORT        = 8080

PUBLIC_HOST   = "jishnupg-opencode-cli.hf.space"
PUBLIC_ORIGIN = f"https://{PUBLIC_HOST}"

# ── Internal-port stripper (for Location headers only) ─────────────────────
_INTERNAL_PORTS = {4096, 20128, 8098, 4097, 8096, 8080}
_PORT_STRIP_RE  = re.compile(
    r"(https?://[^/:]+):(" + "|".join(str(p) for p in _INTERNAL_PORTS) + r")"
)
_PORT_PREFIX = {
    4096:  "",
    20128: "/omniroute",
    8098:  "/openwebui",
    4097:  "/server",
    8096:  "/jellyfin",
    8080:  "/tg-stream",
}

def _fix_location(location: str) -> str:
    """Rewrite a Location header so no internal port leaks out."""
    def _sub(m: "re.Match[str]") -> str:
        port = int(m.group(2))
        prefix = _PORT_PREFIX.get(port, "")
        return f"{PUBLIC_ORIGIN}{prefix}"
    return _PORT_STRIP_RE.sub(_sub, location)

# ── Shared async HTTP client ────────────────────────────────────────────────
client = httpx.AsyncClient(
    timeout=httpx.Timeout(120.0),
    follow_redirects=False,
    limits=httpx.Limits(max_connections=200, max_keepalive_connections=50),
)

# ── Header helpers ──────────────────────────────────────────────────────────
_HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
                "te", "trailers", "transfer-encoding", "upgrade",
                "content-length", "content-encoding"}

def _request_headers(request: Request, extra: dict | None = None) -> dict:
    h = {k: v for k, v in request.headers.items()
         if k.lower() not in {"host", "content-length"}}
    h["X-Forwarded-Host"]   = PUBLIC_HOST
    h["X-Forwarded-Proto"]  = "https"
    h["X-Forwarded-Port"]   = "443"
    h["X-Real-IP"]          = request.client.host if request.client else "127.0.0.1"
    if extra:
        h.update(extra)
    return h

def _response_headers(resp: httpx.Response, location_override: str | None = None) -> dict:
    out = {}
    for k, v in resp.headers.items():
        lk = k.lower()
        if lk in _HOP_BY_HOP:
            continue
        if lk == "location":
            v = _fix_location(v)
            if location_override:
                v = location_override
        out[k] = v
    return out

# ── Core proxy helper ───────────────────────────────────────────────────────
async def proxy_http(
    target_url: str,
    request: Request,
    extra_headers: dict | None = None,
    html_fixup: callable | None = None,
) -> Response:
    """
    Forward an HTTP request to target_url.
    html_fixup(text: str) -> str  — called only on text/html bodies.
    JS/CSS/JSON/binary content is NEVER modified.
    """
    headers = _request_headers(request, extra_headers)
    body    = await request.body()

    try:
        resp = await client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            params=dict(request.query_params),
            content=body,
        )
    except Exception as exc:
        return Response(
            content=f"<h2>502 — upstream unavailable</h2><pre>{exc}</pre>",
            status_code=502,
            media_type="text/html",
        )

    res_headers = _response_headers(resp)
    content     = resp.content
    ctype       = resp.headers.get("content-type", "")
    status      = resp.status_code

    # Only rewrite text/html — never touch JS, CSS, JSON, images, etc.
    if "text/html" in ctype and html_fixup and content:
        try:
            text = content.decode("utf-8", errors="replace")
            text = html_fixup(text)
            content = text.encode("utf-8")
        except Exception:
            pass

    return Response(
        content=content,
        status_code=status,
        headers=res_headers,
        media_type=ctype or None,
    )

# ── WebSocket proxy helper ──────────────────────────────────────────────────
async def proxy_ws(websocket: WebSocket, target_ws_url: str):
    await websocket.accept()
    skip = {"host", "sec-websocket-key", "sec-websocket-version", "sec-websocket-extensions"}
    headers = {k: v for k, v in websocket.headers.items() if k.lower() not in skip}
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.ws_connect(target_ws_url, headers=headers) as ws_up:
                async def fwd_down():
                    async for msg in ws_up:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await websocket.send_text(msg.data)
                        elif msg.type == aiohttp.WSMsgType.BINARY:
                            await websocket.send_bytes(msg.data)
                        elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
                            break

                async def fwd_up():
                    while True:
                        try:
                            msg = await websocket.receive()
                            if "text" in msg:
                                await ws_up.send_str(msg["text"])
                            elif "bytes" in msg:
                                await ws_up.send_bytes(msg["bytes"])
                            elif msg.get("type") == "websocket.disconnect":
                                break
                        except Exception:
                            break

                await asyncio.gather(fwd_down(), fwd_up(), return_exceptions=True)
    except Exception:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════════════════════

# ── 0. Health / Landing ────────────────────────────────────────────────────
@app.api_route("/", methods=["GET", "HEAD"])
async def root_hub(request: Request):
    if request.method == "HEAD":
        return Response(status_code=200)
    for path in ("/index.html", "/app/index.html"):
        if os.path.exists(path):
            return FileResponse(path, media_type="text/html")
    return HTMLResponse("<h1>OpenCode Space Gateway</h1><p>Services: "
                        "<a href='/server/'>OpenCode</a> | "
                        "<a href='/openwebui/'>Open WebUI</a> | "
                        "<a href='/omniroute/'>OmniRoute</a> | "
                        "<a href='/jellyfin/'>Jellyfin</a></p>")

@app.api_route("/favicon.ico", methods=["GET", "HEAD"])
async def favicon():
    return Response(content=b"", status_code=204)

# ── 1. Debug status ────────────────────────────────────────────────────────
@app.get("/debug/status")
async def debug_status():
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
            r = await client.get(url, timeout=4.0)
            results[name] = {"up": True, "status": r.status_code}
        except Exception as exc:
            results[name] = {"up": False, "error": str(exc)}
    return results


# ══════════════════════════════════════════════════════════════════════════════
# 2. OPEN WEBUI  — mounted at /openwebui/
#    Key insight: Open WebUI is built to run at /, so we STRIP /openwebui
#    from the path before proxying. All its asset URLs (/_app/, /static/ etc.)
#    will come in via the catch-all with a Referer: .../openwebui/...
# ══════════════════════════════════════════════════════════════════════════════
def _webui_fixup(html: str) -> str:
    """Rewrite absolute-root asset paths to include /openwebui prefix."""
    # Don't blindly rewrite every /; be surgical about href/src/action attrs
    html = html.replace('href="/', 'href="/openwebui/')
    html = html.replace("href='/", "href='/openwebui/")
    html = html.replace('src="/', 'src="/openwebui/')
    html = html.replace("src='/", "src='/openwebui/")
    html = html.replace('action="/', 'action="/openwebui/')
    return html

@app.api_route("/openwebui", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@app.api_route("/openwebui/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def openwebui_route(request: Request, path: str = ""):
    upstream = f"http://127.0.0.1:{WEBUI_PORT}/{path}"
    return await proxy_http(upstream, request, html_fixup=_webui_fixup)

# Open WebUI WebSocket (socket.io)
@app.websocket("/openwebui/ws")
@app.websocket("/openwebui/ws/")
async def openwebui_ws(websocket: WebSocket):
    await proxy_ws(websocket, f"ws://127.0.0.1:{WEBUI_PORT}/ws")

@app.websocket("/openwebui/socket.io")
async def openwebui_socketio(websocket: WebSocket):
    await proxy_ws(websocket, f"ws://127.0.0.1:{WEBUI_PORT}/socket.io")


# ══════════════════════════════════════════════════════════════════════════════
# 3. OMNIROUTE  — mounted at /omniroute/
#    OmniRoute (Next.js) is built to run at /. We STRIP /omniroute prefix.
# ══════════════════════════════════════════════════════════════════════════════
def _omniroute_fixup(html: str) -> str:
    """Rewrite Next.js root-relative paths to include /omniroute prefix."""
    html = html.replace('href="/', 'href="/omniroute/')
    html = html.replace("href='/", "href='/omniroute/")
    html = html.replace('src="/', 'src="/omniroute/')
    html = html.replace("src='/", "src='/omniroute/")
    html = html.replace('action="/', 'action="/omniroute/')
    html = html.replace('"/_next/', '"/omniroute/_next/')
    html = html.replace("'/_next/", "'/omniroute/_next/")
    # Fix Next.js router base path in __NEXT_DATA__
    html = html.replace('"basePath":""', '"basePath":"/omniroute"')
    html = html.replace('"basePath": ""', '"basePath": "/omniroute"')
    return html

@app.api_route("/omniroute", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@app.api_route("/omniroute/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def omniroute_route(request: Request, path: str = ""):
    upstream = f"http://127.0.0.1:{OMNIROUTE_PORT}/{path}"
    return await proxy_http(upstream, request, html_fixup=_omniroute_fixup)


# ══════════════════════════════════════════════════════════════════════════════
# 4. OPENCODE CLI SERVER  — mounted at /server/
#    OpenCode's Vite frontend connects to its own backend via WebSocket at /ws.
#    We proxy /server/ → 127.0.0.1:4097/ and /server/ws → ws://127.0.0.1:4097/ws
#    We do NOT rewrite JS files — only HTML gets the prefix fixup.
# ══════════════════════════════════════════════════════════════════════════════
def _opencode_fixup(html: str) -> str:
    """Rewrite root-relative asset URLs in opencode HTML to /server prefix."""
    html = html.replace('href="/', 'href="/server/')
    html = html.replace("href='/", "href='/server/")
    html = html.replace('src="/', 'src="/server/')
    html = html.replace("src='/", "src='/server/")
    # Fix the websocket URL embedded in HTML (not in JS - JS is never touched)
    html = html.replace('ws://"+location.host+"/ws', 'ws://"+location.host+"/server/ws')
    html = html.replace("ws://'+location.host+'/ws", "ws://'+location.host+'/server/ws")
    return html

@app.api_route("/server", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@app.api_route("/server/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def opencode_route(request: Request, path: str = ""):
    upstream = f"http://127.0.0.1:{OPENCODE_PORT}/{path}"
    return await proxy_http(upstream, request, html_fixup=_opencode_fixup)

# OpenCode WebSocket — the JS bundle sends to /ws (root), our route catches /server/ws
@app.websocket("/server/ws")
@app.websocket("/ws")
async def opencode_ws(websocket: WebSocket):
    await proxy_ws(websocket, f"ws://127.0.0.1:{OPENCODE_PORT}/ws")


# ══════════════════════════════════════════════════════════════════════════════
# 5. JELLYFIN  — mounted at /jellyfin/
# ══════════════════════════════════════════════════════════════════════════════
@app.api_route("/jellyfin", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@app.api_route("/jellyfin/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@app.api_route("/Jellyfin", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@app.api_route("/Jellyfin/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def jellyfin_route(request: Request, path: str = ""):
    upstream = f"http://127.0.0.1:{JELLYFIN_PORT}/{path}"
    return await proxy_http(
        upstream, request,
        extra_headers={"X-Forwarded-Prefix": "/jellyfin"},
    )


# ══════════════════════════════════════════════════════════════════════════════
# 6. TG-DRIVE STREAMER  — mounted at /tg-stream/
# ══════════════════════════════════════════════════════════════════════════════
@app.api_route("/tg-stream", methods=["GET", "HEAD", "OPTIONS"])
@app.api_route("/tg-stream/{path:path}", methods=["GET", "HEAD", "OPTIONS"])
async def tg_stream_route(request: Request, path: str = ""):
    upstream = f"http://127.0.0.1:{TG_PORT}/{path}"
    return await proxy_http(upstream, request)


# ══════════════════════════════════════════════════════════════════════════════
# 7. CATCH-ALL — smart Referer-based fallback for sub-resource requests
#    When JS/CSS/API assets from a sub-app arrive at the root (e.g. /_app/...)
#    we use the Referer header to route them to the correct upstream.
# ══════════════════════════════════════════════════════════════════════════════
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def catch_all(path: str, request: Request):
    referer = request.headers.get("referer", "").lower()

    if "/openwebui" in referer:
        return await proxy_http(
            f"http://127.0.0.1:{WEBUI_PORT}/{path}", request,
            html_fixup=_webui_fixup,
        )
    elif "/omniroute" in referer or "/dashboard" in referer or "/login" in referer:
        return await proxy_http(
            f"http://127.0.0.1:{OMNIROUTE_PORT}/{path}", request,
            html_fixup=_omniroute_fixup,
        )
    elif "/server" in referer:
        return await proxy_http(
            f"http://127.0.0.1:{OPENCODE_PORT}/{path}", request,
            html_fixup=_opencode_fixup,
        )
    elif "/jellyfin" in referer:
        return await proxy_http(
            f"http://127.0.0.1:{JELLYFIN_PORT}/{path}", request,
            extra_headers={"X-Forwarded-Prefix": "/jellyfin"},
        )

    # Default: try Open WebUI
    return await proxy_http(
        f"http://127.0.0.1:{WEBUI_PORT}/{path}", request,
        html_fixup=_webui_fixup,
    )
