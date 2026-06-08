"""Script handling API routes."""

import os
import shutil
import subprocess
import tempfile
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)

from movie_conceptualizer.api.dependencies import (
    ProjectStore,
    UserInDB,
    Workflow,
    get_project_store,
    get_workflow,
    is_admin_user,
    require_auth_if_enabled,
)
from movie_conceptualizer.api.jobs import get_job_manager
from movie_conceptualizer.api.ratelimit import DEFAULT_RATE_LIMIT, limiter
from movie_conceptualizer.api.schemas import (
    ErrorResponse,
    GenerationJobResponse,
    JobStatus,
    ParseScriptRequest,
    ProjectStatus,
    ScriptResponse,
    UploadScriptRequest,
)
from movie_conceptualizer.parsers import (
    ScriptLoadError,
    coerce_pdf_text_to_fountain,
    extract_text_from_pdf_bytes,
)

router = APIRouter(prefix="/projects/{project_id}", tags=["scripts"])


def _max_upload_bytes() -> int:
    max_mb = float(os.environ.get("MOVIECON_MAX_UPLOAD_MB", "25"))
    return int(max_mb * 1024 * 1024)


def _scan_upload(content: bytes, filename: str) -> None:
    scan_mode = os.environ.get("MOVIECON_AV_SCAN", "").lower().strip()
    if not scan_mode:
        return
    if scan_mode != "clamav":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported AV scan mode: {scan_mode}",
        )
    if shutil.which("clamscan") is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="clamscan not available for AV scanning",
        )
    with tempfile.NamedTemporaryFile(delete=True) as tmp:
        tmp.write(content)
        tmp.flush()
        result = subprocess.run(
            ["clamscan", "--no-summary", tmp.name],
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Upload failed AV scan: {filename}",
        )


async def _process_script_upload(
    project_id: str,
    store: ProjectStore,
    workflow: Workflow,
    script_content: str,
    script_format: str,
) -> ScriptResponse:
    project = await store.get(project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )

    project.script_content = script_content
    project.script_format = script_format
    project.status = ProjectStatus.SCRIPT_UPLOADED
    project.update()

    await store.save_script(project_id, script_content, script_format)
    await store.update_project(project)

    project.status = ProjectStatus.PARSING
    scenes, title, author = await workflow.parse_script(script_content, script_format)

    project.scenes = scenes
    project.script_title = title
    project.script_author = author
    project.status = ProjectStatus.PARSED
    project.update()

    await store.save_scenes(project_id, scenes)
    await store.update_script_info(project_id, title, author)
    await store.update_project(project)

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
    "/script",
    response_model=ScriptResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Script uploaded successfully"},
        404: {"model": ErrorResponse, "description": "Project not found"},
        422: {"description": "Validation error"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Upload script",
    description="Upload a screenplay script as text content.",
)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def upload_script(
    request: Request,
    response: Response,
    project_id: str,
    body: UploadScriptRequest,
    store: ProjectStore = Depends(get_project_store),
    workflow: Workflow = Depends(get_workflow),
    current_user: Annotated[UserInDB | None, Depends(require_auth_if_enabled)] = None,
) -> ScriptResponse:
    """Upload a script to a project."""
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

    content_bytes = body.content.encode("utf-8", errors="ignore")
    if len(content_bytes) > _max_upload_bytes():
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Upload exceeds size limit",
        )

    return await _process_script_upload(
        project_id=project_id,
        store=store,
        workflow=workflow,
        script_content=body.content,
        script_format=body.format,
    )


@router.post(
    "/script/upload",
    response_model=ScriptResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Script file uploaded successfully"},
        404: {"model": ErrorResponse, "description": "Project not found"},
        400: {"model": ErrorResponse, "description": "Invalid file"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Upload script file",
    description="Upload a screenplay script as a file (supports .txt, .fountain, .fdx, .pdf).",
)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def upload_script_file(
    request: Request,
    response: Response,
    project_id: str,
    file: UploadFile = File(..., description="Script file to upload"),
    store: ProjectStore = Depends(get_project_store),
    workflow: Workflow = Depends(get_workflow),
    current_user: Annotated[UserInDB | None, Depends(require_auth_if_enabled)] = None,
) -> ScriptResponse:
    """Upload a script file to a project."""
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

    # Validate file type
    allowed_extensions = {".txt", ".fountain", ".fdx", ".pdf"}
    filename = file.filename or "unknown"
    file_ext = "." + filename.split(".")[-1].lower() if "." in filename else ""

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}",
        )

    # Read file content
    content = await file.read()
    if len(content) > _max_upload_bytes():
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Upload exceeds size limit",
        )
    _scan_upload(content, filename)
    if file_ext == ".pdf":
        try:
            script_content = extract_text_from_pdf_bytes(content)
            script_content = coerce_pdf_text_to_fountain(script_content)
        except ScriptLoadError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
    else:
        try:
            script_content = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unable to decode file. Please ensure it is UTF-8 encoded text.",
            ) from exc

    # Determine format
    if file_ext in {".fountain", ".txt"}:
        script_format = "fountain"
    elif file_ext == ".fdx":
        script_format = "fdx"
    else:
        script_format = "pdf"

    return await _process_script_upload(
        project_id=project_id,
        store=store,
        workflow=workflow,
        script_content=script_content,
        script_format=script_format,
    )


