"""Export API routes."""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from movie_conceptualizer.api.dependencies import (
    ProjectStore,
    UserInDB,
    get_project_store,
    is_admin_user,
    require_auth_if_enabled,
)
from movie_conceptualizer.api.ratelimit import DEFAULT_RATE_LIMIT, limiter
from movie_conceptualizer.api.schemas import (
    ErrorResponse,
    ExportFormat,
    ExportResponse,
)

router = APIRouter(prefix="/projects/{project_id}/export", tags=["export"])


@router.get(
    "/shotlist",
    response_model=ExportResponse,
    responses={
        200: {"description": "Shot list exported successfully"},
        404: {"model": ErrorResponse, "description": "Project or shot list not found"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Export shot list",
    description="Export the shot list in JSON or PDF format.",
)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def export_shot_list(
    request: Request,
    response: Response,
    project_id: str,
    format: ExportFormat = Query(ExportFormat.JSON, description="Export format"),
    include_notes: bool = Query(True, description="Include director notes"),
    include_timing: bool = Query(True, description="Include timing estimates"),
    store: ProjectStore = Depends(get_project_store),
    current_user: Annotated[UserInDB | None, Depends(require_auth_if_enabled)] = None,
) -> ExportResponse:
    """Export the shot list for a project."""
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
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No shot list has been generated for this project",
        )

    # Build export data
    shots_data = []
    for shot in project.shots:
        shot_type_value = (
            shot.shot_type.value if hasattr(shot.shot_type, "value") else shot.shot_type
        )
        camera_movement_value = (
            shot.camera_movement.value
            if hasattr(shot.camera_movement, "value")
            else shot.camera_movement
        )
        shot_dict = {
            "shot_number": shot.shot_number,
            "scene_number": shot.scene_number,
            "shot_type": shot_type_value,
            "camera_movement": camera_movement_value,
            "description": shot.description,
            "characters": getattr(shot, "characters", []),
            "action": getattr(shot, "action", None),
            "dialogue": getattr(shot, "dialogue", None),
            "framing_notes": getattr(shot, "framing_notes", None),
            "lens_suggestion": getattr(shot, "lens_suggestion", None),
        }

        if include_timing:
            shot_dict["duration_seconds"] = shot.duration_seconds

        if include_notes:
            shot_dict["notes"] = getattr(shot, "notes", None)

        shots_data.append(shot_dict)

    # Calculate totals
    total_duration = sum(s.duration_seconds or 0 for s in project.shots)

    export_data = {
        "project": {
            "id": project.id,
            "title": project.title,
            "genre": project.genre,
        },
        "shots": shots_data,
        "summary": {
            "total_shots": len(project.shots),
            "scenes_covered": len(set(s.scene_number for s in project.shots)),
        },
    }

    if include_timing:
        export_data["summary"]["estimated_duration_seconds"] = total_duration
        export_data["summary"]["estimated_duration_minutes"] = round(total_duration / 60, 2)

    # Generate filename
    safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in project.title)
    safe_title = safe_title.replace(" ", "_")[:50]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_title}_shotlist_{timestamp}.{format.value}"

    if format == ExportFormat.PDF:
        # For MVP, return a placeholder for PDF - actual PDF generation would require a library
        return ExportResponse(
            project_id=project.id,
            format=format,
            filename=filename,
            data={
                "message": "PDF export not yet implemented in MVP",
                "json_data": export_data,
            },
            generated_at=datetime.now(timezone.utc),
        )

    return ExportResponse(
        project_id=project.id,
        format=format,
        filename=filename,
        data=export_data,
        generated_at=datetime.now(timezone.utc),
    )


