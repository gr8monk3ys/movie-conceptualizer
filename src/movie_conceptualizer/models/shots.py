"""Shot planning data models for the AI filmmaking platform.

This module defines entities for shot planning and cinematography:
- ShotType: Types of camera shots (wide, medium, close-up, etc.)
- CameraMovement: Camera movement types (pan, tilt, dolly, etc.)
- Shot: Individual shots with cinematography details
- ShotList: Collection of shots for a scene

These models support AI-generated shot lists based on script analysis
and film grammar rules (180-degree rule, eyeline matching, etc.).
"""

from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator


class ShotType(str, Enum):
    """Types of camera shots based on framing.

    These shot types follow standard cinematography terminology and
    are used by the AI to suggest appropriate framing for scenes
    based on emotional beats and narrative context.
    """

    # Establishing shots
    EXTREME_WIDE = "extreme_wide"  # Also called extreme long shot
    WIDE = "wide"  # Also called long shot, establishes location
    FULL = "full"  # Shows full body of subject

    # Medium shots
    MEDIUM_WIDE = "medium_wide"  # Also called medium long shot
    MEDIUM = "medium"  # Waist up, most common shot
    MEDIUM_CLOSE_UP = "medium_close_up"  # Chest up

    # Close shots
    CLOSE_UP = "close_up"  # Face/object fills frame
    EXTREME_CLOSE_UP = "extreme_close_up"  # Detail shot (eyes, hands)
    INSERT = "insert"  # Detail shot of object

    # Two-person shots
    TWO_SHOT = "two_shot"  # Two people in frame
    THREE_SHOT = "three_shot"  # Three people in frame
    GROUP = "group"  # Multiple people

    # Specialty shots
    OVER_THE_SHOULDER = "over_the_shoulder"  # OTS shot for dialogue
    POV = "pov"  # Point of view shot
    DUTCH_ANGLE = "dutch_angle"  # Tilted frame for tension
    AERIAL = "aerial"  # Bird's eye view
    LOW_ANGLE = "low_angle"  # Camera below subject
    HIGH_ANGLE = "high_angle"  # Camera above subject
    COWBOY = "cowboy"  # Mid-thigh up (Western style)
    CHOKER = "choker"  # Tighter than close-up, chin to forehead


class CameraMovement(str, Enum):
    """Camera movement types for dynamic cinematography.

    These movements are used to suggest camera motion that supports
    the emotional intent of the scene. The AI considers pacing,
    mood, and narrative purpose when recommending movements.
    """

    # Static
    STATIC = "static"  # No movement, locked off
    LOCKED_OFF = "locked_off"  # Same as static

    # Rotation movements
    PAN = "pan"  # Horizontal rotation on axis
    TILT = "tilt"  # Vertical rotation on axis
    ROLL = "roll"  # Rotation around lens axis (Dutch)

    # Translation movements
    DOLLY = "dolly"  # Forward/backward on track
    DOLLY_IN = "dolly_in"  # Moving toward subject
    DOLLY_OUT = "dolly_out"  # Moving away from subject
    TRUCK = "truck"  # Side to side movement
    PEDESTAL = "pedestal"  # Vertical up/down movement
    BOOM = "boom"  # Same as pedestal

    # Complex movements
    TRACKING = "tracking"  # Following subject movement
    CRANE = "crane"  # Large vertical arc movement
    JIB = "jib"  # Smaller crane movement
    PUSH_IN = "push_in"  # Slow zoom or dolly in
    PULL_OUT = "pull_out"  # Slow zoom or dolly out

    # Handheld styles
    HANDHELD = "handheld"  # Organic, slightly unstable
    STEADICAM = "steadicam"  # Smooth handheld movement
    GIMBAL = "gimbal"  # Modern stabilized movement

    # Specialty movements
    WHIP_PAN = "whip_pan"  # Fast pan creating blur
    FOLLOW = "follow"  # Camera follows subject
    ORBIT = "orbit"  # Camera circles subject
    VERTIGO = "vertigo"  # Dolly zoom (Hitchcock effect)
    REVEAL = "reveal"  # Movement that reveals new information


