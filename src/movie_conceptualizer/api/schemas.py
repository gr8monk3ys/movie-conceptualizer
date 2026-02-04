"""API request/response schemas using Pydantic models."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# Enums for status tracking
class ProjectStatus(str, Enum):
    """Project processing status."""

    CREATED = "created"
    SCRIPT_UPLOADED = "script_uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    GENERATING_SHOTS = "generating_shots"
    SHOTS_GENERATED = "shots_generated"
    GENERATING_STORYBOARD = "generating_storyboard"
    COMPLETED = "completed"
    ERROR = "error"


class ExportFormat(str, Enum):
    """Export format options."""

    JSON = "json"
    PDF = "pdf"


# Project schemas
class CreateProjectRequest(BaseModel):
    """Request schema for creating a new project."""

    title: str = Field(..., min_length=1, max_length=200, description="Project title")
    description: str | None = Field(None, max_length=2000, description="Project description")
    genre: str | None = Field(None, max_length=100, description="Film genre")
    style_notes: str | None = Field(None, max_length=2000, description="Visual style notes")


class ProjectResponse(BaseModel):
    """Response schema for project data."""

    id: str = Field(..., description="Unique project identifier")
    title: str = Field(..., description="Project title")
    description: str | None = Field(None, description="Project description")
    genre: str | None = Field(None, description="Film genre")
    style_notes: str | None = Field(None, description="Visual style notes")
    status: ProjectStatus = Field(..., description="Current project status")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    has_script: bool = Field(False, description="Whether script has been uploaded")
    scene_count: int = Field(0, description="Number of parsed scenes")
    shot_count: int = Field(0, description="Number of generated shots")

    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    """Response schema for listing projects."""

    projects: list[ProjectResponse] = Field(..., description="List of projects")
    total: int = Field(..., description="Total number of projects")


# Script schemas
class UploadScriptRequest(BaseModel):
    """Request schema for uploading a script."""

    content: str = Field(..., min_length=1, description="Script content as text")
    format: str = Field("fountain", description="Script format (fountain, plaintext)")


class SceneData(BaseModel):
    """Schema for parsed scene data."""

    scene_number: int = Field(..., description="Scene number")
    heading: str = Field(..., description="Scene heading (INT/EXT, location, time)")
    location: str | None = Field(None, description="Scene location")
    time_of_day: str | None = Field(None, description="Time of day")
    int_ext: str | None = Field(None, description="Interior or exterior")
    description: str | None = Field(None, description="Scene description/action")
    characters: list[str] = Field(default_factory=list, description="Characters in scene")
    dialogue: list[dict[str, str]] = Field(default_factory=list, description="Dialogue lines")
    raw_content: str = Field("", description="Raw scene content")


class ScriptResponse(BaseModel):
    """Response schema for script data."""

    project_id: str = Field(..., description="Project ID")
    title: str | None = Field(None, description="Script title")
    author: str | None = Field(None, description="Script author")
    format: str = Field(..., description="Script format")
    scene_count: int = Field(..., description="Number of scenes")
    scenes: list[SceneData] = Field(..., description="Parsed scenes")
    raw_content: str | None = Field(None, description="Original script content")


class ParseScriptRequest(BaseModel):
    """Request to trigger script parsing."""

    force_reparse: bool = Field(False, description="Force re-parsing even if already parsed")


# Generation schemas
class AnalysisRequest(BaseModel):
    """Request to run script analysis."""

    scene_numbers: list[int] | None = Field(
        None, description="Specific scenes to analyze (None for all)"
    )


class SceneAnalysis(BaseModel):
    """Schema for scene analysis results."""

    scene_number: int = Field(..., description="Scene number")
    mood: str | None = Field(None, description="Scene mood/atmosphere")
    themes: list[str] = Field(default_factory=list, description="Thematic elements")
    visual_style: str | None = Field(None, description="Suggested visual style")
    pacing: str | None = Field(None, description="Scene pacing")
    key_moments: list[str] = Field(default_factory=list, description="Key dramatic moments")
    color_palette: list[str] = Field(default_factory=list, description="Suggested color palette")
    lighting_notes: str | None = Field(None, description="Lighting suggestions")


class AnalysisResponse(BaseModel):
    """Response schema for script analysis."""

    project_id: str = Field(..., description="Project ID")
    analyses: list[SceneAnalysis] = Field(..., description="Scene analyses")
    overall_tone: str | None = Field(None, description="Overall film tone")
    visual_motifs: list[str] = Field(default_factory=list, description="Recurring visual motifs")


class ShotType(str, Enum):
    """Camera shot types."""

    WIDE = "wide"
    MEDIUM = "medium"
    CLOSE_UP = "close_up"
    EXTREME_CLOSE_UP = "extreme_close_up"
    ESTABLISHING = "establishing"
    TWO_SHOT = "two_shot"
    OVER_SHOULDER = "over_shoulder"
    POV = "pov"
    INSERT = "insert"
    TRACKING = "tracking"
    DOLLY = "dolly"
    CRANE = "crane"
    HANDHELD = "handheld"
    AERIAL = "aerial"


class CameraMovement(str, Enum):
    """Camera movement types."""

    STATIC = "static"
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    TILT_UP = "tilt_up"
    TILT_DOWN = "tilt_down"
    DOLLY_IN = "dolly_in"
    DOLLY_OUT = "dolly_out"
    TRACK_LEFT = "track_left"
    TRACK_RIGHT = "track_right"
    CRANE_UP = "crane_up"
    CRANE_DOWN = "crane_down"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    HANDHELD = "handheld"


class ShotData(BaseModel):
    """Schema for shot data."""

    shot_number: str = Field(..., description="Shot number (e.g., '1A', '2B')")
    scene_number: int = Field(..., description="Parent scene number")
    shot_type: ShotType = Field(..., description="Type of shot")
    camera_movement: CameraMovement = Field(CameraMovement.STATIC, description="Camera movement")
    description: str = Field(..., description="Shot description")
    duration_seconds: float | None = Field(None, description="Estimated duration")
    characters: list[str] = Field(default_factory=list, description="Characters in shot")
    dialogue: str | None = Field(None, description="Associated dialogue")
    action: str | None = Field(None, description="Action in shot")
    notes: str | None = Field(None, description="Director/DP notes")
    framing_notes: str | None = Field(None, description="Framing details")
    lens_suggestion: str | None = Field(None, description="Suggested lens")


class GenerateShotsRequest(BaseModel):
    """Request to generate shot list."""

    scene_numbers: list[int] | None = Field(
        None, description="Specific scenes (None for all)"
    )
    style: str | None = Field(None, description="Visual style guidance")
    shots_per_scene: int | None = Field(None, ge=1, le=50, description="Target shots per scene")


class ShotListResponse(BaseModel):
    """Response schema for shot list."""

    project_id: str = Field(..., description="Project ID")
    shots: list[ShotData] = Field(..., description="Generated shots")
    total_shots: int = Field(..., description="Total number of shots")
    estimated_duration: float | None = Field(None, description="Estimated total duration")


class StoryboardPrompt(BaseModel):
    """Schema for storyboard image prompt."""

    shot_number: str = Field(..., description="Shot number reference")
    scene_number: int = Field(..., description="Scene number")
    prompt: str = Field(..., description="Image generation prompt")
    negative_prompt: str | None = Field(None, description="Negative prompt")
    style_reference: str | None = Field(None, description="Style reference")
    composition_notes: str | None = Field(None, description="Composition guidance")
    aspect_ratio: str = Field("16:9", description="Image aspect ratio")


class GenerateStoryboardRequest(BaseModel):
    """Request to generate storyboard prompts."""

    scene_numbers: list[int] | None = Field(None, description="Specific scenes (None for all)")
    style: str | None = Field(None, description="Visual style for prompts")
    aspect_ratio: str = Field("16:9", description="Image aspect ratio")


class StoryboardResponse(BaseModel):
    """Response schema for storyboard prompts."""

    project_id: str = Field(..., description="Project ID")
    prompts: list[StoryboardPrompt] = Field(..., description="Generated prompts")
    total_prompts: int = Field(..., description="Total number of prompts")


class RunPipelineRequest(BaseModel):
    """Request to run full generation pipeline."""

    scene_numbers: list[int] | None = Field(None, description="Specific scenes (None for all)")
    style: str | None = Field(None, description="Visual style guidance")
    skip_analysis: bool = Field(False, description="Skip analysis step")
    skip_shots: bool = Field(False, description="Skip shot generation")
    skip_storyboard: bool = Field(False, description="Skip storyboard generation")


class GenerationStatusResponse(BaseModel):
    """Response schema for generation status."""

    project_id: str = Field(..., description="Project ID")
    status: ProjectStatus = Field(..., description="Current status")
    progress: float = Field(0.0, ge=0.0, le=100.0, description="Progress percentage")
    current_step: str | None = Field(None, description="Current processing step")
    steps_completed: list[str] = Field(default_factory=list, description="Completed steps")
    error_message: str | None = Field(None, description="Error message if failed")
    started_at: datetime | None = Field(None, description="Processing start time")
    completed_at: datetime | None = Field(None, description="Processing completion time")


# Export schemas
class ExportShotListRequest(BaseModel):
    """Request for shot list export."""

    format: ExportFormat = Field(ExportFormat.JSON, description="Export format")
    include_notes: bool = Field(True, description="Include director notes")
    include_timing: bool = Field(True, description="Include timing estimates")


class ExportStoryboardRequest(BaseModel):
    """Request for storyboard export."""

    format: ExportFormat = Field(ExportFormat.JSON, description="Export format")
    include_prompts: bool = Field(True, description="Include generation prompts")


class ExportResponse(BaseModel):
    """Response schema for export operations."""

    project_id: str = Field(..., description="Project ID")
    format: ExportFormat = Field(..., description="Export format")
    filename: str = Field(..., description="Generated filename")
    data: Any = Field(..., description="Export data (JSON) or download URL (PDF)")
    generated_at: datetime = Field(..., description="Export generation timestamp")


# Error schemas
class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    detail: str | None = Field(None, description="Additional details")


class ValidationErrorResponse(BaseModel):
    """Validation error response."""

    error: str = Field("validation_error", description="Error type")
    message: str = Field("Validation failed", description="Error message")
    errors: list[dict[str, Any]] = Field(..., description="Validation errors")