@router.get(
    "/storyboard",
    response_model=ExportResponse,
    responses={
        200: {"description": "Storyboard data exported successfully"},
        404: {"model": ErrorResponse, "description": "Project or storyboard not found"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Export storyboard data",
    description="Export the storyboard prompts and data in JSON or PDF format.",
)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def export_storyboard(
    request: Request,
    response: Response,
    project_id: str,
    format: ExportFormat = Query(ExportFormat.JSON, description="Export format"),
    include_prompts: bool = Query(True, description="Include generation prompts"),
    store: ProjectStore = Depends(get_project_store),
    current_user: Annotated[UserInDB | None, Depends(require_auth_if_enabled)] = None,
) -> ExportResponse:
    """Export storyboard data for a project."""
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

    if not project.storyboard_prompts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No storyboard has been generated for this project",
        )

    # Build export data
    frames_data = []
    for prompt in project.storyboard_prompts:
        frame_dict = {
            "shot_number": prompt.shot_number,
            "scene_number": prompt.scene_number,
            "aspect_ratio": prompt.aspect_ratio,
            "composition_notes": prompt.composition_notes,
            "style_reference": prompt.style_reference,
        }

        if include_prompts:
            frame_dict["prompt"] = prompt.prompt
            frame_dict["negative_prompt"] = prompt.negative_prompt

        frames_data.append(frame_dict)

    export_data = {
        "project": {
            "id": project.id,
            "title": project.title,
            "genre": project.genre,
            "style_notes": project.style_notes,
        },
        "frames": frames_data,
        "summary": {
            "total_frames": len(project.storyboard_prompts),
            "scenes_covered": len(set(p.scene_number for p in project.storyboard_prompts)),
        },
    }

    # Add analysis context if available
    if project.overall_tone:
        export_data["context"] = {
            "overall_tone": project.overall_tone,
            "visual_motifs": project.visual_motifs,
        }

    # Generate filename
    safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in project.title)
    safe_title = safe_title.replace(" ", "_")[:50]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_title}_storyboard_{timestamp}.{format.value}"

    if format == ExportFormat.PDF:
        # For MVP, return a placeholder for PDF
        return ExportResponse(
            project_id=project.id,
            format=format,
            filename=filename,
            data={
                "message": "PDF export not yet implemented in MVP",
                "json_data": export_data,
            },
            generated_at=datetime.now(timezone.utc),
        )

    return ExportResponse(
        project_id=project.id,
        format=format,
        filename=filename,
        data=export_data,
        generated_at=datetime.now(timezone.utc),
    )


@router.get(
    "/analysis",
    response_model=ExportResponse,
    responses={
        200: {"description": "Analysis exported successfully"},
        404: {"model": ErrorResponse, "description": "Project or analysis not found"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Export analysis data",
    description="Export the script analysis data in JSON format.",
)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def export_analysis(
    request: Request,
    response: Response,
    project_id: str,
    format: ExportFormat = Query(ExportFormat.JSON, description="Export format"),
    store: ProjectStore = Depends(get_project_store),
    current_user: Annotated[UserInDB | None, Depends(require_auth_if_enabled)] = None,
) -> ExportResponse:
    """Export analysis data for a project."""
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

    if not project.analyses:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No analysis has been performed for this project",
        )

    # Build export data
    analyses_data = []
    for analysis in project.analyses:
        analysis_dict = {
            "scene_number": analysis.scene_number,
            "mood": analysis.mood,
            "themes": analysis.themes,
            "visual_style": analysis.visual_style,
            "pacing": analysis.pacing,
            "key_moments": analysis.key_moments,
            "color_palette": analysis.color_palette,
            "lighting_notes": analysis.lighting_notes,
        }
        analyses_data.append(analysis_dict)

    export_data = {
        "project": {
            "id": project.id,
            "title": project.title,
            "genre": project.genre,
        },
        "overall": {
            "tone": project.overall_tone,
            "visual_motifs": project.visual_motifs,
        },
        "scene_analyses": analyses_data,
        "summary": {
            "scenes_analyzed": len(project.analyses),
        },
    }

    # Generate filename
    safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in project.title)
    safe_title = safe_title.replace(" ", "_")[:50]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_title}_analysis_{timestamp}.{format.value}"

    if format == ExportFormat.PDF:
        return ExportResponse(
            project_id=project.id,
            format=format,
            filename=filename,
            data={
                "message": "PDF export not yet implemented in MVP",
                "json_data": export_data,
            },
            generated_at=datetime.now(timezone.utc),
        )

    return ExportResponse(
        project_id=project.id,
        format=format,
        filename=filename,
        data=export_data,
        generated_at=datetime.now(timezone.utc),
    )
