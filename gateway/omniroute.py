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
    # Deduplicate double prefixes if present
    html = html.replace('/omniroute/omniroute', '/omniroute')
    if "<head>" in html:
        html = html.replace("<head>", f"<head>{OMNIROUTE_JS_PATCH}", 1)
    elif "<head " in html:
        html = re.sub(r"(<head[^>]*>)", r"\1" + OMNIROUTE_JS_PATCH, html, count=1)
    return html

from fastapi.responses import RedirectResponse

@router.api_route("/omniroute", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/omniroute/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def omniroute_main_route(request: Request, path: str = ""):
    req_path = request.url.path
    if not req_path.endswith("/") and req_path == "/omniroute":
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/omniroute/", status_code=307)
    
    extra = {"Host": f"127.0.0.1:{OMNIROUTE_PORT}", "X-Forwarded-Host": f"127.0.0.1:{OMNIROUTE_PORT}", "X-Forwarded-Proto": "http"}
    target = f"http://127.0.0.1:{OMNIROUTE_PORT}{req_path}"
    res = await proxy_http_request(target, request, default_prefix="/omniroute", extra_headers=extra, html_fixup=fixup_omniroute_html)
    
    if res.status_code == 404:
        alt_target = f"http://127.0.0.1:{OMNIROUTE_PORT}/{path}" if path else f"http://127.0.0.1:{OMNIROUTE_PORT}/"
        alt_res = await proxy_http_request(alt_target, request, default_prefix="/omniroute", extra_headers=extra, html_fixup=fixup_omniroute_html)
        if alt_res.status_code != 404:
            return alt_res
    return res

# OpenAI API Endpoint Routing for OmniRoute
@router.api_route("/v1", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def omniroute_v1_api(request: Request, path: str = ""):
    if path in ("openapi.json", "openapi.json/"):
        from fastapi.responses import JSONResponse
        return JSONResponse({
            "openapi": "3.0.0",
            "info": {"title": "OmniRoute AI Gateway API", "version": "1.0.0"},
            "paths": {}
        })
    if path == "models" and request.method == "GET":
        from fastapi.responses import JSONResponse
        import json
        target = f"http://127.0.0.1:{OMNIROUTE_PORT}/v1/models"
        try:
            res = await proxy_http_request(target, request, default_prefix="/omniroute")
            if res.status_code == 200:
                body = json.loads(res.body.decode("utf-8"))
                if isinstance(body, dict) and body.get("data") and len(body.get("data")) > 0:
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

# Next.js Static Asset Routing
@router.api_route("/_next/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/omniroute/_next/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def omniroute_assets(request: Request, path: str = ""):
    extra = {"Host": f"127.0.0.1:{OMNIROUTE_PORT}", "X-Forwarded-Host": f"127.0.0.1:{OMNIROUTE_PORT}", "X-Forwarded-Proto": "http"}
    target = f"http://127.0.0.1:{OMNIROUTE_PORT}/omniroute/_next/{path}"
    res = await proxy_http_request(target, request, default_prefix="/omniroute", extra_headers=extra)
    if res.status_code == 404:
        alt_target = f"http://127.0.0.1:{OMNIROUTE_PORT}/_next/{path}"
        alt_res = await proxy_http_request(alt_target, request, default_prefix="/omniroute", extra_headers=extra)
        if alt_res.status_code != 404:
            return alt_res
    return res
