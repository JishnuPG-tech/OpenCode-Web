import os
from fastapi import APIRouter
from backend.app.core.config import settings
from backend.app.services.ffmpeg_service import FFmpegService

router = APIRouter()

@router.get("/health")
def health_check():
    cookies_active = os.path.exists(settings.COOKIES_FILE) and os.path.getsize(settings.COOKIES_FILE) > 0
    ffmpeg_available = FFmpegService.get_ffmpeg_binary() is not None
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "cookies_active": cookies_active,
        "ffmpeg_available": ffmpeg_available,
        "temp_dir": settings.TEMP_DIR
    }
