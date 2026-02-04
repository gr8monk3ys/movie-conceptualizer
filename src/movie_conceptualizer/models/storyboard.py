"""Storyboard data models for the AI filmmaking platform.

This module defines entities for visual pre-production:
- StoryboardFrame: Individual storyboard images with metadata
- Storyboard: Collection of frames for a project
- CharacterReference: Visual reference for character consistency

These models support AI-generated storyboards with character consistency
tracking and style guidelines for coherent visual storytelling.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator


class StoryboardStyle(StrEnum):
    """Visual styles for storyboard generation.

    Different styles can be used to match the tone of the film
    or the preferences of the production team.
    """

    SKETCH = "sketch"  # Rough pencil sketch style
    LINE_ART = "line_art"  # Clean black and white lines
    GRAYSCALE = "grayscale"  # Shaded grayscale
    COLOR_ROUGH = "color_rough"  # Rough color blocking
    COLOR_DETAILED = "color_detailed"  # Full color illustration
    CINEMATIC = "cinematic"  # Photo-realistic style
    NOIR = "noir"  # High contrast black and white
    COMIC = "comic"  # Comic book style
    ANIME = "anime"  # Anime/manga style
    WATERCOLOR = "watercolor"  # Watercolor painting style
    DIGITAL_PAINT = "digital_paint"  # Digital painting style


class AspectRatio(StrEnum):
    """Standard aspect ratios for storyboard frames.

    Should match the intended final aspect ratio of the film.
    """

    RATIO_16_9 = "16:9"  # Standard HD/4K
    RATIO_2_39_1 = "2.39:1"  # Anamorphic widescreen
    RATIO_1_85_1 = "1.85:1"  # Standard theatrical
    RATIO_4_3 = "4:3"  # Academy standard
    RATIO_1_1 = "1:1"  # Square (social media)
    RATIO_9_16 = "9:16"  # Vertical video
    RATIO_2_1 = "2:1"  # Univisium
    RATIO_1_33_1 = "1.33:1"  # Classic 35mm


class FrameStatus(StrEnum):
    """Status of a storyboard frame in the workflow."""

    PENDING = "pending"  # Not yet generated
    GENERATING = "generating"  # AI generation in progress
    GENERATED = "generated"  # AI generation complete
    REVIEW = "review"  # Awaiting review
    APPROVED = "approved"  # Approved for production
    REJECTED = "rejected"  # Needs regeneration
    REVISED = "revised"  # Manually edited


class VisualTrait(BaseModel):
    """A visual trait for character consistency.

    Captures specific visual attributes that should remain
    consistent across all storyboard frames.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "trait_name": "hair",
                "description": "Short, dark brown hair with slight wave",
                "importance": "high"
            }
        }
    )

    trait_name: str = Field(..., min_length=1, max_length=100, description="Name of the visual trait")
    description: str = Field(..., min_length=1, max_length=500, description="Detailed description of the trait")
    importance: str = Field(
        default="medium",
        description="Importance level: low, medium, high, critical"
    )

    @field_validator("importance")
    @classmethod
    def validate_importance(cls, v: str) -> str:
        """Validate importance is a valid level."""
        valid = {"low", "medium", "high", "critical"}
        v = v.lower().strip()
        if v not in valid:
            raise ValueError(f"Importance must be one of: {valid}")
        return v


