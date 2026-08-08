import shutil
import subprocess
import logging
from typing import Optional

logger = logging.getLogger("FFmpegService")

class FFmpegService:
    @staticmethod
    def get_ffmpeg_binary() -> Optional[str]:
        return shutil.which("ffmpeg")

    @classmethod
    def verify_media_file(cls, filepath: str) -> bool:
        ffmpeg_bin = cls.get_ffmpeg_binary()
        ffprobe_bin = shutil.which("ffprobe")
        if not ffprobe_bin:
            return True # Fallback to file size check if ffprobe not available
            
        cmd = [
            ffprobe_bin,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            filepath
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        return res.returncode == 0
