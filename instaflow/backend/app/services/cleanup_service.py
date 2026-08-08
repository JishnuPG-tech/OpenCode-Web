import logging
from backend.app.utils.temp import cleanup_task_temp_dir

logger = logging.getLogger("CleanupService")

class CleanupService:
    @staticmethod
    def cleanup_task(task_dir: str):
        logger.info(f"Triggering automatic cleanup for task dir: {task_dir}")
        cleanup_task_temp_dir(task_dir)
