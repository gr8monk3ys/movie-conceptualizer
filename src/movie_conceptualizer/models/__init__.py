"""Pydantic data models for the AI filmmaking platform.

This package contains comprehensive data models for all aspects of
film pre-production, from script parsing to blocking diagrams.

Modules:
    core: Core screenplay entities (Project, Script, Scene, Character, etc.)
    shots: Shot planning entities (Shot, ShotType, CameraMovement, ShotList)
    storyboard: Storyboard entities (StoryboardFrame, Storyboard, CharacterReference)
    blocking: Blocking diagram entities (BlockingDiagram, CharacterPosition, etc.)
    analysis: Script analysis models (AnalyzedScene, AnalyzedScript, etc.)

Example usage:
    from movie_conceptualizer.models import Project, Script, Scene, Shot
    from movie_conceptualizer.models import Storyboard, StoryboardFrame
    from movie_conceptualizer.models import BlockingDiagram, CharacterPosition
"""

# Core models
# Analysis models (for script analysis and legacy compatibility)
from movie_conceptualizer.models.analysis import (
    AnalyzedScene,
    AnalyzedScript,
    CameraAngle,
    CharacterVisualDescription,
    DramaticMoment,
    EmotionalTone,
    LightingStyle,
    PacingType,
    VisualEmphasisPoint,
)

# Import analysis versions with aliases for backward compatibility
from movie_conceptualizer.models.analysis import (
    CameraMovement as AnalysisCameraMovement,
)
from movie_conceptualizer.models.analysis import (
    EmotionalBeat as AnalysisEmotionalBeat,
)
from movie_conceptualizer.models.analysis import (
    Shot as AnalysisShot,
)
from movie_conceptualizer.models.analysis import (
    ShotList as AnalysisShotList,
)
from movie_conceptualizer.models.analysis import (
    ShotType as AnalysisShotType,
)
from movie_conceptualizer.models.analysis import (
    Storyboard as AnalysisStoryboard,
)
from movie_conceptualizer.models.analysis import (
    StoryboardFrame as AnalysisStoryboardFrame,
)

# Blocking diagram models
from movie_conceptualizer.models.blocking import (
    BlockingDiagram,
    CameraSetup,
    CameraSetupList,
    CharacterPosition,
    CharacterPositionList,
    Coordinate,
    EntityType,
    FacingDirection,
    FloorPlanElement,
    Movement,
    MovementList,
    MovementType,
    SceneBlockingSet,
    StagePosition,
)
from movie_conceptualizer.models.core import (
    ActionBlock,
    BreakdownCategory,
    BreakdownElement,
    BreakdownElementList,
    Character,
    CharacterList,
    DialogueBlock,
    EmotionalBeat,
    Genre,
    Location,
    LocationList,
    ParsedScript,
    Project,
    ProjectType,
    Scene,
    SceneList,
    SceneType,
    Script,
    TimeOfDay,
    TitlePage,
    TitlePageField,
    Transition,
)

# Shot planning models (comprehensive versions)
from movie_conceptualizer.models.shots import (
    CameraMovement,
    ProjectShotList,
    Shot,
    ShotList,
    ShotListCollection,
    ShotPurpose,
    ShotSize,
    ShotType,
)

# Storyboard models (comprehensive versions)
from movie_conceptualizer.models.storyboard import (
    AspectRatio,
    CharacterReference,
    CharacterReferenceList,
    FrameStatus,
    Storyboard,
    StoryboardFrame,
    StoryboardFrameList,
    StoryboardStyle,
    StyleGuidelines,
    VisualTrait,
)

__all__ = [
    # Core models
    "ActionBlock",
    "BreakdownCategory",
    "BreakdownElement",
    "BreakdownElementList",
    "Character",
    "CharacterList",
    "DialogueBlock",
    "EmotionalBeat",
    "Genre",
    "Location",
    "LocationList",
    "ParsedScript",
    "Project",
    "ProjectType",
    "Scene",
    "SceneList",
    "SceneType",
    "Script",
    "TimeOfDay",
    "TitlePage",
    "TitlePageField",
    "Transition",
    # Shot planning models (comprehensive)
    "CameraMovement",
    "ProjectShotList",
    "Shot",
    "ShotList",
    "ShotListCollection",
    "ShotPurpose",
    "ShotSize",
    "ShotType",
    # Storyboard models (comprehensive)
    "AspectRatio",
    "CharacterReference",
    "CharacterReferenceList",
    "FrameStatus",
    "Storyboard",
    "StoryboardFrame",
    "StoryboardFrameList",
    "StoryboardStyle",
    "StyleGuidelines",
    "VisualTrait",
    # Blocking diagram models
    "BlockingDiagram",
    "CameraSetup",
    "CameraSetupList",
    "CharacterPosition",
    "CharacterPositionList",
    "Coordinate",
    "EntityType",
    "FacingDirection",
    "FloorPlanElement",
    "Movement",
    "MovementList",
    "MovementType",
    "SceneBlockingSet",
    "StagePosition",
    # Analysis models
    "AnalyzedScene",
    "AnalyzedScript",
    "CameraAngle",
    "CharacterVisualDescription",
    "DramaticMoment",
    "EmotionalTone",
    "LightingStyle",
    "PacingType",
    "VisualEmphasisPoint",
    # Legacy aliases for backward compatibility
    "AnalysisCameraMovement",
    "AnalysisShot",
    "AnalysisShotList",
    "AnalysisShotType",
    "AnalysisStoryboard",
    "AnalysisStoryboardFrame",
    "AnalysisEmotionalBeat",
]
