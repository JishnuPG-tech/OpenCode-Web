"""
OmniRoute AI Gateway Router
===========================
Routes /omniroute/, /v1/, /_next/, and /assets/ to OmniRoute Next.js server on port 20128.
Handles Next.js asset URL rewriting, JS fetch interception, Location header fixing, and 500 diagnostic logging.
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
      if (resource.startsWith('/') && !resource.startsWith('/omniroute') && !resource.startsWith('/_next') && !resource.startsWith('/v1')) {
        resource = '/omniroute' + resource;
      }
    }
    return origFetch.call(this, resource, init);
  };
  var origOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url) {
    if (typeof url === 'string' && url.startsWith('/') && !url.startsWith('/omniroute') && !url.startsWith('/_next') && !url.startsWith('/v1')) {
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

# OpenAI API Endpoint Routing for OmniRoute (/v1/chat/completions, /v1/models, etc.)
@router.api_route("/v1", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def omniroute_v1_api(request: Request, path: str = ""):
    target = f"http://127.0.0.1:{OMNIROUTE_PORT}/v1/{path}" if path else f"http://127.0.0.1:{OMNIROUTE_PORT}/v1"
    return await proxy_http_request(target, request, default_prefix="/omniroute")

# Next.js Static Asset Routing
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
