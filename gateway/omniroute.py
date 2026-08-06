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
  var origFetch = window.fetch;
  window.fetch = function(resource, init) {
    if (typeof resource === 'string') {
      if (resource.startsWith('/') && !resource.startsWith('/omniroute')) {
        resource = '/omniroute' + resource;
      }
    } else if (resource && resource.url && typeof resource.url === 'string') {
      if (resource.url.startsWith('/') && !resource.url.startsWith('/omniroute')) {
        resource = new Request('/omniroute' + resource.url, resource);
      }
    }
    return origFetch.call(this, resource, init);
  };
  var origOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url) {
    if (typeof url === 'string' && url.startsWith('/') && !url.startsWith('/omniroute')) {
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

# Next.js Static Asset Routing
@router.api_route("/_next/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def omniroute_assets(request: Request, path: str = ""):
    target = f"http://127.0.0.1:{OMNIROUTE_PORT}/_next/{path}"
    return await proxy_http_request(target, request, default_prefix="/omniroute")
