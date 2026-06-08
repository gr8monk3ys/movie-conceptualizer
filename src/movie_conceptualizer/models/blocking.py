"""Blocking diagram data models for the AI filmmaking platform.

This module defines entities for staging and blocking visualization:
- CharacterPosition: Character placement in a scene
- CameraSetup: Camera position and lens configuration
- Movement: Character or camera movement paths
- BlockingDiagram: Complete blocking diagram for a scene

These models support AI-generated blocking diagrams with film grammar
awareness (180-degree rule, sight lines, etc.) rendered as SVG.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator


class FacingDirection(StrEnum):
    """Cardinal and intercardinal facing directions.

    Used to indicate which way a character is facing in the blocking diagram.
    """

    NORTH = "north"  # Toward camera/audience
    SOUTH = "south"  # Away from camera
    EAST = "east"  # Stage left (camera right)
    WEST = "west"  # Stage right (camera left)
    NORTHEAST = "northeast"
    NORTHWEST = "northwest"
    SOUTHEAST = "southeast"
    SOUTHWEST = "southwest"
    CAMERA = "camera"  # Directly facing camera


class StagePosition(StrEnum):
    """Traditional stage positions for blocking.

    Standard theatrical terminology used in film blocking.
    """

    DOWNSTAGE_LEFT = "downstage_left"  # Closest to camera, left
    DOWNSTAGE_CENTER = "downstage_center"  # Closest to camera, center
    DOWNSTAGE_RIGHT = "downstage_right"  # Closest to camera, right
    CENTER_LEFT = "center_left"
    CENTER_STAGE = "center_stage"
    CENTER_RIGHT = "center_right"
    UPSTAGE_LEFT = "upstage_left"  # Farthest from camera, left
    UPSTAGE_CENTER = "upstage_center"  # Farthest from camera, center
    UPSTAGE_RIGHT = "upstage_right"  # Farthest from camera, right


class EntityType(StrEnum):
    """Types of entities that can be positioned in a blocking diagram."""

    CHARACTER = "character"
    CAMERA = "camera"
    PROP = "prop"
    VEHICLE = "vehicle"
    LIGHT = "light"
    MARKER = "marker"


class MovementType(StrEnum):
    """Types of movement for characters and cameras."""

    WALK = "walk"
    RUN = "run"
    ENTER = "enter"
    EXIT = "exit"
    CROSS = "cross"  # Cross from one position to another
    TURN = "turn"
    SIT = "sit"
    STAND = "stand"
    GESTURE = "gesture"

    # Camera-specific movements
    PAN = "pan"
    TILT = "tilt"
    DOLLY = "dolly"
    TRUCK = "truck"
    CRANE = "crane"
    ORBIT = "orbit"


class Coordinate(BaseModel):
    """A 2D coordinate point for positioning.

    Coordinates are normalized to a 0-100 scale for the diagram,
    with (0,0) at the top-left corner.
    """

    model_config = ConfigDict(json_schema_extra={"example": {"x": 50.0, "y": 30.0}})

    x: float = Field(..., ge=0, le=100, description="X coordinate (0-100)")
    y: float = Field(..., ge=0, le=100, description="Y coordinate (0-100)")

    def distance_to(self, other: Coordinate) -> float:
        """Calculate distance to another coordinate."""
        return float(((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5)

    def midpoint(self, other: Coordinate) -> Coordinate:
        """Calculate midpoint between this and another coordinate."""
        return Coordinate(x=(self.x + other.x) / 2, y=(self.y + other.y) / 2)


class CharacterPosition(BaseModel):
    """Position of a character in a blocking diagram.

    Represents where a character stands, which direction they face,
    and what action they are performing at this moment in the scene.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440030",
                "character_id": "550e8400-e29b-41d4-a716-446655440000",
                "character_name": "SARAH",
                "x": 30.0,
                "y": 50.0,
                "facing_direction": "east",
                "action": "Standing, arms crossed",
            }
        }
    )

    id: UUID = Field(default_factory=uuid4, description="Unique identifier")
    character_id: UUID = Field(..., description="ID of the character")
    character_name: str = Field(..., min_length=1, max_length=100, description="Character name")
    x: float = Field(..., ge=0, le=100, description="X position (0-100)")
    y: float = Field(..., ge=0, le=100, description="Y position (0-100)")
    facing_direction: FacingDirection = Field(
        default=FacingDirection.CAMERA, description="Direction the character is facing"
    )
    action: str | None = Field(
        default=None, max_length=500, description="What the character is doing"
    )

    # Optional stage position reference
    stage_position: StagePosition | None = Field(
        default=None, description="Traditional stage position name"
    )

    # Visual customization
    color: str = Field(default="#3498db", description="Color for the character marker")
    label: str | None = Field(
        default=None, max_length=50, description="Short label for the diagram"
    )
    icon: str | None = Field(
        default=None, max_length=50, description="Icon identifier for the character"
    )

    # Timing
    beat_number: int | None = Field(
        default=None, ge=1, description="Beat number when this position occurs"
    )
    time_code: str | None = Field(default=None, max_length=20, description="Timecode reference")

    @field_validator("character_name")
    @classmethod
    def uppercase_name(cls, v: str) -> str:
        """Character names should be uppercase."""
        return v.upper().strip()

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str) -> str:
        """Validate hex color format."""
        import re

        v = v.strip()
        if not v.startswith("#"):
            v = f"#{v}"
        hex_pattern = re.compile(r"^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$")
        if not hex_pattern.match(v):
            raise ValueError(f"Invalid hex color: {v}")
        return v.lower()

    @computed_field
    @property
    def coordinate(self) -> Coordinate:
        """Get position as a Coordinate object."""
        return Coordinate(x=self.x, y=self.y)

    @computed_field
    @property
    def display_label(self) -> str:
        """Label to display on the diagram."""
        return self.label or self.character_name[:3]