@router.post(
    "/script/upload/async",
    response_model=GenerationJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        202: {"description": "Script upload started in background"},
        404: {"model": ErrorResponse, "description": "Project not found"},
        400: {"model": ErrorResponse, "description": "Invalid file"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Upload script file (async)",
    description="Upload a screenplay script as a file and parse it in the background.",
)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def upload_script_file_async(
    request: Request,
    response: Response,
    project_id: str,
    file: UploadFile = File(..., description="Script file to upload"),
    store: ProjectStore = Depends(get_project_store),
    workflow: Workflow = Depends(get_workflow),
    job_manager=Depends(get_job_manager),
    current_user: Annotated[UserInDB | None, Depends(require_auth_if_enabled)] = None,
) -> GenerationJobResponse:
    """Upload a script file asynchronously."""
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

    allowed_extensions = {".txt", ".fountain", ".fdx", ".pdf"}
    filename = file.filename or "unknown"
    file_ext = "." + filename.split(".")[-1].lower() if "." in filename else ""

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}",
        )

    content = await file.read()
    if len(content) > _max_upload_bytes():
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Upload exceeds size limit",
        )
    _scan_upload(content, filename)

    async def _run_upload(job_id: str) -> None:
        if file_ext == ".pdf":
            script_content = extract_text_from_pdf_bytes(content)
            script_content = coerce_pdf_text_to_fountain(script_content)
            script_format = "pdf"
        else:
            try:
                script_content = content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Unable to decode file. Please ensure it is UTF-8 encoded text.",
                ) from exc
            script_format = "fountain" if file_ext in {".fountain", ".txt"} else "fdx"

        await _process_script_upload(
            project_id=project_id,
            store=store,
            workflow=workflow,
            script_content=script_content,
            script_format=script_format,
        )

    job = await job_manager.submit(
        lambda job_id: _run_upload(job_id),
        description="script_upload",
        project_id=project_id,
        user_id=current_user.id if current_user else None,
    )

    response.status_code = status.HTTP_202_ACCEPTED
    return GenerationJobResponse(
        job_id=job.id,
        status=JobStatus.QUEUED,
        project_id=project_id,
        message="Script upload started in background",
    )


@router.get(
    "/script",
    response_model=ScriptResponse,
    responses={
        200: {"description": "Script data"},
        404: {"model": ErrorResponse, "description": "Project or script not found"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Get parsed script",
    description="Retrieve the parsed script data including scenes.",
)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def get_script(
    request: Request,
    response: Response,
    project_id: str,
    store: ProjectStore = Depends(get_project_store),
    current_user: Annotated[UserInDB | None, Depends(require_auth_if_enabled)] = None,
) -> ScriptResponse:
    """Get the parsed script for a project."""
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
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Trigger script parsing",
    description="Re-parse the uploaded script. Useful after modifications.",
)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def parse_script(
    request: Request,
    response: Response,
    project_id: str,
    body: ParseScriptRequest | None = None,
    store: ProjectStore = Depends(get_project_store),
    workflow: Workflow = Depends(get_workflow),
    current_user: Annotated[UserInDB | None, Depends(require_auth_if_enabled)] = None,
) -> ScriptResponse:
    """Trigger script parsing."""
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

    if not project.has_script:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No script has been uploaded for this project",
        )

    # Check if already parsed and force_reparse is False
    force_reparse = body.force_reparse if body else False
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

    # Save parsed data to database
    await store.save_scenes(project_id, scenes)
    await store.update_script_info(project_id, title, author)
    await store.update_project(project)

    return ScriptResponse(
        project_id=project.id,
        title=project.script_title,
        author=project.script_author,
        format=project.script_format or "fountain",
        scene_count=len(project.scenes),
        scenes=project.scenes,
        raw_content=project.script_content,
    )
