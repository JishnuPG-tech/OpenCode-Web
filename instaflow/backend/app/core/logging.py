import logging
import sys
import uuid
from contextvars import ContextVar

request_id_ctx_var: ContextVar[str] = ContextVar("request_id", default="SYSTEM")

class RequestIDFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_ctx_var.get()
        return True

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [ReqID: %(request_id)s] %(name)s: %(message)s"
    )
    
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(RequestIDFilter())
    
    logger.handlers = [handler]
    return logger

logger = setup_logging()
