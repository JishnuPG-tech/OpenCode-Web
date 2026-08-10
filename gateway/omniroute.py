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

OMNIROUTE_FALLBACK_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OmniRoute AI Gateway Dashboard</title>
    <style>
        body { font-family: system-ui, -apple-system, sans-serif; background: #0b0f19; color: #e2e8f0; margin: 0; padding: 2rem; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 80vh; }
        .card { background: #1e293b; border: 1px solid #334155; border-radius: 16px; padding: 2rem; width: 100%; max-width: 750px; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.5); }
        .header { display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #334155; padding-bottom: 1rem; margin-bottom: 1.5rem; }
        .badge { background: #10b98120; color: #10b981; border: 1px solid #10b98150; padding: 4px 12px; border-radius: 9999px; font-size: 0.85rem; font-weight: 600; }
        h1 { margin: 0; font-size: 1.5rem; color: #f8fafc; }
        p { color: #94a3b8; line-height: 1.6; font-size: 0.95rem; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; margin-top: 1.5rem; }
        .box { background: #0f172a; padding: 1.25rem; border-radius: 12px; border: 1px solid #1e293b; }
        .box h3 { margin: 0 0 0.5rem; font-size: 0.9rem; color: #38bdf8; text-transform: uppercase; letter-spacing: 0.05em; }
        code { background: #020617; color: #a7f3d0; padding: 4px 8px; border-radius: 6px; font-family: monospace; font-size: 0.9rem; display: block; word-break: break-all; margin-top: 0.4rem; }
        .actions { margin-top: 2rem; display: flex; gap: 1rem; }
        .btn { background: #3b82f6; color: white; padding: 0.6rem 1.2rem; border-radius: 8px; text-decoration: none; font-weight: 500; font-size: 0.9rem; }
        .btn-sec { background: #334155; color: white; }
    </style>
</head>
<body>
    <div class="card">
        <div class="header">
            <h1>⚡ OmniRoute AI Gateway</h1>
            <span class="badge">Online & Active</span>
        </div>
        <p>OmniRoute AI Gateway is operational and ready to serve OpenAI-compatible completions for Hermes Agent, Cursor, OpenCode, and Open WebUI.</p>
        <div class="grid">
            <div class="box">
                <h3>OpenAI API Base</h3>
                <code>https://jishnupg-opencode-cli.hf.space/v1</code>
            </div>
            <div class="box">
                <h3>API Key</h3>
                <code>omniroute</code>
            </div>
            <div class="box">
                <h3>Active Model</h3>
                <code>omniroute/auto-best-coding</code>
            </div>
        </div>
        <div class="actions">
            <a href="/v1/models" class="btn" target="_blank">View Models API</a>
            <a href="/" class="btn btn-sec">Open WebUI</a>
            <a href="/server" class="btn btn-sec">OpenCode Server</a>
        </div>
    </div>
</body>
</html>"""

@router.api_route("/omniroute", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/omniroute/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def omniroute_main_route(request: Request, path: str = ""):
    req_path = request.url.path
    if not req_path.endswith("/") and req_path == "/omniroute":
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/omniroute/", status_code=307)
    
    extra = {"Host": f"127.0.0.1:{OMNIROUTE_PORT}", "X-Forwarded-Host": f"127.0.0.1:{OMNIROUTE_PORT}", "X-Forwarded-Proto": "http"}
    target = f"http://127.0.0.1:{OMNIROUTE_PORT}/{path}" if path else f"http://127.0.0.1:{OMNIROUTE_PORT}/"
    res = await proxy_http_request(target, request, default_prefix="/omniroute", extra_headers=extra, html_fixup=fixup_omniroute_html)
    
    if res.status_code in (404, 500):
        alt_target = f"http://127.0.0.1:{OMNIROUTE_PORT}{req_path}"
        try:
            alt_res = await proxy_http_request(alt_target, request, default_prefix="/omniroute", extra_headers=extra, html_fixup=fixup_omniroute_html)
            if alt_res.status_code not in (404, 500):
                return alt_res
        except Exception:
            pass
            
        if request.method == "GET":
            from fastapi.responses import HTMLResponse
            return HTMLResponse(content=OMNIROUTE_FALLBACK_HTML, status_code=200)

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
