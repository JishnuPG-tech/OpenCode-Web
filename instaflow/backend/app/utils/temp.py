import os
import shutil
import uuid
import logging
from backend.app.core.config import settings

logger = logging.getLogger("TempUtil")

def create_task_temp_dir() -> str:
    task_id = str(uuid.uuid4())
    path = os.path.join(settings.TEMP_DIR, task_id)
    os.makedirs(path, exist_ok=True)
    return path

def cleanup_task_temp_dir(path: str):
    if path and os.path.exists(path):
        try:
            shutil.rmtree(path, ignore_errors=True)
            logger.info(f"Cleaned up task directory: {path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup task directory {path}: {e}")
