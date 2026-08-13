"""
OmniRoute Router for FastAPI Gateway
====================================
Routes OmniRoute endpoints to single backend server on 127.0.0.1:20128:
  - /v1/* -> 20128 (OmniRoute API)
  - /v1beta/* -> 20128 (OmniRoute API v1beta)
  - /live-ws -> 20128 (OmniRoute WebSocket)
  - /dashboard/* -> 20128 (OmniRoute Dashboard)
  - /api/providers/* -> 20128 (OmniRoute Providers API)
  - /api/oauth/* -> 20128 (OmniRoute OAuth API)
  - /omniroute/* -> 20128 (OmniRoute Subpath Prefix)
"""

import re
import logging
from fastapi import APIRouter, Request, Response, WebSocket
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from gateway.utils import proxy_http_request, proxy_websocket_stream

logger = logging.getLogger("GatewayOmniRoute")
router = APIRouter(tags=["omniroute"])

OMNIROUTE_PORT = 20128

OMNIROUTE_JS_PATCH = """<script>
(function() {
  var origFetch = window.fetch;
  window.fetch = function(resource, init) {
    if (typeof resource === 'string') {
      if (resource.startsWith('/') && !resource.startsWith('/omniroute') && !resource.startsWith('/_next')) {
        resource = '/omniroute' + resource;
      }
    } else if (resource && resource.url) {
      if (resource.url.startsWith('/') && !resource.url.startsWith('/omniroute') && !resource.url.startsWith('/_next')) {
        resource = new Request('/omniroute' + resource.url, resource);
      }
    }
    return origFetch.call(this, resource, init);
  };
  var origOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url) {
    if (typeof url === 'string' && url.startsWith('/') && !url.startsWith('/omniroute') && !url.startsWith('/_next')) {
      url = '/omniroute' + url;
    }
    return origOpen.apply(this, arguments);
  };
})();
</script>"""

def fixup_omniroute_html(html: str) -> str:
    """Rewrite Next.js root-relative URLs & inject JS fetch interceptor into <head>."""
    html = html.replace('href="/', 'href="/omniroute/')
    html = html.replace("href='/", "href='/omniroute/")
    html = html.replace('src="/', 'src="/omniroute/')
    html = html.replace("src='/", "src='/omniroute/")
    html = html.replace('action="/', 'action="/omniroute/')
    html = html.replace('"/_next/', '"/omniroute/_next/')
    html = html.replace("'/_next/", "'/omniroute/_next/")
    html = html.replace('/omniroute/omniroute', '/omniroute')
    if "<head>" in html:
        html = html.replace("<head>", f"<head>{OMNIROUTE_JS_PATCH}", 1)
    elif "<head " in html:
        html = re.sub(r"(<head[^>]*>)", r"\1" + OMNIROUTE_JS_PATCH, html, count=1)
    return html

# ── Dashboard & Admin UI Routes (20128) ──────────────────────────────────────
@router.api_route("/dashboard", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/dashboard/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def omniroute_dashboard(request: Request, path: str = ""):
    target = f"http://127.0.0.1:{OMNIROUTE_PORT}/dashboard/{path}" if path else f"http://127.0.0.1:{OMNIROUTE_PORT}/dashboard"
    return await proxy_http_request(target, request, default_prefix="/omniroute", html_fixup=fixup_omniroute_html)

@router.api_route("/api/providers", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/api/providers/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def omniroute_providers(request: Request, path: str = ""):
    target = f"http://127.0.0.1:{OMNIROUTE_PORT}/api/providers/{path}" if path else f"http://127.0.0.1:{OMNIROUTE_PORT}/api/providers"
    return await proxy_http_request(target, request, default_prefix="/omniroute")

@router.api_route("/api/oauth", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/api/oauth/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def omniroute_oauth(request: Request, path: str = ""):
    target = f"http://127.0.0.1:{OMNIROUTE_PORT}/api/oauth/{path}" if path else f"http://127.0.0.1:{OMNIROUTE_PORT}/api/oauth"
    return await proxy_http_request(target, request, default_prefix="/omniroute")

# ── OpenAI API Endpoint Routing (20128) ─────────────────────────────────────
@router.api_route("/v1", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def omniroute_v1_api(request: Request, path: str = ""):
    if path in ("openapi.json", "openapi.json/"):
        return JSONResponse({
            "openapi": "3.0.0",
            "info": {"title": "OmniRoute AI Gateway API", "version": "1.0.0"},
            "paths": {}
        })
    if path == "models" and request.method == "GET":
        target = f"http://127.0.0.1:{OMNIROUTE_PORT}/v1/models"
        try:
            res = await proxy_http_request(target, request, default_prefix="/omniroute")
            if res.status_code == 200:
                return res
        except Exception:
            pass

        return JSONResponse({
            "object": "list",
            "data": [
                {"id": "omniroute/auto-best-coding", "object": "model", "owned_by": "omniroute"},
                {"id": "gpt-4o", "object": "model", "owned_by": "openai"},
                {"id": "gpt-4o-mini", "object": "model", "owned_by": "openai"},
                {"id": "claude-3-5-sonnet-20241022", "object": "model", "owned_by": "anthropic"},
                {"id": "gemini-2.5-flash", "object": "model", "owned_by": "google"},
                {"id": "qwen-2.5-coder-32b", "object": "model", "owned_by": "qwen"}
            ]
        })
    target = f"http://127.0.0.1:{OMNIROUTE_PORT}/v1/{path}" if path else f"http://127.0.0.1:{OMNIROUTE_PORT}/v1"
    return await proxy_http_request(target, request, default_prefix="/omniroute")

@router.api_route("/v1beta", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/v1beta/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def omniroute_v1beta_api(request: Request, path: str = ""):
    target = f"http://127.0.0.1:{OMNIROUTE_PORT}/v1beta/{path}" if path else f"http://127.0.0.1:{OMNIROUTE_PORT}/v1beta"
    return await proxy_http_request(target, request, default_prefix="/omniroute")

# ── WebSocket Proxying (20128) ──────────────────────────────────────────────
@router.websocket("/live-ws")
async def omniroute_ws(websocket: WebSocket):
    target_ws = f"ws://127.0.0.1:{OMNIROUTE_PORT}/live-ws"
    await proxy_websocket_stream(websocket, target_ws)

# ── Legacy Subpath Prefixed Routes (/omniroute) ─────────────────────────────
@router.api_route("/omniroute", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/omniroute/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def omniroute_main_route(request: Request, path: str = ""):
    if not path or path in ("", "/"):
        if request.method == "GET":
            return RedirectResponse("/dashboard", status_code=302)
        path = ""
    target = f"http://127.0.0.1:{OMNIROUTE_PORT}/{path}"
    return await proxy_http_request(target, request, default_prefix="/omniroute", html_fixup=fixup_omniroute_html)
