"""Dependency injection for FastAPI endpoints."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from movie_conceptualizer.api.schemas import (
    ProjectStatus,
    SceneAnalysis,
    SceneData,
    ShotData,
    StoryboardPrompt,
)


class Project:
    """In-memory project storage model."""

    def __init__(
        self,
        title: str,
        description: str | None = None,
        genre: str | None = None,
        style_notes: str | None = None,
    ):
        self.id = str(uuid4())
        self.title = title
        self.description = description
        self.genre = genre
        self.style_notes = style_notes
        self.status = ProjectStatus.CREATED
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

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
        self.updated_at = datetime.utcnow()

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


class ProjectStore:
    """In-memory project storage for MVP."""

    def __init__(self):
        self._projects: dict[str, Project] = {}

    def create(
        self,
        title: str,
        description: str | None = None,
        genre: str | None = None,
        style_notes: str | None = None,
    ) -> Project:
        """Create a new project."""
        project = Project(
            title=title,
            description=description,
            genre=genre,
            style_notes=style_notes,
        )
        self._projects[project.id] = project
        return project

    def get(self, project_id: str) -> Project | None:
        """Get a project by ID."""
        return self._projects.get(project_id)

    def list_all(self) -> list[Project]:
        """List all projects."""
        return list(self._projects.values())

    def delete(self, project_id: str) -> bool:
        """Delete a project by ID."""
        if project_id in self._projects:
            del self._projects[project_id]
            return True
        return False

    def exists(self, project_id: str) -> bool:
        """Check if a project exists."""
        return project_id in self._projects


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
        from movie_conceptualizer.api.schemas import CameraMovement, ShotType

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
                    description=f"{shot_type.value.replace('_', ' ').title()} shot of {scene.location or 'scene'}",
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


# Global instances (singleton pattern for MVP)
_project_store: ProjectStore | None = None
_workflow: MockWorkflow | None = None


def get_project_store() -> ProjectStore:
    """Get the project store instance (dependency injection)."""
    global _project_store
    if _project_store is None:
        _project_store = ProjectStore()
    return _project_store


def get_workflow() -> MockWorkflow:
    """Get the workflow instance (dependency injection)."""
    global _workflow
    if _workflow is None:
        _workflow = MockWorkflow()
    return _workflow
