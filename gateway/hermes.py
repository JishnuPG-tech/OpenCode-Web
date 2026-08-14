"""
Hermes Agent Gateway Router
===========================
Proxies '/hermes/*' and '/hermes/v1/*' requests to Hermes Agent on port 8642.
Features:
  - Header preservation
  - Automatic error retries on payload 401 string errors
  - Automatic fallback stripping of /v1/ subpaths
"""

import os
import logging
import asyncio
from fastapi import APIRouter, Request, Response, WebSocket
from gateway.utils import proxy_http_request, proxy_websocket_stream

logger = logging.getLogger("GatewayHermes")
router = APIRouter(tags=["Hermes"])

HERMES_PORT = 8642
API_SERVER_KEY = (
    os.getenv("HERMES_GATEWAY_API_KEY")
    or os.getenv("HERMES_API_KEY_SECRET")
    or os.getenv("API_KEY_SECRET")
    or os.getenv("INITIAL_PASSWORD")
    or "admin123"
)


@router.api_route("/hermes", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
@router.api_route("/hermes/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def hermes_proxy(request: Request, path: str = ""):
    clean_path = path.lstrip("/")
    if not clean_path:
        upstream = f"http://127.0.0.1:{HERMES_PORT}/"
    else:
        upstream = f"http://127.0.0.1:{HERMES_PORT}/{clean_path}"

    primary_headers = {}
    auth_header = request.headers.get("authorization")
    if auth_header:
        primary_headers["Authorization"] = auth_header
    else:
        primary_headers["Authorization"] = f"Bearer {API_SERVER_KEY}"

    res = await proxy_http_request(
        upstream,
        request,
        default_prefix="/hermes",
        extra_headers=primary_headers,
    )

    if res.status_code in (404, 405, 401) and clean_path.startswith("v1/"):
        alt_path = clean_path[3:]
        alt_upstream = f"http://127.0.0.1:{HERMES_PORT}/{alt_path}"
        logger.info(f"[HERMES FALLBACK] Trying path: {alt_upstream}")
        res_alt = await proxy_http_request(
            alt_upstream,
            request,
            default_prefix="/hermes",
            extra_headers=primary_headers,
        )
        if res_alt.status_code < 400:
            return res_alt

    if res.status_code == 401:
        key_headers = {
            "Authorization": f"Bearer {API_SERVER_KEY}",
            "X-API-Key": API_SERVER_KEY,
            "api-key": API_SERVER_KEY,
        }
        logger.info(f"[HERMES FALLBACK] Trying internal API_SERVER_KEY auth on {upstream}")
        res_key = await proxy_http_request(
            upstream,
            request,
            default_prefix="/hermes",
            extra_headers=key_headers,
        )
        if res_key.status_code < 400:
            return res_key

    if res.status_code == 200 and hasattr(res, "body") and b"HTTP 401" in res.body:
        logger.info(f"[HERMES RETRY] Retrying upstream call on 401 body content: {upstream}")
        await asyncio.sleep(0.3)
        res_retry = await proxy_http_request(
            upstream,
            request,
            default_prefix="/hermes",
            extra_headers=primary_headers,
        )
        if hasattr(res_retry, "body") and b"HTTP 401" not in res_retry.body:
            return res_retry

    return res
