"""Shared generation pipeline runner for API and workers."""

from __future__ import annotations

from datetime import UTC, datetime

from movie_conceptualizer.api.dependencies import ProjectStore, Workflow
from movie_conceptualizer.api.schemas import GenerationStatusResponse, ProjectStatus
from movie_conceptualizer.storage import JobRepository


async def _update_job_progress(
    job_repo: JobRepository | None,
    job_id: str | None,
    progress: float,
    current_step: str | None,
) -> None:
    if job_repo is None or job_id is None:
        return
    await job_repo.update_progress(job_id, progress, current_step)


async def run_pipeline_for_project(
    project_id: str,
    store: ProjectStore,
    workflow: Workflow,
    scene_numbers: list[int] | None = None,
    style: str | None = None,
    skip_analysis: bool = False,
    skip_shots: bool = False,
    skip_storyboard: bool = False,
    job_repo: JobRepository | None = None,
    job_id: str | None = None,
) -> GenerationStatusResponse:
    """Run the pipeline for a project and persist results."""
    project = await store.get(project_id)
    if project is None:
        raise ValueError(f"Project with ID '{project_id}' not found")

    if not project.scenes:
        raise ValueError("Script must be uploaded and parsed before running the pipeline")

    scenes_to_process = (
        [s for s in project.scenes if s.scene_number in scene_numbers]
        if scene_numbers
        else project.scenes
    )

    if not scenes_to_process:
        raise ValueError("No matching scenes found for the specified scene numbers")

    project.processing_started_at = datetime.now(UTC)
    project.progress = 0.0
    project.steps_completed = []
    project.error_message = None

    # Step 1: Analysis
    if not skip_analysis:
        project.status = ProjectStatus.ANALYZING
        project.current_step = "Analyzing scenes"
        project.progress = 10.0
        project.update()
        await store.update_project(project)
        await _update_job_progress(job_repo, job_id, project.progress, project.current_step)

        analyses, overall_tone, visual_motifs = await workflow.analyze_scenes(
            scenes_to_process, project.genre
        )
        project.analyses = analyses
        project.overall_tone = overall_tone
        project.visual_motifs = visual_motifs
        project.steps_completed.append("analysis")
        project.progress = 33.0

        await store.save_analyses(project_id, analyses, overall_tone, visual_motifs)
        await _update_job_progress(job_repo, job_id, project.progress, project.current_step)

    # Step 2: Shot Generation
    if not skip_shots:
        project.status = ProjectStatus.GENERATING_SHOTS
        project.current_step = "Generating shot list"
        project.progress = 40.0
        project.update()
        await store.update_project(project)
        await _update_job_progress(job_repo, job_id, project.progress, project.current_step)

        shots = await workflow.generate_shots(
            scenes_to_process,
            project.analyses if project.analyses else None,
            style,
        )
        project.shots = shots
        project.steps_completed.append("shot_generation")
        project.progress = 66.0

        await store.save_shots(project_id, shots, style)
        await _update_job_progress(job_repo, job_id, project.progress, project.current_step)

    # Step 3: Storyboard Prompts
    if not skip_storyboard and project.shots:
        project.status = ProjectStatus.GENERATING_STORYBOARD
        project.current_step = "Generating storyboard prompts"
        project.progress = 75.0
        project.update()
        await store.update_project(project)
        await _update_job_progress(job_repo, job_id, project.progress, project.current_step)

        shots_to_process = project.shots
        if scene_numbers:
            shots_to_process = [s for s in project.shots if s.scene_number in scene_numbers]

        prompts = await workflow.generate_storyboard_prompts(
            shots_to_process,
            style,
            scenes=scenes_to_process,
            analyses=project.analyses,
        )
        project.storyboard_prompts = prompts
        project.steps_completed.append("storyboard_generation")

        await store.save_storyboard(project_id, prompts, style)
        await _update_job_progress(job_repo, job_id, project.progress, project.current_step)

    project.status = ProjectStatus.COMPLETED
    project.current_step = None
    project.progress = 100.0
    project.processing_completed_at = datetime.now(UTC)
    project.update()
    await store.update_project(project)
    await _update_job_progress(job_repo, job_id, project.progress, project.current_step)

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


