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
    html = html.replace('href="/assets/', 'href="/openwebui/assets/')
    html = html.replace('src="/assets/', 'src="/openwebui/assets/')
    html = html.replace('href="/favicon', 'href="/openwebui/favicon')
    html = html.replace('src="/favicon', 'src="/openwebui/favicon')
    html = html.replace('href="/manifest.json', 'href="/openwebui/manifest.json')
    html = html.replace('"/api/', '"/openwebui/api/')
    html = html.replace("'/api/", "'/openwebui/api/")
    html = html.replace('"/ws/socket.io', '"/openwebui/ws/socket.io')
    html = html.replace("'/ws/socket.io", "'/openwebui/ws/socket.io")
    return html

@router.api_route("/openwebui", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@router.api_route("/openwebui/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def webui_prefix_proxy(request: Request, path: str = ""):
    sub_path = path.lstrip("/")
    target = f"http://127.0.0.1:{WEBUI_PORT}/{sub_path}" if sub_path else f"http://127.0.0.1:{WEBUI_PORT}/"
    resp = await proxy_http_request(
        target,
        request,
        default_prefix="/openwebui",
        html_fixup=fixup_webui_html
    )
    resp.set_cookie("OWUI_SCOPE", "1", path="/", samesite="lax")
    return resp

@router.api_route("/openwebui/sw.js", methods=["GET", "HEAD"])
async def webui_sw(request: Request):
    target = f"http://127.0.0.1:{WEBUI_PORT}/sw.js"
    res = await proxy_http_request(target, request, default_prefix="/openwebui")
    if res.status_code >= 400:
        sw_code = "self.addEventListener('install', (e) => { self.skipWaiting(); }); self.addEventListener('activate', (e) => { e.waitUntil(clients.claim()); });"
        return Response(content=sw_code, status_code=200, media_type="application/javascript")
    return res

@router.websocket("/openwebui/ws")
@router.websocket("/openwebui/ws/{path:path}")
@router.websocket("/openwebui/ws/socket.io")
@router.websocket("/openwebui/ws/socket.io/{path:path}")
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
