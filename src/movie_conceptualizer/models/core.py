"""Core data models for movie conceptualizer.

These models represent the fundamental screenplay elements used throughout
the application, from parsing to visualization. Built with Pydantic v2
for robust validation, serialization, and type safety.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator


class ProjectType(StrEnum):
    """Type of film project based on length."""

    SHORT = "short"
    FEATURE = "feature"


class Genre(StrEnum):
    """Common film genres for categorization."""

    ACTION = "action"
    ADVENTURE = "adventure"
    COMEDY = "comedy"
    CRIME = "crime"
    DOCUMENTARY = "documentary"
    DRAMA = "drama"
    FANTASY = "fantasy"
    HORROR = "horror"
    MUSICAL = "musical"
    MYSTERY = "mystery"
    ROMANCE = "romance"
    SCI_FI = "sci_fi"
    THRILLER = "thriller"
    WESTERN = "western"
    ANIMATION = "animation"
    EXPERIMENTAL = "experimental"


class SceneType(StrEnum):
    """Type of scene based on location prefix (INT/EXT)."""

    INTERIOR = "INT"
    EXTERIOR = "EXT"
    INTERIOR_EXTERIOR = "INT/EXT"
    UNKNOWN = "UNKNOWN"


class TimeOfDay(StrEnum):
    """Time of day for a scene setting."""

    DAY = "DAY"
    NIGHT = "NIGHT"
    DAWN = "DAWN"
    DUSK = "DUSK"
    MORNING = "MORNING"
    AFTERNOON = "AFTERNOON"
    EVENING = "EVENING"
    CONTINUOUS = "CONTINUOUS"
    LATER = "LATER"
    SAME = "SAME"
    UNKNOWN = "UNKNOWN"


class BreakdownCategory(StrEnum):
    """Categories for production breakdown elements.

    These categories align with industry-standard script breakdown sheets
    used in film and television production.
    """

    PROP = "prop"
    VEHICLE = "vehicle"
    VFX = "vfx"
    SFX = "sfx"
    WARDROBE = "wardrobe"
    MAKEUP = "makeup"
    HAIR = "hair"
    ANIMAL = "animal"
    EXTRA = "extra"
    STUNT = "stunt"
    GREENERY = "greenery"
    SPECIAL_EQUIPMENT = "special_equipment"
    MUSIC = "music"
    SOUND = "sound"
    ART_DEPARTMENT = "art_department"
    SET_DRESSING = "set_dressing"
    SECURITY = "security"
    MECHANICAL_FX = "mechanical_fx"
    OPTICAL_FX = "optical_fx"
    NOTES = "notes"


class EmotionalBeat(StrEnum):
    """Emotional beats for AI cinematography decisions.

    These help inform shot selection and camera movement choices
    to support the narrative's emotional intent.
    """

    TENSION = "tension"
    RELIEF = "relief"
    JOY = "joy"
    SADNESS = "sadness"
    ANGER = "anger"
    FEAR = "fear"
    SURPRISE = "surprise"
    ROMANTIC = "romantic"
    COMEDIC = "comedic"
    SUSPENSE = "suspense"
    DRAMATIC = "dramatic"
    INTIMATE = "intimate"
    EPIC = "epic"
    MELANCHOLIC = "melancholic"
    TRIUMPHANT = "triumphant"
    MYSTERIOUS = "mysterious"
    NEUTRAL = "neutral"


class DialogueBlock(BaseModel):
    """A block of dialogue spoken by a character.

    Represents a single dialogue exchange in the screenplay,
    including the speaker, their words, and any parenthetical direction.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "character_name": "SARAH",
                "dialogue": "We need to talk about what happened.",
                "parenthetical": "softly",
                "is_dual_dialogue": False,
                "character_extension": "V.O."
            }
        }
    )

    character_name: str = Field(..., description="Name of the character speaking")
    dialogue: str = Field(..., description="The spoken dialogue text")
    parenthetical: str | None = Field(
        default=None, description="Acting direction in parentheses"
    )
    is_dual_dialogue: bool = Field(
        default=False, description="Whether this is dual dialogue (two characters speaking simultaneously)"
    )
    character_extension: str | None = Field(
        default=None, description="Extension like (V.O.), (O.S.), (CONT'D)"
    )

    @field_validator("character_name")
    @classmethod
    def uppercase_character_name(cls, v: str) -> str:
        """Character names in screenplays are traditionally uppercase."""
        return v.upper().strip()


