import os
import re
import asyncio
from fastapi import FastAPI, Request, Response, WebSocket
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
import httpx
import aiohttp

app = FastAPI(title="OpenCode Space Gateway", docs_url=None, redoc_url=None)

WEBUI_PORT = 8098
OMNIROUTE_PORT = 20128
OPENCODE_PORT = 4097
JELLYFIN_PORT = 8096
TG_STREAM_PORT = 8080
GATEWAY_PORT = 4096

PUBLIC_HOST = "jishnupg-opencode-cli.hf.space"
PUBLIC_ORIGIN = f"https://{PUBLIC_HOST}"

PORT_TO_PREFIX = {
    GATEWAY_PORT: "",
    OMNIROUTE_PORT: "/omniroute",
    WEBUI_PORT: "/openwebui",
    OPENCODE_PORT: "/server",
    JELLYFIN_PORT: "/jellyfin",
    TG_STREAM_PORT: "/tg-stream",
}

_PORT_PATTERN = re.compile(
    r"https?://[^/\s\"'>]+:(" + "|".join(str(p) for p in PORT_TO_PREFIX) + r")(?=/|\"|'|\s|$)"
)

def _strip_internal_ports(text: str) -> str:
    def _sub(m: "re.Match[str]") -> str:
        port = int(m.group(1))
        return PORT_TO_PREFIX.get(port, "")
    text = re.sub(r":4096", "", text)
    return _PORT_PATTERN.sub(_sub, text)

client = httpx.AsyncClient(timeout=120.0, follow_redirects=False)

def get_headers(request: Request, extra_headers: dict = None):
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)
    headers["X-Forwarded-Host"] = PUBLIC_HOST
    headers["X-Forwarded-Proto"] = "https"
    headers["X-Forwarded-Port"] = "443"
    headers["X-Forwarded-Server"] = PUBLIC_HOST
    if extra_headers:
        headers.update(extra_headers)
    return headers

async def proxy_http(target_url: str, request: Request, extra_headers: dict = None, sub_filters: list = None):
    headers = get_headers(request, extra_headers)
    method = request.method
    params = dict(request.query_params)
    body = await request.body()

    try:
        resp = await client.request(
            method=method,
            url=target_url,
            headers=headers,
            params=params,
            content=body,
        )
    except Exception as e:
        return Response(content=f"Service Unavailable ({target_url}): {e}", status_code=502)

    res_headers = {}
    for k, v in resp.headers.items():
        lk = k.lower()
        if lk in ["content-length", "transfer-encoding", "content-encoding"]:
            continue
        if lk == "location":
            v = re.sub(r":4096", "", v)
            v = _strip_internal_ports(v)
            if v == "/login" or v.startswith("/login?"):
                v = "/omniroute" + v
            elif v == "/dashboard" or v.startswith("/dashboard?"):
                v = "/omniroute" + v
        res_headers[k] = v

    content = resp.content
    ctype = resp.headers.get("content-type", "")

    # Apply text rewriting exclusively to HTML responses
    if "text/html" in ctype:
        try:
            text_str = content.decode("utf-8", errors="ignore")
            if sub_filters:
                for old_s, new_s in sub_filters:
                    text_str = text_str.replace(old_s, new_s)
            text_str = _strip_internal_ports(text_str)
            content = text_str.encode("utf-8")
        except Exception:
            pass

    return Response(
        content=content,
        status_code=resp.status_code,
        headers=res_headers,
        media_type=ctype if ctype else None
    )

async def proxy_ws(websocket: WebSocket, target_ws_url: str):
    await websocket.accept()
    async with aiohttp.ClientSession() as session:
        headers = {k: v for k, v in websocket.headers.items() if k.lower() not in ["host", "sec-websocket-key", "sec-websocket-version", "sec-websocket-extensions"]}
        try:
            async with session.ws_connect(target_ws_url, headers=headers) as target_ws:
                async def forward_to_client():
                    async for msg in target_ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await websocket.send_text(msg.data)
                        elif msg.type == aiohttp.WSMsgType.BINARY:
                            await websocket.send_bytes(msg.data)
                        elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
                            break

                async def forward_to_target():
                    while True:
                        try:
                            msg = await websocket.receive()
                            if "text" in msg:
                                await target_ws.send_str(msg["text"])
                            elif "bytes" in msg:
                                await target_ws.send_bytes(msg["bytes"])
                            elif msg.get("type") == "websocket.disconnect":
                                break
                        except Exception:
                            break

                await asyncio.gather(forward_to_client(), forward_to_target(), return_exceptions=True)
        except Exception as e:
            try:
                await websocket.close()
            except Exception:
                pass

