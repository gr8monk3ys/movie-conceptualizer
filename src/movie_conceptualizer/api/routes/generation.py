"""AI generation API routes."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status

from movie_conceptualizer.api.dependencies import (
    MockWorkflow,
    ProjectStore,
    get_project_store,
    get_workflow,
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
    GenerateShotsRequest,
    GenerateStoryboardRequest,
    GenerationStatusResponse,
    ProjectStatus,
    RunPipelineRequest,
    ShotListResponse,
    StoryboardResponse,
)

router = APIRouter(prefix="/projects/{project_id}", tags=["generation"])


def _filter_scenes_by_numbers(scenes: list, scene_numbers: list[int] | None) -> list:
    """Filter scenes by scene numbers if provided."""
    if scene_numbers is None:
        return scenes
    return [s for s in scenes if s.scene_number in scene_numbers]


@router.post(
    "/analyze",
    response_model=AnalysisResponse,
    responses={
        200: {"description": "Analysis completed successfully"},
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
    project_id: str,
    body: AnalysisRequest | None = None,
    store: ProjectStore = Depends(get_project_store),
    workflow: MockWorkflow = Depends(get_workflow),
) -> AnalysisResponse:
    """Run script analysis."""
    project = await store.get(project_id)

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
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

    # Update status
    project.status = ProjectStatus.ANALYZING
    project.current_step = "Analyzing scenes"
    project.update()
    await store.update_project(project)

    # Run analysis
    analyses, overall_tone, visual_motifs = await workflow.analyze_scenes(
        scenes_to_analyze, project.genre
    )

    # Store results
    project.analyses = analyses
    project.overall_tone = overall_tone
    project.visual_motifs = visual_motifs
    project.status = ProjectStatus.ANALYZED
    project.current_step = None
    project.steps_completed.append("analysis")
    project.update()

    # Save to database
    await store.save_analyses(project_id, analyses, overall_tone, visual_motifs)
    await store.update_project(project)

    return AnalysisResponse(
        project_id=project.id,
        analyses=project.analyses,
        overall_tone=project.overall_tone,
        visual_motifs=project.visual_motifs,
    )


@router.post(
    "/shots",
    response_model=ShotListResponse,
    responses={
        200: {"description": "Shot list generated successfully"},
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
    project_id: str,
    body: GenerateShotsRequest | None = None,
    store: ProjectStore = Depends(get_project_store),
    workflow: MockWorkflow = Depends(get_workflow),
) -> ShotListResponse:
    """Generate shot list for the project."""
    project = await store.get(project_id)

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
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

    # Update status
    project.status = ProjectStatus.GENERATING_SHOTS
    project.current_step = "Generating shot list"
    project.update()
    await store.update_project(project)

    # Generate shots
    shots = await workflow.generate_shots(
        scenes_to_process,
        project.analyses if project.analyses else None,
        style,
        shots_per_scene,
    )

    # Store results
    project.shots = shots
    project.status = ProjectStatus.SHOTS_GENERATED
    project.current_step = None
    project.steps_completed.append("shot_generation")
    project.update()

    # Save to database
    await store.save_shots(project_id, shots, style)
    await store.update_project(project)

    # Calculate estimated duration
    total_duration = sum(s.duration_seconds or 0 for s in shots)

    return ShotListResponse(
        project_id=project.id,
        shots=project.shots,
        total_shots=len(project.shots),
        estimated_duration=total_duration if total_duration > 0 else None,
    )


@router.post(
    "/storyboard",
    response_model=StoryboardResponse,
    responses={
        200: {"description": "Storyboard prompts generated successfully"},
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
    project_id: str,
    body: GenerateStoryboardRequest | None = None,
    store: ProjectStore = Depends(get_project_store),
    workflow: MockWorkflow = Depends(get_workflow),
) -> StoryboardResponse:
    """Generate storyboard prompts for the project."""
    project = await store.get(project_id)

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
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

    # Update status
    project.status = ProjectStatus.GENERATING_STORYBOARD
    project.current_step = "Generating storyboard prompts"
    project.update()
    await store.update_project(project)

    # Generate storyboard prompts
    prompts = await workflow.generate_storyboard_prompts(
        shots_to_process,
        style,
        aspect_ratio,
    )

    # Store results
    project.storyboard_prompts = prompts
    project.status = ProjectStatus.COMPLETED
    project.current_step = None
    project.steps_completed.append("storyboard_generation")
    project.processing_completed_at = datetime.utcnow()
    project.update()

    # Save to database
    await store.save_storyboard(project_id, prompts, style, aspect_ratio)
    await store.update_project(project)

    return StoryboardResponse(
        project_id=project.id,
        prompts=project.storyboard_prompts,
        total_prompts=len(project.storyboard_prompts),
    )


@router.post(
    "/generate",
    response_model=GenerationStatusResponse,
    responses={
        200: {"description": "Pipeline completed successfully"},
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
    project_id: str,
    body: RunPipelineRequest | None = None,
    store: ProjectStore = Depends(get_project_store),
    workflow: MockWorkflow = Depends(get_workflow),
) -> GenerationStatusResponse:
    """Run the full generation pipeline."""
    project = await store.get(project_id)

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
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

    # Initialize processing
    project.processing_started_at = datetime.utcnow()
    project.progress = 0.0
    project.steps_completed = []
    project.error_message = None

    try:
        # Step 1: Analysis
        if not skip_analysis:
            project.status = ProjectStatus.ANALYZING
            project.current_step = "Analyzing scenes"
            project.progress = 10.0
            project.update()
            await store.update_project(project)

            analyses, overall_tone, visual_motifs = await workflow.analyze_scenes(
                scenes_to_process, project.genre
            )
            project.analyses = analyses
            project.overall_tone = overall_tone
            project.visual_motifs = visual_motifs
            project.steps_completed.append("analysis")
            project.progress = 33.0

            # Save analyses to database
            await store.save_analyses(project_id, analyses, overall_tone, visual_motifs)

        # Step 2: Shot Generation
        if not skip_shots:
            project.status = ProjectStatus.GENERATING_SHOTS
            project.current_step = "Generating shot list"
            project.progress = 40.0
            project.update()
            await store.update_project(project)

            shots = await workflow.generate_shots(
                scenes_to_process,
                project.analyses if project.analyses else None,
                style,
            )
            project.shots = shots
            project.steps_completed.append("shot_generation")
            project.progress = 66.0

            # Save shots to database
            await store.save_shots(project_id, shots, style)

        # Step 3: Storyboard Prompts
        if not skip_storyboard and project.shots:
            project.status = ProjectStatus.GENERATING_STORYBOARD
            project.current_step = "Generating storyboard prompts"
            project.progress = 75.0
            project.update()
            await store.update_project(project)

            # Filter shots for specified scenes
            shots_to_process = project.shots
            if scene_numbers:
                shots_to_process = [s for s in project.shots if s.scene_number in scene_numbers]

            prompts = await workflow.generate_storyboard_prompts(
                shots_to_process,
                style,
            )
            project.storyboard_prompts = prompts
            project.steps_completed.append("storyboard_generation")

            # Save storyboard to database
            await store.save_storyboard(project_id, prompts, style)

        # Complete
        project.status = ProjectStatus.COMPLETED
        project.current_step = None
        project.progress = 100.0
        project.processing_completed_at = datetime.utcnow()
        project.update()
        await store.update_project(project)

    except Exception as e:
        project.status = ProjectStatus.ERROR
        project.error_message = str(e)
        project.current_step = None
        project.update()
        await store.update_project(project)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline failed: {str(e)}",
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
    project_id: str,
    store: ProjectStore = Depends(get_project_store),
) -> GenerationStatusResponse:
    """Get the generation status for a project."""
    project = await store.get(project_id)

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
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