class ActionBlock(BaseModel):
    """An action or description block in the screenplay.

    Contains scene description, character actions, and other
    non-dialogue narrative content.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "text": "Sarah enters the dimly lit room, her footsteps echoing on the hardwood floor.",
                "is_centered": False
            }
        }
    )

    text: str = Field(..., description="The action/description text")
    is_centered: bool = Field(default=False, description="Whether text is centered (e.g., for montages)")


class Transition(BaseModel):
    """A transition between scenes.

    Standard film transitions like CUT TO:, DISSOLVE TO:, FADE IN:, etc.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "text": "CUT TO:"
            }
        }
    )

    text: str = Field(..., description="The transition text (e.g., CUT TO:)")

    @field_validator("text")
    @classmethod
    def uppercase_transition(cls, v: str) -> str:
        """Transitions are uppercase in screenplays."""
        return v.upper().strip()


class Character(BaseModel):
    """A character extracted from the screenplay.

    Tracks character appearances, dialogue count, and metadata
    for casting, scheduling, and storyboard consistency.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "SARAH CHEN",
                "description": "A determined detective in her late 30s with sharp instincts",
                "first_appearance": 1,
                "dialogue_count": 45
            }
        }
    )

    id: UUID = Field(default_factory=uuid4, description="Unique identifier")
    name: str = Field(..., min_length=1, max_length=100, description="Character name as appears in script")
    normalized_name: str = Field(
        default="", description="Normalized name for matching"
    )
    dialogue_count: int = Field(
        default=0, ge=0, description="Number of dialogue blocks"
    )
    scene_appearances: list[int] = Field(
        default_factory=list, description="Scene numbers where character appears"
    )
    first_appearance: int | None = Field(
        default=None, ge=1, description="First scene number"
    )
    description: str | None = Field(
        default=None, max_length=2000, description="Character description if found"
    )
    aliases: list[str] = Field(
        default_factory=list, description="Alternative names/references"
    )
    is_principal: bool = Field(
        default=False, description="Whether this is a principal/speaking role"
    )

    def model_post_init(self, __context: Any) -> None:
        """Set normalized name if not provided."""
        if not self.normalized_name:
            self.normalized_name = self.name.upper().strip()

    @computed_field
    @property
    def is_featured(self) -> bool:
        """Character is featured if they have more than 10 lines of dialogue."""
        return self.dialogue_count > 10

    @computed_field
    @property
    def appearance_count(self) -> int:
        """Number of scenes where this character appears."""
        return len(self.scene_appearances)


class Location(BaseModel):
    """A location extracted from scene headings.

    Represents filming locations for production planning,
    scheduling, and breakdown purposes.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440001",
                "name": "POLICE STATION",
                "scene_type": "INT",
                "time_of_day": "DAY",
                "description": "A busy metropolitan police precinct"
            }
        }
    )

    id: UUID = Field(default_factory=uuid4, description="Unique identifier")
    name: str = Field(..., min_length=1, max_length=200, description="Location name")
    normalized_name: str = Field(
        default="", description="Normalized name for matching"
    )
    scene_type: SceneType = Field(
        default=SceneType.UNKNOWN, description="Interior/Exterior"
    )
    time_of_day: TimeOfDay = Field(
        default=TimeOfDay.UNKNOWN, description="Default time of day"
    )
    scene_appearances: list[int] = Field(
        default_factory=list, description="Scene numbers at this location"
    )
    sub_locations: list[str] = Field(
        default_factory=list, description="Sub-locations (e.g., KITCHEN within HOUSE)"
    )
    description: str | None = Field(
        default=None, max_length=2000, description="Location description"
    )
    address: str | None = Field(
        default=None, max_length=500, description="Real-world address if scouted"
    )
    notes: str | None = Field(
        default=None, max_length=1000, description="Production notes"
    )

    def model_post_init(self, __context: Any) -> None:
        """Set normalized name if not provided."""
        if not self.normalized_name:
            self.normalized_name = self.name.upper().strip()

    @computed_field
    @property
    def slugline_prefix(self) -> str:
        """Generate the slugline prefix for this location."""
        return f"{self.scene_type.value}. {self.normalized_name}"

    @computed_field
    @property
    def appearance_count(self) -> int:
        """Number of scenes at this location."""
        return len(self.scene_appearances)


