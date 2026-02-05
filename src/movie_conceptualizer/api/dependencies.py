"""Dependency injection for FastAPI endpoints.

This module provides dependency injection for database connections,
repositories, and workflow services.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator, Iterable
from datetime import datetime, timezone
import re
from typing import Any, Protocol, runtime_checkable

# Re-export auth dependencies for convenience
from movie_conceptualizer.api.auth import (
    UserInDB,
    UserStore,
    get_current_active_user,
    get_current_user,
    get_current_user_required,
    get_optional_current_user,
    get_user_store,
    is_admin_user,
    require_auth_if_enabled,
    require_admin_if_enabled,
)
from movie_conceptualizer.api.schemas import (
    CameraMovement,
    ProjectStatus,
    SceneAnalysis,
    SceneData,
    ShotData,
    ShotType,
    StoryboardPrompt,
)
from movie_conceptualizer.models.analysis import (
    AnalyzedScene,
    CameraAngle as AnalysisCameraAngle,
    CameraMovement as AnalysisCameraMovement,
    EmotionalTone,
    PacingType,
    Shot as AnalysisShot,
    ShotList as AnalysisShotList,
    ShotType as AnalysisShotType,
)
from movie_conceptualizer.models.core import (
    ActionBlock,
    DialogueBlock,
    Scene,
    SceneType,
    Script,
    TimeOfDay,
)
from movie_conceptualizer.parsers import load_text
from movie_conceptualizer.agents import (
    ScriptAnalyzerAgent,
    ShotDesignerAgent,
    StoryboardArtistAgent,
)
from movie_conceptualizer.storage import (
    Database,
    GenerationRepository,
    ProjectModel,
    ProjectRepository,
    ScriptRepository,
    get_database,
    init_database,
)

__all__ = [
    # Project dependencies
    "Project",
    "ProjectStore",
    "MockWorkflow",
    "RealWorkflow",
    "Workflow",
    "get_project_store",
    "get_workflow",
    # Database dependencies
    "get_db",
    "get_database_sync",
    "get_project_repository",
    "get_script_repository",
    "get_generation_repository",
    # Auth dependencies
    "UserInDB",
    "UserStore",
    "get_current_active_user",
    "get_current_user",
    "get_current_user_required",
    "get_optional_current_user",
    "get_user_store",
    "require_auth_if_enabled",
    "require_admin_if_enabled",
    "is_admin_user",
]

logger = logging.getLogger(__name__)

DEV_MODE = os.environ.get("MOVIECON_DEV_MODE", "true").lower() in ("true", "1", "yes")


@runtime_checkable
class Workflow(Protocol):
    """Protocol for workflow implementations used by the API."""

    async def parse_script(
        self, content: str, format: str = "fountain"
    ) -> tuple[list[SceneData], str | None, str | None]:
        ...

    async def analyze_scenes(
        self, scenes: list[SceneData], genre: str | None = None
    ) -> tuple[list[SceneAnalysis], str | None, list[str]]:
        ...

    async def generate_shots(
        self,
        scenes: list[SceneData],
        analyses: list[SceneAnalysis] | None = None,
        style: str | None = None,
        shots_per_scene: int | None = None,
    ) -> list[ShotData]:
        ...

    async def generate_storyboard_prompts(
        self,
        shots: list[ShotData],
        style: str | None = None,
        aspect_ratio: str = "16:9",
        scenes: list[SceneData] | None = None,
        analyses: list[SceneAnalysis] | None = None,
    ) -> list[StoryboardPrompt]:
        ...


def _scene_to_scene_data(scene: Scene) -> SceneData:
    """Convert core Scene to API SceneData."""
    description_parts = []
    dialogue_blocks: list[dict[str, str]] = []
    for element in scene.content:
        if isinstance(element, DialogueBlock):
            dialogue_blocks.append(
                {"character": element.character_name, "dialogue": element.dialogue}
            )
        elif isinstance(element, ActionBlock):
            description_parts.append(element.text)

    return SceneData(
        scene_number=scene.scene_number,
        heading=scene.heading,
        location=scene.location or None,
        time_of_day=scene.time_of_day.value if scene.time_of_day else None,
        int_ext=scene.scene_type.value if scene.scene_type else None,
        description=" ".join(description_parts).strip() or None,
        characters=list(scene.characters),
        dialogue=dialogue_blocks,
        raw_content=scene.raw_text or "",
    )


def _parse_time_of_day(value: str | None) -> TimeOfDay:
    if not value:
        return TimeOfDay.UNKNOWN
    normalized = value.strip().upper().replace(" ", "_")
    for member in TimeOfDay:
        if normalized == member.value or normalized == member.name:
            return member
    return TimeOfDay.UNKNOWN


def _parse_scene_type(value: str | None) -> SceneType:
    if not value:
        return SceneType.UNKNOWN
    normalized = value.strip().upper()
    if normalized in ("INT", "INT."):
        return SceneType.INTERIOR
    if normalized in ("EXT", "EXT."):
        return SceneType.EXTERIOR
    if "INT/EXT" in normalized or "I/E" in normalized:
        return SceneType.INTERIOR_EXTERIOR
    return SceneType.UNKNOWN


def _scene_data_to_scene(scene_data: SceneData) -> Scene:
    """Convert API SceneData to core Scene."""
    content: list[ActionBlock | DialogueBlock] = []
    if scene_data.description:
        content.append(ActionBlock(text=scene_data.description))
    for entry in scene_data.dialogue or []:
        character = entry.get("character") or entry.get("character_name") or entry.get("speaker")
        dialogue = entry.get("dialogue") or entry.get("text") or ""
        if character and dialogue:
            content.append(DialogueBlock(character_name=character, dialogue=dialogue))

    return Scene(
        scene_number=scene_data.scene_number,
        heading=scene_data.heading,
        scene_type=_parse_scene_type(scene_data.int_ext),
        location=scene_data.location or "",
        time_of_day=_parse_time_of_day(scene_data.time_of_day),
        content=content,
        characters=scene_data.characters or [],
        raw_text=scene_data.raw_content or scene_data.description or "",
    )


def _script_from_scene_data(
    scenes: Iterable[SceneData],
    title: str = "Untitled",
) -> Script:
    return Script(title=title, scenes=[_scene_data_to_scene(s) for s in scenes])


def _parse_duration_hint(hint: str | None) -> float | None:
    if not hint:
        return None
    numbers = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", hint)]
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


_ANALYSIS_TO_API_SHOT_TYPE = {
    AnalysisShotType.EXTREME_WIDE: ShotType.ESTABLISHING,
    AnalysisShotType.WIDE: ShotType.WIDE,
    AnalysisShotType.FULL: ShotType.WIDE,
    AnalysisShotType.MEDIUM_WIDE: ShotType.MEDIUM,
    AnalysisShotType.MEDIUM: ShotType.MEDIUM,
    AnalysisShotType.MEDIUM_CLOSE: ShotType.CLOSE_UP,
    AnalysisShotType.CLOSE_UP: ShotType.CLOSE_UP,
    AnalysisShotType.EXTREME_CLOSE_UP: ShotType.EXTREME_CLOSE_UP,
    AnalysisShotType.TWO_SHOT: ShotType.TWO_SHOT,
    AnalysisShotType.OVER_THE_SHOULDER: ShotType.OVER_SHOULDER,
    AnalysisShotType.POV: ShotType.POV,
    AnalysisShotType.INSERT: ShotType.INSERT,
    AnalysisShotType.CUTAWAY: ShotType.INSERT,
}

_ANALYSIS_TO_API_MOVEMENT = {
    AnalysisCameraMovement.STATIC: CameraMovement.STATIC,
    AnalysisCameraMovement.PAN: CameraMovement.PAN_RIGHT,
    AnalysisCameraMovement.TILT: CameraMovement.TILT_UP,
    AnalysisCameraMovement.DOLLY: CameraMovement.DOLLY_IN,
    AnalysisCameraMovement.TRACKING: CameraMovement.TRACK_LEFT,
    AnalysisCameraMovement.CRANE: CameraMovement.CRANE_UP,
    AnalysisCameraMovement.STEADICAM: CameraMovement.HANDHELD,
    AnalysisCameraMovement.HANDHELD: CameraMovement.HANDHELD,
    AnalysisCameraMovement.ZOOM: CameraMovement.ZOOM_IN,
    AnalysisCameraMovement.PUSH_IN: CameraMovement.DOLLY_IN,
    AnalysisCameraMovement.PULL_OUT: CameraMovement.DOLLY_OUT,
    AnalysisCameraMovement.ARC: CameraMovement.TRACK_RIGHT,
}

_API_TO_ANALYSIS_SHOT_TYPE = {
    ShotType.ESTABLISHING: AnalysisShotType.EXTREME_WIDE,
    ShotType.WIDE: AnalysisShotType.WIDE,
    ShotType.MEDIUM: AnalysisShotType.MEDIUM,
    ShotType.CLOSE_UP: AnalysisShotType.CLOSE_UP,
    ShotType.EXTREME_CLOSE_UP: AnalysisShotType.EXTREME_CLOSE_UP,
    ShotType.TWO_SHOT: AnalysisShotType.TWO_SHOT,
    ShotType.OVER_SHOULDER: AnalysisShotType.OVER_THE_SHOULDER,
    ShotType.POV: AnalysisShotType.POV,
    ShotType.INSERT: AnalysisShotType.INSERT,
    ShotType.TRACKING: AnalysisShotType.WIDE,
    ShotType.DOLLY: AnalysisShotType.WIDE,
    ShotType.CRANE: AnalysisShotType.WIDE,
    ShotType.HANDHELD: AnalysisShotType.MEDIUM,
    ShotType.AERIAL: AnalysisShotType.EXTREME_WIDE,
}

_API_TO_ANALYSIS_MOVEMENT = {
    CameraMovement.STATIC: AnalysisCameraMovement.STATIC,
    CameraMovement.PAN_LEFT: AnalysisCameraMovement.PAN,
    CameraMovement.PAN_RIGHT: AnalysisCameraMovement.PAN,
    CameraMovement.TILT_UP: AnalysisCameraMovement.TILT,
    CameraMovement.TILT_DOWN: AnalysisCameraMovement.TILT,
    CameraMovement.DOLLY_IN: AnalysisCameraMovement.DOLLY,
    CameraMovement.DOLLY_OUT: AnalysisCameraMovement.DOLLY,
    CameraMovement.TRACK_LEFT: AnalysisCameraMovement.TRACKING,
    CameraMovement.TRACK_RIGHT: AnalysisCameraMovement.TRACKING,
    CameraMovement.CRANE_UP: AnalysisCameraMovement.CRANE,
    CameraMovement.CRANE_DOWN: AnalysisCameraMovement.CRANE,
    CameraMovement.ZOOM_IN: AnalysisCameraMovement.ZOOM,
    CameraMovement.ZOOM_OUT: AnalysisCameraMovement.ZOOM,
    CameraMovement.HANDHELD: AnalysisCameraMovement.HANDHELD,
}


class Project:
    """Project model that wraps SQLite-backed data.

    Provides a compatible interface with the old in-memory project model
    while using SQLite for persistence through the repositories.
    """

    def __init__(
        self,
        title: str,
        description: str | None = None,
        genre: str | None = None,
        style_notes: str | None = None,
        id: str | None = None,
        user_id: str | None = None,
        status: ProjectStatus = ProjectStatus.CREATED,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        from uuid import uuid4

        self.id = id or str(uuid4())
        self.user_id = user_id
        self.title = title
        self.description = description
        self.genre = genre
        self.style_notes = style_notes
        self.status = status
        self.created_at = created_at or datetime.now(timezone.utc)
        self.updated_at = updated_at or datetime.now(timezone.utc)

        # Script data
        self.script_content: str | None = None
        self.script_format: str | None = None
        self.script_title: str | None = None
        self.script_author: str | None = None
        self.scenes: list[SceneData] = []

        # Analysis data
        self.analyses: list[SceneAnalysis] = []
        self.overall_tone: str | None = None
        self.visual_motifs: list[str] = []

        # Shot list data
        self.shots: list[ShotData] = []

        # Storyboard data
        self.storyboard_prompts: list[StoryboardPrompt] = []

        # Processing status
        self.progress: float = 0.0
        self.current_step: str | None = None
        self.steps_completed: list[str] = []
        self.error_message: str | None = None
        self.processing_started_at: datetime | None = None
        self.processing_completed_at: datetime | None = None

    def update(self) -> None:
        """Update the timestamp."""
        self.updated_at = datetime.now(timezone.utc)

    @property
    def has_script(self) -> bool:
        """Check if script has been uploaded."""
        return self.script_content is not None

    @property
    def scene_count(self) -> int:
        """Get number of parsed scenes."""
        return len(self.scenes)

    @property
    def shot_count(self) -> int:
        """Get number of generated shots."""
        return len(self.shots)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "description": self.description,
            "genre": self.genre,
            "style_notes": self.style_notes,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "has_script": self.has_script,
            "scene_count": self.scene_count,
            "shot_count": self.shot_count,
        }

    @classmethod
    def from_model(cls, model: ProjectModel) -> Project:
        """Create a Project from a ProjectModel."""
        project = cls(
            id=model.id,
            user_id=model.user_id,
            title=model.title,
            description=model.description,
            genre=model.genre,
            style_notes=model.style_notes,
            status=model.status,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
        project.progress = model.progress
        project.current_step = model.current_step
        project.steps_completed = model.steps_completed
        project.error_message = model.error_message
        project.processing_started_at = model.processing_started_at
        project.processing_completed_at = model.processing_completed_at
        return project


class ProjectStore:
    """SQLite-backed project storage.

    Provides the same interface as the old in-memory ProjectStore
    but uses SQLite repositories for persistence.
    """

    def __init__(self):
        self._db: Database | None = None
        self._project_repo: ProjectRepository | None = None
        self._script_repo: ScriptRepository | None = None
        self._generation_repo: GenerationRepository | None = None
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """Ensure the database and repositories are initialized."""
        if self._initialized:
            return

        if self._db is None:
            self._db = get_database()

        # Initialize database
        if not self._db.is_initialized:
            await self._db.initialize()

        if self._project_repo is None:
            self._project_repo = ProjectRepository(self._db)
        if self._script_repo is None:
            self._script_repo = ScriptRepository(self._db)
        if self._generation_repo is None:
            self._generation_repo = GenerationRepository(self._db)

        self._initialized = True

    def _ensure_repos_sync(self) -> None:
        """Synchronously ensure repositories exist (for non-async calls)."""
        if self._db is None:
            self._db = get_database()
        if self._project_repo is None:
            self._project_repo = ProjectRepository(self._db)
        if self._script_repo is None:
            self._script_repo = ScriptRepository(self._db)
        if self._generation_repo is None:
            self._generation_repo = GenerationRepository(self._db)

    @property
    def project_repo(self) -> ProjectRepository:
        """Get the project repository."""
        self._ensure_repos_sync()
        return self._project_repo  # type: ignore

    @property
    def script_repo(self) -> ScriptRepository:
        """Get the script repository."""
        self._ensure_repos_sync()
        return self._script_repo  # type: ignore

    @property
    def generation_repo(self) -> GenerationRepository:
        """Get the generation repository."""
        self._ensure_repos_sync()
        return self._generation_repo  # type: ignore

    async def create(
        self,
        title: str,
        description: str | None = None,
        genre: str | None = None,
        style_notes: str | None = None,
        user_id: str | None = None,
    ) -> Project:
        """Create a new project."""
        await self._ensure_initialized()
        model = await self._project_repo.create(  # type: ignore
            title=title,
            description=description,
            genre=genre,
            style_notes=style_notes,
            user_id=user_id,
        )
        return Project.from_model(model)

    async def get(self, project_id: str) -> Project | None:
        """Get a project by ID, loading all related data."""
        await self._ensure_initialized()

        model = await self._project_repo.get(project_id)  # type: ignore
        if model is None:
            return None

        project = Project.from_model(model)

        # Load script data
        script = await self._script_repo.get_script(project_id)  # type: ignore
        if script:
            project.script_content = script.content
            project.script_format = script.format
            project.script_title = script.title
            project.script_author = script.author

        # Load scenes
        project.scenes = await self._script_repo.get_scenes(project_id)  # type: ignore

        # Load analyses
        project.analyses = await self._generation_repo.get_analyses(project_id)  # type: ignore
        overall_tone, visual_motifs = await self._generation_repo.get_project_analysis(project_id)  # type: ignore
        project.overall_tone = overall_tone
        project.visual_motifs = visual_motifs

        # Load shots
        project.shots = await self._generation_repo.get_shots(project_id)  # type: ignore

        # Load storyboard prompts
        project.storyboard_prompts = await self._generation_repo.get_storyboard_prompts(project_id)  # type: ignore

        return project

    async def list_all(self, user_id: str | None = None) -> list[Project]:
        """List all projects, optionally filtered by user_id."""
        await self._ensure_initialized()
        models = await self._project_repo.list_all(user_id=user_id)  # type: ignore
        return [Project.from_model(m) for m in models]

    async def assign_owner(self, project_id: str, user_id: str) -> bool:
        """Assign owner to a project."""
        await self._ensure_initialized()
        return await self._project_repo.assign_owner(project_id, user_id)  # type: ignore

    async def bulk_assign_owner(
        self, user_id: str, only_unassigned: bool = True
    ) -> int:
        """Bulk assign owners to projects."""
        await self._ensure_initialized()
        return await self._project_repo.bulk_assign_owner(user_id, only_unassigned)  # type: ignore

    async def delete(self, project_id: str) -> bool:
        """Delete a project by ID."""
        await self._ensure_initialized()
        return await self._project_repo.delete(project_id)  # type: ignore

    async def exists(self, project_id: str) -> bool:
        """Check if a project exists."""
        await self._ensure_initialized()
        return await self._project_repo.exists(project_id)  # type: ignore

    async def update_project(self, project: Project) -> None:
        """Update project data in the database."""
        await self._ensure_initialized()

        # Update project
        await self._project_repo.update(  # type: ignore
            project.id,
            title=project.title,
            description=project.description,
            genre=project.genre,
            style_notes=project.style_notes,
            status=project.status,
            progress=project.progress,
            current_step=project.current_step,
            steps_completed=project.steps_completed,
            error_message=project.error_message,
            processing_started_at=project.processing_started_at,
            processing_completed_at=project.processing_completed_at,
        )

    async def save_script(
        self,
        project_id: str,
        content: str,
        format: str,
        title: str | None = None,
        author: str | None = None,
    ) -> None:
        """Save script content."""
        await self._ensure_initialized()
        await self._script_repo.save_script(  # type: ignore
            project_id=project_id,
            content=content,
            format=format,
            title=title,
            author=author,
        )

    async def save_scenes(self, project_id: str, scenes: list[SceneData]) -> None:
        """Save parsed scenes."""
        await self._ensure_initialized()
        await self._script_repo.save_scenes(project_id, scenes)  # type: ignore

    async def update_script_info(
        self,
        project_id: str,
        title: str | None = None,
        author: str | None = None,
    ) -> None:
        """Update script title and author."""
        await self._ensure_initialized()
        await self._script_repo.update_parsed_info(project_id, title, author)  # type: ignore

    async def save_analyses(
        self,
        project_id: str,
        analyses: list[SceneAnalysis],
        overall_tone: str | None = None,
        visual_motifs: list[str] | None = None,
    ) -> None:
        """Save analysis results."""
        await self._ensure_initialized()
        await self._generation_repo.save_analyses(  # type: ignore
            project_id, analyses, overall_tone, visual_motifs
        )

    async def save_shots(
        self,
        project_id: str,
        shots: list[ShotData],
        style: str | None = None,
    ) -> None:
        """Save shot list."""
        await self._ensure_initialized()
        await self._generation_repo.save_shots(project_id, shots, style)  # type: ignore

    async def save_storyboard(
        self,
        project_id: str,
        prompts: list[StoryboardPrompt],
        style: str | None = None,
        aspect_ratio: str = "16:9",
    ) -> None:
        """Save storyboard prompts."""
        await self._ensure_initialized()
        await self._generation_repo.save_storyboard(  # type: ignore
            project_id, prompts, style, aspect_ratio
        )


class MockWorkflow:
    """Mock workflow for MVP - simulates the LangGraph pipeline."""

    async def parse_script(
        self, content: str, format: str = "fountain"
    ) -> tuple[list[SceneData], str | None, str | None]:
        """
        Parse a screenplay script.

        Returns:
            Tuple of (scenes, title, author)
        """
        # Simple parsing logic for MVP
        scenes: list[SceneData] = []
        lines = content.strip().split("\n")

        current_scene: dict[str, Any] | None = None
        scene_number = 0
        title = None
        author = None

        for line in lines:
            line = line.strip()

            # Skip empty lines
            if not line:
                continue

            # Check for title
            if line.lower().startswith("title:"):
                title = line[6:].strip()
                continue

            # Check for author
            if line.lower().startswith("author:") or line.lower().startswith("written by:"):
                author = line.split(":", 1)[1].strip()
                continue

            # Check for scene heading (INT./EXT.)
            if line.upper().startswith(("INT.", "INT ", "EXT.", "EXT ", "INT/EXT", "I/E")):
                # Save previous scene
                if current_scene:
                    scenes.append(SceneData(**current_scene))

                scene_number += 1

                # Parse scene heading
                int_ext = "INT" if "INT" in line.upper()[:4] else "EXT"
                heading_parts = line.split("-")
                location = heading_parts[0].replace("INT.", "").replace("EXT.", "").strip()
                time_of_day = heading_parts[-1].strip() if len(heading_parts) > 1 else None

                current_scene = {
                    "scene_number": scene_number,
                    "heading": line,
                    "location": location,
                    "time_of_day": time_of_day,
                    "int_ext": int_ext,
                    "description": "",
                    "characters": [],
                    "dialogue": [],
                    "raw_content": line + "\n",
                }
            elif current_scene:
                # Add to current scene content
                current_scene["raw_content"] += line + "\n"

                # Check if this looks like a character name (ALL CAPS followed by dialogue)
                if line.isupper() and len(line) < 50:
                    char_name = line.strip()
                    if char_name not in current_scene["characters"]:
                        current_scene["characters"].append(char_name)
                elif not line.isupper():
                    # Likely action or dialogue
                    if current_scene["description"]:
                        current_scene["description"] += " " + line
                    else:
                        current_scene["description"] = line

        # Don't forget the last scene
        if current_scene:
            scenes.append(SceneData(**current_scene))

        return scenes, title, author

    async def analyze_scenes(
        self, scenes: list[SceneData], genre: str | None = None
    ) -> tuple[list[SceneAnalysis], str | None, list[str]]:
        """
        Analyze scenes for mood, themes, and visual style.

        Returns:
            Tuple of (analyses, overall_tone, visual_motifs)
        """
        analyses: list[SceneAnalysis] = []

        for scene in scenes:
            # Generate mock analysis based on scene data
            mood = "dramatic"
            if scene.time_of_day and "night" in scene.time_of_day.lower():
                mood = "tense"
            elif scene.time_of_day and "day" in scene.time_of_day.lower():
                mood = "bright"

            analysis = SceneAnalysis(
                scene_number=scene.scene_number,
                mood=mood,
                themes=["tension", "character development"],
                visual_style="cinematic",
                pacing="moderate",
                key_moments=["Opening moment", "Character introduction"],
                color_palette=["muted blues", "warm oranges", "deep shadows"],
                lighting_notes=f"Natural lighting for {scene.time_of_day or 'day'} scene",
            )
            analyses.append(analysis)

        overall_tone = "dramatic thriller" if genre else "character-driven drama"
        visual_motifs = ["shadows", "reflections", "confined spaces"]

        return analyses, overall_tone, visual_motifs

    async def generate_shots(
        self,
        scenes: list[SceneData],
        analyses: list[SceneAnalysis] | None = None,
        style: str | None = None,
        shots_per_scene: int | None = None,
    ) -> list[ShotData]:
        """Generate shot list for scenes."""
        shots: list[ShotData] = []
        target_shots = shots_per_scene or 5

        for scene in scenes:
            for i in range(target_shots):
                shot_letter = chr(ord("A") + i)
                shot_number = f"{scene.scene_number}{shot_letter}"

                # Vary shot types
                shot_types = [
                    ShotType.ESTABLISHING,
                    ShotType.WIDE,
                    ShotType.MEDIUM,
                    ShotType.CLOSE_UP,
                    ShotType.OVER_SHOULDER,
                ]
                shot_type = shot_types[i % len(shot_types)]

                movements = [
                    CameraMovement.STATIC,
                    CameraMovement.PAN_RIGHT,
                    CameraMovement.DOLLY_IN,
                    CameraMovement.TRACK_LEFT,
                ]
                movement = movements[i % len(movements)]

                shot = ShotData(
                    shot_number=shot_number,
                    scene_number=scene.scene_number,
                    shot_type=shot_type,
                    camera_movement=movement,
                    description=(
                        f"{shot_type.value.replace('_', ' ').title()} "
                        f"shot of {scene.location or 'scene'}"
                    ),
                    duration_seconds=3.0 + (i * 0.5),
                    characters=scene.characters[:2] if scene.characters else [],
                    action=scene.description[:100] if scene.description else None,
                    notes=f"Shot {shot_number} - {style or 'standard'} style",
                    framing_notes="Rule of thirds composition",
                    lens_suggestion="50mm" if shot_type == ShotType.MEDIUM else "35mm",
                )
                shots.append(shot)

        return shots

    async def generate_storyboard_prompts(
        self,
        shots: list[ShotData],
        style: str | None = None,
        aspect_ratio: str = "16:9",
        scenes: list[SceneData] | None = None,
        analyses: list[SceneAnalysis] | None = None,
    ) -> list[StoryboardPrompt]:
        """Generate storyboard image prompts for shots."""
        prompts: list[StoryboardPrompt] = []

        for shot in shots:
            # Build descriptive prompt
            prompt_parts = [
                f"Cinematic {shot.shot_type.value.replace('_', ' ')} shot",
                shot.description,
            ]
            if style:
                prompt_parts.append(f"in {style} style")
            if shot.framing_notes:
                prompt_parts.append(shot.framing_notes)

            prompt_text = ", ".join(prompt_parts)

            storyboard_prompt = StoryboardPrompt(
                shot_number=shot.shot_number,
                scene_number=shot.scene_number,
                prompt=prompt_text,
                negative_prompt="blurry, low quality, amateur, overexposed",
                style_reference=style,
                composition_notes=shot.framing_notes,
                aspect_ratio=aspect_ratio,
            )
            prompts.append(storyboard_prompt)

        return prompts


class RealWorkflow:
    """Real workflow backed by the production agents."""

    async def parse_script(
        self, content: str, format: str = "fountain"
    ) -> tuple[list[SceneData], str | None, str | None]:
        if format not in ("fountain", "plaintext", "txt", "fdx"):
            raise ValueError(f"Unsupported script format: {format}")

        if format == "fdx":
            from movie_conceptualizer.parsers.fdx_parser import parse_fdx

            script = parse_fdx(content)
        else:
            script = load_text(content)
        scenes = [_scene_to_scene_data(scene) for scene in script.scenes]
        title = script.title_page.title or script.title
        author = script.title_page.author

        return scenes, title, author

    async def analyze_scenes(
        self, scenes: list[SceneData], genre: str | None = None
    ) -> tuple[list[SceneAnalysis], str | None, list[str]]:
        if not scenes:
            return [], None, []

        script = _script_from_scene_data(scenes)
        analyzer = ScriptAnalyzerAgent()
        analyzed_script = analyzer.analyze_script(script)

        analyses: list[SceneAnalysis] = []
        for analyzed_scene in analyzed_script.analyzed_scenes:
            palette = (
                [analyzed_scene.suggested_color_palette]
                if analyzed_scene.suggested_color_palette
                else []
            )
            analyses.append(
                SceneAnalysis(
                    scene_number=analyzed_scene.scene_number,
                    mood=analyzed_scene.overall_tone.value,
                    themes=[],
                    visual_style=analyzed_scene.scene_atmosphere,
                    pacing=analyzed_scene.pacing.value,
                    key_moments=[m.description for m in analyzed_scene.dramatic_moments],
                    color_palette=palette,
                    lighting_notes=None,
                )
            )

        overall_tone = analyzed_script.overall_tone.value
        visual_motifs = analyzed_script.genre_hints

        return analyses, overall_tone, visual_motifs

    async def generate_shots(
        self,
        scenes: list[SceneData],
        analyses: list[SceneAnalysis] | None = None,
        style: str | None = None,
        shots_per_scene: int | None = None,
    ) -> list[ShotData]:
        if not scenes:
            return []

        script = _script_from_scene_data(scenes)
        analyzer = ScriptAnalyzerAgent()
        analyzed_script = analyzer.analyze_script(script)

        designer = ShotDesignerAgent()
        shot_lists = [designer.design_shot_list(scene) for scene in analyzed_script.analyzed_scenes]

        api_shots: list[ShotData] = []
        for shot_list in shot_lists:
            for shot in shot_list.shots:
                api_shots.append(
                    ShotData(
                        shot_number=str(shot.shot_id or shot.shot_number),
                        scene_number=shot_list.scene_number,
                        shot_type=_ANALYSIS_TO_API_SHOT_TYPE.get(
                            shot.shot_type, ShotType.MEDIUM
                        ),
                        camera_movement=_ANALYSIS_TO_API_MOVEMENT.get(
                            shot.camera_movement, CameraMovement.STATIC
                        ),
                        description=shot.description,
                        duration_seconds=_parse_duration_hint(shot.duration_hint),
                        characters=[],
                        dialogue=shot.dialogue_covered,
                        action=shot.action_covered,
                        notes=shot.emotional_purpose,
                        framing_notes=shot.composition_notes,
                        lens_suggestion=None,
                    )
                )

        return api_shots

    async def generate_storyboard_prompts(
        self,
        shots: list[ShotData],
        style: str | None = None,
        aspect_ratio: str = "16:9",
        scenes: list[SceneData] | None = None,
        analyses: list[SceneAnalysis] | None = None,
    ) -> list[StoryboardPrompt]:
        if not shots:
            return []

        if scenes:
            script = _script_from_scene_data(scenes)
            analyzer = ScriptAnalyzerAgent()
            analyzed_script = analyzer.analyze_script(script)
            analyzed_scenes = analyzed_script.analyzed_scenes
        else:
            scene_fallback: dict[int, AnalyzedScene] = {}
            for shot in shots:
                if shot.scene_number in scene_fallback:
                    continue
                scene_fallback[shot.scene_number] = AnalyzedScene(
                    scene_number=shot.scene_number,
                    scene_heading=f"Scene {shot.scene_number}",
                    summary=shot.description,
                    emotional_beats=[],
                    overall_tone=EmotionalTone.NEUTRAL,
                    pacing=PacingType.MODERATE,
                    dramatic_moments=[],
                    visual_emphasis_points=[],
                    character_descriptions=[],
                    scene_atmosphere="neutral",
                    suggested_color_palette=None,
                    is_dialogue_heavy=bool(shot.dialogue),
                    is_action_heavy=bool(shot.action),
                    character_count=len(shot.characters),
                )
            analyzed_scenes = list(scene_fallback.values())

        shot_lists: dict[int, AnalysisShotList] = {}
        for shot in shots:
            if shot.scene_number not in shot_lists:
                shot_lists[shot.scene_number] = AnalysisShotList(
                    scene_number=shot.scene_number,
                    scene_heading=f"Scene {shot.scene_number}",
                    shots=[],
                    coverage_notes="",
                    master_shot_id=None,
                    estimated_screen_time=None,
                )

            shot_number = len(shot_lists[shot.scene_number].shots) + 1
            analysis_shot = AnalysisShot(
                shot_number=shot_number,
                shot_id=shot.shot_number,
                shot_type=_API_TO_ANALYSIS_SHOT_TYPE.get(shot.shot_type, AnalysisShotType.MEDIUM),
                camera_angle=AnalysisCameraAngle.EYE_LEVEL,
                camera_movement=_API_TO_ANALYSIS_MOVEMENT.get(
                    shot.camera_movement, AnalysisCameraMovement.STATIC
                ),
                subject=shot.description,
                description=shot.description,
                duration_hint=f"{shot.duration_seconds} seconds" if shot.duration_seconds else None,
                dialogue_covered=shot.dialogue,
                action_covered=shot.action,
                emotional_purpose=shot.notes or "coverage",
                lighting_notes=None,
                composition_notes=shot.framing_notes,
                transition_in=None,
                transition_out=None,
            )

            shot_lists[shot.scene_number].shots.append(analysis_shot)

        artist = StoryboardArtistAgent()
        storyboards = artist.create_storyboards(
            shot_lists=list(shot_lists.values()),
            analyzed_scenes=analyzed_scenes,
            style_guide=style,
        )

        prompts: list[StoryboardPrompt] = []
        for storyboard in storyboards:
            for frame in storyboard.frames:
                prompts.append(
                    StoryboardPrompt(
                        shot_number=frame.shot_id,
                        scene_number=frame.scene_number,
                        prompt=frame.image_prompt,
                        negative_prompt=frame.negative_prompt,
                        style_reference=storyboard.style_guide or style,
                        composition_notes=frame.composition_description,
                        aspect_ratio=aspect_ratio,
                    )
                )

        return prompts


# Global instances
_database: Database | None = None
_workflow: Workflow | None = None
_project_store: ProjectStore | None = None


async def get_db() -> AsyncIterator[Database]:
    """Get the database instance (dependency injection).

    Initializes the database on first call.

    Yields:
        The Database instance.
    """
    global _database
    if _database is None:
        _database = await init_database()
    yield _database


def get_database_sync() -> Database:
    """Get the database instance synchronously.

    For use in dependency injection where async is not available.

    Returns:
        The Database instance.
    """
    global _database
    if _database is None:
        _database = get_database()
    return _database


def get_project_repository(db: Database | None = None) -> ProjectRepository:
    """Get the project repository instance.

    Args:
        db: Optional database instance.

    Returns:
        The ProjectRepository instance.
    """
    return ProjectRepository(db or get_database_sync())


def get_script_repository(db: Database | None = None) -> ScriptRepository:
    """Get the script repository instance.

    Args:
        db: Optional database instance.

    Returns:
        The ScriptRepository instance.
    """
    return ScriptRepository(db or get_database_sync())


def get_generation_repository(db: Database | None = None) -> GenerationRepository:
    """Get the generation repository instance.

    Args:
        db: Optional database instance.

    Returns:
        The GenerationRepository instance.
    """
    return GenerationRepository(db or get_database_sync())


def get_project_store() -> ProjectStore:
    """Get the project store instance (dependency injection)."""
    global _project_store
    if _project_store is None:
        _project_store = ProjectStore()
    return _project_store


def get_workflow() -> Workflow:
    """Get the workflow instance (dependency injection)."""
    global _workflow
    if _workflow is None:
        backend = os.environ.get("MOVIECON_WORKFLOW_BACKEND")
        if backend is None:
            backend = "mock" if DEV_MODE else "real"

        backend = backend.lower().strip()

        if backend == "mock":
            if not DEV_MODE:
                raise RuntimeError(
                    "Mock workflow is disabled when MOVIECON_DEV_MODE is false. "
                    "Set MOVIECON_WORKFLOW_BACKEND=real to use the production pipeline "
                    "or explicitly set MOVIECON_WORKFLOW_BACKEND=mock for non-production use."
                )
            logger.warning("Using MockWorkflow (dev mode only).")
            _workflow = MockWorkflow()
        elif backend == "real":
            logger.info("Using RealWorkflow backend.")
            _workflow = RealWorkflow()
        else:
            raise RuntimeError(
                f"Unknown MOVIECON_WORKFLOW_BACKEND='{backend}'. "
                "Valid options: 'mock', 'real'."
            )
    return _workflow
