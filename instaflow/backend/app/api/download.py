from typing import Optional
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from backend.app.models.request import DownloadRequest
from backend.app.models.response import ErrorCode
from backend.app.services.metadata_service import MetadataService
from backend.app.services.download_service import DownloadService
from backend.app.services.stream_service import StreamService
from backend.app.services.cleanup_service import CleanupService
from backend.app.utils.temp import create_task_temp_dir
from backend.app.utils.media import is_valid_instagram_url

router = APIRouter()

@router.get("/download")
def download_get(
    background_tasks: BackgroundTasks,
    url: str = Query(...),
    item: Optional[int] = Query(None)
):
    if not is_valid_instagram_url(url):
        raise HTTPException(
            status_code=400,
            detail={"success": False, "error_code": ErrorCode.INVALID_URL.value, "message": "Invalid Instagram URL format"}
        )

    task_dir = create_task_temp_dir()
    background_tasks.add_task(CleanupService.cleanup_task, task_dir)

    try:
        raw_meta = MetadataService.fetch_metadata(url)
        entries = raw_meta.get("entries") or []
        item_entry = None
        
        if entries:
            idx = (item - 1) if (item and 0 < item <= len(entries)) else 0
            item_entry = entries[idx]
        else:
            item_entry = raw_meta

        filepath = DownloadService.download_item(
            url=url,
            task_dir=task_dir,
            item_index=item,
            item_entry=item_entry
        )
        
        return StreamService.create_streaming_response(filepath)

    except ValueError as ve:
        CleanupService.cleanup_task(task_dir)
        raise HTTPException(
            status_code=422,
            detail={"success": False, "error_code": ErrorCode.VALIDATION_FAILED.value, "message": str(ve)}
        )
    except Exception as e:
        CleanupService.cleanup_task(task_dir)
        raise HTTPException(
            status_code=500,
            detail={"success": False, "error_code": ErrorCode.DOWNLOAD_FAILED.value, "message": str(e)}
        )

@router.post("/download")
def download_post(req: DownloadRequest, background_tasks: BackgroundTasks):
    return download_get(background_tasks=background_tasks, url=req.url, item=req.item)