class BreakdownElement(BaseModel):
    """A production element identified during script breakdown.

    Breakdown elements include props, vehicles, VFX shots, wardrobe items,
    and other items needed for production planning and budgeting.
    These follow industry-standard breakdown sheet categories.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440002",
                "category": "prop",
                "name": "Detective Badge",
                "description": "Authentic-looking police detective badge, gold finish",
                "scenes": [1, 3, 7, 12],
                "quantity": 2,
                "estimated_cost": 150.00
            }
        }
    )

    id: UUID = Field(default_factory=uuid4, description="Unique identifier")
    category: BreakdownCategory = Field(..., description="Category of the breakdown element")
    name: str = Field(..., min_length=1, max_length=200, description="Name of the element")
    description: str | None = Field(
        default=None, max_length=2000, description="Detailed description"
    )
    scenes: list[int] = Field(
        default_factory=list, description="Scene numbers where this element appears"
    )
    quantity: int = Field(default=1, ge=1, description="Number of items needed")
    notes: str | None = Field(
        default=None, max_length=1000, description="Additional production notes"
    )
    estimated_cost: float | None = Field(
        default=None, ge=0, description="Estimated cost in USD"
    )
    is_critical: bool = Field(
        default=False, description="Whether this element is critical to the scene"
    )

    @computed_field
    @property
    def scene_count(self) -> int:
        """Number of scenes where this element appears."""
        return len(self.scenes)


class Scene(BaseModel):
    """A scene in the screenplay.

    The fundamental unit of a screenplay, identified by a slugline
    and containing action and dialogue. Scenes are used for breakdown,
    scheduling, shot planning, and storyboarding.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440003",
                "scene_number": 1,
                "heading": "INT. POLICE STATION - DAY",
                "scene_type": "INT",
                "location": "POLICE STATION",
                "time_of_day": "DAY",
                "page_count": 2.5,
                "emotional_beat": "tension",
                "characters": ["SARAH", "CHIEF MARTINEZ"]
            }
        }
    )

    id: UUID = Field(default_factory=uuid4, description="Unique identifier")
    scene_number: int = Field(..., ge=1, description="Sequential scene number")
    heading: str = Field(..., min_length=1, description="Full scene heading/slugline")
    scene_type: SceneType = Field(
        default=SceneType.UNKNOWN, description="INT/EXT type"
    )
    location: str = Field(default="", description="Location name")
    time_of_day: TimeOfDay = Field(
        default=TimeOfDay.UNKNOWN, description="Time of day"
    )
    content: list[ActionBlock | DialogueBlock | Transition] = Field(
        default_factory=list, description="Scene content blocks"
    )
    characters: list[str] = Field(
        default_factory=list, description="Character names in this scene"
    )
    page_start: float = Field(
        default=0.0, ge=0, description="Approximate starting page"
    )
    page_length: float = Field(
        default=0.0, ge=0, description="Approximate page length"
    )
    page_count: float = Field(
        default=0.0, ge=0, le=50, description="Page count (alias for page_length)"
    )
    raw_text: str = Field(default="", description="Raw text of the scene")
    emotional_beat: str | None = Field(
        default=None, max_length=100, description="Primary emotional tone for AI cinematography"
    )
    shot_ids: list[UUID] = Field(
        default_factory=list, description="Associated shot IDs from shot list"
    )
    synopsis: str | None = Field(
        default=None, max_length=500, description="Brief summary of the scene"
    )
    notes: str | None = Field(
        default=None, max_length=1000, description="Director/writer notes"
    )

    @field_validator("heading")
    @classmethod
    def uppercase_heading(cls, v: str) -> str:
        """Scene headings (sluglines) are always uppercase."""
        return v.upper().strip()

    @field_validator("characters")
    @classmethod
    def uppercase_characters(cls, v: list[str]) -> list[str]:
        """Character names should be uppercase."""
        return [name.upper().strip() for name in v]

    @computed_field
    @property
    def duration_minutes(self) -> float:
        """Estimated duration in minutes (1 page = 1 minute)."""
        return self.page_length or self.page_count

    @computed_field
    @property
    def page_eighths(self) -> str:
        """Convert page count to industry-standard eighths notation."""
        length = self.page_length or self.page_count
        whole = int(length)
        fraction = length - whole
        eighths = round(fraction * 8)
        if eighths == 0:
            return str(whole) if whole > 0 else "0"
        elif eighths == 8:
            return str(whole + 1)
        else:
            return f"{whole} {eighths}/8" if whole > 0 else f"{eighths}/8"

    @computed_field
    @property
    def estimated_duration_seconds(self) -> int:
        """Estimate scene duration in seconds."""
        return int(self.duration_minutes * 60)


