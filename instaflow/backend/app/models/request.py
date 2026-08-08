from typing import Optional
from pydantic import BaseModel, Field, HttpUrl

class AnalyzeRequest(BaseModel):
    url: str = Field(..., description="Instagram URL (Reel, Post, Carousel, Story)")

class DownloadRequest(BaseModel):
    url: str = Field(..., description="Instagram URL")
    item: Optional[int] = Field(None, description="Index of item for carousel posts (1-based)")
    index: Optional[int] = Field(None, description="Alias for item")
    format: Optional[str] = Field(None, description="Format or quality string (e.g. 1080p, 720p)")
    quality: Optional[str] = Field(None, description="Alias for format")
    audio_only: Optional[bool] = Field(False, description="Extract audio only")
    mux_audio: Optional[bool] = Field(False, description="Mux photo and audio into single-frame MP4")
    merge_photo_audio: Optional[bool] = Field(False, description="Alias for mux_audio")

class CookieInjectRequest(BaseModel):
    cookies: str = Field(..., description="Raw Netscape cookies or Cookie header string or JSON array")
