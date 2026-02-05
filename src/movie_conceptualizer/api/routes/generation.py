"""AI generation API routes."""

import os
from uuid import uuid4
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from movie_conceptualizer.api.dependencies import (
    ProjectStore,
    UserInDB,
    Workflow,
    get_project_store,
    get_workflow,
    is_admin_user,
    require_auth_if_enabled,
)
from movie_conceptualizer.api.generation_service import (
    run_analysis_for_project,
    run_pipeline_for_project,
    run_shots_for_project,
    run_storyboard_for_project,
)
from movie_conceptualizer.api.job_payloads import (
    AnalysisJobPayload,
    PipelineJobPayload,
    ShotsJobPayload,
    StoryboardJobPayload,
    encode_payload,
)
from movie_conceptualizer.api.jobs import get_job_manager
from movie_conceptualizer.api.arq_queue import (
    enqueue_analysis_job,
    enqueue_full_pipeline_job,
    enqueue_shots_job,
    enqueue_storyboard_job,
)
from movie_conceptualizer.api.ratelimit import (
    DEFAULT_RATE_LIMIT,
    GENERATION_RATE_LIMIT,
    limiter,
)
from movie_conceptualizer.api.schemas import (
    AnalysisRequest,
    AnalysisResponse,
    ErrorResponse,
    GenerationJobResponse,
    GenerateShotsRequest,
    GenerateStoryboardRequest,
    GenerationStatusResponse,
    JobStatus,
    ProjectStatus,
    RunPipelineRequest,
    ShotListResponse,
    StoryboardResponse,
)
from movie_conceptualizer.storage import JobRepository

router = APIRouter(prefix="/projects/{project_id}", tags=["generation"])


def _filter_scenes_by_numbers(scenes: list, scene_numbers: list[int] | None) -> list:
    """Filter scenes by scene numbers if provided."""
    if scene_numbers is None:
        return scenes
    return [s for s in scenes if s.scene_number in scene_numbers]


@router.post(
    "/analyze",
    response_model=AnalysisResponse | GenerationJobResponse,
    responses={
        200: {"description": "Analysis completed successfully"},
        202: {"description": "Analysis started in background"},
        404: {"model": ErrorResponse, "description": "Project not found"},
        400: {"model": ErrorResponse, "description": "Script not parsed"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Run script analysis",
    description="Analyze the script for mood, themes, visual style, and other cinematic elements.",
)
@limiter.limit(GENERATION_RATE_LIMIT)
async def analyze_script(
    request: Request,
    response: Response,
    project_id: str,
    body: AnalysisRequest | None = None,
    async_run: bool = Query(
        False, description="Run analysis in background and return a job ID"
    ),
    store: ProjectStore = Depends(get_project_store),
    workflow: Workflow = Depends(get_workflow),
    current_user: Annotated[UserInDB | None, Depends(require_auth_if_enabled)] = None,
    job_manager=Depends(get_job_manager),
) -> AnalysisResponse:
    """Run script analysis."""
    project = await store.get(project_id)

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )
    if current_user and not is_admin_user(current_user):
        if project.user_id is None or project.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this project",
            )

    if not project.scenes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Script must be uploaded and parsed before analysis",
        )

    # Filter scenes if specific ones requested
    scene_numbers = body.scene_numbers if body else None
    scenes_to_analyze = _filter_scenes_by_numbers(project.scenes, scene_numbers)

    if not scenes_to_analyze:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No matching scenes found for the specified scene numbers",
        )

    if async_run:
        backend = os.environ.get("MOVIECON_JOB_BACKEND", "inprocess").lower()
        payload = encode_payload(AnalysisJobPayload(scene_numbers=scene_numbers))
        if backend == "arq":
            job_id = str(uuid4())
            repo = JobRepository()
            await repo.create(
                job_id=job_id,
                status=JobStatus.QUEUED.value,
                project_id=project.id,
                user_id=current_user.id if current_user else None,
                description="analysis",
                payload=payload,
            )
            await enqueue_analysis_job(job_id, project.id, scene_numbers)
            response.status_code = status.HTTP_202_ACCEPTED
            return GenerationJobResponse(
                job_id=job_id,
                status=JobStatus.QUEUED,
                project_id=project.id,
                message="Analysis started in background",
            )

        repo = JobRepository()
        job = await job_manager.submit(
            lambda job_id: run_analysis_for_project(
                project_id=project.id,
                store=store,
                workflow=workflow,
                scene_numbers=scene_numbers,
                job_repo=repo,
                job_id=job_id,
            ),
            description="analysis",
            project_id=project.id,
            user_id=current_user.id if current_user else None,
            payload=payload,
        )
        response.status_code = status.HTTP_202_ACCEPTED
        return GenerationJobResponse(
            job_id=job.id,
            status=JobStatus.QUEUED,
            project_id=project.id,
            message="Analysis started in background",
        )

    await run_analysis_for_project(
        project_id=project.id,
        store=store,
        workflow=workflow,
        scene_numbers=scene_numbers,
    )
    project = await store.get(project_id)

    return AnalysisResponse(
        project_id=project.id if project else project_id,
        analyses=project.analyses if project else [],
        overall_tone=project.overall_tone if project else None,
        visual_motifs=project.visual_motifs if project else [],
    )