class TitlePageField(BaseModel):
    """A field from the title page."""

    key: str = Field(..., description="Field name (e.g., 'Title', 'Author')")
    value: str = Field(..., description="Field value")


class TitlePage(BaseModel):
    """Title page metadata from the screenplay.

    Contains all standard title page fields as specified in
    industry screenwriting formats.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "The Investigation",
                "author": "Jane Doe",
                "draft_date": "January 15, 2024"
            }
        }
    )

    title: str | None = Field(default=None, description="Script title")
    credit: str | None = Field(default=None, description="Credit line (e.g., 'Written by')")
    author: str | None = Field(default=None, description="Author name(s)")
    authors: list[str] = Field(default_factory=list, description="List of authors")
    source: str | None = Field(default=None, description="Source material")
    draft_date: str | None = Field(default=None, description="Draft date")
    contact: str | None = Field(default=None, description="Contact information")
    copyright: str | None = Field(default=None, description="Copyright notice")
    notes: str | None = Field(default=None, description="Additional notes")
    revision: str | None = Field(default=None, description="Revision information")
    extra_fields: list[TitlePageField] = Field(
        default_factory=list, description="Additional title page fields"
    )


class Script(BaseModel):
    """A complete parsed screenplay.

    The Script model contains scenes, characters, locations, and
    breakdown elements extracted from the screenplay text. It serves
    as the foundation for all downstream processing including shot
    planning, storyboarding, and production scheduling.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440004",
                "title": "The Investigation",
                "total_pages": 95.0,
                "format_type": "fountain"
            }
        }
    )

    id: UUID = Field(default_factory=uuid4, description="Unique identifier")
    title: str = Field(default="Untitled", description="Script title")
    title_page: TitlePage = Field(
        default_factory=TitlePage, description="Title page metadata"
    )
    scenes: list[Scene] = Field(default_factory=list, description="All scenes")
    characters: list[Character] = Field(
        default_factory=list, description="All unique characters"
    )
    locations: list[Location] = Field(
        default_factory=list, description="All unique locations"
    )
    elements: list[BreakdownElement] = Field(
        default_factory=list, description="All breakdown elements"
    )
    total_pages: float = Field(default=0.0, ge=0, description="Total page count")
    raw_text: str = Field(default="", description="Original raw text")
    source_file: str | None = Field(default=None, description="Source file path")
    parsed_at: datetime = Field(
        default_factory=datetime.now, description="When script was parsed"
    )
    format_type: str = Field(
        default="fountain", description="Source format (fountain, fdx, pdf, etc.)"
    )
    logline: str | None = Field(
        default=None, max_length=500, description="One-sentence summary"
    )
    synopsis: str | None = Field(
        default=None, max_length=5000, description="Full synopsis"
    )

    @computed_field
    @property
    def duration_minutes(self) -> float:
        """Estimated total duration in minutes."""
        return self.total_pages

    @computed_field
    @property
    def scene_count(self) -> int:
        """Total number of scenes."""
        return len(self.scenes)

    @computed_field
    @property
    def character_count(self) -> int:
        """Total number of unique characters."""
        return len(self.characters)

    @computed_field
    @property
    def location_count(self) -> int:
        """Total number of unique locations."""
        return len(self.locations)

    @computed_field
    @property
    def element_count(self) -> int:
        """Total number of breakdown elements."""
        return len(self.elements)

    def get_scene(self, scene_number: int) -> Scene | None:
        """Get a scene by its number."""
        for scene in self.scenes:
            if scene.scene_number == scene_number:
                return scene
        return None

    def get_scene_by_id(self, scene_id: UUID) -> Scene | None:
        """Get a scene by its unique ID."""
        for scene in self.scenes:
            if scene.id == scene_id:
                return scene
        return None

    def get_character(self, name: str) -> Character | None:
        """Get a character by name (case-insensitive)."""
        normalized = name.upper().strip()
        for character in self.characters:
            if character.normalized_name == normalized:
                return character
            if normalized in [a.upper() for a in character.aliases]:
                return character
        return None

    def get_character_by_id(self, character_id: UUID) -> Character | None:
        """Get a character by unique ID."""
        for character in self.characters:
            if character.id == character_id:
                return character
        return None

    def get_location(self, name: str) -> Location | None:
        """Get a location by name (case-insensitive)."""
        normalized = name.upper().strip()
        for location in self.locations:
            if location.normalized_name == normalized:
                return location
        return None

    def get_location_by_id(self, location_id: UUID) -> Location | None:
        """Get a location by unique ID."""
        for location in self.locations:
            if location.id == location_id:
                return location
        return None

    def get_scenes_with_character(self, name: str) -> list[Scene]:
        """Get all scenes featuring a character."""
        normalized = name.upper().strip()
        return [
            scene for scene in self.scenes
            if normalized in [c.upper() for c in scene.characters]
        ]

    def get_scenes_at_location(self, name: str) -> list[Scene]:
        """Get all scenes at a location."""
        normalized = name.upper().strip()
        return [
            scene for scene in self.scenes
            if scene.location.upper().strip() == normalized
        ]

    def get_elements_by_category(self, category: BreakdownCategory) -> list[BreakdownElement]:
        """Get all breakdown elements in a specific category."""
        return [element for element in self.elements if element.category == category]

    def get_elements_for_scene(self, scene_number: int) -> list[BreakdownElement]:
        """Get all breakdown elements needed for a specific scene."""
        return [element for element in self.elements if scene_number in element.scenes]


