from typing import Optional, List, Any, Dict
from enum import Enum
from pydantic import BaseModel

class ErrorCode(str, Enum):
    INVALID_URL = "InvalidURL"
    PRIVATE_POST = "PrivatePost"
    LOGIN_REQUIRED = "LoginRequired"
    RATE_LIMITED = "RateLimited"
    NOT_FOUND = "NotFound"
    UNSUPPORTED_MEDIA = "UnsupportedMedia"
    DOWNLOAD_FAILED = "DownloadFailed"
    MERGE_FAILED = "MergeFailed"
    VALIDATION_FAILED = "ValidationFailed"
    STREAMING_FAILED = "StreamingFailed"
    INTERNAL_ERROR = "InternalError"

class MediaItem(BaseModel):
    index: int
    id: str
    title: str
    is_video: bool
    thumbnail: Optional[str] = None
    duration: float = 0.0

class AnalyzeResponse(BaseModel):
    success: bool
    type: str
    author: str
    title: str
    thumbnail: Optional[str] = None
    items: List[MediaItem]
    raw_metadata: Optional[Dict[str, Any]] = None

class ErrorResponse(BaseModel):
    success: bool = False
    error_code: ErrorCode
    message: str
    request_id: Optional[str] = None
