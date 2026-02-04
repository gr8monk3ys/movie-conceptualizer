"""AI agents for the movie conceptualizer pipeline.

This module provides specialized agents for different stages of the
screenplay-to-storyboard pipeline:

- ScriptAnalyzerAgent: Analyzes scripts for emotional and visual content
- ShotDesignerAgent: Creates shot lists based on scene analysis
- StoryboardArtistAgent: Generates image prompts for storyboard frames
"""

from movie_conceptualizer.agents.base import BaseAgent
from movie_conceptualizer.agents.script_analyzer import (
    ScriptAnalyzerAgent,
    aanalyze_script,
    analyze_script,
)
from movie_conceptualizer.agents.shot_designer import (
    ShotDesignerAgent,
    adesign_shot_list,
    design_shot_list,
)
from movie_conceptualizer.agents.storyboard_artist import (
    StoryboardArtistAgent,
    acreate_storyboard,
    create_storyboard,
)

__all__ = [
    # Base
    "BaseAgent",
    # Script Analyzer
    "ScriptAnalyzerAgent",
    "analyze_script",
    "aanalyze_script",
    # Shot Designer
    "ShotDesignerAgent",
    "design_shot_list",
    "adesign_shot_list",
    # Storyboard Artist
    "StoryboardArtistAgent",
    "create_storyboard",
    "acreate_storyboard",
]
