"""Persistent job manager for background processing."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field

from movie_conceptualizer.api.schemas import JobStatus
from movie_conceptualizer.api.logging_utils import request_id_var
from movie_conceptualizer.storage import JobRepository

class JobRecord(BaseModel):
    """Record for a background job."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    status: JobStatus = Field(default=JobStatus.QUEUED)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    description: str | None = None
    project_id: str | None = None
    user_id: str | None = None
    error: str | None = None
    last_error: str | None = None
    attempts: int = 0
    progress: float = 0.0
    current_step: str | None = None
    payload: str | None = None


class JobManager:
    """Background job manager backed by database storage."""

    def __init__(self, repository: JobRepository | None = None) -> None:
        self._repo = repository or JobRepository()
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()

    async def submit(
        self,
        coro_or_factory: Coroutine | Callable[[str], Coroutine],
        description: str | None = None,
        project_id: str | None = None,
        user_id: str | None = None,
        payload: str | None = None,
    ) -> JobRecord:
        """Submit a coroutine as a background job."""
        record = JobRecord(
            description=description,
            project_id=project_id,
            user_id=user_id,
            payload=payload,
        )
        await self._repo.create(
            job_id=record.id,
            status=record.status.value,
            project_id=record.project_id,
            user_id=user_id,
            description=record.description,
            error=record.error,
            payload=record.payload,
        )

        if os.environ.get("MOVIECON_INPROCESS_INLINE", "false").lower() in ("true", "1", "yes"):
            await self._run(record.id, coro_or_factory)
            return record

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop (e.g. sync context/tests). Run inline to avoid orphaned coroutines.
            await self._run(record.id, coro_or_factory)
            return record

        task = loop.create_task(self._run(record.id, coro_or_factory))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return record

    async def _run(
        self,
        job_id: str,
        coro_or_factory: Coroutine | Callable[[str], Coroutine],
    ) -> None:
        token = request_id_var.set(job_id)
        coro = (
            coro_or_factory(job_id)
            if callable(coro_or_factory)
            else coro_or_factory
        )
        try:
            await self._repo.start_job(job_id)
        except Exception:
            # Best-effort job tracking; still run the coroutine to avoid leaks.
            pass

        try:
            await coro
            status = JobStatus.SUCCEEDED
            error = None
        except Exception as exc:  # pragma: no cover - best-effort background reporting
            status = JobStatus.FAILED
            error = str(exc)

        try:
            await self._repo.update_status(job_id, status.value, error=error)
        except Exception:
            pass

        if status == JobStatus.FAILED:
            try:
                model = await self._repo.get(job_id)
                if model:
                    await self._repo.create_dead_letter(
                        job_id=model.id,
                        project_id=model.project_id,
                        user_id=model.user_id,
                        status=model.status,
                        description=model.description,
                        error=error,
                        payload=model.payload,
                    )
            except Exception:
                pass
        request_id_var.reset(token)

    async def get(self, job_id: str) -> JobRecord | None:
        model = await self._repo.get(job_id)
        if model is None:
            return None
        return JobRecord(
            id=model.id,
            status=JobStatus(model.status),
            created_at=model.created_at,
            updated_at=model.updated_at,
            description=model.description,
            project_id=model.project_id,
            error=model.error,
            last_error=model.last_error,
            attempts=model.attempts,
            progress=model.progress,
            current_step=model.current_step,
            payload=model.payload,
            user_id=model.user_id,
        )


_job_manager: JobManager | None = None


def get_job_manager() -> JobManager:
    global _job_manager
    if _job_manager is None:
        _job_manager = JobManager()
    return _job_manager
