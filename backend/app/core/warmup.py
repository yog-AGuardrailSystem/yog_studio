"""Do the slow first-request work at boot (build or load the retrieval index), in the background, never fatally."""
import threading

from app.core.log import logger


def _warm() -> None:
    try:
        from app.api.retrieve import get_retriever
        get_retriever()._load()
        logger.info("warm", extra={"fields": {"index": "ready"}})
    except Exception as e:                                    # noqa: BLE001 - warm-up must never stop the server
        logger.warning("warm", extra={"fields": {"index": "skipped", "reason": type(e).__name__}})


def start() -> threading.Thread:
    t = threading.Thread(target=_warm, daemon=True, name="warmup")
    t.start()
    return t