@router.post(
    "/shots",
    response_model=ShotListResponse | GenerationJobResponse,
    responses={
        200: {"description": "Shot list generated successfully"},
        202: {"description": "Shot generation started in background"},
        404: {"model": ErrorResponse, "description": "Project not found"},
        400: {"model": ErrorResponse, "description": "Script not parsed"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Generate shot list",
    description="Generate a detailed shot list based on the parsed script and analysis.",
)
@limiter.limit(GENERATION_RATE_LIMIT)
async def generate_shots(
    request: Request,
    response: Response,
    project_id: str,
    body: GenerateShotsRequest | None = None,
    async_run: bool = Query(
        False, description="Run shot generation in background and return a job ID"
    ),
    store: ProjectStore = Depends(get_project_store),
    workflow: Workflow = Depends(get_workflow),
    current_user: Annotated[UserInDB | None, Depends(require_auth_if_enabled)] = None,
    job_manager=Depends(get_job_manager),
) -> ShotListResponse:
    """Generate shot list for the project."""
    project = await store.get(project_id)

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )
    if current_user and not is_admin_user(current_user):
        if project.user_id is None or project.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this project",
            )

    if not project.scenes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Script must be uploaded and parsed before generating shots",
        )

    # Get request parameters
    scene_numbers = body.scene_numbers if body else None
    style = body.style if body else project.style_notes
    shots_per_scene = body.shots_per_scene if body else None

    # Filter scenes if specific ones requested
    scenes_to_process = _filter_scenes_by_numbers(project.scenes, scene_numbers)

    if not scenes_to_process:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No matching scenes found for the specified scene numbers",
        )

    if async_run:
        backend = os.environ.get("MOVIECON_JOB_BACKEND", "inprocess").lower()
        payload = encode_payload(
            ShotsJobPayload(
                scene_numbers=scene_numbers,
                style=style,
                shots_per_scene=shots_per_scene,
            )
        )
        if backend == "arq":
            job_id = str(uuid4())
            repo = JobRepository()
            await repo.create(
                job_id=job_id,
                status=JobStatus.QUEUED.value,
                project_id=project.id,
                user_id=current_user.id if current_user else None,
                description="shots",
                payload=payload,
            )
            await enqueue_shots_job(
                job_id=job_id,
                project_id=project.id,
                scene_numbers=scene_numbers,
                style=style,
                shots_per_scene=shots_per_scene,
            )
            response.status_code = status.HTTP_202_ACCEPTED
            return GenerationJobResponse(
                job_id=job_id,
                status=JobStatus.QUEUED,
                project_id=project.id,
                message="Shot generation started in background",
            )

        repo = JobRepository()
        job = await job_manager.submit(
            lambda job_id: run_shots_for_project(
                project_id=project.id,
                store=store,
                workflow=workflow,
                scene_numbers=scene_numbers,
                style=style,
                shots_per_scene=shots_per_scene,
                job_repo=repo,
                job_id=job_id,
            ),
            description="shots",
            project_id=project.id,
            user_id=current_user.id if current_user else None,
            payload=payload,
        )
        response.status_code = status.HTTP_202_ACCEPTED
        return GenerationJobResponse(
            job_id=job.id,
            status=JobStatus.QUEUED,
            project_id=project.id,
            message="Shot generation started in background",
        )

    await run_shots_for_project(
        project_id=project.id,
        store=store,
        workflow=workflow,
        scene_numbers=scene_numbers,
        style=style,
        shots_per_scene=shots_per_scene,
    )
    project = await store.get(project_id)

    total_duration = sum(s.duration_seconds or 0 for s in project.shots) if project else 0
    return ShotListResponse(
        project_id=project.id if project else project_id,
        shots=project.shots if project else [],
        total_shots=len(project.shots) if project else 0,
        estimated_duration=total_duration if total_duration > 0 else None,
    )