class CharacterReference(BaseModel):
    """Visual reference for maintaining character consistency.

    Stores detailed visual descriptions and reference images
    to ensure the same character looks consistent across all
    storyboard frames throughout the project.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440020",
                "character_id": "550e8400-e29b-41d4-a716-446655440000",
                "character_name": "SARAH",
                "description": "Female detective, late 30s, determined expression",
                "visual_traits": [],
                "reference_images": []
            }
        }
    )

    id: UUID = Field(default_factory=uuid4, description="Unique identifier for the reference")
    character_id: UUID = Field(..., description="ID of the character from the script")
    character_name: str = Field(..., min_length=1, max_length=100, description="Character name")
    description: str = Field(
        ..., min_length=1, max_length=2000,
        description="Detailed visual description for AI generation"
    )
    visual_traits: list[VisualTrait] = Field(
        default_factory=list,
        description="Specific visual traits for consistency"
    )
    reference_images: list[str] = Field(
        default_factory=list,
        description="URLs or paths to reference images"
    )

    # Physical attributes for AI prompting
    age_range: str | None = Field(
        default=None, max_length=50,
        description="Age range (e.g., 'late 30s', '20-25')"
    )
    gender: str | None = Field(
        default=None, max_length=50,
        description="Gender presentation"
    )
    ethnicity: str | None = Field(
        default=None, max_length=100,
        description="Ethnicity/appearance notes"
    )
    body_type: str | None = Field(
        default=None, max_length=100,
        description="Body type description"
    )
    hair: str | None = Field(
        default=None, max_length=200,
        description="Hair color, style, length"
    )
    eyes: str | None = Field(
        default=None, max_length=100,
        description="Eye color and notable features"
    )
    distinctive_features: str | None = Field(
        default=None, max_length=500,
        description="Scars, tattoos, or other distinctive features"
    )

    # Wardrobe
    default_wardrobe: str | None = Field(
        default=None, max_length=500,
        description="Default costume/wardrobe description"
    )
    wardrobe_variations: list[str] = Field(
        default_factory=list,
        description="Alternative wardrobe descriptions by scene"
    )

    # AI generation metadata
    ai_embedding: list[float] | None = Field(
        default=None,
        description="Embedding vector for character consistency"
    )
    consistency_seed: int | None = Field(
        default=None,
        description="Seed value for consistent generation"
    )

    @field_validator("character_name")
    @classmethod
    def uppercase_name(cls, v: str) -> str:
        """Character names should be uppercase."""
        return v.upper().strip()

    @computed_field
    @property
    def has_reference_images(self) -> bool:
        """Whether reference images have been provided."""
        return len(self.reference_images) > 0

    @computed_field
    @property
    def trait_count(self) -> int:
        """Number of defined visual traits."""
        return len(self.visual_traits)

    def get_full_description(self) -> str:
        """Generate a complete description for AI prompting."""
        parts = [self.description]

        if self.age_range:
            parts.append(f"Age: {self.age_range}")
        if self.gender:
            parts.append(f"Gender: {self.gender}")
        if self.ethnicity:
            parts.append(f"Ethnicity: {self.ethnicity}")
        if self.body_type:
            parts.append(f"Build: {self.body_type}")
        if self.hair:
            parts.append(f"Hair: {self.hair}")
        if self.eyes:
            parts.append(f"Eyes: {self.eyes}")
        if self.distinctive_features:
            parts.append(f"Distinctive features: {self.distinctive_features}")

        for trait in self.visual_traits:
            if trait.importance in ("high", "critical"):
                parts.append(f"{trait.trait_name}: {trait.description}")

        return ". ".join(parts)


class StoryboardFrame(BaseModel):
    """An individual frame in a storyboard.

    Represents a single storyboard image with associated metadata,
    including the AI prompt used for generation and the resulting image.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440021",
                "shot_id": "550e8400-e29b-41d4-a716-446655440010",
                "frame_number": 1,
                "image_prompt": "Medium shot of Sarah entering police station...",
                "image_url": "https://storage.example.com/frames/001.png",
                "description": "Sarah enters the bustling police station",
                "status": "approved"
            }
        }
    )

    id: UUID = Field(default_factory=uuid4, description="Unique identifier for the frame")
    shot_id: UUID | None = Field(default=None, description="ID of the associated shot")
    scene_id: UUID | None = Field(default=None, description="ID of the scene")
    scene_number: int | None = Field(default=None, ge=1, description="Scene number")
    frame_number: int = Field(..., ge=1, description="Frame number within the storyboard")

    # Image data
    image_prompt: str = Field(
        ..., min_length=1, max_length=5000,
        description="AI prompt used to generate the image"
    )
    image_url: str | None = Field(
        default=None, max_length=2000,
        description="URL of the generated image"
    )
    image_path: str | None = Field(
        default=None, max_length=1000,
        description="Local file path of the image"
    )
    thumbnail_url: str | None = Field(
        default=None, max_length=2000,
        description="URL of a thumbnail version"
    )

    # Description and notes
    description: str = Field(
        ..., min_length=1, max_length=1000,
        description="Visual description of the frame content"
    )
    notes: str | None = Field(
        default=None, max_length=2000,
        description="Additional notes for the frame"
    )
    dialogue: str | None = Field(
        default=None, max_length=1000,
        description="Dialogue occurring during this frame"
    )
    action: str | None = Field(
        default=None, max_length=1000,
        description="Action occurring in this frame"
    )
    sound_notes: str | None = Field(
        default=None, max_length=500,
        description="Sound effects or music notes"
    )

    # Characters in frame
    characters: list[str] = Field(
        default_factory=list,
        description="Character names appearing in this frame"
    )
    character_reference_ids: list[UUID] = Field(
        default_factory=list,
        description="IDs of character references used"
    )

    # Technical details
    camera_angle: str | None = Field(
        default=None, max_length=100,
        description="Camera angle description"
    )
    shot_type: str | None = Field(
        default=None, max_length=50,
        description="Shot type (wide, medium, close-up, etc.)"
    )
    movement_arrows: bool = Field(
        default=False,
        description="Whether to include movement indicator arrows"
    )
    duration: float | None = Field(
        default=None, ge=0.1, le=60,
        description="Estimated duration in seconds"
    )

    # Workflow status
    status: FrameStatus = Field(
        default=FrameStatus.PENDING,
        description="Current status in the workflow"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the frame was created"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the frame was last updated"
    )
    approved_by: UUID | None = Field(
        default=None,
        description="User ID who approved the frame"
    )
    approved_at: datetime | None = Field(
        default=None,
        description="When the frame was approved"
    )

    # AI generation metadata
    ai_model: str | None = Field(
        default=None, max_length=100,
        description="AI model used for generation"
    )
    generation_seed: int | None = Field(
        default=None,
        description="Seed used for generation"
    )
    generation_params: dict[str, Any] | None = Field(
        default=None,
        description="Additional generation parameters"
    )
    generation_attempts: int = Field(
        default=0, ge=0,
        description="Number of generation attempts"
    )

    # Revision tracking
    revision_number: int = Field(
        default=1, ge=1,
        description="Current revision number"
    )
    previous_versions: list[str] = Field(
        default_factory=list,
        description="URLs/paths to previous versions"
    )
    revision_notes: str | None = Field(
        default=None, max_length=1000,
        description="Notes about current revision"
    )

    @field_validator("characters")
    @classmethod
    def uppercase_characters(cls, v: list[str]) -> list[str]:
        """Character names should be uppercase."""
        return [name.upper().strip() for name in v]

    @computed_field
    @property
    def has_image(self) -> bool:
        """Whether an image has been generated."""
        return self.image_url is not None or self.image_path is not None

    @computed_field
    @property
    def is_approved(self) -> bool:
        """Whether the frame has been approved."""
        return self.status == FrameStatus.APPROVED

    @computed_field
    @property
    def character_count(self) -> int:
        """Number of characters in this frame."""
        return len(self.characters)

    def update_status(self, new_status: FrameStatus) -> None:
        """Update the frame status and timestamp."""
        self.status = new_status
        self.updated_at = datetime.utcnow()

    def approve(self, approver_id: UUID) -> None:
        """Mark the frame as approved."""
        self.status = FrameStatus.APPROVED
        self.approved_by = approver_id
        self.approved_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()


