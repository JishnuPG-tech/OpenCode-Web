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
    item: Optional[int] = Query(None),
    index: Optional[int] = Query(None),
    item_index: Optional[int] = Query(None),
    format: Optional[str] = Query(None),
    quality: Optional[str] = Query(None),
    res: Optional[str] = Query(None),
    resolution: Optional[str] = Query(None),
    audio_only: Optional[bool] = Query(False),
    audioOnly: Optional[bool] = Query(False),
    extract_audio: Optional[bool] = Query(False),
    mux_audio: Optional[bool] = Query(False),
    merge_photo_audio: Optional[bool] = Query(False),
    mergePhotoAudio: Optional[bool] = Query(False)
):
    if not is_valid_instagram_url(url):
        raise HTTPException(
            status_code=400,
            detail={"success": False, "error_code": ErrorCode.INVALID_URL.value, "message": "Invalid Instagram URL format"}
        )

    task_dir = create_task_temp_dir()
    background_tasks.add_task(CleanupService.cleanup_task, task_dir)

    target_item = item if item is not None else (index if index is not None else item_index)
    raw_fmt = format or quality or res or resolution
    target_format = str(raw_fmt).strip() if raw_fmt is not None else None
    is_audio = bool(audio_only or audioOnly or extract_audio)
    is_mux = bool(mux_audio or merge_photo_audio or mergePhotoAudio)

    item_entry = None
    try:
        raw_meta = MetadataService.fetch_metadata(url)
        entries = raw_meta.get("entries") or []
        if entries:
            idx = (target_item - 1) if (target_item and 0 < target_item <= len(entries)) else 0
            item_entry = entries[idx]
        else:
            item_entry = raw_meta
    except Exception as meta_err:
        import logging
        logging.getLogger("DownloadAPI").warning(f"Metadata pre-fetch failed ({meta_err}). Proceeding directly to download...")

    try:
        filepath = DownloadService.download_item(
            url=url,
            task_dir=task_dir,
            item_index=target_item,
            item_entry=item_entry,
            requested_format=target_format,
            audio_only=is_audio,
            mux_audio=is_mux
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
    target_item = req.item if req.item is not None else req.index
    target_format = req.format or req.quality
    is_audio = bool(req.audio_only)
    is_mux = bool(req.mux_audio or req.merge_photo_audio)
    return download_get(
        background_tasks=background_tasks,
        url=req.url,
        item=target_item,
        format=target_format,
        audio_only=is_audio,
        mux_audio=is_mux
    )
