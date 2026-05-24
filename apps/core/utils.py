"""
Core utility classes for the EduOS platform.

Provides shared helpers used across the entire project, including
structured logging formatters.
"""

import json
import logging
import traceback
from datetime import datetime, timezone


class JsonLogFormatter(logging.Formatter):
    """
    Formats log records as single-line JSON objects.

    Designed for structured logging pipelines (ELK, CloudWatch, Datadog, etc.).
    Each log entry includes timestamp, level, logger name, message, and any
    extra context attached to the record.  Exception info is serialised as a
    ``traceback`` field when present.

    Usage in ``settings.LOGGING``::

        "formatters": {
            "json": {
                "()": "apps.core.utils.JsonLogFormatter",
            },
        },
    """

    # Keys that belong to the standard LogRecord and should be excluded when
    # collecting "extra" fields added by the caller.
    _BUILTIN_ATTRS = frozenset(
        {
            "args",
            "created",
            "exc_info",
            "exc_text",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "message",
            "module",
            "msecs",
            "msg",
            "name",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "taskName",
            "thread",
            "threadName",
        }
    )

    def format(self, record: logging.LogRecord) -> str:
        """Return a JSON-serialised string for *record*."""
        # Ensure record.message is populated.
        record.message = record.getMessage()

        log_entry: dict = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.message,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Attach exception traceback when available.
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["traceback"] = self.formatException(record.exc_info)

        if record.stack_info:
            log_entry["stack_info"] = self.formatStack(record.stack_info)

        # Collect any extra fields the caller attached to the record
        # (e.g. ``logger.info("msg", extra={"tenant_id": "abc"})``).
        for key, value in record.__dict__.items():
            if key not in self._BUILTIN_ATTRS and not key.startswith("_"):
                try:
                    json.dumps(value)  # ensure serialisable
                    log_entry[key] = value
                except (TypeError, ValueError):
                    log_entry[key] = str(value)

        return json.dumps(log_entry, default=str)
