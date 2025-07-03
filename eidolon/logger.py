"""
Shared logging module for Lambda functions.

Provides consistent logging configuration and utilities for all Lambda functions
in the Eidolon Engine project.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from functools import wraps


class LambdaLogger:
    """Enhanced logger for AWS Lambda functions with structured logging support."""
    
    def __init__(self, name: str, level: str | None = None):
        """
        Initialize Lambda logger with consistent configuration.
        
        Args:
            name: Logger name (typically __name__ from the calling module)
            level: Logging level (default from LOG_LEVEL env var or INFO)
        """
        self.logger = logging.getLogger(name)
        
        # Set logging level from environment or parameter
        log_level = level or os.environ.get('LOG_LEVEL', 'INFO')
        self.logger.setLevel(getattr(logging, log_level.upper()))
        
        # Remove existing handlers to avoid duplicates
        self.logger.handlers.clear()
        
        # Create console handler with custom formatter
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(self._get_formatter())
        self.logger.addHandler(handler)
        
        # Prevent propagation to avoid duplicate logs
        self.logger.propagate = False
        
        # Store context for structured logging
        self.context: dict[str, any] = {}
    
    def _get_formatter(self) -> logging.Formatter:
        """Get appropriate formatter based on environment."""
        # Use JSON formatter for production, readable format for development
        if os.environ.get('AWS_EXECUTION_ENV'):
            # Running in Lambda environment
            return JsonFormatter()
        else:
            # Local development
            return logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
    
    def set_context(self, **kwargs) -> None:
        """
        Set persistent context for all subsequent log messages.
        
        Args:
            **kwargs: Context key-value pairs
        """
        self.context.update(kwargs)
    
    def clear_context(self) -> None:
        """Clear all persistent context."""
        self.context.clear()
    
    def _log_with_context(self, level: int, message: str, **kwargs) -> None:
        """
        Log message with context.
        
        Args:
            level: Logging level
            message: Log message
            **kwargs: Additional context for this log entry
        """
        extra = {
            'context': {**self.context, **kwargs}
        }
        self.logger.log(level, message, extra=extra)
    
    def debug(self, message: str, **kwargs) -> None:
        """Log debug message with optional context."""
        self._log_with_context(logging.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs) -> None:
        """Log info message with optional context."""
        self._log_with_context(logging.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs) -> None:
        """Log warning message with optional context."""
        self._log_with_context(logging.WARNING, message, **kwargs)
    
    def error(self, message: str, error: Exception | None = None, **kwargs) -> None:
        """
        Log error message with optional exception and context.
        
        Args:
            message: Error message
            error: Optional exception object
            **kwargs: Additional context
        """
        if error:
            kwargs['error_type'] = type(error).__name__
            kwargs['error_message'] = str(error)
        self._log_with_context(logging.ERROR, message, **kwargs)
    
    def critical(self, message: str, **kwargs) -> None:
        """Log critical message with optional context."""
        self._log_with_context(logging.CRITICAL, message, **kwargs)
    
    def log_lambda_event(self, event: dict[str, any], context: any) -> None:
        """
        Log Lambda invocation details.
        
        Args:
            event: Lambda event
            context: Lambda context
        """
        self.set_context(
            request_id=context.aws_request_id if hasattr(context, 'aws_request_id') else 'unknown',
            function_name=context.function_name if hasattr(context, 'function_name') else 'unknown',
            function_version=context.function_version if hasattr(context, 'function_version') else 'unknown'
        )
        
        # Log HTTP method and path if available (API Gateway event)
        if 'httpMethod' in event:
            self.info(
                "Lambda invocation",
                http_method=event.get('httpMethod'),
                path=event.get('path'),
                source_ip=event.get('requestContext', {}).get('identity', {}).get('sourceIp'),
                user_agent=event.get('headers', {}).get('User-Agent')
            )
        else:
            self.info("Lambda invocation", event_source=event.get('source', 'unknown'))
    
    def log_response(self, status_code: int, response_time_ms: float | None = None) -> None:
        """
        Log API response details.
        
        Args:
            status_code: HTTP status code
            response_time_ms: Response time in milliseconds
        """
        self.info(
            "Lambda response",
            status_code=status_code,
            response_time_ms=response_time_ms
        )


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging in CloudWatch."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_obj = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add context if available
        if hasattr(record, 'context'):
            log_obj['context'] = record.context
        
        # Add exception info if present
        if record.exc_info:
            log_obj['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_obj, default=str)


def get_logger(name: str, level: str | None = None) -> LambdaLogger:
    """
    Get a configured logger instance.
    
    Args:
        name: Logger name (typically __name__)
        level: Optional logging level
        
    Returns:
        Configured LambdaLogger instance
    """
    return LambdaLogger(name, level)


def log_duration(logger: LambdaLogger | None = None):
    """
    Decorator to log function execution duration.
    
    Args:
        logger: Logger instance (will create one if not provided)
        
    Returns:
        Decorated function
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal logger
            if logger is None:
                logger = get_logger(func.__module__)
            
            start_time = datetime.now(timezone.utc)
            
            try:
                result = func(*args, **kwargs)
                duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                logger.debug(
                    f"Function completed: {func.__name__}",
                    function=func.__name__,
                    duration_ms=duration_ms
                )
                return result
            except Exception as err:
                duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                logger.error(
                    f"Function failed: {func.__name__}",
                    error=err,
                    function=func.__name__,
                    duration_ms=duration_ms
                )
                raise
        
        return wrapper
    return decorator


def sanitize_error(error: str | Exception) -> str:
    """
    Sanitize error messages to avoid exposing sensitive information.
    
    Args:
        error: Error message or exception
        
    Returns:
        Sanitized error message
    """
    error_str = str(error)
    
    # List of patterns to redact
    sensitive_patterns = [
        r'password["\']?\s*[:=]\s*["\']?[^"\'\s]+',
        r'token["\']?\s*[:=]\s*["\']?[^"\'\s]+',
        r'key["\']?\s*[:=]\s*["\']?[^"\'\s]+',
        r'secret["\']?\s*[:=]\s*["\']?[^"\'\s]+',
        r'arn:aws:[^:\s]+:[^:\s]+:\d+:[^:\s]+',  # AWS ARNs
    ]
    
    import re
    for pattern in sensitive_patterns:
        error_str = re.sub(pattern, '[REDACTED]', error_str, flags=re.IGNORECASE)
    
    return error_str