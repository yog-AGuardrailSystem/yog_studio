"""One JSON line per request on stdout (Render shows it as-is). Never logs bodies, cookies, keys or client addresses:
only what is needed to find a slow or failing request."""
import json
import logging
import sys
import time

logger = logging.getLogger("yog")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {"ts": round(record.created, 3), "level": record.levelname.lower(), "msg": record.getMessage()}
        data.update(getattr(record, "fields", {}))
        if record.exc_info:
            data["error"] = record.exc_info[0].__name__ if record.exc_info[0] else "error"      # type only, no message or trace text
        return json.dumps(data, separators=(",", ":"))


def setup() -> None:
    if logger.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def request_line(rid: str, method: str, path: str, status: int, started: float) -> None:
    logger.info("request", extra={"fields": {"rid": rid, "method": method, "path": path, "status": status,
                                              "ms": round((time.perf_counter() - started) * 1000, 1)}})


def error_line(rid: str, method: str, path: str) -> None:
    logger.error("unhandled", exc_info=True, extra={"fields": {"rid": rid, "method": method, "path": path}})
