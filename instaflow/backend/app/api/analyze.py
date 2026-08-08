from fastapi import APIRouter, HTTPException
from backend.app.models.request import AnalyzeRequest
from backend.app.models.response import AnalyzeResponse, ErrorResponse, ErrorCode
from backend.app.services.metadata_service import MetadataService
from backend.app.services.instagram_service import InstagramService
from backend.app.utils.media import is_valid_instagram_url

router = APIRouter()

@router.post("/analyze", response_model=AnalyzeResponse)
def analyze_endpoint(req: AnalyzeRequest):
    if not is_valid_instagram_url(req.url):
        raise HTTPException(
            status_code=400,
            detail={"success": False, "error_code": ErrorCode.INVALID_URL.value, "message": "Invalid Instagram URL format"}
        )
    try:
        raw_meta = MetadataService.fetch_metadata(req.url)
        return InstagramService.parse_metadata(req.url, raw_meta)
    except ValueError as ve:
        raise HTTPException(
            status_code=401,
            detail={"success": False, "error_code": ErrorCode.LOGIN_REQUIRED.value, "message": str(ve)}
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"success": False, "error_code": ErrorCode.DOWNLOAD_FAILED.value, "message": str(e)}
        )
