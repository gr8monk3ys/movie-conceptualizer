"""Project management API routes."""

from fastapi import APIRouter, Depends, HTTPException, Request, status

from movie_conceptualizer.api.dependencies import ProjectStore, get_project_store
from movie_conceptualizer.api.ratelimit import DEFAULT_RATE_LIMIT, limiter
from movie_conceptualizer.api.schemas import (
    CreateProjectRequest,
    ErrorResponse,
    ProjectListResponse,
    ProjectResponse,
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Project created successfully"},
        422: {"description": "Validation error"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Create a new project",
    description="Create a new filmmaking project with title, description, genre, and style notes.",
)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def create_project(
    request: Request,
    body: CreateProjectRequest,
    store: ProjectStore = Depends(get_project_store),
) -> ProjectResponse:
    """Create a new project."""
    project = await store.create(
        title=body.title,
        description=body.description,
        genre=body.genre,
        style_notes=body.style_notes,
    )

    return ProjectResponse(**project.to_dict())


@router.get(
    "",
    response_model=ProjectListResponse,
    responses={
        200: {"description": "List of all projects"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="List all projects",
    description="Retrieve a list of all projects with their current status.",
)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def list_projects(
    request: Request,
    store: ProjectStore = Depends(get_project_store),
) -> ProjectListResponse:
    """List all projects."""
    projects = await store.list_all()

    return ProjectListResponse(
        projects=[ProjectResponse(**p.to_dict()) for p in projects],
        total=len(projects),
    )


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    responses={
        200: {"description": "Project details"},
        404: {"model": ErrorResponse, "description": "Project not found"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Get project details",
    description="Retrieve detailed information about a specific project.",
)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def get_project(
    request: Request,
    project_id: str,
    store: ProjectStore = Depends(get_project_store),
) -> ProjectResponse:
    """Get project details by ID."""
    project = await store.get(project_id)

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )

    return ProjectResponse(**project.to_dict())


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "Project deleted successfully"},
        404: {"model": ErrorResponse, "description": "Project not found"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Delete a project",
    description="Delete a project and all its associated data.",
)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def delete_project(
    request: Request,
    project_id: str,
    store: ProjectStore = Depends(get_project_store),
) -> None:
    """Delete a project by ID."""
    if not await store.exists(project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )

    await store.delete(project_id)