class ShotSize(str, Enum):
    """Shot size classification for quick reference.

    A simplified categorization used for filtering and sorting shots.
    """

    WIDE = "wide"
    MEDIUM = "medium"
    CLOSE = "close"
    DETAIL = "detail"


class ShotPurpose(str, Enum):
    """The narrative purpose of a shot.

    Helps the AI understand why a particular shot is being used
    and ensures variety in shot selection.
    """

    ESTABLISHING = "establishing"  # Sets location/context
    MASTER = "master"  # Wide coverage of scene
    COVERAGE = "coverage"  # Standard scene coverage
    REACTION = "reaction"  # Character reaction
    DIALOGUE = "dialogue"  # Conversation coverage
    ACTION = "action"  # Physical action
    TRANSITION = "transition"  # Scene transition
    INSERT = "insert"  # Detail/object focus
    PICKUP = "pickup"  # Additional coverage
    CUTAWAY = "cutaway"  # Away from main action


class Shot(BaseModel):
    """An individual shot in a shot list.

    Represents a single camera setup with all cinematography details
    needed for production planning and storyboard generation.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440010",
                "shot_number": "1A",
                "shot_type": "medium",
                "camera_movement": "static",
                "description": "Sarah enters the police station, badge in hand",
                "duration": 4.5,
                "scene_id": "550e8400-e29b-41d4-a716-446655440003",
                "lens_mm": 50,
                "notes": "Natural lighting from windows"
            }
        }
    )

    id: UUID = Field(default_factory=uuid4, description="Unique identifier for the shot")
    shot_number: str = Field(..., min_length=1, max_length=20, description="Shot identifier (e.g., '1A', '2B')")
    shot_type: ShotType = Field(..., description="Type of shot framing")
    camera_movement: CameraMovement = Field(
        default=CameraMovement.STATIC, description="Camera movement for this shot"
    )
    description: str = Field(..., min_length=1, max_length=1000, description="Description of the shot content")
    duration: float | None = Field(
        default=None, ge=0.1, le=300, description="Estimated duration in seconds"
    )
    scene_id: UUID | None = Field(default=None, description="ID of the scene this shot belongs to")
    scene_number: int | None = Field(default=None, ge=1, description="Scene number for reference")

    # Technical details
    lens_mm: int | None = Field(
        default=None, ge=8, le=800, description="Suggested lens focal length in mm"
    )
    aperture: str | None = Field(
        default=None, max_length=20, description="Suggested aperture (e.g., 'f/2.8')"
    )
    frame_rate: int | None = Field(
        default=None, ge=1, le=240, description="Frame rate if different from project default"
    )

    # Composition
    subject: str | None = Field(
        default=None, max_length=200, description="Primary subject of the shot"
    )
    characters: list[str] = Field(
        default_factory=list, description="Characters appearing in this shot"
    )
    purpose: ShotPurpose | None = Field(
        default=None, description="Narrative purpose of this shot"
    )

    # Additional metadata
    notes: str | None = Field(default=None, max_length=1000, description="Additional notes for the shot")
    audio_notes: str | None = Field(
        default=None, max_length=500, description="Audio/dialogue notes"
    )
    vfx_required: bool = Field(default=False, description="Whether VFX is needed for this shot")
    vfx_notes: str | None = Field(
        default=None, max_length=500, description="VFX requirements if applicable"
    )

    # AI-generated metadata
    emotional_intent: str | None = Field(
        default=None, max_length=100, description="Intended emotional impact"
    )
    film_grammar_notes: str | None = Field(
        default=None, max_length=500, description="Film grammar considerations (180-degree rule, etc.)"
    )
    ai_confidence: float | None = Field(
        default=None, ge=0, le=1, description="AI confidence score for this shot suggestion"
    )

    @field_validator("shot_number")
    @classmethod
    def validate_shot_number(cls, v: str) -> str:
        """Ensure shot number is properly formatted."""
        return v.upper().strip()

    @field_validator("characters")
    @classmethod
    def uppercase_characters(cls, v: list[str]) -> list[str]:
        """Character names should be uppercase."""
        return [name.upper().strip() for name in v]

    @computed_field
    @property
    def shot_size(self) -> ShotSize:
        """Categorize shot into broad size category."""
        wide_shots = {
            ShotType.EXTREME_WIDE, ShotType.WIDE, ShotType.FULL,
            ShotType.MEDIUM_WIDE, ShotType.GROUP, ShotType.AERIAL
        }
        medium_shots = {
            ShotType.MEDIUM, ShotType.MEDIUM_CLOSE_UP, ShotType.TWO_SHOT,
            ShotType.THREE_SHOT, ShotType.COWBOY, ShotType.OVER_THE_SHOULDER
        }
        close_shots = {
            ShotType.CLOSE_UP, ShotType.CHOKER, ShotType.POV
        }

        if self.shot_type in wide_shots:
            return ShotSize.WIDE
        elif self.shot_type in medium_shots:
            return ShotSize.MEDIUM
        elif self.shot_type in close_shots:
            return ShotSize.CLOSE
        else:
            return ShotSize.DETAIL

    @computed_field
    @property
    def is_moving_shot(self) -> bool:
        """Whether this shot involves camera movement."""
        static_movements = {CameraMovement.STATIC, CameraMovement.LOCKED_OFF}
        return self.camera_movement not in static_movements

    @computed_field
    @property
    def display_name(self) -> str:
        """Human-readable shot name."""
        movement = "" if not self.is_moving_shot else f" ({self.camera_movement.value})"
        return f"{self.shot_number}: {self.shot_type.value.replace('_', ' ').title()}{movement}"


class ShotList(BaseModel):
    """A collection of shots for a scene.

    Represents the complete shot list for a single scene, including
    all coverage and specialty shots needed for production.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440011",
                "scene_id": "550e8400-e29b-41d4-a716-446655440003",
                "scene_number": 1,
                "shots": [],
                "notes": "Focus on tension building through shot progression"
            }
        }
    )

    id: UUID = Field(default_factory=uuid4, description="Unique identifier for the shot list")
    scene_id: UUID = Field(..., description="ID of the scene this shot list covers")
    scene_number: int | None = Field(default=None, ge=1, description="Scene number for reference")
    shots: list[Shot] = Field(default_factory=list, description="All shots in this shot list")
    notes: str | None = Field(
        default=None, max_length=2000, description="General notes for the shot list"
    )
    style_notes: str | None = Field(
        default=None, max_length=1000, description="Visual style guidelines"
    )

    # Coverage tracking
    master_shot_id: UUID | None = Field(
        default=None, description="ID of the master shot if designated"
    )
    coverage_complete: bool = Field(
        default=False, description="Whether full coverage has been planned"
    )

    # AI metadata
    ai_generated: bool = Field(default=False, description="Whether this shot list was AI-generated")
    ai_model: str | None = Field(
        default=None, max_length=100, description="AI model used for generation"
    )
    generation_prompt: str | None = Field(
        default=None, max_length=2000, description="Prompt used for AI generation"
    )

    @model_validator(mode="after")
    def update_shots_scene_id(self) -> "ShotList":
        """Ensure all shots have the correct scene_id."""
        for shot in self.shots:
            if shot.scene_id is None:
                shot.scene_id = self.scene_id
            if shot.scene_number is None and self.scene_number is not None:
                shot.scene_number = self.scene_number
        return self

    @computed_field
    @property
    def shot_count(self) -> int:
        """Total number of shots in the list."""
        return len(self.shots)

    @computed_field
    @property
    def total_duration(self) -> float:
        """Total estimated duration of all shots in seconds."""
        return sum(shot.duration or 0 for shot in self.shots)

    @computed_field
    @property
    def total_duration_formatted(self) -> str:
        """Total duration formatted as MM:SS."""
        total_seconds = int(self.total_duration)
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    @computed_field
    @property
    def moving_shot_count(self) -> int:
        """Number of shots with camera movement."""
        return sum(1 for shot in self.shots if shot.is_moving_shot)

    @computed_field
    @property
    def vfx_shot_count(self) -> int:
        """Number of shots requiring VFX."""
        return sum(1 for shot in self.shots if shot.vfx_required)

    def get_shot(self, shot_number: str) -> Shot | None:
        """Get a shot by its number."""
        normalized = shot_number.upper().strip()
        for shot in self.shots:
            if shot.shot_number == normalized:
                return shot
        return None

    def get_shot_by_id(self, shot_id: UUID) -> Shot | None:
        """Get a shot by its unique ID."""
        for shot in self.shots:
            if shot.id == shot_id:
                return shot
        return None

    def get_shots_by_type(self, shot_type: ShotType) -> list[Shot]:
        """Get all shots of a specific type."""
        return [shot for shot in self.shots if shot.shot_type == shot_type]

    def get_shots_by_size(self, size: ShotSize) -> list[Shot]:
        """Get all shots of a specific size category."""
        return [shot for shot in self.shots if shot.shot_size == size]

    def get_shots_by_purpose(self, purpose: ShotPurpose) -> list[Shot]:
        """Get all shots with a specific purpose."""
        return [shot for shot in self.shots if shot.purpose == purpose]

    def get_shots_with_character(self, character_name: str) -> list[Shot]:
        """Get all shots featuring a specific character."""
        normalized = character_name.upper().strip()
        return [
            shot for shot in self.shots
            if normalized in shot.characters
        ]

    def add_shot(self, shot: Shot) -> None:
        """Add a shot to the list, setting scene_id if not set."""
        if shot.scene_id is None:
            shot.scene_id = self.scene_id
        if shot.scene_number is None and self.scene_number is not None:
            shot.scene_number = self.scene_number
        self.shots.append(shot)

    def reorder_shots(self, shot_ids: list[UUID]) -> None:
        """Reorder shots based on a list of shot IDs."""
        shot_map = {shot.id: shot for shot in self.shots}
        reordered = []
        for shot_id in shot_ids:
            if shot_id in shot_map:
                reordered.append(shot_map[shot_id])
        # Add any shots not in the reorder list at the end
        remaining = [shot for shot in self.shots if shot.id not in shot_ids]
        self.shots = reordered + remaining


