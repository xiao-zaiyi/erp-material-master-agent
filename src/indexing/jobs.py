from __future__ import annotations

import threading
import uuid
import logging
from collections.abc import Callable

from materials.models import IndexStatusResponse


logger = logging.getLogger("material_agent.index_job")


class IndexJobManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._status = IndexStatusResponse(status="idle")

    def start(self, task: Callable[[], int]) -> tuple[str, str]:
        with self._lock:
            if self._status.status in {"queued", "running"}:
                return self._status.job_id or "", self._status.status
            job_id = uuid.uuid4().hex
            self._status = IndexStatusResponse(job_id=job_id, status="queued")
        logger.info("索引任务已排队：job_id=%s", job_id)
        return job_id, "queued"

    def run(self, job_id: str, task: Callable[[], int]) -> None:
        with self._lock:
            self._status = IndexStatusResponse(job_id=job_id, status="running")
        logger.info("索引任务开始执行：job_id=%s", job_id)
        try:
            count = task()
            with self._lock:
                self._status = IndexStatusResponse(job_id=job_id, status="succeeded", indexed_count=count)
            logger.info("索引任务执行成功：job_id=%s, indexed_count=%d", job_id, count)
        except Exception as exc:
            with self._lock:
                self._status = IndexStatusResponse(job_id=job_id, status="failed", error=str(exc)[:500])
            logger.exception("索引任务执行失败：job_id=%s", job_id)

    def status(self) -> IndexStatusResponse:
        with self._lock:
            return self._status.model_copy()