# ==========================================
# 1. LANDING HUB ROUTE (GET & HEAD)
# ==========================================
@app.api_route("/", methods=["GET", "HEAD"])
async def root_hub():
    if os.path.exists("/index.html"):
        return FileResponse("/index.html", media_type="text/html")
    return HTMLResponse("<h1>OpenCode Space Gateway Active</h1>")

@app.api_route("/favicon.ico", methods=["GET", "HEAD"])
async def favicon():
    return Response(content=b"", status_code=204)

# ==========================================
# 1b. DEBUG STATUS ROUTE
# ==========================================
@app.api_route("/debug/status", methods=["GET"])
async def debug_status():
    checks = {
        "opencode_server": f"http://127.0.0.1:{OPENCODE_PORT}/",
        "omniroute": f"http://127.0.0.1:{OMNIROUTE_PORT}/",
        "open_webui": f"http://127.0.0.1:{WEBUI_PORT}/openwebui/",
        "jellyfin": f"http://127.0.0.1:{JELLYFIN_PORT}/",
        "tg_streamer": f"http://127.0.0.1:{TG_STREAM_PORT}/",
    }
    results = {}
    for name, url in checks.items():
        try:
            r = await client.get(url, timeout=5.0)
            results[name] = {"status": "up", "http_status": r.status_code}
        except Exception as e:
            results[name] = {"status": "down", "error": str(e)}
    return results

