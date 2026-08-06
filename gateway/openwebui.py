"""
Open WebUI Gateway Router
=========================
Routes /openwebui/ and SvelteKit static/API endpoints to Open WebUI (port 8098).
Injects client-side JS fetch interceptors to seamlessly handle root-relative AJAX calls.
"""

import re
from fastapi import APIRouter, Request, WebSocket
from gateway.utils import WEBUI_PORT, proxy_http_request, proxy_websocket_stream

router = APIRouter(tags=["OpenWebUI"])

WEBUI_JS_PATCH = """<script>
(function() {
  if (window.__WEBUI_PATCHED__) return;
  window.__WEBUI_PATCHED__ = true;
  var origPushState = history.pushState;
  history.pushState = function(state, title, url) {
    if (typeof url === 'string' && url.startsWith('/') && !url.startsWith('/openwebui')) {
      url = '/openwebui' + url;
    }
    return origPushState.call(this, state, title, url);
  };
  var origReplaceState = history.replaceState;
  history.replaceState = function(state, title, url) {
    if (typeof url === 'string' && url.startsWith('/') && !url.startsWith('/openwebui')) {
      url = '/openwebui' + url;
    }
    return origReplaceState.call(this, state, title, url);
  };
  var origFetch = window.fetch;
  window.fetch = function(resource, init) {
    if (typeof resource === 'string') {
      if (resource.startsWith('/') && !resource.startsWith('/openwebui')) {
        resource = '/openwebui' + resource;
      }
    } else if (resource && resource.url && typeof resource.url === 'string') {
      if (resource.url.startsWith('/') && !resource.url.startsWith('/openwebui')) {
        resource = new Request('/openwebui' + resource.url, resource);
      }
    }
    return origFetch.call(this, resource, init);
  };
  var origOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url) {
    if (typeof url === 'string' && url.startsWith('/') && !url.startsWith('/openwebui')) {
      url = '/openwebui' + url;
    }
    return origOpen.apply(this, arguments);
  };
})();
</script>"""

def fixup_webui_html(html: str) -> str:
    """Rewrite absolute links & inject JS fetch interceptor into <head>."""
    html = html.replace('href="/', 'href="/openwebui/')
    html = html.replace("href='/", "href='/openwebui/")
    html = html.replace('src="/', 'src="/openwebui/')
    html = html.replace("src='/", "src='/openwebui/")
    html = html.replace('action="/', 'action="/openwebui/')
    if "<head>" in html:
        html = html.replace("<head>", f"<head>{WEBUI_JS_PATCH}", 1)
    elif "<head " in html:
        html = re.sub(r"(<head[^>]*>)", r"\1" + WEBUI_JS_PATCH, html, count=1)
    return html

from fastapi.responses import RedirectResponse

@router.api_route("/openwebui", methods=["GET"])
async def webui_redirect_slash(request: Request):
    return RedirectResponse("/openwebui/", status_code=307)

@router.api_route("/openwebui/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def webui_main_route(request: Request, path: str = ""):
    target = f"http://127.0.0.1:{WEBUI_PORT}/{path}"
    return await proxy_http_request(target, request, default_prefix="/openwebui", html_fixup=fixup_webui_html)

@router.api_route("/sw.js", methods=["GET", "HEAD"])
async def webui_sw(request: Request):
    target = f"http://127.0.0.1:{WEBUI_PORT}/sw.js"
    res = await proxy_http_request(target, request, default_prefix="/openwebui")
    if res.status_code == 404:
        sw_code = "self.addEventListener('install', (e) => { self.skipWaiting(); }); self.addEventListener('activate', (e) => { e.waitUntil(clients.claim()); });"
        return Response(content=sw_code, status_code=200, media_type="application/javascript")
    return res

@router.websocket("/openwebui/ws")
@router.websocket("/openwebui/ws/{path:path}")
@router.websocket("/openwebui/socket.io")
@router.websocket("/openwebui/socket.io/{path:path}")
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
    return await proxy_http_request(target, request, default_prefix="/openwebui")
