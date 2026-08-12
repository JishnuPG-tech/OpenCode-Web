"""
Open WebUI Gateway Router
=========================
Proxies '/openwebui/*' and Open WebUI API/WebSocket/static endpoints to Open WebUI on port 8098.
"""

from fastapi import APIRouter, Request, Response, WebSocket
from gateway.utils import WEBUI_PORT, proxy_http_request, proxy_websocket_stream

router = APIRouter(tags=["OpenWebUI"])

def fixup_webui_html(html: str) -> str:
    if not html:
        return html
    html = html.replace('href="/_app/', 'href="/openwebui/_app/')
    html = html.replace('src="/_app/', 'src="/openwebui/_app/')
    html = html.replace('href="/static/', 'href="/openwebui/static/')
    html = html.replace('src="/static/', 'src="/openwebui/static/')
    html = html.replace('href="/favicon', 'href="/openwebui/favicon')
    html = html.replace('src="/favicon', 'src="/openwebui/favicon')
    return html

@router.api_route("/openwebui", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/openwebui/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def webui_prefix_proxy(request: Request, path: str = ""):
    target = f"http://127.0.0.1:{WEBUI_PORT}/{path}" if path else f"http://127.0.0.1:{WEBUI_PORT}/"
    return await proxy_http_request(
        target,
        request,
        default_prefix="/openwebui",
        html_fixup=fixup_webui_html
    )

@router.api_route("/sw.js", methods=["GET", "HEAD"])
@router.api_route("/openwebui/sw.js", methods=["GET", "HEAD"])
async def webui_sw(request: Request):
    target = f"http://127.0.0.1:{WEBUI_PORT}/sw.js"
    res = await proxy_http_request(target, request, default_prefix="/openwebui")
    if res.status_code >= 400:
        sw_code = "self.addEventListener('install', (e) => { self.skipWaiting(); }); self.addEventListener('activate', (e) => { e.waitUntil(clients.claim()); });"
        return Response(content=sw_code, status_code=200, media_type="application/javascript")
    return res

@router.websocket("/ws")
@router.websocket("/ws/{path:path}")
@router.websocket("/ws/socket.io")
@router.websocket("/ws/socket.io/{path:path}")
@router.websocket("/socket.io")
@router.websocket("/socket.io/{path:path}")
@router.websocket("/openwebui/ws")
@router.websocket("/openwebui/ws/{path:path}")
@router.websocket("/openwebui/ws/socket.io")
@router.websocket("/openwebui/ws/socket.io/{path:path}")
@router.websocket("/openwebui/socket.io")
@router.websocket("/openwebui/socket.io/{path:path}")
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
@router.api_route("/openwebui/_app/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def webui_assets(request: Request, path: str = ""):
    target = f"http://127.0.0.1:{WEBUI_PORT}/_app/{path}"
    return await proxy_http_request(target, request, default_prefix="/openwebui")
