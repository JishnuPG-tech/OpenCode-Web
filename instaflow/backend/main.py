import os
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query, Body, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, HttpUrl

from backend.config import HOST, PORT, COOKIES_FILE, DOWNLOADS_DIR
from backend.extractor import (
    InstagramUrlValidator,
    parse_and_inject_cookies,
    fetch_metadata,
    download_media_item
)

app = FastAPI(
    title="InstaFlow High-Performance Downloader API",
    description="Production-ready FastAPI backend for Instagram Reels, Posts & Carousels",
    version="2.0.0"
)

# Enable CORS for cross-platform access (Android apps, Web, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize pre-configured session cookies if available
if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 0:
    print(f"[InstaFlow API] Loaded active session cookies from {COOKIES_FILE}")

# Pydantic Schemas
class AnalyzeRequest(BaseModel):
    url: str

class CookieInjectRequest(BaseModel):
    cookies: str

class DownloadRequest(BaseModel):
    url: str
    playlist_index: Optional[int] = None

@app.get("/")
def read_root():
    cookies_active = os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 0
    return {
        "app": "InstaFlow API",
        "status": "online",
        "version": "2.0.0",
        "cookies_active": cookies_active,
        "engine": "yt-dlp + FFmpeg + FastAPI"
    }

@app.post("/api/v1/cookies")
def inject_cookies(req: CookieInjectRequest):
    try:
        content, count = parse_and_inject_cookies(req.cookies)
        return {
            "status": "success",
            "message": f"Successfully injected {count} session cookies",
            "cookies_file": COOKIES_FILE,
            "cookie_count": count
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to inject cookies: {str(e)}")

@app.get("/api/v1/cookies/status")
def cookie_status():
    exists = os.path.exists(COOKIES_FILE)
    size = os.path.getsize(COOKIES_FILE) if exists else 0
    return {
        "cookies_active": exists and size > 0,
        "size_bytes": size,
        "path": COOKIES_FILE
    }

@app.post("/api/v1/analyze")
def analyze_url(req: AnalyzeRequest):
    val = InstagramUrlValidator.parse_url(req.url)
    if not val["is_valid"]:
        raise HTTPException(status_code=400, detail="Invalid Instagram URL format")
    
    try:
        meta = fetch_metadata(req.url)
        
        # Build clean response payload
        uploader = meta.get("uploader") or meta.get("channel") or "Instagram User"
        title = meta.get("title") or meta.get("description") or f"Post by {uploader}"
        thumbnails = [t.get("url") for t in meta.get("thumbnails", []) if t.get("url")]
        
        entries = meta.get("entries") or []
        items = []
        
        if entries:
            for idx, entry in enumerate(entries):
                vcodec = entry.get("vcodec")
                is_video = (vcodec and vcodec != "none") or (entry.get("duration") or 0) > 0
                items.append({
                    "index": idx + 1,
                    "id": entry.get("id"),
                    "title": entry.get("title") or f"Item {idx + 1}",
                    "is_video": is_video,
                    "thumbnail": entry.get("thumbnail") or (entry.get("thumbnails") or [{}])[-1].get("url"),
                    "duration": entry.get("duration") or 0
                })
        else:
            vcodec = meta.get("vcodec")
            is_video = (vcodec and vcodec != "none") or (meta.get("duration") or 0) > 0
            items.append({
                "index": 1,
                "id": meta.get("id"),
                "title": title,
                "is_video": is_video,
                "thumbnail": meta.get("thumbnail") or (thumbnails[-1] if thumbnails else None),
                "duration": meta.get("duration") or 0
            })
            
        return {
            "status": "success",
            "url": req.url,
            "type": val["type"],
            "id": meta.get("id"),
            "uploader": uploader,
            "title": title,
            "item_count": len(items),
            "items": items,
            "raw_metadata": meta
        }
    except Exception as e:
        detail = str(e)
        if "LOGIN_REQUIRED" in detail:
            raise HTTPException(status_code=401, detail="Instagram session cookie expired or login required for this post.")
        raise HTTPException(status_code=500, detail=detail)

@app.get("/api/v1/download")
def download_get(url: str = Query(...), index: Optional[int] = Query(None)):
    try:
        meta = fetch_metadata(url)
        item_entry = None
        entries = meta.get("entries") or []
        
        if entries and index and index > 0 and index <= len(entries):
            item_entry = entries[index - 1]
        elif not entries:
            item_entry = meta

        filepath = download_media_item(url, playlist_index=index, item_entry=item_entry)
        if not filepath or not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail="File download failed or file not found")
        
        filename = os.path.basename(filepath)
        media_type = "image/jpeg" if filename.lower().endswith((".jpg", ".jpeg", ".webp", ".png")) else "video/mp4"
        
        return FileResponse(
            path=filepath,
            filename=filename,
            media_type=media_type
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/download")
def download_post(req: DownloadRequest):
    return download_get(url=req.url, index=req.playlist_index)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
