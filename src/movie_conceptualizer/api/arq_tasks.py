"""Arq worker tasks for background processing."""

from __future__ import annotations

import os

from arq import Retry
from arq.connections import RedisSettings

from movie_conceptualizer.api.dependencies import ProjectStore, get_workflow
from movie_conceptualizer.api.generation_service import (
    run_analysis_for_project,
    run_pipeline_for_project,
    run_shots_for_project,
    run_storyboard_for_project,
)
from movie_conceptualizer.api.schemas import JobStatus
from movie_conceptualizer.storage import JobRepository


async def _handle_job_failure(
    repo: JobRepository,
    job_id: str,
    exc: Exception,
    ctx: dict,
) -> None:
    job_try = ctx.get("job_try", 1)
    max_tries = ctx.get("max_tries", 3)
    error_message = str(exc)

    if job_try < max_tries:
        await repo.update_status(job_id, JobStatus.QUEUED.value, error=error_message)
        delay = min(2**job_try, 60)
        raise Retry(delay=delay)

    await repo.update_status(job_id, JobStatus.FAILED.value, error=error_message)
    model = await repo.get(job_id)
    if model:
        await repo.create_dead_letter(
            job_id=model.id,
            project_id=model.project_id,
            user_id=model.user_id,
            status=model.status,
            description=model.description,
            error=error_message,
            payload=model.payload,
        )
    raise


async def run_full_pipeline_job(
    ctx: dict,
    job_id: str,
    project_id: str,
    scene_numbers: list[int] | None = None,
    style: str | None = None,
    skip_analysis: bool = False,
    skip_shots: bool = False,
    skip_storyboard: bool = False,
) -> None:
    repo = JobRepository()
    await repo.start_job(job_id)

    store = ProjectStore()
    workflow = get_workflow()

    try:
        await run_pipeline_for_project(
            project_id=project_id,
            store=store,
            workflow=workflow,
            scene_numbers=scene_numbers,
            style=style,
            skip_analysis=skip_analysis,
            skip_shots=skip_shots,
            skip_storyboard=skip_storyboard,
            job_repo=repo,
            job_id=job_id,
        )
        await repo.update_status(job_id, JobStatus.SUCCEEDED.value)
    except Exception as exc:
        await _handle_job_failure(repo, job_id, exc, ctx)


async def run_analysis_job(
    ctx: dict,
    job_id: str,
    project_id: str,
    scene_numbers: list[int] | None = None,
) -> None:
    repo = JobRepository()
    await repo.start_job(job_id)
    store = ProjectStore()
    workflow = get_workflow()

    try:
        await run_analysis_for_project(
            project_id=project_id,
            store=store,
            workflow=workflow,
            scene_numbers=scene_numbers,
            job_repo=repo,
            job_id=job_id,
        )
        await repo.update_status(job_id, JobStatus.SUCCEEDED.value)
    except Exception as exc:
        await _handle_job_failure(repo, job_id, exc, ctx)


async def run_shots_job(
    ctx: dict,
    job_id: str,
    project_id: str,
    scene_numbers: list[int] | None = None,
    style: str | None = None,
    shots_per_scene: int | None = None,
) -> None:
    repo = JobRepository()
    await repo.start_job(job_id)
    store = ProjectStore()
    workflow = get_workflow()

    try:
        await run_shots_for_project(
            project_id=project_id,
            store=store,
            workflow=workflow,
            scene_numbers=scene_numbers,
            style=style,
            shots_per_scene=shots_per_scene,
            job_repo=repo,
            job_id=job_id,
        )
        await repo.update_status(job_id, JobStatus.SUCCEEDED.value)
    except Exception as exc:
        await _handle_job_failure(repo, job_id, exc, ctx)


async def run_storyboard_job(
    ctx: dict,
    job_id: str,
    project_id: str,
    scene_numbers: list[int] | None = None,
    style: str | None = None,
    aspect_ratio: str = "16:9",
) -> None:
    repo = JobRepository()
    await repo.start_job(job_id)
    store = ProjectStore()
    workflow = get_workflow()

    try:
        await run_storyboard_for_project(
            project_id=project_id,
            store=store,
            workflow=workflow,
            scene_numbers=scene_numbers,
            style=style,
            aspect_ratio=aspect_ratio,
            job_repo=repo,
            job_id=job_id,
        )
        await repo.update_status(job_id, JobStatus.SUCCEEDED.value)
    except Exception as exc:
        await _handle_job_failure(repo, job_id, exc, ctx)


class WorkerSettings:
    """Arq worker settings."""

    functions = [
        run_full_pipeline_job,
        run_analysis_job,
        run_shots_job,
        run_storyboard_job,
    ]
    max_tries = 3

    redis_settings = RedisSettings.from_dsn(
        os.environ.get("MOVIECON_JOB_REDIS_URL")
        or os.environ.get("MOVIECON_REDIS_URL")
        or "redis://localhost:6379/0"
    )