class CameraSetup(BaseModel):
    """Camera position and configuration in a blocking diagram.

    Defines camera placement, lens choice, and framing target
    for shot planning and blocking visualization.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440031",
                "position_x": 50.0,
                "position_y": 90.0,
                "target_x": 50.0,
                "target_y": 30.0,
                "lens_mm": 50,
                "shot_type": "medium",
            }
        }
    )

    id: UUID = Field(default_factory=uuid4, description="Unique identifier")
    name: str = Field(default="Camera A", max_length=50, description="Camera designation")

    # Position
    position_x: float = Field(..., ge=0, le=100, description="Camera X position")
    position_y: float = Field(..., ge=0, le=100, description="Camera Y position")
    height: float | None = Field(
        default=None, ge=0, le=50, description="Camera height in feet (0=ground level)"
    )

    # Target/framing
    target_x: float = Field(..., ge=0, le=100, description="Target X position")
    target_y: float = Field(..., ge=0, le=100, description="Target Y position")
    target_character_id: UUID | None = Field(
        default=None, description="ID of character being framed"
    )

    # Lens configuration
    lens_mm: int = Field(default=50, ge=8, le=800, description="Lens focal length in mm")
    aperture: str | None = Field(default=None, max_length=20, description="Aperture setting")
    aspect_ratio: str = Field(default="16:9", description="Frame aspect ratio")

    # Shot information
    shot_type: str | None = Field(
        default=None, max_length=50, description="Shot type (wide, medium, close-up)"
    )
    shot_id: UUID | None = Field(default=None, description="ID of associated shot")
    shot_number: str | None = Field(
        default=None, max_length=20, description="Shot number reference"
    )

    # Visual customization
    color: str = Field(default="#e74c3c", description="Color for the camera marker")
    show_fov: bool = Field(default=True, description="Whether to show field of view cone")
    fov_angle: float | None = Field(
        default=None, ge=1, le=180, description="Field of view angle in degrees"
    )

    # Notes
    notes: str | None = Field(default=None, max_length=500, description="Camera setup notes")

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str) -> str:
        """Validate hex color format."""
        import re

        v = v.strip()
        if not v.startswith("#"):
            v = f"#{v}"
        hex_pattern = re.compile(r"^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$")
        if not hex_pattern.match(v):
            raise ValueError(f"Invalid hex color: {v}")
        return v.lower()

    @computed_field
    @property
    def position(self) -> Coordinate:
        """Get camera position as Coordinate."""
        return Coordinate(x=self.position_x, y=self.position_y)

    @computed_field
    @property
    def target(self) -> Coordinate:
        """Get target position as Coordinate."""
        return Coordinate(x=self.target_x, y=self.target_y)

    @computed_field
    @property
    def calculated_fov(self) -> float:
        """Calculate approximate FOV based on lens mm.

        Uses 35mm full-frame equivalent calculation.
        """
        if self.fov_angle:
            return self.fov_angle
        # Approximate horizontal FOV for 35mm full frame
        # FOV = 2 * arctan(sensor_width / (2 * focal_length))
        # For 35mm: sensor_width = 36mm
        import math

        return 2 * math.degrees(math.atan(36 / (2 * self.lens_mm)))

    def get_lens_description(self) -> str:
        """Get human-readable lens description."""
        if self.lens_mm <= 24:
            return f"{self.lens_mm}mm (wide angle)"
        elif self.lens_mm <= 50:
            return f"{self.lens_mm}mm (normal)"
        elif self.lens_mm <= 85:
            return f"{self.lens_mm}mm (portrait)"
        else:
            return f"{self.lens_mm}mm (telephoto)"


class Movement(BaseModel):
    """Movement path for characters or cameras.

    Defines a movement from one position to another, including
    the path taken and timing information.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440032",
                "entity_id": "550e8400-e29b-41d4-a716-446655440030",
                "entity_type": "character",
                "entity_name": "SARAH",
                "movement_type": "cross",
                "path": [{"x": 30.0, "y": 50.0}, {"x": 70.0, "y": 50.0}],
                "timing": "2 seconds",
            }
        }
    )

    id: UUID = Field(default_factory=uuid4, description="Unique identifier")
    entity_id: UUID = Field(..., description="ID of the moving entity")
    entity_type: EntityType = Field(..., description="Type of entity moving")
    entity_name: str | None = Field(default=None, max_length=100, description="Name of the entity")

    # Movement details
    movement_type: MovementType = Field(default=MovementType.WALK, description="Type of movement")
    path: list[Coordinate] = Field(
        ..., min_length=2, description="Path coordinates from start to end"
    )
    timing: str | None = Field(default=None, max_length=100, description="Timing description")
    duration_seconds: float | None = Field(
        default=None, ge=0.1, le=120, description="Duration in seconds"
    )

    # Beat/timing reference
    start_beat: int | None = Field(
        default=None, ge=1, description="Beat number when movement starts"
    )
    end_beat: int | None = Field(default=None, ge=1, description="Beat number when movement ends")

    # Visual customization
    color: str = Field(default="#2ecc71", description="Color for the movement line")
    line_style: str = Field(default="dashed", description="Line style: solid, dashed, dotted")
    arrow_style: str = Field(default="end", description="Arrow placement: none, start, end, both")

    # Notes
    notes: str | None = Field(default=None, max_length=500, description="Movement notes")
    dialogue_during: str | None = Field(
        default=None, max_length=500, description="Dialogue spoken during movement"
    )

    @field_validator("entity_name")
    @classmethod
    def uppercase_name(cls, v: str | None) -> str | None:
        """Entity names should be uppercase if provided."""
        return v.upper().strip() if v else None

    @field_validator("line_style")
    @classmethod
    def validate_line_style(cls, v: str) -> str:
        """Validate line style."""
        valid = {"solid", "dashed", "dotted"}
        v = v.lower().strip()
        if v not in valid:
            raise ValueError(f"Line style must be one of: {valid}")
        return v

    @field_validator("arrow_style")
    @classmethod
    def validate_arrow_style(cls, v: str) -> str:
        """Validate arrow style."""
        valid = {"none", "start", "end", "both"}
        v = v.lower().strip()
        if v not in valid:
            raise ValueError(f"Arrow style must be one of: {valid}")
        return v

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str) -> str:
        """Validate hex color format."""
        import re

        v = v.strip()
        if not v.startswith("#"):
            v = f"#{v}"
        hex_pattern = re.compile(r"^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$")
        if not hex_pattern.match(v):
            raise ValueError(f"Invalid hex color: {v}")
        return v.lower()

    @computed_field
    @property
    def start_position(self) -> Coordinate:
        """Get the starting position."""
        return self.path[0]

    @computed_field
    @property
    def end_position(self) -> Coordinate:
        """Get the ending position."""
        return self.path[-1]

    @computed_field
    @property
    def total_distance(self) -> float:
        """Calculate total distance of the path."""
        if len(self.path) < 2:
            return 0.0
        total = 0.0
        for i in range(len(self.path) - 1):
            total += self.path[i].distance_to(self.path[i + 1])
        return total

    @computed_field
    @property
    def waypoint_count(self) -> int:
        """Number of waypoints in the path."""
        return len(self.path)


