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
    upstream = f"http://127.0.0.1:{HERMES_PORT}/{path}"
    logger.info(f"[HERMES] /{path} -> :{HERMES_PORT}")
    extra_headers = {"Authorization": f"Bearer {API_SERVER_KEY}"}
    return await proxy_http_request(
        upstream,
        request,
        default_prefix="/hermes",
        extra_headers=extra_headers,
    )


