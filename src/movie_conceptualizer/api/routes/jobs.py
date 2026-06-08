"""Background job status API routes."""

import csv
import io
import os
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi import status as http_status

from movie_conceptualizer.api.arq_queue import (
    enqueue_analysis_job,
    enqueue_full_pipeline_job,
    enqueue_shots_job,
    enqueue_storyboard_job,
)
from movie_conceptualizer.api.dependencies import (
    UserInDB,
    is_admin_user,
    require_admin_access,
    require_auth_if_enabled,
)
from movie_conceptualizer.api.job_payloads import (
    AnalysisJobPayload,
    PipelineJobPayload,
    ShotsJobPayload,
    StoryboardJobPayload,
    decode_payload,
)
from movie_conceptualizer.api.jobs import get_job_manager
from movie_conceptualizer.api.ratelimit import DEFAULT_RATE_LIMIT, limiter
from movie_conceptualizer.api.schemas import (
    ErrorResponse,
    JobListResponse,
    JobMetricsResponse,
    JobStatus,
    JobStatusResponse,
)
from movie_conceptualizer.storage import (
    JobAuditLogRepository,
    JobIdempotencyRepository,
    JobRepository,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])
IDEMPOTENCY_TTL_DAYS = int(os.environ.get("MOVIECON_IDEMPOTENCY_TTL_DAYS", "7"))
JOB_AUDIT_SCHEMA_VERSION = 1


