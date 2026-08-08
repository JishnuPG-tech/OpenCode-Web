import os
import logging
from typing import Generator
from fastapi.responses import StreamingResponse
from backend.app.core.config import settings

logger = logging.getLogger("StreamService")

class StreamService:
    @staticmethod
    def file_chunk_generator(filepath: str, chunk_size: int = settings.CHUNK_SIZE) -> Generator[bytes, None, None]:
        with open(filepath, "rb") as f:
            while chunk := f.read(chunk_size):
                yield chunk

    @classmethod
    def create_streaming_response(cls, filepath: str) -> StreamingResponse:
        filename = os.path.basename(filepath)
        file_size = os.path.getsize(filepath)
        media_type = "image/jpeg" if filename.lower().endswith((".jpg", ".jpeg", ".webp", ".png")) else "video/mp4"
        
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes"
        }
        
        logger.info(f"Streaming file {filename} ({file_size} bytes, type: {media_type})")
        return StreamingResponse(
            cls.file_chunk_generator(filepath),
            media_type=media_type,
            headers=headers
        )
