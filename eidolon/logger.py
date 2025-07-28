"""Shared logging module for Lambda functions."""

import json
import logging
import sys
from datetime import datetime, timezone
from functools import wraps

from eidolon.environment import AWS_EXECUTION_ENV, LOG_LEVEL


def get_logger(name: str, level=None):
    """Get a configured logger instance.

    Args:
        name: Logger name (typically __name__)
        level: Optional logging level

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Set logging level from environment or parameter
    log_level = level or LOG_LEVEL
    logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Create console handler
    handler = logging.StreamHandler(sys.stdout)

    # Use JSON formatter in Lambda, simple formatter locally
    if AWS_EXECUTION_ENV:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))

    logger.addHandler(handler)
    logger.propagate = False

    return logger


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging in CloudWatch."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add extra fields if present
        for key, value in record.__dict__.items():
            if key not in [
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "thread",
                "threadName",
                "exc_info",
                "exc_text",
                "stack_info",
            ]:
                log_obj[key] = value

        # Add exception info if present
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj, default=str)


def log_duration(func):
    """Decorator to log function execution duration."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        logger = get_logger(func.__module__)
        start_time = datetime.now(timezone.utc)

        try:
            result = func(*args, **kwargs)
            duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            logger.debug(f"Function completed: {func.__name__}", extra={"function": func.__name__, "duration_ms": duration_ms})
            return result
        except Exception as err:
            duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            logger.error(
                f"Function failed: {func.__name__}",
                extra={"function": func.__name__, "duration_ms": duration_ms, "error": str(err)},
                exc_info=True,
            )
            raise

    return wrapper
