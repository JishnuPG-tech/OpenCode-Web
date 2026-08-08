"""
OmniRoute AI Gateway Router
===========================
Routes /omniroute/, Next.js static assets (/_next/), and dashboard endpoints (port 20128).
Fixes Next.js internal router redirects (Location: /dashboard -> Location: /omniroute/dashboard).
"""

import re
from fastapi import APIRouter, Request
from gateway.utils import OMNIROUTE_PORT, proxy_http_request

router = APIRouter(tags=["OmniRoute"])

OMNIROUTE_JS_PATCH = """<script>
(function() {
  if (window.__OMNIROUTE_PATCHED__) return;
  window.__OMNIROUTE_PATCHED__ = true;

  // 1. Intercept link clicks so href="/api-keys" becomes href="/omniroute/api-keys"
  document.addEventListener('click', function(e) {
    var a = e.target.closest('a');
    if (a) {
      var href = a.getAttribute('href');
      if (href && href.startsWith('/') && !href.startsWith('/omniroute') && !href.startsWith('http')) {
        a.setAttribute('href', '/omniroute' + href);
      }
    }
  }, true);

  // 2. Intercept history pushState & replaceState
  var origPushState = history.pushState;
  history.pushState = function(state, title, url) {
    if (typeof url === 'string' && url.startsWith('/') && !url.startsWith('/omniroute')) {
      url = '/omniroute' + url;
    }
    return origPushState.call(this, state, title, url);
  };
  var origReplaceState = history.replaceState;
  history.replaceState = function(state, title, url) {
    if (typeof url === 'string' && url.startsWith('/') && !url.startsWith('/omniroute')) {
      url = '/omniroute' + url;
    }
    return origReplaceState.call(this, state, title, url);
  };

  // 3. Intercept fetch & XHR
  var origFetch = window.fetch;
  window.fetch = function(resource, init) {
    if (typeof resource === 'string') {
      if (resource.startsWith('/') && !resource.startsWith('/omniroute') && !resource.startsWith('/_next')) {
        resource = '/omniroute' + resource;
      }
    } else if (resource && resource.url && typeof resource.url === 'string') {
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
    html = html.replace('"basePath":""', '"basePath":"/omniroute"')
    html = html.replace('"basePath": ""', '"basePath": "/omniroute"')
    if "<head>" in html:
        html = html.replace("<head>", f"<head>{OMNIROUTE_JS_PATCH}", 1)
    elif "<head " in html:
        html = re.sub(r"(<head[^>]*>)", r"\1" + OMNIROUTE_JS_PATCH, html, count=1)
    return html

from fastapi.responses import RedirectResponse

@router.api_route("/omniroute", methods=["GET"])
async def omniroute_redirect_slash(request: Request):
    return RedirectResponse("/omniroute/", status_code=307)

@router.api_route("/omniroute/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def omniroute_main_route(request: Request, path: str = ""):
    target = f"http://127.0.0.1:{OMNIROUTE_PORT}/{path}"
    return await proxy_http_request(target, request, default_prefix="/omniroute", html_fixup=fixup_omniroute_html)

# Explicit OmniRoute Dashboard Webapp Routes (e.g. /dashboard/settings/general, /dashboard/api-keys, etc.)
@router.api_route("/dashboard", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/dashboard/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/settings", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/settings/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/providers", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/providers/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/models", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/models/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/api-keys", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/api-keys/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/logs", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/logs/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/stats", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/stats/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/users", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/users/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def omniroute_dashboard_direct_routes(request: Request, path: str = ""):
    req_path = request.url.path
    target = f"http://127.0.0.1:{OMNIROUTE_PORT}{req_path}"
    return await proxy_http_request(target, request, default_prefix="/omniroute", html_fixup=fixup_omniroute_html)

# OpenAI API Endpoint Routing for OmniRoute
@router.api_route("/v1", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def omniroute_v1_api(request: Request, path: str = ""):
    if path == "openapi.json":
        from fastapi.responses import JSONResponse
        return JSONResponse({
            "openapi": "3.0.0",
            "info": {"title": "OmniRoute OpenAI Gateway API", "version": "1.0.0"},
            "paths": {}
        })
    target = f"http://127.0.0.1:{OMNIROUTE_PORT}/v1/{path}" if path else f"http://127.0.0.1:{OMNIROUTE_PORT}/v1"
    return await proxy_http_request(target, request, default_prefix="/omniroute")

# Next.js Static Asset Routing
@router.api_route("/_next/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def omniroute_assets(request: Request, path: str = ""):
    target = f"http://127.0.0.1:{OMNIROUTE_PORT}/_next/{path}"
    return await proxy_http_request(target, request, default_prefix="/omniroute")
