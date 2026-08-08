import logging
from fastapi import APIRouter, Request, Response
from gateway.utils import proxy_http_request

logger = logging.getLogger("gateway.instaflow")

INSTAFLOW_TARGET = "http://127.0.0.1:8090"
router = APIRouter()

@router.api_route("/instaflow", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
@router.api_route("/instaflow/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
async def instaflow_proxy(request: Request, path: str = ""):
    """
    Proxies all /instaflow requests directly to the InstaFlow FastAPI backend (port 8090).
    Strips the '/instaflow' prefix so InstaFlow receives standard endpoints like /, /api/v1/analyze, etc.
    """
    subpath = f"/{path}" if path else "/"
    return await proxy_http_request(f"{INSTAFLOW_TARGET}{subpath}", request, default_prefix="/instaflow")
