"""
Open WebUI Gateway Router (Clean Container Architecture)
======================================================
Serves Open WebUI (port 8098) via a clean full-viewport application container.
Bypasses SvelteKit subpath routing limitations by rendering Open WebUI in an isolated viewport context.
"""

from fastapi import APIRouter, Request, Response, WebSocket
from fastapi.responses import HTMLResponse
from gateway.utils import WEBUI_PORT, proxy_http_request, proxy_websocket_stream

router = APIRouter(tags=["OpenWebUI"])

def fixup_webui_html(html: str) -> str:
    return html

WEBUI_CONTAINER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Open WebUI</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html, body { width: 100%; height: 100%; overflow: hidden; background-color: #0d1117; font-family: system-ui, -apple-system, sans-serif; }
        iframe { width: 100%; height: 100%; border: none; display: block; }
    </style>
</head>
<body>
    <iframe id="webui-frame" src="/webui-core/" allow="clipboard-read; clipboard-write; microphone; camera;"></iframe>
</body>
</html>"""

@router.api_route("/chat", methods=["GET"])
@router.api_route("/chat/", methods=["GET"])
@router.api_route("/openwebui", methods=["GET"])
@router.api_route("/openwebui/", methods=["GET"])
async def webui_container_view(request: Request):
    return HTMLResponse(content=WEBUI_CONTAINER_HTML, status_code=200)

@router.api_route("/webui-core", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/webui-core/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def webui_core_proxy(request: Request, path: str = ""):
    target = f"http://127.0.0.1:{WEBUI_PORT}/{path}"
    return await proxy_http_request(target, request, default_prefix="/webui-core")

@router.api_route("/sw.js", methods=["GET", "HEAD"])
async def webui_sw(request: Request):
    target = f"http://127.0.0.1:{WEBUI_PORT}/sw.js"
    res = await proxy_http_request(target, request, default_prefix="/webui-core")
    if res.status_code == 404:
        sw_code = "self.addEventListener('install', (e) => { self.skipWaiting(); }); self.addEventListener('activate', (e) => { e.waitUntil(clients.claim()); });"
        return Response(content=sw_code, status_code=200, media_type="application/javascript")
    return res

@router.websocket("/webui-core/ws")
@router.websocket("/webui-core/ws/{path:path}")
@router.websocket("/webui-core/socket.io")
@router.websocket("/webui-core/socket.io/{path:path}")
@router.websocket("/chat/ws")
@router.websocket("/chat/socket.io")
@router.websocket("/openwebui/ws")
@router.websocket("/openwebui/socket.io")
@router.websocket("/ws/socket.io")
@router.websocket("/ws/socket.io/{path:path}")
async def webui_ws_route(websocket: WebSocket, path: str = ""):
    req_path = websocket.scope.get("path", "")
    if "socket.io" in req_path:
        target = f"ws://127.0.0.1:{WEBUI_PORT}/ws/socket.io"
        if path:
            target = f"{target}/{path}"
    else:
        target = f"ws://127.0.0.1:{WEBUI_PORT}/ws"
        if path:
            target = f"{target}/{path}"
    await proxy_websocket_stream(websocket, target)

# SvelteKit Asset Routing
@router.api_route("/_app/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def webui_assets(request: Request, path: str = ""):
    target = f"http://127.0.0.1:{WEBUI_PORT}/_app/{path}"
    return await proxy_http_request(target, request, default_prefix="/webui-core")
