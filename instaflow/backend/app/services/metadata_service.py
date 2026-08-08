import os
import sys
import json
import subprocess
import logging
from typing import Dict, Any, List
from backend.app.core.config import settings
from backend.app.utils.media import normalize_instagram_url
from backend.app.models.response import ErrorCode

logger = logging.getLogger("MetadataService")

class MetadataService:
    @staticmethod
    def get_ig_headers() -> List[str]:
        args = [
            "--add-header", "X-IG-App-ID:936619743392459",
            "--add-header", "User-Agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "--add-header", "Referer:https://www.instagram.com/",
            "--allow-unplayable-formats",
            "--ignore-no-formats-error"
        ]
        if os.path.exists(settings.COOKIES_FILE) and os.path.getsize(settings.COOKIES_FILE) > 0:
            args.extend(["--cookies", settings.COOKIES_FILE])
        return args

    @classmethod
    def fetch_metadata(cls, url: str) -> Dict[str, Any]:
        norm_url = normalize_instagram_url(url)
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--dump-single-json",
            "-4"
        ] + cls.get_ig_headers() + [norm_url]

        logger.info(f"Fetching yt-dlp metadata for {norm_url}")
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            err = res.stderr
            logger.error(f"yt-dlp metadata extraction failed: {err}")
            if "No video formats found" in err or "Login required" in err:
                raise ValueError(ErrorCode.LOGIN_REQUIRED.value)
            raise RuntimeError(f"{ErrorCode.DOWNLOAD_FAILED.value}: {err[:200]}")

        try:
            return json.loads(res.stdout)
        except Exception as e:
            raise RuntimeError(f"{ErrorCode.INTERNAL_ERROR.value}: Failed to parse JSON metadata: {e}")
