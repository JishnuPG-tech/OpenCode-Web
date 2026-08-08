import os
import sys
import re
import json
import shutil
import subprocess
import urllib.request
import logging
from typing import Dict, Any, Optional, List, Tuple
from backend.config import DOWNLOADS_DIR, COOKIES_FILE

logger = logging.getLogger("InstaFlowExtractor")
logging.basicConfig(level=logging.INFO)

# ----------------------------------------------------
# 1. URL NORMALIZER & VALIDATOR
# ----------------------------------------------------
class InstagramUrlNormalizer:
    @staticmethod
    def normalize(raw_url: str) -> str:
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

class InstagramUrlValidator:
    REEL_PATTERN = re.compile(r"https?://(?:www\.)?instagram\.com/(?:reel|reels|tv)/([A-Za-z0-9_-]+)", re.I)
    POST_PATTERN = re.compile(r"https?://(?:www\.)?instagram\.com/p/([A-Za-z0-9_-]+)", re.I)
    STORY_PATTERN = re.compile(r"https?://(?:www\.)?instagram\.com/stories/([A-Za-z0-9._-]+)/(\d+)", re.I)

    @classmethod
    def parse_url(cls, url: str) -> Dict[str, Any]:
        trimmed = InstagramUrlNormalizer.normalize(url)
        if not trimmed:
            return {"is_valid": False, "type": "UNKNOWN", "raw": url}
        
        m_reel = cls.REEL_PATTERN.search(trimmed)
        if m_reel:
            return {"is_valid": True, "type": "REEL", "shortcode": m_reel.group(1), "raw": trimmed}
        
        m_post = cls.POST_PATTERN.search(trimmed)
        if m_post:
            return {"is_valid": True, "type": "POST", "shortcode": m_post.group(1), "raw": trimmed}
        
        m_story = cls.STORY_PATTERN.search(trimmed)
        if m_story:
            return {"is_valid": True, "type": "STORY", "username": m_story.group(1), "shortcode": m_story.group(2), "raw": trimmed}
        
        return {"is_valid": False, "type": "UNKNOWN", "raw": trimmed}

