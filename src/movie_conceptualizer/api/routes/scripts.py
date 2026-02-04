"""Script handling API routes."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from movie_conceptualizer.api.dependencies import (
    MockWorkflow,
    ProjectStore,
    get_project_store,
    get_workflow,
)
from movie_conceptualizer.api.schemas import (
    ErrorResponse,
    ParseScriptRequest,
    ProjectStatus,
    ScriptResponse,
    UploadScriptRequest,
)

router = APIRouter(prefix="/projects/{project_id}", tags=["scripts"])


@router.post(
    "/script",
    response_model=ScriptResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Script uploaded successfully"},
        404: {"model": ErrorResponse, "description": "Project not found"},
        422: {"description": "Validation error"},
    },
    summary="Upload script",
    description="Upload a screenplay script as text content.",
)
async def upload_script(
    project_id: str,
    request: UploadScriptRequest,
    store: ProjectStore = Depends(get_project_store),
    workflow: MockWorkflow = Depends(get_workflow),
) -> ScriptResponse:
    """Upload a script to a project."""
    project = store.get(project_id)

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )

    # Store the script content
    project.script_content = request.content
    project.script_format = request.format
    project.status = ProjectStatus.SCRIPT_UPLOADED
    project.update()

    # Automatically parse the script
    project.status = ProjectStatus.PARSING
    scenes, title, author = await workflow.parse_script(request.content, request.format)

    project.scenes = scenes
    project.script_title = title
    project.script_author = author
    project.status = ProjectStatus.PARSED
    project.update()

    return ScriptResponse(
        project_id=project.id,
        title=project.script_title,
        author=project.script_author,
        format=project.script_format or "fountain",
        scene_count=len(project.scenes),
        scenes=project.scenes,
        raw_content=project.script_content,
    )


@router.post(
    "/script/upload",
    response_model=ScriptResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Script file uploaded successfully"},
        404: {"model": ErrorResponse, "description": "Project not found"},
        400: {"model": ErrorResponse, "description": "Invalid file"},
    },
    summary="Upload script file",
    description="Upload a screenplay script as a file (supports .txt, .fountain, .fdx).",
)
async def upload_script_file(
    project_id: str,
    file: UploadFile = File(..., description="Script file to upload"),
    store: ProjectStore = Depends(get_project_store),
    workflow: MockWorkflow = Depends(get_workflow),
) -> ScriptResponse:
    """Upload a script file to a project."""
    project = store.get(project_id)

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )

    # Validate file type
    allowed_extensions = {".txt", ".fountain", ".fdx"}
    filename = file.filename or "unknown"
    file_ext = "." + filename.split(".")[-1].lower() if "." in filename else ""

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}",
        )

    # Read file content
    try:
        content = await file.read()
        script_content = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to decode file. Please ensure it is UTF-8 encoded text.",
        )

    # Determine format
    script_format = "fountain" if file_ext in {".fountain", ".txt"} else "fdx"

    # Store the script content
    project.script_content = script_content
    project.script_format = script_format
    project.status = ProjectStatus.SCRIPT_UPLOADED
    project.update()

    # Automatically parse the script
    project.status = ProjectStatus.PARSING
    scenes, title, author = await workflow.parse_script(script_content, script_format)

    project.scenes = scenes
    project.script_title = title
    project.script_author = author
    project.status = ProjectStatus.PARSED
    project.update()

    return ScriptResponse(
        project_id=project.id,
        title=project.script_title,
        author=project.script_author,
        format=project.script_format or "fountain",
        scene_count=len(project.scenes),
        scenes=project.scenes,
        raw_content=project.script_content,
    )


@router.get(
    "/script",
    response_model=ScriptResponse,
    responses={
        200: {"description": "Script data"},
        404: {"model": ErrorResponse, "description": "Project or script not found"},
    },
    summary="Get parsed script",
    description="Retrieve the parsed script data including scenes.",
)
async def get_script(
    project_id: str,
    store: ProjectStore = Depends(get_project_store),
) -> ScriptResponse:
    """Get the parsed script for a project."""
    project = store.get(project_id)

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )

    if not project.has_script:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No script has been uploaded for this project",
        )

    return ScriptResponse(
        project_id=project.id,
        title=project.script_title,
        author=project.script_author,
        format=project.script_format or "fountain",
        scene_count=len(project.scenes),
        scenes=project.scenes,
        raw_content=project.script_content,
    )


@router.post(
    "/script/parse",
    response_model=ScriptResponse,
    responses={
        200: {"description": "Script parsed successfully"},
        404: {"model": ErrorResponse, "description": "Project or script not found"},
    },
    summary="Trigger script parsing",
    description="Re-parse the uploaded script. Useful after modifications.",
)
async def parse_script(
    project_id: str,
    request: ParseScriptRequest | None = None,
    store: ProjectStore = Depends(get_project_store),
    workflow: MockWorkflow = Depends(get_workflow),
) -> ScriptResponse:
    """Trigger script parsing."""
    project = store.get(project_id)

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )

    if not project.has_script:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No script has been uploaded for this project",
        )

    # Check if already parsed and force_reparse is False
    force_reparse = request.force_reparse if request else False
    if project.scenes and not force_reparse:
        return ScriptResponse(
            project_id=project.id,
            title=project.script_title,
            author=project.script_author,
            format=project.script_format or "fountain",
            scene_count=len(project.scenes),
            scenes=project.scenes,
            raw_content=project.script_content,
        )

    # Parse the script
    project.status = ProjectStatus.PARSING
    scenes, title, author = await workflow.parse_script(
        project.script_content or "",
        project.script_format or "fountain",
    )

    project.scenes = scenes
    project.script_title = title
    project.script_author = author
    project.status = ProjectStatus.PARSED
    project.update()

    return ScriptResponse(
        project_id=project.id,
        title=project.script_title,
        author=project.script_author,
        format=project.script_format or "fountain",
        scene_count=len(project.scenes),
        scenes=project.scenes,
        raw_content=project.script_content,
    )
