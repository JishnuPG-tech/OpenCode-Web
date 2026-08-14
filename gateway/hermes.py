"""
Hermes Agent Router for FastAPI Gateway
========================================
Proxies Hermes Agent endpoints to internal server on 127.0.0.1:8642:
  - /hermes/v1/models          -> 8642 (OpenAI-compatible models catalog)
  - /hermes/v1/chat/completions -> 8642 (OpenAI-compatible agent completions)
  - /hermes/health             -> 8642 (health check)
  - /hermes, /hermes/v1         -> JSON status & discovery response
"""

import os
import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from gateway.utils import proxy_http_request

logger = logging.getLogger("GatewayHermes")
router = APIRouter(tags=["hermes"])

HERMES_PORT = 8642
API_SERVER_KEY = (
    os.getenv("API_SERVER_KEY")
    or os.getenv("HERMES_GATEWAY_API_KEY")
    or os.getenv("HERMES_API_KEY_SECRET")
    or os.getenv("API_KEY_SECRET")
    or os.getenv("INITIAL_PASSWORD")
    or "hermes_secret_key"
)


@router.api_route("/hermes", methods=["GET", "HEAD"])
@router.api_route("/hermes/", methods=["GET", "HEAD"])
@router.api_route("/hermes/v1", methods=["GET", "HEAD"])
@router.api_route("/hermes/v1/", methods=["GET", "HEAD"])
async def hermes_status(request: Request):
    """Return friendly JSON status for root Hermes API endpoints."""
    return JSONResponse(
        content={
            "service": "Hermes Agent Framework",
            "status": "online",
            "llm_backend": "OmniRoute AI Gateway (:20129)",
            "api_endpoint": "https://jishnupg-opencode-cli.hf.space/hermes/v1",
            "endpoints": [
                "/hermes/v1/models",
                "/hermes/v1/chat/completions",
                "/hermes/health",
            ],
            "capabilities": [
                "web_search",
                "web_extract",
                "browser_automation",
                "persistent_memory",
                "self_improving_skills",
            ],
        },
        status_code=200,
    )


@router.api_route(
    "/hermes/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
)
async def hermes_proxy(path: str, request: Request):
    clean_path = path.lstrip("/")
    upstream = f"http://127.0.0.1:{HERMES_PORT}/{clean_path}"
    logger.info(f"[HERMES] /{clean_path} -> :{HERMES_PORT}")

    primary_headers = {
        "Authorization": f"Bearer {API_SERVER_KEY}",
        "X-API-Key": API_SERVER_KEY,
        "api-key": API_SERVER_KEY,
    }

    res = await proxy_http_request(
        upstream,
        request,
        default_prefix="/hermes",
        extra_headers=primary_headers,
    )

    # Stage 2: If 404 or 401 on /v1/..., try stripping /v1/ prefix
    if res.status_code in (404, 401) and clean_path.startswith("v1/"):
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

    # Stage 3: If 401 persists, fallback to explicit internal API_SERVER_KEY Bearer auth
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

    # Stage 4: If 200 returned but body has 401 error string, retry once after short delay
    if res.status_code == 200 and hasattr(res, "body") and b"HTTP 401" in res.body:
        import asyncio
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


