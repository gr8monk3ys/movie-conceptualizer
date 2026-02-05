"""Project management API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from movie_conceptualizer.api.dependencies import (
    ProjectStore,
    UserInDB,
    get_project_store,
    is_admin_user,
    require_auth_if_enabled,
)
from movie_conceptualizer.api.ratelimit import DEFAULT_RATE_LIMIT, limiter
from movie_conceptualizer.api.schemas import (
    AssignProjectOwnerRequest,
    BulkAssignProjectOwnerRequest,
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
    response: Response,
    body: CreateProjectRequest,
    store: ProjectStore = Depends(get_project_store),
    current_user: Annotated[UserInDB | None, Depends(require_auth_if_enabled)] = None,
) -> ProjectResponse:
    """Create a new project."""
    project = await store.create(
        title=body.title,
        description=body.description,
        genre=body.genre,
        style_notes=body.style_notes,
        user_id=current_user.id if current_user else None,
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
    response: Response,
    store: ProjectStore = Depends(get_project_store),
    current_user: Annotated[UserInDB | None, Depends(require_auth_if_enabled)] = None,
) -> ProjectListResponse:
    """List all projects."""
    if current_user and not is_admin_user(current_user):
        projects = await store.list_all(user_id=current_user.id)
    else:
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
    response: Response,
    project_id: str,
    store: ProjectStore = Depends(get_project_store),
    current_user: Annotated[UserInDB | None, Depends(require_auth_if_enabled)] = None,
) -> ProjectResponse:
    """Get project details by ID."""
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
    response: Response,
    project_id: str,
    store: ProjectStore = Depends(get_project_store),
    current_user: Annotated[UserInDB | None, Depends(require_auth_if_enabled)] = None,
) -> None:
    """Delete a project by ID."""
    if not await store.exists(project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )

    if current_user and not is_admin_user(current_user):
        project = await store.get(project_id)
        if project is None or project.user_id is None or project.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this project",
            )

    await store.delete(project_id)


@router.post(
    "/{project_id}/owner",
    responses={
        200: {"description": "Owner assigned"},
        404: {"model": ErrorResponse, "description": "Project not found"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Assign project owner",
    description="Assign an owner to a project (admin only).",
)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def assign_project_owner(
    request: Request,
    response: Response,
    project_id: str,
    body: AssignProjectOwnerRequest,
    store: ProjectStore = Depends(get_project_store),
    current_user: Annotated[UserInDB, Depends(require_auth_if_enabled)] = None,
) -> dict:
    if current_user is None or not is_admin_user(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    if not await store.exists(project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )

    updated = await store.assign_owner(project_id, body.user_id)
    return {"project_id": project_id, "user_id": body.user_id, "updated": updated}


@router.post(
    "/owner/bulk-assign",
    responses={
        200: {"description": "Owners assigned"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Bulk assign project owners",
    description="Bulk assign a user as owner to projects (admin only).",
)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def bulk_assign_project_owner(
    request: Request,
    response: Response,
    body: BulkAssignProjectOwnerRequest,
    store: ProjectStore = Depends(get_project_store),
    current_user: Annotated[UserInDB, Depends(require_auth_if_enabled)] = None,
) -> dict:
    if current_user is None or not is_admin_user(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    updated = await store.bulk_assign_owner(
        user_id=body.user_id,
        only_unassigned=body.only_unassigned,
    )
    return {
        "user_id": body.user_id,
        "only_unassigned": body.only_unassigned,
        "updated": updated,
    }
