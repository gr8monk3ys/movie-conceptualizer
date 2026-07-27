"""Pydantic data models for the AI filmmaking platform.

Modules:
    core: Core screenplay entities (Project, Script, Scene, Character, etc.)
    analysis: AI pipeline models (AnalyzedScene, Shot, ShotList, Storyboard, etc.)

Example usage:
    from movie_conceptualizer.models import Script, Scene, Shot, ShotList
    from movie_conceptualizer.models import Storyboard, StoryboardFrame
"""

from movie_conceptualizer.models.analysis import (
    AnalyzedScene,
    AnalyzedScript,
    CameraAngle,
    CameraMovement,
    CharacterVisualDescription,
    DramaticMoment,
    EmotionalTone,
    LightingStyle,
    PacingType,
    Shot,
    ShotList,
    ShotType,
    Storyboard,
    StoryboardFrame,
    VisualEmphasisPoint,
)

# Both core and analysis define an EmotionalBeat; the core one keeps the plain
# name (existing behavior) and the analysis one is exported with a prefix.
from movie_conceptualizer.models.analysis import (
    EmotionalBeat as AnalysisEmotionalBeat,
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
    # Analysis / pipeline models
    "AnalysisEmotionalBeat",
    "AnalyzedScene",
    "AnalyzedScript",
    "CameraAngle",
    "CameraMovement",
    "CharacterVisualDescription",
    "DramaticMoment",
    "EmotionalTone",
    "LightingStyle",
    "PacingType",
    "Shot",
    "ShotList",
    "ShotType",
    "Storyboard",
    "StoryboardFrame",
    "VisualEmphasisPoint",
]
