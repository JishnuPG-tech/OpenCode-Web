from typing import Optional
from pydantic import BaseModel, Field, HttpUrl

class AnalyzeRequest(BaseModel):
    url: str = Field(..., description="Instagram URL (Reel, Post, Carousel, Story)")

class DownloadRequest(BaseModel):
    url: str = Field(..., description="Instagram URL")
    item: Optional[int] = Field(None, description="Index of item for carousel posts (1-based)")

class CookieInjectRequest(BaseModel):
    cookies: str = Field(..., description="Raw Netscape cookies or Cookie header string or JSON array")