class StyleGuidelines(BaseModel):
    """Visual style guidelines for a storyboard.

    Defines the overall visual approach to maintain consistency
    across all frames in the storyboard.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "style": "cinematic",
                "aspect_ratio": "2.39:1",
                "color_palette": ["#1a1a2e", "#16213e", "#0f3460"],
                "mood": "noir thriller"
            }
        }
    )

    style: StoryboardStyle = Field(
        default=StoryboardStyle.CINEMATIC,
        description="Visual style for frame generation"
    )
    aspect_ratio: AspectRatio = Field(
        default=AspectRatio.RATIO_16_9,
        description="Aspect ratio for all frames"
    )
    color_palette: list[str] = Field(
        default_factory=list,
        description="Hex color codes for the color palette"
    )
    mood: str | None = Field(
        default=None, max_length=200,
        description="Overall mood/atmosphere"
    )
    lighting_style: str | None = Field(
        default=None, max_length=200,
        description="Preferred lighting approach"
    )
    visual_references: list[str] = Field(
        default_factory=list,
        description="URLs to visual reference images"
    )
    film_references: list[str] = Field(
        default_factory=list,
        description="Film titles for visual reference"
    )
    avoid_elements: list[str] = Field(
        default_factory=list,
        description="Visual elements to avoid"
    )
    custom_instructions: str | None = Field(
        default=None, max_length=2000,
        description="Additional style instructions for AI"
    )
    negative_prompt: str | None = Field(
        default=None, max_length=1000,
        description="Negative prompt for AI generation"
    )

    @field_validator("color_palette")
    @classmethod
    def validate_hex_colors(cls, v: list[str]) -> list[str]:
        """Validate that colors are valid hex codes."""
        import re
        hex_pattern = re.compile(r'^#?([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$')
        validated = []
        for color in v:
            color = color.strip()
            if not color.startswith('#'):
                color = f'#{color}'
            if not hex_pattern.match(color):
                raise ValueError(f"Invalid hex color: {color}")
            validated.append(color.lower())
        return validated


class Storyboard(BaseModel):
    """A complete storyboard for a project.

    Contains all frames, character references, and style guidelines
    for visual pre-production.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440022",
                "project_id": "550e8400-e29b-41d4-a716-446655440005",
                "title": "The Investigation - Storyboard",
                "frames": [],
                "character_references": []
            }
        }
    )

    id: UUID = Field(default_factory=uuid4, description="Unique identifier for the storyboard")
    project_id: UUID = Field(..., description="ID of the associated project")
    title: str = Field(
        default="Untitled Storyboard",
        max_length=200,
        description="Storyboard title"
    )
    description: str | None = Field(
        default=None, max_length=2000,
        description="Overall storyboard description"
    )

    # Content
    frames: list[StoryboardFrame] = Field(
        default_factory=list,
        description="All storyboard frames"
    )
    character_references: list[CharacterReference] = Field(
        default_factory=list,
        description="Character references for consistency"
    )
    style_guidelines: StyleGuidelines = Field(
        default_factory=StyleGuidelines,
        description="Visual style guidelines"
    )

    # Organization
    scenes_covered: list[int] = Field(
        default_factory=list,
        description="Scene numbers included in this storyboard"
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the storyboard was created"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the storyboard was last updated"
    )

    # Workflow
    status: str = Field(
        default="draft",
        description="Overall storyboard status"
    )
    version: int = Field(
        default=1, ge=1,
        description="Storyboard version number"
    )

    # AI generation settings
    default_ai_model: str | None = Field(
        default=None, max_length=100,
        description="Default AI model for frame generation"
    )
    consistency_mode: bool = Field(
        default=True,
        description="Whether to enforce character consistency"
    )

    @computed_field
    @property
    def frame_count(self) -> int:
        """Total number of frames."""
        return len(self.frames)

    @computed_field
    @property
    def approved_frame_count(self) -> int:
        """Number of approved frames."""
        return sum(1 for f in self.frames if f.is_approved)

    @computed_field
    @property
    def completion_percentage(self) -> float:
        """Percentage of frames that are approved."""
        if not self.frames:
            return 0.0
        return (self.approved_frame_count / self.frame_count) * 100

    @computed_field
    @property
    def character_reference_count(self) -> int:
        """Number of character references defined."""
        return len(self.character_references)

    @computed_field
    @property
    def total_duration(self) -> float:
        """Total estimated duration in seconds."""
        return sum(f.duration or 0 for f in self.frames)

    def get_frame(self, frame_number: int) -> StoryboardFrame | None:
        """Get a frame by its number."""
        for frame in self.frames:
            if frame.frame_number == frame_number:
                return frame
        return None

    def get_frame_by_id(self, frame_id: UUID) -> StoryboardFrame | None:
        """Get a frame by its unique ID."""
        for frame in self.frames:
            if frame.id == frame_id:
                return frame
        return None

    def get_frames_for_scene(self, scene_number: int) -> list[StoryboardFrame]:
        """Get all frames for a specific scene."""
        return [f for f in self.frames if f.scene_number == scene_number]

    def get_frames_for_shot(self, shot_id: UUID) -> list[StoryboardFrame]:
        """Get all frames associated with a specific shot."""
        return [f for f in self.frames if f.shot_id == shot_id]

    def get_frames_with_character(self, character_name: str) -> list[StoryboardFrame]:
        """Get all frames featuring a specific character."""
        normalized = character_name.upper().strip()
        return [f for f in self.frames if normalized in f.characters]

    def get_character_reference(self, character_name: str) -> CharacterReference | None:
        """Get the character reference for a specific character."""
        normalized = character_name.upper().strip()
        for ref in self.character_references:
            if ref.character_name == normalized:
                return ref
        return None

    def get_character_reference_by_id(self, ref_id: UUID) -> CharacterReference | None:
        """Get a character reference by ID."""
        for ref in self.character_references:
            if ref.id == ref_id:
                return ref
        return None

    def get_pending_frames(self) -> list[StoryboardFrame]:
        """Get all frames pending generation."""
        return [f for f in self.frames if f.status == FrameStatus.PENDING]

    def get_frames_needing_review(self) -> list[StoryboardFrame]:
        """Get all frames awaiting review."""
        return [f for f in self.frames if f.status == FrameStatus.REVIEW]

    def add_frame(self, frame: StoryboardFrame) -> None:
        """Add a frame to the storyboard."""
        self.frames.append(frame)
        self.updated_at = datetime.utcnow()

    def add_character_reference(self, reference: CharacterReference) -> None:
        """Add a character reference."""
        self.character_references.append(reference)
        self.updated_at = datetime.utcnow()

    def update_timestamp(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.utcnow()


# Type aliases
StoryboardFrameList = list[StoryboardFrame]
CharacterReferenceList = list[CharacterReference]
