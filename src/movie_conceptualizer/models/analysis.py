"""Analysis, shot design, and storyboard models for movie conceptualizer.

These models represent the output of the AI analysis pipeline, including
emotional analysis, shot lists, and storyboard frames.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

# ============================================================================
# Enums for structured data
# ============================================================================


class EmotionalTone(StrEnum):
    """Emotional tone categories for scenes."""

    TENSE = "tense"
    ROMANTIC = "romantic"
    COMEDIC = "comedic"
    DRAMATIC = "dramatic"
    ACTION = "action"
    SUSPENSEFUL = "suspenseful"
    MELANCHOLIC = "melancholic"
    HOPEFUL = "hopeful"
    TERRIFYING = "terrifying"
    MYSTERIOUS = "mysterious"
    JOYFUL = "joyful"
    SOMBER = "somber"
    NEUTRAL = "neutral"


def _coerce_emotional_tone(value: object) -> EmotionalTone:
    """Coerce unknown tone strings to a safe default."""
    if isinstance(value, EmotionalTone):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if not normalized:
            return EmotionalTone.NEUTRAL
        synonyms = {
            "sad": "somber",
            "somber": "somber",
            "melancholy": "melancholic",
            "moody": "melancholic",
            "eerie": "mysterious",
            "ominous": "mysterious",
            "scary": "terrifying",
            "fearful": "terrifying",
            "formal": "neutral",
        }
        normalized = synonyms.get(normalized, normalized)
        if normalized in {tone.value for tone in EmotionalTone}:
            return EmotionalTone(normalized)
    return EmotionalTone.NEUTRAL


class PacingType(StrEnum):
    """Pacing categories for scenes."""

    SLOW = "slow"
    MODERATE = "moderate"
    FAST = "fast"
    BUILDING = "building"
    CLIMACTIC = "climactic"


class ShotType(StrEnum):
    """Standard cinematographic shot types."""

    EXTREME_WIDE = "extreme_wide"
    WIDE = "wide"
    FULL = "full"
    MEDIUM_WIDE = "medium_wide"
    MEDIUM = "medium"
    MEDIUM_CLOSE = "medium_close"
    CLOSE_UP = "close_up"
    EXTREME_CLOSE_UP = "extreme_close_up"
    TWO_SHOT = "two_shot"
    OVER_THE_SHOULDER = "over_the_shoulder"
    POV = "pov"
    INSERT = "insert"
    CUTAWAY = "cutaway"


class CameraMovement(StrEnum):
    """Camera movement types."""

    STATIC = "static"
    PAN = "pan"
    TILT = "tilt"
    DOLLY = "dolly"
    TRACKING = "tracking"
    CRANE = "crane"
    STEADICAM = "steadicam"
    HANDHELD = "handheld"
    ZOOM = "zoom"
    PUSH_IN = "push_in"
    PULL_OUT = "pull_out"
    ARC = "arc"


def _coerce_camera_movement(value: object) -> CameraMovement:
    """Coerce unknown camera movement strings to a safe default."""
    if isinstance(value, CameraMovement):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if not normalized:
            return CameraMovement.STATIC
        synonyms = {
            "slow_push_in": "push_in",
            "slow_pull_out": "pull_out",
            "push-in": "push_in",
            "pull-out": "pull_out",
            "handheld_cam": "handheld",
            "steadycam": "steadicam",
        }
        normalized = synonyms.get(normalized, normalized)
        if normalized in {mv.value for mv in CameraMovement}:
            return CameraMovement(normalized)
    return CameraMovement.STATIC


class CameraAngle(StrEnum):
    """Camera angle types."""

    EYE_LEVEL = "eye_level"
    LOW_ANGLE = "low_angle"
    HIGH_ANGLE = "high_angle"
    BIRDS_EYE = "birds_eye"
    WORMS_EYE = "worms_eye"
    DUTCH_ANGLE = "dutch_angle"


class LightingStyle(StrEnum):
    """Lighting style categories."""

    HIGH_KEY = "high_key"
    LOW_KEY = "low_key"
    NATURAL = "natural"
    DRAMATIC = "dramatic"
    SOFT = "soft"
    HARSH = "harsh"
    SILHOUETTE = "silhouette"
    CHIAROSCURO = "chiaroscuro"
    PRACTICAL = "practical"


# ============================================================================
# Analysis Models
# ============================================================================


class EmotionalBeat(BaseModel):
    """An emotional moment or beat within a scene."""

    description: str = Field(description="Description of the emotional beat")
    tone: EmotionalTone = Field(description="The emotional tone of this beat")
    intensity: float = Field(
        ge=0.0, le=1.0, description="Intensity level from 0 (subtle) to 1 (extreme)"
    )
    timestamp_hint: str | None = Field(
        default=None,
        description="Approximate location in scene (e.g., 'opening', 'midpoint')",
    )

    @field_validator("tone", mode="before")
    @classmethod
    def _normalize_tone(cls, value: object) -> EmotionalTone:
        return _coerce_emotional_tone(value)


class DramaticMoment(BaseModel):
    """A key dramatic moment that deserves visual emphasis."""

    description: str = Field(description="Description of the dramatic moment")
    importance: float = Field(ge=0.0, le=1.0, description="Importance level from 0 to 1")
    suggested_emphasis: str = Field(
        description="Suggested visual emphasis technique (e.g., 'close-up', 'slow motion')"
    )
    associated_dialogue: str | None = Field(
        default=None, description="Key dialogue line associated with this moment"
    )


class VisualEmphasisPoint(BaseModel):
    """A point in the scene that should receive visual emphasis."""

    element_description: str = Field(description="What should be emphasized visually")
    reason: str = Field(description="Why this needs visual emphasis")
    suggested_technique: str = Field(description="Suggested cinematographic technique")


class CharacterVisualDescription(BaseModel):
    """Physical and visual description of a character for consistency."""

    name: str = Field(description="Character name")
    physical_description: str = Field(
        description="Detailed physical description for visual consistency"
    )
    costume_notes: str | None = Field(
        default=None, description="Notes about character's costume/wardrobe"
    )
    distinctive_features: list[str] = Field(
        default_factory=list, description="Distinctive visual features"
    )


class AnalyzedScene(BaseModel):
    """A scene with full dramatic and visual analysis."""

    scene_number: int = Field(description="Scene number")
    scene_heading: str = Field(description="Scene heading")
    summary: str = Field(description="Brief summary of scene content")
    emotional_beats: list[EmotionalBeat] = Field(
        default_factory=list, description="Emotional beats in the scene"
    )
    overall_tone: EmotionalTone = Field(description="Overall emotional tone")
    pacing: PacingType = Field(description="Scene pacing")
    dramatic_moments: list[DramaticMoment] = Field(
        default_factory=list, description="Key dramatic moments"
    )
    visual_emphasis_points: list[VisualEmphasisPoint] = Field(
        default_factory=list, description="Points requiring visual emphasis"
    )
    character_descriptions: list[CharacterVisualDescription] = Field(
        default_factory=list, description="Character visual descriptions for this scene"
    )
    scene_atmosphere: str = Field(description="Overall visual atmosphere description")
    suggested_color_palette: str | None = Field(
        default=None, description="Suggested color palette for the scene"
    )
    is_dialogue_heavy: bool = Field(description="Whether scene is primarily dialogue")
    is_action_heavy: bool = Field(description="Whether scene is primarily action")
    character_count: int = Field(description="Number of characters in scene")

    @field_validator("overall_tone", mode="before")
    @classmethod
    def _normalize_overall_tone(cls, value: object) -> EmotionalTone:
        return _coerce_emotional_tone(value)


class AnalyzedScript(BaseModel):
    """Complete analyzed script with all scene analyses."""

    title: str = Field(description="Script title")
    analyzed_scenes: list[AnalyzedScene] = Field(
        default_factory=list, description="All analyzed scenes"
    )
    main_characters: list[CharacterVisualDescription] = Field(
        default_factory=list, description="Main character descriptions for consistency"
    )
    overall_tone: EmotionalTone = Field(description="Overall tone of the script")
    genre_hints: list[str] = Field(
        default_factory=list, description="Detected genre elements"
    )

    @field_validator("overall_tone", mode="before")
    @classmethod
    def _normalize_script_tone(cls, value: object) -> EmotionalTone:
        return _coerce_emotional_tone(value)


# ============================================================================
# Shot Design Models
# ============================================================================


class Shot(BaseModel):
    """A single shot in a shot list."""

    shot_number: int = Field(description="Shot number within the scene")
    shot_id: str = Field(description="Unique shot identifier (e.g., '1A', '1B')")
    shot_type: ShotType = Field(description="Type of shot")
    camera_angle: CameraAngle = Field(description="Camera angle")
    camera_movement: CameraMovement = Field(description="Camera movement")
    subject: str = Field(description="Main subject of the shot")
    description: str = Field(description="Detailed shot description")
    duration_hint: str | None = Field(
        default=None, description="Suggested duration (e.g., '2-3 seconds')"
    )
    dialogue_covered: str | None = Field(
        default=None, description="Dialogue this shot covers, if any"
    )
    action_covered: str | None = Field(
        default=None, description="Action this shot covers, if any"
    )
    emotional_purpose: str = Field(description="What emotion/purpose this shot serves")

    @field_validator("camera_movement", mode="before")
    @classmethod
    def _normalize_camera_movement(cls, value: object) -> CameraMovement:
        return _coerce_camera_movement(value)
    lighting_notes: str | None = Field(
        default=None, description="Specific lighting notes for this shot"
    )
    composition_notes: str | None = Field(
        default=None, description="Composition and framing notes"
    )
    transition_in: str | None = Field(
        default=None, description="Transition from previous shot"
    )
    transition_out: str | None = Field(
        default=None, description="Transition to next shot"
    )


class ShotList(BaseModel):
    """Complete shot list for a scene."""

    scene_number: int = Field(description="Scene number")
    scene_heading: str = Field(description="Scene heading")
    shots: list[Shot] = Field(default_factory=list, description="Ordered list of shots")
    coverage_notes: str = Field(description="Notes about coverage strategy for the scene")
    master_shot_id: str | None = Field(
        default=None, description="ID of the master/establishing shot"
    )
    estimated_screen_time: str | None = Field(
        default=None, description="Estimated screen time for the scene"
    )


# ============================================================================
# Storyboard Models
# ============================================================================


class StoryboardFrame(BaseModel):
    """A single storyboard frame with image generation prompt."""

    frame_number: int = Field(description="Frame number in sequence")
    frame_id: str = Field(description="Unique frame identifier")
    scene_number: int = Field(description="Scene this frame belongs to")
    shot_id: str = Field(description="Shot this frame represents")
    image_prompt: str = Field(
        description="Detailed prompt for image generation, including all visual details"
    )
    composition_description: str = Field(description="Description of frame composition")
    lighting_description: str = Field(description="Description of lighting")
    mood_description: str = Field(description="Description of mood/atmosphere")
    character_positions: str | None = Field(
        default=None, description="Where characters are positioned in frame"
    )
    camera_info: str = Field(description="Camera angle, movement, and shot type info")
    action_description: str | None = Field(
        default=None, description="What action is happening in this frame"
    )
    dialogue_text: str | None = Field(
        default=None, description="Dialogue being spoken in this frame"
    )
    notes: str | None = Field(default=None, description="Additional notes for the frame")
    style_keywords: list[str] = Field(
        default_factory=list, description="Style keywords for image generation"
    )
    negative_prompt: str | None = Field(
        default=None, description="Things to avoid in generation"
    )
    generated_image_url: str | None = Field(
        default=None, description="URL of generated image, if available"
    )


class Storyboard(BaseModel):
    """Complete storyboard for a scene or script."""

    title: str = Field(description="Storyboard title")
    scene_number: int | None = Field(
        default=None, description="Scene number if for a single scene"
    )
    frames: list[StoryboardFrame] = Field(
        default_factory=list, description="All storyboard frames"
    )
    style_guide: str | None = Field(
        default=None, description="Overall style guide for the storyboard"
    )
    character_reference_notes: str | None = Field(
        default=None, description="Character consistency reference notes"
    )


# ============================================================================
# Export all models
# ============================================================================

__all__ = [
    # Enums
    "EmotionalTone",
    "PacingType",
    "ShotType",
    "CameraMovement",
    "CameraAngle",
    "LightingStyle",
    # Analysis Models
    "EmotionalBeat",
    "DramaticMoment",
    "VisualEmphasisPoint",
    "CharacterVisualDescription",
    "AnalyzedScene",
    "AnalyzedScript",
    # Shot Design Models
    "Shot",
    "ShotList",
    # Storyboard Models
    "StoryboardFrame",
    "Storyboard",
]