class FloorPlanElement(BaseModel):
    """A static element in the floor plan (walls, furniture, etc.)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440033",
                "element_type": "furniture",
                "name": "Desk",
                "x": 60.0,
                "y": 40.0,
                "width": 15.0,
                "height": 8.0,
            }
        }
    )

    id: UUID = Field(default_factory=uuid4, description="Unique identifier")
    element_type: str = Field(
        ..., max_length=50, description="Type of element (wall, door, furniture, prop)"
    )
    name: str = Field(..., max_length=100, description="Element name")
    x: float = Field(..., ge=0, le=100, description="X position")
    y: float = Field(..., ge=0, le=100, description="Y position")
    width: float = Field(default=5.0, ge=0.1, le=100, description="Element width")
    height: float = Field(default=5.0, ge=0.1, le=100, description="Element height")
    rotation: float = Field(default=0, ge=0, le=360, description="Rotation in degrees")
    color: str = Field(default="#95a5a6", description="Element color")
    label: str | None = Field(default=None, max_length=50, description="Display label")


class BlockingDiagram(BaseModel):
    """Complete blocking diagram for a scene.

    Contains the floor plan, all character positions, camera setups,
    and movement paths. Can be rendered as SVG for visualization.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440034",
                "scene_id": "550e8400-e29b-41d4-a716-446655440003",
                "scene_number": 1,
                "title": "Scene 1 Blocking",
                "character_positions": [],
                "camera_positions": [],
                "movements": [],
            }
        }
    )

    id: UUID = Field(default_factory=uuid4, description="Unique identifier")
    scene_id: UUID = Field(..., description="ID of the scene")
    scene_number: int | None = Field(default=None, ge=1, description="Scene number")
    title: str = Field(default="Blocking Diagram", max_length=200, description="Diagram title")
    description: str | None = Field(
        default=None, max_length=1000, description="Diagram description"
    )

    # Floor plan
    floor_plan_svg: str | None = Field(
        default=None, description="SVG content for the floor plan background"
    )
    floor_plan_url: str | None = Field(
        default=None, max_length=2000, description="URL to floor plan image"
    )
    floor_plan_elements: list[FloorPlanElement] = Field(
        default_factory=list, description="Static floor plan elements"
    )

    # Positions and movements
    character_positions: list[CharacterPosition] = Field(
        default_factory=list, description="All character positions"
    )
    camera_positions: list[CameraSetup] = Field(
        default_factory=list, description="All camera setups"
    )
    movements: list[Movement] = Field(default_factory=list, description="All movement paths")

    # Diagram settings
    width: int = Field(default=800, ge=100, le=4000, description="Diagram width in pixels")
    height: int = Field(default=600, ge=100, le=4000, description="Diagram height in pixels")
    grid_visible: bool = Field(default=True, description="Whether to show grid")
    grid_size: int = Field(default=10, ge=5, le=50, description="Grid cell size")
    scale: str | None = Field(
        default=None, max_length=50, description="Scale reference (e.g., '1 unit = 1 foot')"
    )

    # Film grammar metadata
    axis_line_visible: bool = Field(
        default=True, description="Whether to show 180-degree rule axis"
    )
    axis_line_start: Coordinate | None = Field(
        default=None, description="Start of 180-degree axis line"
    )
    axis_line_end: Coordinate | None = Field(
        default=None, description="End of 180-degree axis line"
    )
    sight_lines_visible: bool = Field(
        default=True, description="Whether to show character sight lines"
    )

    # Beat/timing
    current_beat: int = Field(default=1, ge=1, description="Current beat being displayed")
    total_beats: int = Field(default=1, ge=1, description="Total number of beats")

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last update timestamp"
    )

    # AI metadata
    ai_generated: bool = Field(default=False, description="Whether AI generated this diagram")
    ai_model: str | None = Field(default=None, max_length=100, description="AI model used")
    film_grammar_compliant: bool | None = Field(
        default=None, description="Whether diagram follows film grammar rules"
    )
    film_grammar_notes: str | None = Field(
        default=None, max_length=1000, description="Film grammar compliance notes"
    )

    @computed_field
    @property
    def character_count(self) -> int:
        """Number of character positions."""
        return len(self.character_positions)

    @computed_field
    @property
    def camera_count(self) -> int:
        """Number of camera setups."""
        return len(self.camera_positions)

    @computed_field
    @property
    def movement_count(self) -> int:
        """Number of movements defined."""
        return len(self.movements)

    @computed_field
    @property
    def aspect_ratio(self) -> float:
        """Diagram aspect ratio."""
        return self.width / self.height

    def get_character_position(self, character_id: UUID) -> CharacterPosition | None:
        """Get position for a specific character."""
        for pos in self.character_positions:
            if pos.character_id == character_id:
                return pos
        return None

    def get_character_position_by_name(self, name: str) -> CharacterPosition | None:
        """Get position by character name."""
        normalized = name.upper().strip()
        for pos in self.character_positions:
            if pos.character_name == normalized:
                return pos
        return None

    def get_camera_setup(self, camera_id: UUID) -> CameraSetup | None:
        """Get a camera setup by ID."""
        for cam in self.camera_positions:
            if cam.id == camera_id:
                return cam
        return None

    def get_camera_by_name(self, name: str) -> CameraSetup | None:
        """Get a camera setup by name."""
        for cam in self.camera_positions:
            if cam.name.upper() == name.upper():
                return cam
        return None

    def get_movements_for_character(self, character_id: UUID) -> list[Movement]:
        """Get all movements for a specific character."""
        return [
            m
            for m in self.movements
            if m.entity_id == character_id and m.entity_type == EntityType.CHARACTER
        ]

    def get_movements_for_beat(self, beat_number: int) -> list[Movement]:
        """Get all movements occurring during a specific beat."""
        return [
            m
            for m in self.movements
            if m.start_beat and m.end_beat and m.start_beat <= beat_number <= m.end_beat
        ]

    def get_positions_for_beat(self, beat_number: int) -> list[CharacterPosition]:
        """Get character positions at a specific beat."""
        return [
            pos
            for pos in self.character_positions
            if pos.beat_number is None or pos.beat_number == beat_number
        ]

    def add_character_position(self, position: CharacterPosition) -> None:
        """Add a character position."""
        self.character_positions.append(position)
        self.updated_at = datetime.now(UTC)

    def add_camera_setup(self, camera: CameraSetup) -> None:
        """Add a camera setup."""
        self.camera_positions.append(camera)
        self.updated_at = datetime.now(UTC)

    def add_movement(self, movement: Movement) -> None:
        """Add a movement path."""
        self.movements.append(movement)
        self.updated_at = datetime.now(UTC)

    def update_timestamp(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now(UTC)

    def to_svg(self) -> str:
        """Generate SVG representation of the blocking diagram.

        Returns a basic SVG string. For production use, this should
        be enhanced with proper styling and interactivity.
        """
        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}">',
            "<style>",
            "  .character { fill-opacity: 0.8; }",
            "  .camera { fill-opacity: 0.8; }",
            "  .movement { stroke-dasharray: 5,5; fill: none; }",
            "  .label { font-family: Arial, sans-serif; font-size: 12px; }",
            "</style>",
        ]

        # Background
        svg_parts.append(f'<rect width="{self.width}" height="{self.height}" fill="#f5f5f5"/>')

        # Grid
        if self.grid_visible:
            svg_parts.append('<g class="grid" stroke="#ddd" stroke-width="0.5">')
            for x in range(0, self.width + 1, self.grid_size * self.width // 100):
                svg_parts.append(f'<line x1="{x}" y1="0" x2="{x}" y2="{self.height}"/>')
            for y in range(0, self.height + 1, self.grid_size * self.height // 100):
                svg_parts.append(f'<line x1="0" y1="{y}" x2="{self.width}" y2="{y}"/>')
            svg_parts.append("</g>")

        # Floor plan elements
        for elem in self.floor_plan_elements:
            ex = elem.x * self.width / 100
            ey = elem.y * self.height / 100
            ew = elem.width * self.width / 100
            eh = elem.height * self.height / 100
            svg_parts.append(
                f'<rect x="{ex - ew / 2}" y="{ey - eh / 2}" width="{ew}" height="{eh}" '
                f'fill="{elem.color}" stroke="#333" stroke-width="1" '
                f'transform="rotate({elem.rotation} {ex} {ey})"/>'
            )

        # Movements
        for movement in self.movements:
            if len(movement.path) >= 2:
                path_d = f"M {movement.path[0].x * self.width / 100} {movement.path[0].y * self.height / 100}"
                for coord in movement.path[1:]:
                    path_d += f" L {coord.x * self.width / 100} {coord.y * self.height / 100}"
                svg_parts.append(
                    f'<path d="{path_d}" class="movement" stroke="{movement.color}" stroke-width="2"/>'
                )

        # Camera setups (as triangles representing FOV)
        for cam in self.camera_positions:
            cx = cam.position_x * self.width / 100
            cy = cam.position_y * self.height / 100
            svg_parts.append(
                f'<circle cx="{cx}" cy="{cy}" r="10" class="camera" fill="{cam.color}" stroke="#333" stroke-width="2"/>'
            )
            svg_parts.append(
                f'<text x="{cx}" y="{cy + 4}" class="label" text-anchor="middle" fill="white">{cam.name[0]}</text>'
            )
            # Line to target
            tx = cam.target_x * self.width / 100
            ty = cam.target_y * self.height / 100
            svg_parts.append(
                f'<line x1="{cx}" y1="{cy}" x2="{tx}" y2="{ty}" stroke="{cam.color}" stroke-width="1" stroke-dasharray="3,3"/>'
            )

        # Character positions
        for pos in self.character_positions:
            px = pos.x * self.width / 100
            py = pos.y * self.height / 100
            svg_parts.append(
                f'<circle cx="{px}" cy="{py}" r="15" class="character" fill="{pos.color}" stroke="#333" stroke-width="2"/>'
            )
            svg_parts.append(
                f'<text x="{px}" y="{py + 5}" class="label" text-anchor="middle" fill="white">{pos.display_label}</text>'
            )

        svg_parts.append("</svg>")
        return "\n".join(svg_parts)


class SceneBlockingSet(BaseModel):
    """Collection of blocking diagrams for different beats in a scene.

    Allows for multiple blocking states to be stored for different
    moments within the same scene.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"scene_id": "550e8400-e29b-41d4-a716-446655440003", "diagrams": []}
        }
    )

    scene_id: UUID = Field(..., description="ID of the scene")
    scene_number: int | None = Field(default=None, ge=1, description="Scene number")
    diagrams: list[BlockingDiagram] = Field(
        default_factory=list, description="Blocking diagrams for different beats"
    )
    notes: str | None = Field(
        default=None, max_length=2000, description="General blocking notes for the scene"
    )

    @computed_field
    @property
    def diagram_count(self) -> int:
        """Number of blocking diagrams."""
        return len(self.diagrams)

    def get_diagram_for_beat(self, beat: int) -> BlockingDiagram | None:
        """Get the blocking diagram for a specific beat."""
        for diagram in self.diagrams:
            if diagram.current_beat == beat:
                return diagram
        return None


# Type aliases
CharacterPositionList = list[CharacterPosition]
CameraSetupList = list[CameraSetup]
MovementList = list[Movement]