@router.post(
    "/storyboard",
    response_model=StoryboardResponse | GenerationJobResponse,
    responses={
        200: {"description": "Storyboard prompts generated successfully"},
        202: {"description": "Storyboard generation started in background"},
        404: {"model": ErrorResponse, "description": "Project not found"},
        400: {"model": ErrorResponse, "description": "Shot list not generated"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Generate storyboard prompts",
    description="Generate AI image prompts for storyboard frames based on the shot list.",
)
@limiter.limit(GENERATION_RATE_LIMIT)
async def generate_storyboard(
    request: Request,
    response: Response,
    project_id: str,
    body: GenerateStoryboardRequest | None = None,
    async_run: bool = Query(
        False, description="Run storyboard generation in background and return a job ID"
    ),
    store: ProjectStore = Depends(get_project_store),
    workflow: Workflow = Depends(get_workflow),
    current_user: Annotated[UserInDB | None, Depends(require_auth_if_enabled)] = None,
    job_manager=Depends(get_job_manager),
) -> StoryboardResponse:
    """Generate storyboard prompts for the project."""
    project = await store.get(project_id)

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )
    if current_user and not is_admin_user(current_user):
        if project.user_id is None or project.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this project",
            )

    if not project.shots:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Shot list must be generated before creating storyboard prompts",
        )

    # Get request parameters
    scene_numbers = body.scene_numbers if body else None
    style = body.style if body else project.style_notes
    aspect_ratio = body.aspect_ratio if body else "16:9"

    # Filter shots if specific scenes requested
    shots_to_process = project.shots
    if scene_numbers:
        shots_to_process = [s for s in project.shots if s.scene_number in scene_numbers]

    if not shots_to_process:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No matching shots found for the specified scene numbers",
        )

    if async_run:
        backend = os.environ.get("MOVIECON_JOB_BACKEND", "inprocess").lower()
        payload = encode_payload(
            StoryboardJobPayload(
                scene_numbers=scene_numbers,
                style=style,
                aspect_ratio=aspect_ratio,
            )
        )
        if backend == "arq":
            job_id = str(uuid4())
            repo = JobRepository()
            await repo.create(
                job_id=job_id,
                status=JobStatus.QUEUED.value,
                project_id=project.id,
                user_id=current_user.id if current_user else None,
                description="storyboard",
                payload=payload,
            )
            await enqueue_storyboard_job(
                job_id=job_id,
                project_id=project.id,
                scene_numbers=scene_numbers,
                style=style,
                aspect_ratio=aspect_ratio,
            )
            response.status_code = status.HTTP_202_ACCEPTED
            return GenerationJobResponse(
                job_id=job_id,
                status=JobStatus.QUEUED,
                project_id=project.id,
                message="Storyboard generation started in background",
            )

        repo = JobRepository()
        job = await job_manager.submit(
            lambda job_id: run_storyboard_for_project(
                project_id=project.id,
                store=store,
                workflow=workflow,
                scene_numbers=scene_numbers,
                style=style,
                aspect_ratio=aspect_ratio,
                job_repo=repo,
                job_id=job_id,
            ),
            description="storyboard",
            project_id=project.id,
            user_id=current_user.id if current_user else None,
            payload=payload,
        )
        response.status_code = status.HTTP_202_ACCEPTED
        return GenerationJobResponse(
            job_id=job.id,
            status=JobStatus.QUEUED,
            project_id=project.id,
            message="Storyboard generation started in background",
        )

    await run_storyboard_for_project(
        project_id=project.id,
        store=store,
        workflow=workflow,
        scene_numbers=scene_numbers,
        style=style,
        aspect_ratio=aspect_ratio,
    )
    project = await store.get(project_id)

    return StoryboardResponse(
        project_id=project.id if project else project_id,
        prompts=project.storyboard_prompts if project else [],
        total_prompts=len(project.storyboard_prompts) if project else 0,
    )


