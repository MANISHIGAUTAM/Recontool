"""Observability — structured JSON logs + per-scan trace IDs.

Every scan gets a trace_id (the scan_id) that is bound to a context var and
emitted on every structured log line, so logs/audit can be correlated across the
parallel adapter fan-out. Logs are line-delimited JSON (machine-parseable) when
``RECON_LOG_FORMAT=json`` (default), or human text otherwise.

The DB ``audit_log`` table remains the durable audit trail; this module adds the
runtime structured-log stream + trace correlation requested by the architecture
(structured logs, trace IDs, audit trails).
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar

_trace_id: ContextVar[str] = ContextVar("trace_id", default="-")

LOG_FORMAT = os.getenv("RECON_LOG_FORMAT", "json").lower()
LOG_LEVEL = os.getenv("RECON_LOG_LEVEL", "INFO").upper()


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "trace_id": _trace_id.get(),
            "msg": record.getMessage(),
        }
        # attach structured extras passed via logger.x(..., extra={"fields": {...}})
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str | None = None) -> None:
    """Idempotently configure the root recontool logger."""
    root = logging.getLogger("recontool")
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    if LOG_FORMAT == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] trace=%(trace_id)s %(message)s"))

        # inject trace_id into text records
        class _Filter(logging.Filter):
            def filter(self, rec):
                rec.trace_id = _trace_id.get()
                return True
        handler.addFilter(_Filter())
    root.addHandler(handler)
    root.setLevel(level or LOG_LEVEL)
    root.propagate = False


def get_logger(name: str = "recontool") -> logging.Logger:
    configure_logging()
    return logging.getLogger(name if name.startswith("recontool") else f"recontool.{name}")


def set_trace_id(trace_id: str | None = None) -> str:
    """Bind a trace id (scan_id) to the current context; returns the id used."""
    tid = trace_id or uuid.uuid4().hex[:16]
    _trace_id.set(tid)
    return tid


def get_trace_id() -> str:
    return _trace_id.get()


def log_event(action: str, level: str = "INFO", **fields) -> None:
    """Emit a structured log line with arbitrary fields under the bound trace id."""
    logger = get_logger("recontool.event")
    logger.log(getattr(logging, level.upper(), logging.INFO), action,
               extra={"fields": {"action": action, **fields}})
