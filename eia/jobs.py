"""Background research jobs.

Streamlit stops a running script whenever the user clicks something, which used to kill research half-way.
Research now runs in a daemon thread that survives reruns and page changes; the UI polls the job for progress.
Set EIA_SYNC_JOBS=1 to run jobs inline (used by the tests).
"""
from __future__ import annotations

import os
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class Job:
    id: str
    label: str
    started: float = field(default_factory=time.time)
    frac: float = 0.0
    messages: list[str] = field(default_factory=list)
    run_id: Optional[str] = None
    done: bool = False
    status: str = "running"            # running | completed | partial | failed
    error: str = ""
    summary: str = ""
    seen: bool = False                 # the UI has already reacted to completion

    def progress(self, stage: str, msg: str, frac: float) -> None:
        self.messages.append(f"{stage.capitalize()}: {msg}")
        self.messages = self.messages[-60:]
        if frac >= 0:
            self.frac = max(self.frac, min(1.0, frac))


class JobRegistry:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def start(self, label: str, work: Callable[[Job], object]) -> Job:
        job = Job(uuid.uuid4().hex[:10], label)
        with self._lock:
            self._jobs[job.id] = job

        def runner():
            try:
                out = work(job)
                job.run_id = getattr(out, "run_id", job.run_id)
                job.status = getattr(out, "status", "completed")
                job.summary = (f"{getattr(out, 'n_sources', 0)} sources, {getattr(out, 'n_facts', 0)} facts, "
                               f"{getattr(out, 'n_hypotheses', 0)} findings")
            except Exception as e:  # never leave a job hanging
                job.status, job.error = "failed", f"{type(e).__name__}: {e}"
                job.messages.append(traceback.format_exc()[-600:])
            finally:
                job.frac, job.done = 1.0, True

        if os.getenv("EIA_SYNC_JOBS"):
            runner()
        else:
            threading.Thread(target=runner, name=f"research-{job.id}", daemon=True).start()
        return job

    def get(self, job_id: Optional[str]) -> Optional[Job]:
        return self._jobs.get(job_id or "")

    def active(self) -> list[Job]:
        return [j for j in self._jobs.values() if not j.done]

    def running_run_ids(self) -> set[str]:
        return {j.run_id for j in self._jobs.values() if not j.done and j.run_id}
