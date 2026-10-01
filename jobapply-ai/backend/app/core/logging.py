"""Structured JSON logging with secret/PII scrubbing."""
from __future__ import annotations

import json
import logging
import re
import sys
import time
from datetime import datetime, timezone

_SCRUB = [(re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"), "<email>"), (re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+"), "Bearer <token>"),
          (re.compile(r"/files/[A-Za-z0-9_\-.]+"), "/files/<signed>")]


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()
        for rx, rep in _SCRUB:
            msg = rx.sub(rep, msg)
        out = {"ts": datetime.now(timezone.utc).isoformat(), "level": record.levelname, "logger": record.name, "msg": msg}
        for k in ("request_id", "path", "method", "status", "duration_ms", "user_id"):
            if hasattr(record, k):
                out[k] = getattr(record, k)
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info).splitlines()[-1]
        return json.dumps(out, ensure_ascii=False)


def setup_logging(debug: bool = False) -> None:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [h]
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").disabled = True  # replaced by request middleware (no query strings → no tokens in logs)