# ==========================================
# 2. OPEN WEBUI ROUTES (/openwebui, /api, /auth)
# ==========================================
@app.api_route("/openwebui/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@app.api_route("/openwebui", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def openwebui_route(request: Request, path: str = ""):
    url = f"http://127.0.0.1:{WEBUI_PORT}/openwebui/{path}" if path else f"http://127.0.0.1:{WEBUI_PORT}/openwebui/"
    return await proxy_http(url, request, extra_headers={"X-Forwarded-Prefix": "/openwebui"})

@app.api_route("/api/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def openwebui_api(path: str, request: Request):
    url = f"http://127.0.0.1:{WEBUI_PORT}/api/v1/{path}"
    return await proxy_http(url, request)

@app.api_route("/auth/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def openwebui_auth(path: str, request: Request):
    url = f"http://127.0.0.1:{WEBUI_PORT}/auth/{path}"
    return await proxy_http(url, request)

# ==========================================
# 3. OMNIROUTE GATEWAY ROUTES (/omniroute, /v1, /_next, /dashboard, /login)
# ==========================================
OMNIROUTE_FILTERS = [
    ('href="/', 'href="/omniroute/'),
    ('src="/', 'src="/omniroute/'),
    ('action="/', 'action="/omniroute/'),
    ('="/_next/', '="/omniroute/_next/'),
    ('"/_next/', '"/omniroute/_next/'),
]

@app.api_route("/omniroute/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@app.api_route("/omniroute", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def omniroute_route(request: Request, path: str = ""):
    url = f"http://127.0.0.1:{OMNIROUTE_PORT}/{path}" if path else f"http://127.0.0.1:{OMNIROUTE_PORT}/"
    return await proxy_http(url, request, sub_filters=OMNIROUTE_FILTERS)

@app.api_route("/dashboard/{path:path}", methods=["GET", "POST", "HEAD", "OPTIONS"])
@app.api_route("/dashboard", methods=["GET", "POST", "HEAD", "OPTIONS"])
async def omniroute_dashboard(request: Request, path: str = ""):
    url = f"http://127.0.0.1:{OMNIROUTE_PORT}/dashboard/{path}" if path else f"http://127.0.0.1:{OMNIROUTE_PORT}/dashboard"
    return await proxy_http(url, request, sub_filters=OMNIROUTE_FILTERS)

@app.api_route("/login/{path:path}", methods=["GET", "POST", "HEAD", "OPTIONS"])
@app.api_route("/login", methods=["GET", "POST", "HEAD", "OPTIONS"])
async def omniroute_login(request: Request, path: str = ""):
    url = f"http://127.0.0.1:{OMNIROUTE_PORT}/login/{path}" if path else f"http://127.0.0.1:{OMNIROUTE_PORT}/login"
    return await proxy_http(url, request, sub_filters=OMNIROUTE_FILTERS)

@app.api_route("/_next/{path:path}", methods=["GET", "POST", "OPTIONS"])
async def omniroute_next(path: str, request: Request):
    url = f"http://127.0.0.1:{OMNIROUTE_PORT}/_next/{path}"
    return await proxy_http(url, request)

@app.api_route("/v1/{path:path}", methods=["GET", "POST", "OPTIONS"])
async def omniroute_v1(path: str, request: Request):
    url = f"http://127.0.0.1:{OMNIROUTE_PORT}/v1/{path}"
    return await proxy_http(url, request)

# ==========================================
# 4. OPENCODE CLI SERVER ROUTES (/server, /ws, APIs)
# ==========================================
OPENCODE_FILTERS = [
    ('href="/', 'href="/server/'),
    ('src="/', 'src="/server/'),
]

@app.api_route("/server/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@app.api_route("/server", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def opencode_server_route(request: Request, path: str = ""):
    url = f"http://127.0.0.1:{OPENCODE_PORT}/{path}" if path else f"http://127.0.0.1:{OPENCODE_PORT}/"
    return await proxy_http(url, request, sub_filters=OPENCODE_FILTERS)

def make_endpoint_route(ep_name: str):
    @app.api_route(f"/{ep_name}/{{path:path}}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
    async def opencode_endpoint(path: str, request: Request):
        url = f"http://127.0.0.1:{OPENCODE_PORT}/{ep_name}/{path}"
        return await proxy_http(url, request)

    @app.api_route(f"/{ep_name}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
    async def opencode_endpoint_root(request: Request):
        url = f"http://127.0.0.1:{OPENCODE_PORT}/{ep_name}"
        return await proxy_http(url, request)

# Added /command, /provider, /model, /mcp required by OpenCode Web UI!
OPENCODE_ENDPOINTS = [
    "session", "project", "config", "permission", "question",
    "file", "find", "events", "event", "command", "provider", "model", "mcp"
]
for ep in OPENCODE_ENDPOINTS:
    make_endpoint_route(ep)

@app.websocket("/ws")
@app.websocket("/server/ws")
async def opencode_ws(websocket: WebSocket):
    target = f"ws://127.0.0.1:{OPENCODE_PORT}/ws"
    await proxy_ws(websocket, target)

# ==========================================
# 5. JELLYFIN MEDIA SERVER ROUTES (/jellyfin and /Jellyfin)
# ==========================================
@app.api_route("/jellyfin/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@app.api_route("/jellyfin", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@app.api_route("/Jellyfin/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@app.api_route("/Jellyfin", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def jellyfin_route(request: Request, path: str = ""):
    url = f"http://127.0.0.1:{JELLYFIN_PORT}/{path}" if path else f"http://127.0.0.1:{JELLYFIN_PORT}/"
    return await proxy_http(url, request, extra_headers={"X-Forwarded-Prefix": "/jellyfin"})

# ==========================================
# 6. TELEGRAM DIRECT STREAM PROXY (/tg-stream)
# ==========================================
@app.api_route("/tg-stream/{path:path}", methods=["GET", "HEAD", "OPTIONS"])
@app.api_route("/tg-stream", methods=["GET", "HEAD", "OPTIONS"])
async def tg_stream_route(request: Request, path: str = ""):
    url = f"http://127.0.0.1:{TG_STREAM_PORT}/{path}" if path else f"http://127.0.0.1:{TG_STREAM_PORT}/"
    return await proxy_http(url, request)

# ==========================================
# 7. SMART REFERER FALLBACK
# ==========================================
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def catch_all_fallback(path: str, request: Request):
    referer = request.headers.get("referer", "").lower()
    
    if "openwebui" in referer:
        url = f"http://127.0.0.1:{WEBUI_PORT}/openwebui/{path}"
        return await proxy_http(url, request, extra_headers={"X-Forwarded-Prefix": "/openwebui"})
    elif "omniroute" in referer or "dashboard" in referer or "login" in referer:
        url = f"http://127.0.0.1:{OMNIROUTE_PORT}/{path}"
        return await proxy_http(url, request, sub_filters=OMNIROUTE_FILTERS)
    elif "server" in referer:
        url = f"http://127.0.0.1:{OPENCODE_PORT}/{path}"
        return await proxy_http(url, request)
    elif "jellyfin" in referer:
        url = f"http://127.0.0.1:{JELLYFIN_PORT}/{path}"
        return await proxy_http(url, request, extra_headers={"X-Forwarded-Prefix": "/jellyfin"})

    url = f"http://127.0.0.1:{WEBUI_PORT}/openwebui/{path}"
    return await proxy_http(url, request, extra_headers={"X-Forwarded-Prefix": "/openwebui"})
