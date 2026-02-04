"""LangGraph state definitions for the movie conceptualizer pipeline.

This module defines the state objects that flow through the LangGraph
workflow, carrying data between nodes.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from movie_conceptualizer.models import Script
from movie_conceptualizer.models.analysis import (
    AnalyzedScene,
    CharacterVisualDescription,
    ShotList,
    Storyboard,
    StoryboardFrame,
)


class PipelineState(TypedDict, total=False):
    """State object for the movie conceptualizer LangGraph pipeline.

    This TypedDict defines all the data that flows through the pipeline,
    from the initial script input to the final storyboard output.
    """

    # Input
    script: Script
    """The parsed screenplay to process."""

    # Configuration
    style_guide: str | None
    """Optional style guide for consistent visual output."""

    model_name: str
    """The Claude model to use for generation."""

    temperature: float
    """The temperature for LLM sampling."""

    # Analysis outputs
    analyzed_scenes: list[AnalyzedScene]
    """List of analyzed scenes with emotional/visual metadata."""

    main_characters: list[CharacterVisualDescription]
    """Main character descriptions for visual consistency."""

    # Shot design outputs
    shot_lists: list[ShotList]
    """List of shot lists, one per scene."""

    # Storyboard outputs
    storyboards: list[Storyboard]
    """List of storyboards, one per scene."""

    storyboard_frames: list[StoryboardFrame]
    """Flattened list of all storyboard frames."""

    # Progress tracking
    current_scene_index: int
    """Current scene being processed (for incremental processing)."""

    total_scenes: int
    """Total number of scenes to process."""

    # Error handling
    errors: list[str]
    """List of any errors encountered during processing."""

    # Messages for human-in-the-loop
    messages: Annotated[list, add_messages]
    """Messages for human-in-the-loop interaction."""


class PipelineConfig(BaseModel):
    """Configuration for the pipeline execution."""

    model_name: str = Field(
        default="claude-sonnet-4-20250514",
        description="The Claude model to use for generation",
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Temperature for LLM sampling",
    )
    style_guide: str | None = Field(
        default=None,
        description="Optional style guide for visual consistency",
    )
    max_concurrent_scenes: int = Field(
        default=5,
        ge=1,
        description="Maximum number of scenes to process concurrently",
    )
    enable_checkpoints: bool = Field(
        default=True,
        description="Whether to enable checkpointing for human-in-the-loop",
    )


class PipelineResult(BaseModel):
    """Result of running the complete pipeline."""

    script_title: str = Field(description="Title of the processed script")
    scenes_processed: int = Field(description="Number of scenes processed")
    total_shots: int = Field(description="Total number of shots generated")
    total_frames: int = Field(description="Total number of storyboard frames")
    analyzed_scenes: list[AnalyzedScene] = Field(
        default_factory=list, description="All analyzed scenes"
    )
    shot_lists: list[ShotList] = Field(
        default_factory=list, description="All shot lists"
    )
    storyboards: list[Storyboard] = Field(
        default_factory=list, description="All storyboards"
    )
    errors: list[str] = Field(
        default_factory=list, description="Any errors encountered"
    )
    success: bool = Field(description="Whether the pipeline completed successfully")

    @classmethod
    def from_state(cls, state: PipelineState) -> "PipelineResult":
        """Create a PipelineResult from a PipelineState.

        Args:
            state: The final pipeline state

        Returns:
            A PipelineResult summarizing the pipeline output
        """
        script = state.get("script")
        analyzed_scenes = state.get("analyzed_scenes", [])
        shot_lists = state.get("shot_lists", [])
        storyboards = state.get("storyboards", [])
        errors = state.get("errors", [])

        total_shots = sum(len(sl.shots) for sl in shot_lists)
        total_frames = sum(len(sb.frames) for sb in storyboards)

        return cls(
            script_title=script.title if script else "Unknown",
            scenes_processed=len(analyzed_scenes),
            total_shots=total_shots,
            total_frames=total_frames,
            analyzed_scenes=analyzed_scenes,
            shot_lists=shot_lists,
            storyboards=storyboards,
            errors=errors,
            success=len(errors) == 0,
        )


def create_initial_state(
    script: Script,
    config: PipelineConfig | None = None,
) -> PipelineState:
    """Create the initial pipeline state from a script.

    Args:
        script: The parsed script to process
        config: Optional pipeline configuration

    Returns:
        The initial PipelineState
    """
    config = config or PipelineConfig()

    return PipelineState(
        script=script,
        style_guide=config.style_guide,
        model_name=config.model_name,
        temperature=config.temperature,
        analyzed_scenes=[],
        main_characters=[],
        shot_lists=[],
        storyboards=[],
        storyboard_frames=[],
        current_scene_index=0,
        total_scenes=len(script.scenes),
        errors=[],
        messages=[],
    )


__all__ = [
    "PipelineState",
    "PipelineConfig",
    "PipelineResult",
    "create_initial_state",
]