@router.post(
    "/generate",
    response_model=GenerationStatusResponse | GenerationJobResponse,
    responses={
        200: {"description": "Pipeline completed successfully"},
        202: {"description": "Pipeline started in background"},
        404: {"model": ErrorResponse, "description": "Project not found"},
        400: {"model": ErrorResponse, "description": "Script not uploaded"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Run full pipeline",
    description="Run the complete generation pipeline: analysis, shot list, and storyboard.",
)
@limiter.limit(GENERATION_RATE_LIMIT)
async def run_full_pipeline(
    request: Request,
    response: Response,
    project_id: str,
    body: RunPipelineRequest | None = None,
    async_run: bool = Query(
        False, description="Run pipeline in background and return a job ID"
    ),
    store: ProjectStore = Depends(get_project_store),
    workflow: Workflow = Depends(get_workflow),
    current_user: Annotated[UserInDB | None, Depends(require_auth_if_enabled)] = None,
    job_manager=Depends(get_job_manager),
) -> GenerationStatusResponse | GenerationJobResponse:
    """Run the full generation pipeline."""
    project = await store.get(project_id)

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )
    if current_user and not is_admin_user(current_user):
        if project.user_id is None or project.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this project",
            )

    if not project.scenes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Script must be uploaded and parsed before running the pipeline",
        )

    # Get request parameters
    scene_numbers = body.scene_numbers if body else None
    style = body.style if body else project.style_notes
    skip_analysis = body.skip_analysis if body else False
    skip_shots = body.skip_shots if body else False
    skip_storyboard = body.skip_storyboard if body else False

    # Filter scenes
    scenes_to_process = _filter_scenes_by_numbers(project.scenes, scene_numbers)

    if not scenes_to_process:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No matching scenes found for the specified scene numbers",
        )

    async def _execute_pipeline() -> GenerationStatusResponse:
        return await run_pipeline_for_project(
            project_id=project.id,
            store=store,
            workflow=workflow,
            scene_numbers=scene_numbers,
            style=style,
            skip_analysis=skip_analysis,
            skip_shots=skip_shots,
            skip_storyboard=skip_storyboard,
        )

    if async_run:
        payload = encode_payload(
            PipelineJobPayload(
                scene_numbers=scene_numbers,
                style=style,
                skip_analysis=skip_analysis,
                skip_shots=skip_shots,
                skip_storyboard=skip_storyboard,
            )
        )
        backend = os.environ.get("MOVIECON_JOB_BACKEND", "inprocess").lower()
        if backend == "arq":
            job_id = str(uuid4())
            repo = JobRepository()
            await repo.create(
                job_id=job_id,
                status=JobStatus.QUEUED.value,
                project_id=project.id,
                user_id=current_user.id if current_user else None,
                description="full_pipeline",
                payload=payload,
            )
            await enqueue_full_pipeline_job(
                job_id=job_id,
                project_id=project.id,
                scene_numbers=scene_numbers,
                style=style,
                skip_analysis=skip_analysis,
                skip_shots=skip_shots,
                skip_storyboard=skip_storyboard,
            )
            response.status_code = status.HTTP_202_ACCEPTED
            return GenerationJobResponse(
                job_id=job_id,
                status=JobStatus.QUEUED,
                project_id=project.id,
                message="Pipeline started in background",
            )

        repo = JobRepository()
        job = await job_manager.submit(
            lambda job_id: run_pipeline_for_project(
                project_id=project.id,
                store=store,
                workflow=workflow,
                scene_numbers=scene_numbers,
                style=style,
                skip_analysis=skip_analysis,
                skip_shots=skip_shots,
                skip_storyboard=skip_storyboard,
                job_repo=repo,
                job_id=job_id,
            ),
            description="full_pipeline",
            project_id=project.id,
            user_id=current_user.id if current_user else None,
            payload=payload,
        )
        response.status_code = status.HTTP_202_ACCEPTED
        return GenerationJobResponse(
            job_id=job.id,
            status=JobStatus.QUEUED,
            project_id=project.id,
            message="Pipeline started in background",
        )

    try:
        return await _execute_pipeline()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline failed: {str(e)}",
        )


@router.get(
    "/status",
    response_model=GenerationStatusResponse,
    responses={
        200: {"description": "Generation status"},
        404: {"model": ErrorResponse, "description": "Project not found"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Get generation status",
    description="Get the current status of the generation pipeline for a project.",
)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def get_generation_status(
    request: Request,
    response: Response,
    project_id: str,
    store: ProjectStore = Depends(get_project_store),
    current_user: Annotated[UserInDB | None, Depends(require_auth_if_enabled)] = None,
) -> GenerationStatusResponse:
    """Get the generation status for a project."""
    project = await store.get(project_id)

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )
    if current_user and not is_admin_user(current_user):
        if project.user_id is None or project.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this project",
            )

    return GenerationStatusResponse(
        project_id=project.id,
        status=project.status,
        progress=project.progress,
        current_step=project.current_step,
        steps_completed=project.steps_completed,
        error_message=project.error_message,
        started_at=project.processing_started_at,
        completed_at=project.processing_completed_at,
    )
