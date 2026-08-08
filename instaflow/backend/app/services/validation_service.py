import os
import logging
from backend.app.services.ffmpeg_service import FFmpegService
from backend.app.models.response import ErrorCode

logger = logging.getLogger("ValidationService")

class ValidationService:
    @staticmethod
    def validate_file(filepath: str, is_video: bool = False) -> None:
        if not filepath or not os.path.exists(filepath):
            raise ValueError(f"{ErrorCode.VALIDATION_FAILED.value}: File does not exist: {filepath}")

        size = os.path.getsize(filepath)
        if size == 0:
            os.remove(filepath)
            raise ValueError(f"{ErrorCode.VALIDATION_FAILED.value}: File size is 0 bytes")

        if is_video:
            if not FFmpegService.verify_media_file(filepath):
                os.remove(filepath)
                raise ValueError(f"{ErrorCode.VALIDATION_FAILED.value}: Corrupted video file or missing media stream")

        logger.info(f"File validation passed: {filepath} ({size} bytes)")
