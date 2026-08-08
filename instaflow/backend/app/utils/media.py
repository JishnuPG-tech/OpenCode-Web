import re

def normalize_instagram_url(raw_url: str) -> str:
    if not raw_url or not raw_url.strip():
        return ""
    trimmed = raw_url.strip()
    if "?" not in trimmed:
        return trimmed
    base, q = trimmed.split("?", 1)
    clean_params = [
        p for p in q.split("&")
        if not p.lower().startswith(("utm_", "igsh", "igshid", "fbclid", "share_id"))
    ]
    return f"{base}?{'&'.join(clean_params)}" if clean_params else base

REEL_PATTERN = re.compile(r"https?://(?:www\.)?instagram\.com/(?:reel|reels|tv)/([A-Za-z0-9_-]+)", re.I)
POST_PATTERN = re.compile(r"https?://(?:www\.)?instagram\.com/p/([A-Za-z0-9_-]+)", re.I)
STORY_PATTERN = re.compile(r"https?://(?:www\.)?instagram\.com/stories/([A-Za-z0-9._-]+)/(\d+)", re.I)

def is_valid_instagram_url(url: str) -> bool:
    norm = normalize_instagram_url(url)
    return bool(REEL_PATTERN.search(norm) or POST_PATTERN.search(norm) or STORY_PATTERN.search(norm))
