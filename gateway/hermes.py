"""
Hermes Agent Router for FastAPI Gateway
========================================
Proxies Hermes Agent endpoints to internal server on 127.0.0.1:8642:
  - /hermes/v1/*     -> 8642 (OpenAI-compatible agent API)
  - /hermes/health   -> 8642 (health check)
  - /hermes/         -> 8642 (Hermes root / status)
"""

import logging
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from gateway.utils import proxy_http_request

logger = logging.getLogger("GatewayHermes")
router = APIRouter(tags=["hermes"])

HERMES_PORT = 8642


@router.api_route("/hermes", methods=["GET", "HEAD"])
@router.api_route("/hermes/", methods=["GET", "HEAD"])
async def hermes_root(request: Request):
    try:
        return await proxy_http_request(
            f"http://127.0.0.1:{HERMES_PORT}/",
            request,
            default_prefix="/hermes",
        )
    except Exception:
        return JSONResponse(
            content={"service": "hermes-agent", "status": "starting"},
            status_code=503,
        )


@router.api_route(
    "/hermes/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
)
async def hermes_proxy(path: str, request: Request):
    upstream = f"http://127.0.0.1:{HERMES_PORT}/{path}"
    logger.info(f"[HERMES] /{path} -> :{HERMES_PORT}")
    return await proxy_http_request(
        upstream,
        request,
        default_prefix="/hermes",
    )