# ----------------------------------------------------
# 2. SMART COOKIE PARSER & INJECTOR
# ----------------------------------------------------
def parse_and_inject_cookies(raw_text: str) -> Tuple[str, int]:
    text = raw_text.strip()
    if not text:
        return "", 0
        
    lines = ["# Netscape HTTP Cookie File", "# http://curl.haxx.se/rfc/cookie_spec.html\n"]
    
    # JSON array check
    if text.startswith("[") and text.endswith("]"):
        try:
            arr = json.loads(text)
            count = 0
            for item in arr:
                name = item.get("name")
                value = item.get("value")
                domain = item.get("domain", ".instagram.com")
                if name and value:
                    lines.append(f"{domain}\tTRUE\t/\tTRUE\t2147483647\t{name}\t{value}")
                    count += 1
            content = "\n".join(lines)
            with open(COOKIES_FILE, "w", encoding="utf-8") as f:
                f.write(content)
            return content, count
        except Exception as e:
            logger.warning(f"Failed to parse JSON cookies: {e}")

    # Header style check
    if text.lower().startswith("cookie:"):
        text = text[7:].strip()
        
    pairs = text.split(";")
    count = 0
    for p in pairs:
        if "=" in p:
            parts = p.strip().split("=", 1)
            k, v = parts[0].strip(), parts[1].strip()
            if k and v:
                lines.append(f".instagram.com\tTRUE\t/\tTRUE\t2147483647\t{k}\t{v}")
                count += 1
                
    if count == 0 and len(text) > 10:
        lines.append(f".instagram.com\tTRUE\t/\tTRUE\t2147483647\tsessionid\t{text}")
        count = 1
        
    content = "\n".join(lines)
    with open(COOKIES_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    return content, count

# ----------------------------------------------------
# 3. EXTRACTION & DOWNLOAD ENGINE
# ----------------------------------------------------
def find_ffmpeg_path() -> Optional[str]:
    ffmpeg_bin = shutil.which("ffmpeg")
    return ffmpeg_bin if ffmpeg_bin else None

def get_ig_headers() -> List[str]:
    args = [
        "--add-header", "X-IG-App-ID:936619743392459",
        "--add-header", "User-Agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "--add-header", "Referer:https://www.instagram.com/",
        "--allow-unplayable-formats",
        "--ignore-no-formats-error"
    ]
    if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 0:
        args.extend(["--cookies", COOKIES_FILE])
    return args

def fetch_metadata(url: str) -> Dict[str, Any]:
    norm_url = InstagramUrlNormalizer.normalize(url)
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--dump-single-json",
        "-4"
    ] + get_ig_headers() + [norm_url]
    
    logger.info(f"[Extractor] Extracting metadata for: {norm_url}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        err = res.stderr
        logger.error(f"[Extractor] Metadata fetch failed: {err}")
        if "No video formats found" in err or "Login required" in err:
            raise Exception("LOGIN_REQUIRED_OR_PRIVATE")
        raise Exception(f"yt-dlp extraction failed: {err[:300]}")
    
    return json.loads(res.stdout)

def download_media_item(
    url: str,
    playlist_index: Optional[int] = None,
    item_entry: Optional[Dict[str, Any]] = None,
    quality: Optional[int] = None,
    audio_only: bool = False,
    merge_photo_audio: bool = False
) -> str:
    norm_url = InstagramUrlNormalizer.normalize(url)
    ffmpeg_path = find_ffmpeg_path()

    # Strategy 1: Photo / Direct CDN Image Download
    if item_entry and not audio_only and not merge_photo_audio:
        img_url = item_entry.get("thumbnail") or item_entry.get("url")
        if not img_url and item_entry.get("thumbnails"):
            img_url = item_entry["thumbnails"][-1].get("url")
            
        vcodec = item_entry.get("vcodec")
        acodec = item_entry.get("acodec")
        duration = item_entry.get("duration") or 0.0
        
        # Pure Photo Post check
        if img_url and (not vcodec or vcodec == "none") and (not acodec or acodec == "none") and duration == 0.0:
            logger.info(f"[Extractor] Photo item detected. Executing direct high-res CDN download.")
            ext = "jpg"
            if ".webp" in img_url.lower(): ext = "webp"
            elif ".png" in img_url.lower(): ext = "png"
            
            filename = f"InstaFlow_{item_entry.get('id', 'photo')}.{ext}"
            filepath = os.path.join(DOWNLOADS_DIR, filename)
            
            req = urllib.request.Request(img_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Referer": "https://www.instagram.com/"
            })
            with urllib.request.urlopen(req) as resp, open(filepath, "wb") as f:
                f.write(resp.read())
            
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                return filepath

    # Strategy 1.5: Photo + Music Merge (Single-Frame MP4)
    if merge_photo_audio and item_entry and ffmpeg_path:
        img_url = item_entry.get("thumbnail") or item_entry.get("url")
        if not img_url and item_entry.get("thumbnails"):
            img_url = item_entry["thumbnails"][-1].get("url")

        if img_url:
            logger.info(f"[Extractor] Merging photo and music into MP4...")
            photo_path = os.path.join(DOWNLOADS_DIR, f"temp_photo_{item_entry.get('id')}.jpg")
            audio_path = os.path.join(DOWNLOADS_DIR, f"temp_audio_{item_entry.get('id')}.m4a")
            output_path = os.path.join(DOWNLOADS_DIR, f"InstaFlow_{item_entry.get('id')}_music.mp4")

            try:
                # 1. Download Photo
                req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.instagram.com/"})
                with urllib.request.urlopen(req) as resp, open(photo_path, "wb") as f:
                    f.write(resp.read())

                # 2. Download Audio via yt-dlp
                audio_cmd = [sys.executable, "-m", "yt_dlp", "-4", "-f", "bestaudio", "-o", audio_path]
                if playlist_index: audio_cmd.extend(["--playlist-items", str(playlist_index)])
                audio_cmd.extend(get_ig_headers())
                audio_cmd.append(norm_url)
                subprocess.run(audio_cmd, capture_output=True)

                # 3. Merge via FFmpeg
                # cmd: ffmpeg -loop 1 -i photo.jpg -i music.m4a -c:v libx264 -tune stillimage -c:a aac -b:a 192k -pix_fmt yuv420p -shortest output.mp4
                merge_cmd = [
                    ffmpeg_path, "-y", "-loop", "1", "-i", photo_path, "-i", audio_path,
                    "-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac", "-b:a", "192k",
                    "-pix_fmt", "yuv420p", "-shortest", output_path
                ]
                subprocess.run(merge_cmd, capture_output=True)

                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    return output_path
            finally:
                if os.path.exists(photo_path): os.remove(photo_path)
                if os.path.exists(audio_path): os.remove(audio_path)

    # Strategy 2: Video Reel Download via yt-dlp + FFmpeg Audio Merge
    out_tmpl = os.path.join(DOWNLOADS_DIR, "InstaFlow_%(title).100s.%(ext)s")
    cmd = [sys.executable, "-m", "yt_dlp", "-4", "-o", out_tmpl]
    
    ffmpeg_path = find_ffmpeg_path()
    if ffmpeg_path:
        cmd.extend(["--ffmpeg-location", os.path.dirname(ffmpeg_path)])
    
    cmd.extend(["--merge-output-format", "mp4"])

    if audio_only:
        cmd.extend(["-f", "bestaudio/best"])
        cmd.append("-x")
    else:
        # Quality mapping
        res_map = {1: 2160, 2: 1440, 3: 1080, 4: 720, 5: 480, 6: 360}
        limit = res_map.get(quality)

        if limit:
            # Try to get best video up to the limit, then merge with best audio
            fmt_str = f"bestvideo[height<={limit}]+bestaudio/best[height<={limit}]/best"
            cmd.extend(["-f", fmt_str])
        elif quality == 7: # Lowest
            cmd.extend(["-f", "worstvideo+worstaudio/worst"])
        else: # Best (0) or None
            cmd.extend(["-f", "bestvideo+bestaudio/best"])
    
    if playlist_index and playlist_index > 0:
        cmd.extend(["--playlist-items", str(playlist_index)])
    else:
        cmd.append("--no-playlist")
    
    cmd.extend(get_ig_headers())
    cmd.append(norm_url)
    
    logger.info(f"[Extractor] Executing yt-dlp Video Download: {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    
    # Fallback to auto format if explicit quality selector failed
    if res.returncode != 0:
        logger.warning(f"[Extractor] Explicit quality selector failed. Retrying with default selector.")
        cmd_fallback = [sys.executable, "-m", "yt_dlp", "-4", "-o", out_tmpl]
        if ffmpeg_path:
            cmd_fallback.extend(["--ffmpeg-location", os.path.dirname(ffmpeg_path)])
        if audio_only:
            cmd_fallback.extend(["-f", "bestaudio/best", "-x"])
        if playlist_index and playlist_index > 0:
            cmd_fallback.extend(["--playlist-items", str(playlist_index)])
        else:
            cmd_fallback.append("--no-playlist")
        cmd_fallback.extend(get_ig_headers())
        cmd_fallback.append(norm_url)
        res = subprocess.run(cmd_fallback, capture_output=True, text=True)
        if res.returncode != 0:
            raise Exception(f"Download failed: {res.stderr[:300]}")
    
    # Locate output file
    files = [
        os.path.join(DOWNLOADS_DIR, f)
        for f in os.listdir(DOWNLOADS_DIR)
        if not f.endswith(".part") and not f.endswith(".ytdl") and not f.endswith(".tmp")
    ]
    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    if not files or os.path.getsize(files[0]) == 0:
        raise Exception("Download succeeded but no output file was produced.")
    
    return files[0]
