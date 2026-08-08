from typing import Dict, Any, List
from backend.app.models.response import AnalyzeResponse, MediaItem

class InstagramService:
    @staticmethod
    def parse_metadata(url: str, meta: Dict[str, Any]) -> AnalyzeResponse:
        uploader = meta.get("uploader") or meta.get("channel") or "Instagram User"
        raw_title = (meta.get("title") or meta.get("description") or "").strip()
        
        vcodec = meta.get("vcodec")
        duration = float(meta.get("duration") or 0.0)
        is_vid = bool((vcodec and vcodec != "none") or duration > 0.0)
        
        if not raw_title or raw_title.startswith("Video by ") or raw_title.startswith("Post by "):
            title = f"Video by {uploader}" if is_vid else f"Post by {uploader}"
        else:
            title = raw_title
        thumbnails = [t.get("url") for t in meta.get("thumbnails", []) if t.get("url")]
        
        entries = meta.get("entries") or []
        items: List[MediaItem] = []
        
        post_type = "single"
        if entries:
            post_type = "carousel"
            for idx, entry in enumerate(entries):
                vcodec = entry.get("vcodec")
                is_vid = bool((vcodec and vcodec != "none") or (entry.get("duration") or 0) > 0)
                thumb = entry.get("thumbnail") or (entry.get("thumbnails") or [{}])[-1].get("url")
                items.append(MediaItem(
                    index=idx + 1,
                    id=str(entry.get("id", idx + 1)),
                    title=entry.get("title") or f"Item {idx + 1}",
                    is_video=is_vid,
                    thumbnail=thumb,
                    duration=float(entry.get("duration") or 0.0)
                ))
        else:
            vcodec = meta.get("vcodec")
            is_vid = bool((vcodec and vcodec != "none") or (meta.get("duration") or 0) > 0)
            if "reel" in url.lower() or "tv" in url.lower():
                post_type = "reel"
            else:
                post_type = "video" if is_vid else "photo"

            thumb = meta.get("thumbnail") or (thumbnails[-1] if thumbnails else None)
            items.append(MediaItem(
                index=1,
                id=str(meta.get("id", "1")),
                title=title,
                is_video=is_vid,
                thumbnail=thumb,
                duration=float(meta.get("duration") or 0.0)
            ))

        return AnalyzeResponse(
            success=True,
            type=post_type,
            author=uploader,
            title=title,
            thumbnail=items[0].thumbnail if items else None,
            items=items,
            raw_metadata=meta
        )
