"""Background translation jobs, so the UI can show live progress (retrieved examples, each attempt, each error) and
cancel. In memory only: a restart forgets jobs, which is fine for a tool whose results are re-creatable drafts."""
import threading
import time
import uuid
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, Field

from app.core.models import PolicyDraft
from app.llm.provider import LLMError
from app.translate.translator import TranslateCancelled

MAX_JOBS = 50
TTL_SECONDS = 3600

Run = Callable[[Callable[[dict], None], Callable[[], bool]], PolicyDraft]


class JobView(BaseModel):
    id: str
    status: Literal["running", "done", "error", "cancelled"]
    events: list[dict] = Field(default_factory=list)      # only the events after `since`
    next: int = 0                                         # pass this as `since` on the next poll
    result: PolicyDraft | None = None
    error: str | None = None


class _Job:
    def __init__(self) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.status = "running"
        self.events: list[dict] = []
        self.result: PolicyDraft | None = None
        self.error: str | None = None
        self.cancel = threading.Event()
        self.created = time.time()


class JobStore:
    def __init__(self, max_jobs: int = MAX_JOBS, ttl: float = TTL_SECONDS) -> None:
        self._jobs: dict[str, _Job] = {}
        self._lock = threading.Lock()
        self.max_jobs, self.ttl = max_jobs, ttl

    def _prune(self) -> None:
        now = time.time()
        for jid in [j for j, job in self._jobs.items() if now - job.created > self.ttl]:
            del self._jobs[jid]
        while len(self._jobs) >= self.max_jobs:                      # drop the oldest finished job first
            finished = [j for j, job in self._jobs.items() if job.status != "running"] or list(self._jobs)
            del self._jobs[min(finished, key=lambda j: self._jobs[j].created)]

    def start(self, run: Run, *, blocking: bool = False) -> str:
        job = _Job()
        with self._lock:
            self._prune()
            self._jobs[job.id] = job

        def emit(event: dict) -> None:
            with self._lock:
                job.events.append({"i": len(job.events), "t": round(time.time(), 2), **event})

        def work() -> None:
            try:
                result = run(emit, job.cancel.is_set)
                with self._lock:
                    job.result, job.status = result, "done"
            except TranslateCancelled:
                with self._lock:
                    job.status = "cancelled"
            except LLMError as e:
                with self._lock:
                    job.status, job.error = "error", str(e)
            except Exception as e:                                   # noqa: BLE001 - a job must always finish
                with self._lock:
                    job.status, job.error = "error", f"internal error ({type(e).__name__})"

        if blocking:                                                 # tests run the job inline
            work()
        else:
            threading.Thread(target=work, daemon=True, name=f"translate-{job.id}").start()
        return job.id

    def view(self, job_id: str, since: int = 0) -> JobView | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return JobView(id=job.id, status=job.status, events=list(job.events[max(0, since):]),
                           next=len(job.events), result=job.result, error=job.error)

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            return False
        job.cancel.set()
        return True