class ProjectShotList(BaseModel):
    """Collection of all shot lists for an entire project.

    Aggregates shot lists across all scenes for project-wide
    statistics and management.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": "550e8400-e29b-41d4-a716-446655440005",
                "shot_lists": []
            }
        }
    )

    project_id: UUID = Field(..., description="ID of the project")
    shot_lists: list[ShotList] = Field(
        default_factory=list, description="Shot lists for each scene"
    )
    global_notes: str | None = Field(
        default=None, max_length=2000, description="Project-wide shot list notes"
    )
    visual_style_guide: str | None = Field(
        default=None, max_length=5000, description="Overall visual style guidelines"
    )

    @computed_field
    @property
    def total_shots(self) -> int:
        """Total number of shots across all scenes."""
        return sum(sl.shot_count for sl in self.shot_lists)

    @computed_field
    @property
    def total_duration(self) -> float:
        """Total duration across all shot lists in seconds."""
        return sum(sl.total_duration for sl in self.shot_lists)

    @computed_field
    @property
    def scene_count(self) -> int:
        """Number of scenes with shot lists."""
        return len(self.shot_lists)

    def get_shot_list_for_scene(self, scene_id: UUID) -> ShotList | None:
        """Get the shot list for a specific scene."""
        for shot_list in self.shot_lists:
            if shot_list.scene_id == scene_id:
                return shot_list
        return None

    def get_all_shots(self) -> list[Shot]:
        """Get all shots across all scenes."""
        all_shots = []
        for shot_list in self.shot_lists:
            all_shots.extend(shot_list.shots)
        return all_shots


# Type aliases for convenience
ShotListCollection = list[ShotList]
