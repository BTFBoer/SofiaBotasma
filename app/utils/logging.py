"""Structured logging.

Message contents are only ever logged at DEBUG level, so the default INFO
logs contain metadata (timings, token usage, ids) but no intimate content.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = {k: v for k, v in record.__dict__.items() if k not in _RESERVED and not k.startswith("_")}
        if extras:
            base += "  " + " ".join(f"{k}={v}" for k, v in extras.items())
        return base


class _QuietNetworkRetries(logging.Filter):
    """python-telegram-bot logs a full traceback for every failed network retry; one line is enough."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name.startswith("telegram") and "Network Retry Loop" in record.getMessage():
            record.exc_info = None
            record.exc_text = None
        return True


def setup_logging(level: str = "INFO", fmt: str = "text") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_QuietNetworkRetries())
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(TextFormatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # Third-party libraries are chatty at INFO (every HTTP request).
    for noisy in ("httpx", "httpcore", "httpx2", "httpcore2", "telegram", "apscheduler", "openai"):
        logging.getLogger(noisy).setLevel(max(logging.WARNING, logging.getLevelName(level)))


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