def _format_datetime(value: datetime) -> str:
    """Format datetime consistently in UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


@router.get(
    "",
    response_model=JobListResponse,
    responses={
        200: {"description": "Job list"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="List jobs",
    description="List jobs for the current user (admin can list all).",
)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def list_jobs(
    request: Request,
    response: Response,
    status: str | None = Query(None, description="Filter by job status"),
    limit: int = Query(50, ge=1, le=200, description="Number of jobs to return"),
    current_user: Annotated[UserInDB | None, Depends(require_auth_if_enabled)] = None,
) -> JobListResponse:
    repo = JobRepository()
    normalized_status = status.lower() if status else None
    if normalized_status is not None and normalized_status not in {s.value for s in JobStatus}:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Invalid status filter.",
        )
    if current_user and not is_admin_user(current_user):
        jobs = await repo.list_jobs(user_id=current_user.id, status=normalized_status, limit=limit)
    else:
        jobs = await repo.list_jobs(status=normalized_status, limit=limit)

    items = [
        JobStatusResponse(
            job_id=job.id,
            status=JobStatus(job.status),
            project_id=job.project_id,
            user_id=job.user_id,
            error=job.error,
            last_error=job.last_error,
            attempts=job.attempts,
            progress=job.progress,
            current_step=job.current_step,
            created_at=job.created_at,
            updated_at=job.updated_at,
            description=job.description,
        )
        for job in jobs
    ]

    return JobListResponse(items=items, total=len(items))


@router.get(
    "/dead-letter",
    responses={
        200: {"description": "List of dead-letter jobs"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="List dead-letter jobs",
    description="Retrieve recent failed jobs that were moved to dead-letter storage.",
)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def list_dead_letter_jobs(
    request: Request,
    response: Response,
    limit: int = Query(50, ge=1, le=200, description="Number of records to return"),
    current_user: Annotated[UserInDB, Depends(require_admin_access)] = None,
):
    repo = JobRepository()
    records = await repo.list_dead_letters(limit=limit)
    for record in records:
        record["payload"] = decode_payload(record.get("payload"))
    audit_repo = JobAuditLogRepository()
    await audit_repo.create(
        actor_user_id=current_user.id,
        action="dead_letter_list",
        metadata=f"limit={limit}",
    )
    return {"items": records, "total": len(records)}


@router.post(
    "/{job_id}/retry",
    responses={
        200: {"description": "Job re-enqueued"},
        404: {"model": ErrorResponse, "description": "Job not found"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Retry a failed job",
    description="Re-enqueue a failed job based on its stored payload.",
)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def retry_job(
    request: Request,
    response: Response,
    job_id: str,
    current_user: Annotated[UserInDB, Depends(require_admin_access)] = None,
):
    repo = JobRepository()
    job = await repo.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found",
        )
    if not job.project_id:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Job is missing project_id and cannot be retried",
        )

    payload = decode_payload(job.payload)
    description = (job.description or "").lower()

    backend = os.environ.get("MOVIECON_JOB_BACKEND", "inprocess").lower()
    if backend != "arq":
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Retry is only supported for arq backend",
        )

    await repo.reset_job(job_id)

    if description == "analysis":
        analysis_parsed = AnalysisJobPayload.model_validate(payload)
        await enqueue_analysis_job(
            job_id=job_id,
            project_id=job.project_id,
            scene_numbers=analysis_parsed.scene_numbers,
        )
    elif description == "shots":
        shots_parsed = ShotsJobPayload.model_validate(payload)
        await enqueue_shots_job(
            job_id=job_id,
            project_id=job.project_id,
            scene_numbers=shots_parsed.scene_numbers,
            style=shots_parsed.style,
            shots_per_scene=shots_parsed.shots_per_scene,
        )
    elif description == "storyboard":
        storyboard_parsed = StoryboardJobPayload.model_validate(payload)
        await enqueue_storyboard_job(
            job_id=job_id,
            project_id=job.project_id,
            scene_numbers=storyboard_parsed.scene_numbers,
            style=storyboard_parsed.style,
            aspect_ratio=storyboard_parsed.aspect_ratio,
        )
    else:
        pipeline_parsed = PipelineJobPayload.model_validate(payload)
        await enqueue_full_pipeline_job(
            job_id=job_id,
            project_id=job.project_id,
            scene_numbers=pipeline_parsed.scene_numbers,
            style=pipeline_parsed.style,
            skip_analysis=pipeline_parsed.skip_analysis,
            skip_shots=pipeline_parsed.skip_shots,
            skip_storyboard=pipeline_parsed.skip_storyboard,
        )

    audit_repo = JobAuditLogRepository()
    await audit_repo.create(
        actor_user_id=current_user.id,
        action="job_retry",
        target_job_id=job_id,
        metadata=f"description={description}",
    )

    return {"job_id": job_id, "status": "queued"}


@router.post(
    "/dead-letter/replay",
    responses={
        200: {"description": "Dead-letter jobs replayed"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Replay dead-letter jobs",
    description="Bulk re-enqueue dead-letter jobs with new job IDs.",
)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def replay_dead_letter_jobs(
    request: Request,
    response: Response,
    limit: int = Query(50, ge=1, le=200, description="Number of records to replay"),
    current_user: Annotated[UserInDB, Depends(require_admin_access)] = None,
):
    backend = os.environ.get("MOVIECON_JOB_BACKEND", "inprocess").lower()
    if backend != "arq":
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Replay is only supported for arq backend",
        )

    repo = JobRepository()
    records = await repo.list_dead_letters(limit=limit)
    created_jobs: list[str] = []

    for record in records:
        payload = decode_payload(record.get("payload"))
        description = (record.get("description") or "full_pipeline").lower()
        project_id = record.get("project_id")
        if not project_id:
            continue

        job_id = str(uuid4())
        await repo.create(
            job_id=job_id,
            status="queued",
            project_id=project_id,
            user_id=current_user.id,
            description=description,
            payload=record.get("payload"),
        )

        if description == "analysis":
            analysis_parsed = AnalysisJobPayload.model_validate(payload)
            await enqueue_analysis_job(
                job_id=job_id,
                project_id=project_id,
                scene_numbers=analysis_parsed.scene_numbers,
            )
        elif description == "shots":
            shots_parsed = ShotsJobPayload.model_validate(payload)
            await enqueue_shots_job(
                job_id=job_id,
                project_id=project_id,
                scene_numbers=shots_parsed.scene_numbers,
                style=shots_parsed.style,
                shots_per_scene=shots_parsed.shots_per_scene,
            )
        elif description == "storyboard":
            storyboard_parsed = StoryboardJobPayload.model_validate(payload)
            await enqueue_storyboard_job(
                job_id=job_id,
                project_id=project_id,
                scene_numbers=storyboard_parsed.scene_numbers,
                style=storyboard_parsed.style,
                aspect_ratio=storyboard_parsed.aspect_ratio,
            )
        else:
            pipeline_parsed = PipelineJobPayload.model_validate(payload)
            await enqueue_full_pipeline_job(
                job_id=job_id,
                project_id=project_id,
                scene_numbers=pipeline_parsed.scene_numbers,
                style=pipeline_parsed.style,
                skip_analysis=pipeline_parsed.skip_analysis,
                skip_shots=pipeline_parsed.skip_shots,
                skip_storyboard=pipeline_parsed.skip_storyboard,
            )

        created_jobs.append(job_id)

    audit_repo = JobAuditLogRepository()
    await audit_repo.create(
        actor_user_id=current_user.id,
        action="dead_letter_replay",
        metadata=f"limit={limit},created={len(created_jobs)}",
    )

    return {"created_jobs": created_jobs, "count": len(created_jobs)}


@router.get(
    "/metrics",
    response_model=JobMetricsResponse,
    responses={
        200: {"description": "Job metrics"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Get job metrics",
    description="Aggregate metrics about background jobs.",
)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def get_job_metrics(
    request: Request,
    response: Response,
    current_user: Annotated[UserInDB, Depends(require_admin_access)] = None,
) -> JobMetricsResponse:
    repo = JobRepository()
    metrics = await repo.get_metrics()
    audit_repo = JobAuditLogRepository()
    await audit_repo.create(
        actor_user_id=current_user.id,
        action="job_metrics",
    )
    return JobMetricsResponse(**metrics)


@router.post(
    "/purge",
    responses={
        200: {"description": "Jobs purged"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Purge jobs",
    description="Delete job records by status and/or age.",
)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def purge_jobs(
    request: Request,
    response: Response,
    status: str | None = Query(None, description="Only purge jobs with this status"),
    older_than_days: int | None = Query(
        30, ge=1, le=3650, description="Purge jobs older than N days"
    ),
    include_dead_letter: bool = Query(False, description="Also purge dead-letter records"),
    current_user: Annotated[UserInDB, Depends(require_admin_access)] = None,
):
    repo = JobRepository()
    older_than = (
        datetime.now(UTC) - timedelta(days=older_than_days) if older_than_days is not None else None
    )
    deleted_jobs = await repo.purge_jobs(status=status, older_than=older_than)
    deleted_dead = 0
    if include_dead_letter:
        deleted_dead = await repo.purge_dead_letters(older_than=older_than)

    audit_repo = JobAuditLogRepository()
    await audit_repo.create(
        actor_user_id=current_user.id,
        action="job_purge",
        metadata=(
            f"status={status},older_than_days={older_than_days},"
            f"include_dead_letter={include_dead_letter},"
            f"deleted_jobs={deleted_jobs},deleted_dead={deleted_dead}"
        ),
    )

    return {
        "deleted_jobs": deleted_jobs,
        "deleted_dead_letter": deleted_dead,
    }


@router.post(
    "/idempotency/purge",
    responses={
        200: {"description": "Idempotency records purged"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Purge idempotency records",
    description="Delete idempotency records older than the configured TTL.",
)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def purge_job_idempotency(
    request: Request,
    response: Response,
    older_than_days: int | None = Query(
        None, ge=1, le=3650, description="Purge idempotency records older than N days"
    ),
    current_user: Annotated[UserInDB, Depends(require_admin_access)] = None,
):
    ttl_days = older_than_days if older_than_days is not None else IDEMPOTENCY_TTL_DAYS
    if ttl_days <= 0:
        return {"deleted": 0, "older_than_days": ttl_days}

    repo = JobIdempotencyRepository()
    deleted = await repo.purge_expired(ttl_days * 24 * 60 * 60)

    audit_repo = JobAuditLogRepository()
    await audit_repo.create(
        actor_user_id=current_user.id,
        action="job_idempotency_purge",
        metadata=f"older_than_days={ttl_days},deleted={deleted}",
    )

    return {
        "deleted": deleted,
        "older_than_days": ttl_days,
    }


@router.get(
    "/audit",
    responses={
        200: {"description": "Audit log entries"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="List job audit logs",
    description="Retrieve audit logs for admin job actions.",
)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def list_job_audit_logs(
    request: Request,
    response: Response,
    format: str = Query("json", description="Response format: json or csv"),
    limit: int = Query(100, ge=1, le=500, description="Number of records to return"),
    current_user: Annotated[UserInDB, Depends(require_admin_access)] = None,
):
    repo = JobAuditLogRepository()
    logs = await repo.list(limit=limit)

    audit_repo = JobAuditLogRepository()
    await audit_repo.create(
        actor_user_id=current_user.id,
        action="audit_log_list",
        metadata=f"limit={limit},format={format}",
    )

    normalized_format = format.strip().lower()
    if normalized_format == "csv":
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "schema_version",
                "id",
                "actor_user_id",
                "action",
                "target_job_id",
                "metadata",
                "prev_hash",
                "hash",
                "created_at",
            ]
        )
        for log in logs:
            writer.writerow(
                [
                    JOB_AUDIT_SCHEMA_VERSION,
                    log.id,
                    log.actor_user_id,
                    log.action,
                    log.target_job_id,
                    log.metadata,
                    log.prev_hash,
                    log.hash,
                    _format_datetime(log.created_at),
                ]
            )
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=job_audit_logs_{timestamp}.csv",
            },
        )
    if normalized_format != "json":
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Invalid format. Use 'json' or 'csv'.",
        )

    return {
        "items": [log.model_dump(mode="json") for log in logs],
        "total": len(logs),
        "schema_version": JOB_AUDIT_SCHEMA_VERSION,
    }


@router.post(
    "/audit/purge",
    responses={
        200: {"description": "Audit logs purged"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Purge audit logs",
    description="Delete audit logs older than N days.",
)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def purge_job_audit_logs(
    request: Request,
    response: Response,
    older_than_days: int = Query(30, ge=1, le=3650, description="Purge logs older than N days"),
    current_user: Annotated[UserInDB, Depends(require_admin_access)] = None,
):
    repo = JobAuditLogRepository()
    older_than = datetime.now(UTC) - timedelta(days=older_than_days)
    deleted = await repo.purge(older_than=older_than)
    return {"deleted": deleted, "older_than_days": older_than_days}


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    responses={
        200: {"description": "Job status"},
        404: {"model": ErrorResponse, "description": "Job not found"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Get background job status",
    description="Fetch the current status of a background job.",
)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def get_job_status(
    request: Request,
    response: Response,
    job_id: str,
    job_manager=Depends(get_job_manager),
    current_user: Annotated[UserInDB | None, Depends(require_auth_if_enabled)] = None,
) -> JobStatusResponse:
    job = await job_manager.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found",
        )

    if current_user is not None and not is_admin_user(current_user):
        if job.user_id is None or job.user_id != current_user.id:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this job",
            )

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        project_id=job.project_id,
        user_id=job.user_id,
        error=job.error,
        last_error=job.last_error,
        attempts=job.attempts,
        progress=job.progress,
        current_step=job.current_step,
        created_at=job.created_at,
        updated_at=job.updated_at,
        description=job.description,
    )
