"""Arq queue integration for background jobs."""

from __future__ import annotations

import os

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arq.connections import RedisSettings


def get_redis_settings():
    url = (
        os.environ.get("MOVIECON_JOB_REDIS_URL")
        or os.environ.get("MOVIECON_REDIS_URL")
        or "redis://localhost:6379/0"
    )
    from arq.connections import RedisSettings

    return RedisSettings.from_dsn(url)


async def enqueue_full_pipeline_job(
    job_id: str,
    project_id: str,
    scene_numbers: list[int] | None,
    style: str | None,
    skip_analysis: bool,
    skip_shots: bool,
    skip_storyboard: bool,
) -> None:
    from arq import create_pool
    redis = await create_pool(get_redis_settings())
    await redis.enqueue_job(
        "run_full_pipeline_job",
        job_id=job_id,
        project_id=project_id,
        scene_numbers=scene_numbers,
        style=style,
        skip_analysis=skip_analysis,
        skip_shots=skip_shots,
        skip_storyboard=skip_storyboard,
    )
    await redis.close()


async def enqueue_analysis_job(
    job_id: str,
    project_id: str,
    scene_numbers: list[int] | None,
) -> None:
    from arq import create_pool
    redis = await create_pool(get_redis_settings())
    await redis.enqueue_job(
        "run_analysis_job",
        job_id=job_id,
        project_id=project_id,
        scene_numbers=scene_numbers,
    )
    await redis.close()


async def enqueue_shots_job(
    job_id: str,
    project_id: str,
    scene_numbers: list[int] | None,
    style: str | None,
    shots_per_scene: int | None,
) -> None:
    from arq import create_pool
    redis = await create_pool(get_redis_settings())
    await redis.enqueue_job(
        "run_shots_job",
        job_id=job_id,
        project_id=project_id,
        scene_numbers=scene_numbers,
        style=style,
        shots_per_scene=shots_per_scene,
    )
    await redis.close()


async def enqueue_storyboard_job(
    job_id: str,
    project_id: str,
    scene_numbers: list[int] | None,
    style: str | None,
    aspect_ratio: str,
) -> None:
    from arq import create_pool
    redis = await create_pool(get_redis_settings())
    await redis.enqueue_job(
        "run_storyboard_job",
        job_id=job_id,
        project_id=project_id,
        scene_numbers=scene_numbers,
        style=style,
        aspect_ratio=aspect_ratio,
    )
    await redis.close()


async def get_queue_health() -> dict:
    """Check health of the job queue backend."""
    try:
        from arq import create_pool

        redis = await create_pool(get_redis_settings())
        await redis.ping()
        await redis.close()
        return {"status": "healthy"}
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}
