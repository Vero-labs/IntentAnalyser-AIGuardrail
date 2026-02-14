import logging
import json
import sys
from typing import Any, Dict

class JSONFormatter(logging.Formatter):
    """
    Formatter that outputs JSON strings after parsing the LogRecord.
    """
    def format(self, record: logging.LogRecord) -> str:
        log_record: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "module": record.module,
            "line": record.lineno,
        }
        
        # Add extra fields if available
        if hasattr(record, "request_id"):
            log_record["request_id"] = record.request_id
            
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_record)

def setup_logging(level: str = "INFO"):
    """
    Configures the root logger to use JSON formatting.
    """
    logger = logging.getLogger()
    logger.setLevel(level)
    
    # Remove existing handlers to avoid duplication
    if logger.handlers:
        logger.handlers.clear()
        
    handler = logging.StreamHandler(sys.stdout)
    formatter = JSONFormatter()
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    
    # Set uvicorn loggers to use our handler as well, or propagate
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.error").handlers = []
    
    # We want uvicorn to propagate to root
    logging.getLogger("uvicorn").propagate = True
    logging.getLogger("uvicorn.access").propagate = True
    logging.getLogger("uvicorn.error").propagate = True