async def run_analysis_for_project(
    project_id: str,
    store: ProjectStore,
    workflow: Workflow,
    scene_numbers: list[int] | None = None,
    job_repo: JobRepository | None = None,
    job_id: str | None = None,
) -> GenerationStatusResponse:
    project = await store.get(project_id)
    if project is None:
        raise ValueError(f"Project with ID '{project_id}' not found")

    if not project.scenes:
        raise ValueError("Script must be uploaded and parsed before analysis")

    scenes_to_process = (
        [s for s in project.scenes if s.scene_number in scene_numbers]
        if scene_numbers
        else project.scenes
    )

    if not scenes_to_process:
        raise ValueError("No matching scenes found for the specified scene numbers")

    project.status = ProjectStatus.ANALYZING
    project.current_step = "Analyzing scenes"
    project.progress = 10.0
    project.update()
    await store.update_project(project)
    await _update_job_progress(job_repo, job_id, project.progress, project.current_step)

    analyses, overall_tone, visual_motifs = await workflow.analyze_scenes(
        scenes_to_process, project.genre
    )
    project.analyses = analyses
    project.overall_tone = overall_tone
    project.visual_motifs = visual_motifs
    project.steps_completed.append("analysis")
    project.status = ProjectStatus.ANALYZED
    project.current_step = None
    project.progress = 100.0
    project.update()

    await store.save_analyses(project_id, analyses, overall_tone, visual_motifs)
    await store.update_project(project)
    await _update_job_progress(job_repo, job_id, project.progress, project.current_step)

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


async def run_shots_for_project(
    project_id: str,
    store: ProjectStore,
    workflow: Workflow,
    scene_numbers: list[int] | None = None,
    style: str | None = None,
    shots_per_scene: int | None = None,
    job_repo: JobRepository | None = None,
    job_id: str | None = None,
) -> GenerationStatusResponse:
    project = await store.get(project_id)
    if project is None:
        raise ValueError(f"Project with ID '{project_id}' not found")

    if not project.scenes:
        raise ValueError("Script must be uploaded and parsed before generating shots")

    scenes_to_process = (
        [s for s in project.scenes if s.scene_number in scene_numbers]
        if scene_numbers
        else project.scenes
    )

    if not scenes_to_process:
        raise ValueError("No matching scenes found for the specified scene numbers")

    project.status = ProjectStatus.GENERATING_SHOTS
    project.current_step = "Generating shot list"
    project.progress = 40.0
    project.update()
    await store.update_project(project)
    await _update_job_progress(job_repo, job_id, project.progress, project.current_step)

    shots = await workflow.generate_shots(
        scenes_to_process,
        project.analyses if project.analyses else None,
        style,
        shots_per_scene,
    )
    project.shots = shots
    project.steps_completed.append("shot_generation")
    project.status = ProjectStatus.SHOTS_GENERATED
    project.current_step = None
    project.progress = 100.0
    project.update()

    await store.save_shots(project_id, shots, style)
    await store.update_project(project)
    await _update_job_progress(job_repo, job_id, project.progress, project.current_step)

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


async def run_storyboard_for_project(
    project_id: str,
    store: ProjectStore,
    workflow: Workflow,
    scene_numbers: list[int] | None = None,
    style: str | None = None,
    aspect_ratio: str = "16:9",
    job_repo: JobRepository | None = None,
    job_id: str | None = None,
) -> GenerationStatusResponse:
    project = await store.get(project_id)
    if project is None:
        raise ValueError(f"Project with ID '{project_id}' not found")

    if not project.shots:
        raise ValueError("Shot list must be generated before creating storyboard prompts")

    shots_to_process = project.shots
    if scene_numbers:
        shots_to_process = [s for s in project.shots if s.scene_number in scene_numbers]

    if not shots_to_process:
        raise ValueError("No matching shots found for the specified scene numbers")

    project.status = ProjectStatus.GENERATING_STORYBOARD
    project.current_step = "Generating storyboard prompts"
    project.progress = 75.0
    project.update()
    await store.update_project(project)
    await _update_job_progress(job_repo, job_id, project.progress, project.current_step)

    prompts = await workflow.generate_storyboard_prompts(
        shots_to_process,
        style,
        aspect_ratio,
        scenes=project.scenes,
        analyses=project.analyses,
    )

    project.storyboard_prompts = prompts
    project.status = ProjectStatus.COMPLETED
    project.current_step = None
    project.progress = 100.0
    project.processing_completed_at = datetime.now(UTC)
    project.update()

    await store.save_storyboard(project_id, prompts, style, aspect_ratio)
    await store.update_project(project)
    await _update_job_progress(job_repo, job_id, project.progress, project.current_step)

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
