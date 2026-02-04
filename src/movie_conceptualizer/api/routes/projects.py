"""Project management API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from movie_conceptualizer.api.dependencies import ProjectStore, get_project_store
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
    },
    summary="Create a new project",
    description="Create a new filmmaking project with title, description, genre, and style notes.",
)
async def create_project(
    request: CreateProjectRequest,
    store: ProjectStore = Depends(get_project_store),
) -> ProjectResponse:
    """Create a new project."""
    project = store.create(
        title=request.title,
        description=request.description,
        genre=request.genre,
        style_notes=request.style_notes,
    )

    return ProjectResponse(**project.to_dict())


@router.get(
    "",
    response_model=ProjectListResponse,
    responses={
        200: {"description": "List of all projects"},
    },
    summary="List all projects",
    description="Retrieve a list of all projects with their current status.",
)
async def list_projects(
    store: ProjectStore = Depends(get_project_store),
) -> ProjectListResponse:
    """List all projects."""
    projects = store.list_all()

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
    },
    summary="Get project details",
    description="Retrieve detailed information about a specific project.",
)
async def get_project(
    project_id: str,
    store: ProjectStore = Depends(get_project_store),
) -> ProjectResponse:
    """Get project details by ID."""
    project = store.get(project_id)

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
    },
    summary="Delete a project",
    description="Delete a project and all its associated data.",
)
async def delete_project(
    project_id: str,
    store: ProjectStore = Depends(get_project_store),
) -> None:
    """Delete a project by ID."""
    if not store.exists(project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )

    store.delete(project_id)