class Project(BaseModel):
    """Top-level container for a film project.

    A Project encompasses all aspects of a film production including
    the script, storyboards, shot lists, and production schedules.
    This is the primary entity that users interact with.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440005",
                "title": "The Investigation",
                "type": "feature",
                "target_length": 90,
                "genres": ["thriller", "drama"],
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-20T14:45:00Z"
            }
        }
    )

    id: UUID = Field(default_factory=uuid4, description="Unique identifier for the project")
    title: str = Field(..., min_length=1, max_length=200, description="Project title")
    type: ProjectType = Field(..., description="Short film or feature length")
    target_length: int = Field(..., gt=0, le=300, description="Target runtime in minutes")
    genres: list[Genre] = Field(default_factory=list, description="Film genres (can be multiple)")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Project creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")
    script: Script | None = Field(default=None, description="The screenplay")
    description: str | None = Field(default=None, max_length=2000, description="Project description/logline")
    status: str = Field(default="draft", description="Project status (draft, in_progress, complete)")
    owner_id: UUID | None = Field(default=None, description="User ID of project owner")
    collaborator_ids: list[UUID] = Field(default_factory=list, description="User IDs of collaborators")
    tags: list[str] = Field(default_factory=list, description="Custom tags for organization")

    @field_validator("genres")
    @classmethod
    def validate_genres(cls, v: list[Genre]) -> list[Genre]:
        """Remove duplicate genres while preserving order."""
        return list(dict.fromkeys(v))

    @field_validator("target_length")
    @classmethod
    def validate_target_length(cls, v: int) -> int:
        """Validate target length is positive."""
        if v <= 0:
            raise ValueError("Target length must be positive")
        return v

    @computed_field
    @property
    def is_feature_length(self) -> bool:
        """Feature films are typically 40+ minutes."""
        return self.target_length >= 40

    @computed_field
    @property
    def page_estimate(self) -> int:
        """Estimated page count (1 page = 1 minute)."""
        return self.target_length

    @computed_field
    @property
    def has_script(self) -> bool:
        """Whether a script has been added to the project."""
        return self.script is not None

    def update_timestamp(self) -> None:
        """Update the updated_at timestamp to current time."""
        self.updated_at = datetime.utcnow()


# Type alias for parsed script (for backwards compatibility)
ParsedScript = Script

# Type aliases for convenience
CharacterList = list[Character]
LocationList = list[Location]
SceneList = list[Scene]
BreakdownElementList = list[BreakdownElement]
