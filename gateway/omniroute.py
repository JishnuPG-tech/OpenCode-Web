"""
OmniRoute AI Gateway Router
===========================
Routes OmniRoute endpoints cleanly without interfering with Open WebUI, Jellyfin, or TG-Streamer.
Handles:
  - /omniroute/ (Dashboard & frontend routes)
  - /_next/ (Next.js assets)
  - /v1/ (OpenAI API compatibility format)
  - /v1beta/ (Gemini API compatibility format)
  - /authorize (OAuth authorization route)
  - OmniRoute backend settings & management APIs (/api/providers, /api/combos, /api/settings, /api/usage, etc.)
"""

import os
import re
import logging
from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from gateway.utils import OMNIROUTE_PORT, proxy_http_request

logger = logging.getLogger("OmniRouteGateway")
router = APIRouter(tags=["OmniRoute"])

OMNIROUTE_JS_PATCH = """<script>
(function() {
  var origFetch = window.fetch;
  window.fetch = function(resource, init) {
    if (typeof resource === 'string') {
      if (resource.startsWith('/') && !resource.startsWith('/omniroute') && !resource.startsWith('/_next') && !resource.startsWith('/v1') && !resource.startsWith('/v1beta')) {
        resource = '/omniroute' + resource;
      }
    }
    return origFetch.call(this, resource, init);
  };
  var origOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url) {
    if (typeof url === 'string' && url.startsWith('/') && !url.startsWith('/omniroute') && !url.startsWith('/_next') && !url.startsWith('/v1') && !url.startsWith('/v1beta')) {
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
    # Deduplicate double prefixes
    html = html.replace('/omniroute/omniroute', '/omniroute')
    if "<head>" in html:
        html = html.replace("<head>", f"<head>{OMNIROUTE_JS_PATCH}", 1)
    elif "<head " in html:
        html = re.sub(r"(<head[^>]*>)", r"\1" + OMNIROUTE_JS_PATCH, html, count=1)
    return html

# ── 1. OmniRoute Dashboard Pages ──────────────────────────────────────────────
@router.api_route("/omniroute", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/omniroute/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def omniroute_main_route(request: Request, path: str = ""):
    if not path or path in ("", "/"):
        if request.method == "GET":
            return RedirectResponse("/omniroute/dashboard", status_code=302)
        path = ""
    
    extra = {
        "Host": f"127.0.0.1:{OMNIROUTE_PORT}",
        "X-Forwarded-Host": f"127.0.0.1:{OMNIROUTE_PORT}",
        "X-Forwarded-Proto": "http"
    }
    target = f"http://127.0.0.1:{OMNIROUTE_PORT}/{path}"
    res = await proxy_http_request(
        target,
        request,
        default_prefix="/omniroute",
        extra_headers=extra,
        html_fixup=fixup_omniroute_html
    )
    
    if res.status_code in (301, 302, 307, 308):
        location = res.headers.get("location", "")
        if location and location.rstrip("/") in ("/omniroute", f"https://127.0.0.1:{OMNIROUTE_PORT}", "http://127.0.0.1:20128", "/"):
            return RedirectResponse("/omniroute/dashboard", status_code=302)
            
    return res

# ── 2. OpenAI & Gemini Compatibility APIs ─────────────────────────────────────
@router.api_route("/v1", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def omniroute_v1_api(request: Request, path: str = ""):
    target = f"http://127.0.0.1:{OMNIROUTE_PORT}/v1/{path}" if path else f"http://127.0.0.1:{OMNIROUTE_PORT}/v1"
    return await proxy_http_request(target, request, default_prefix="/omniroute")

@router.api_route("/v1beta/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def omniroute_v1beta_api(request: Request, path: str = ""):
    target = f"http://127.0.0.1:{OMNIROUTE_PORT}/v1beta/{path}"
    return await proxy_http_request(target, request, default_prefix="/omniroute")

# ── 3. Next.js Static Asset Routing ──────────────────────────────────────────
@router.api_route("/_next/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/omniroute/_next/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def omniroute_assets(request: Request, path: str = ""):
    extra = {
        "Host": f"127.0.0.1:{OMNIROUTE_PORT}",
        "X-Forwarded-Host": f"127.0.0.1:{OMNIROUTE_PORT}",
        "X-Forwarded-Proto": "http"
    }
    target = f"http://127.0.0.1:{OMNIROUTE_PORT}/omniroute/_next/{path}"
    res = await proxy_http_request(target, request, default_prefix="/omniroute", extra_headers=extra)
    if res.status_code == 404:
        alt_target = f"http://127.0.0.1:{OMNIROUTE_PORT}/_next/{path}"
        alt_res = await proxy_http_request(alt_target, request, default_prefix="/omniroute", extra_headers=extra)
        if alt_res.status_code != 404:
            return alt_res
    return res

# ── 4. OAuth & Health Endpoints ──────────────────────────────────────────────
@router.api_route("/authorize", methods=["GET", "POST", "OPTIONS"])
async def omniroute_authorize(request: Request):
    target = f"http://127.0.0.1:{OMNIROUTE_PORT}/authorize"
    return await proxy_http_request(target, request, default_prefix="/omniroute")

# ── 5. Specific OmniRoute Backend Management APIs ─────────────────────────────
OMNIROUTE_API_PREFIXES = (
    "/api/providers",
    "/api/combos",
    "/api/circuit-breakers",
    "/api/settings",
    "/api/usage",
    "/api/system",
    "/api/skills",
    "/api/tunnels",
    "/api/version-manager",
    "/api/tools",
    "/api/mcp",
    "/api/a2a",
    "/api/webhooks",
    "/api/token-health",
    "/api/synced-available-models",
    "/api/shutdown",
    "/api/storage",
    "/api/sync",
    "/api/telemetry",
    "/api/translator",
    "/api/upstream-proxy",
)

@router.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def omniroute_specific_apis(request: Request, path: str = ""):
    full_path = f"/api/{path}"
    # Check if this route belongs to OmniRoute's management API suite
    if any(full_path.startswith(prefix) for prefix in OMNIROUTE_API_PREFIXES):
        target = f"http://127.0.0.1:{OMNIROUTE_PORT}/api/{path}"
        return await proxy_http_request(target, request, default_prefix="/omniroute")
    
    # If not an OmniRoute-specific management route, return 404 to let Open WebUI / fallback router handle it
    return Response(status_code=404)
