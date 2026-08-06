"""
OpenCode CLI Server Gateway Router
==================================
Routes /server/ and OpenCode unique API endpoints (port 4097).
"""

from fastapi import APIRouter, Request, WebSocket
from gateway.utils import OPENCODE_PORT, proxy_http_request, proxy_websocket_stream

router = APIRouter(tags=["OpenCode"])

def fixup_opencode_html(html: str) -> str:
    """Re-anchor OpenCode static assets to /server/ subpath."""
    html = html.replace('href="/', 'href="/server/')
    html = html.replace("href='/", "href='/server/")
    html = html.replace('src="/', 'src="/server/')
    html = html.replace("src='/", "src='/server/")
    html = html.replace('ws://"+location.host+"/ws', 'ws://"+location.host+"/server/ws')
    html = html.replace("ws://'+location.host+'/ws", "ws://'+location.host+'/server/ws")
    return html

@router.api_route("/server", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/server/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def opencode_main_route(request: Request, path: str = ""):
    target = f"http://127.0.0.1:{OPENCODE_PORT}/{path}"
    return await proxy_http_request(target, request, default_prefix="/server", html_fixup=fixup_opencode_html)

@router.websocket("/server/ws")
@router.websocket("/ws")
async def opencode_ws_route(websocket: WebSocket):
    await proxy_websocket_stream(websocket, f"ws://127.0.0.1:{OPENCODE_PORT}/ws")

# Unique OpenCode Direct Endpoints
OPENCODE_DIRECT_ENDPOINTS = [
    "session", "project", "permission", "question",
    "file", "find", "events", "event", "command", "provider", "mcp"
]

def _register_direct_route(prefix: str):
    @router.api_route(f"/{prefix}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
    @router.api_route(f"/{prefix}/{{path:path}}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
    async def direct_endpoint(request: Request, path: str = ""):
        full_path = f"{prefix}/{path}" if path else prefix
        target = f"http://127.0.0.1:{OPENCODE_PORT}/{full_path}"
        return await proxy_http_request(target, request, default_prefix="/server", html_fixup=fixup_opencode_html)

for p in OPENCODE_DIRECT_ENDPOINTS:
    _register_direct_route(p)
