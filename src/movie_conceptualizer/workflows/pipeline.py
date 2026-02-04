"""Main LangGraph workflow for the movie conceptualizer pipeline.

This module defines the complete LangGraph workflow that processes scripts
through analysis, shot design, and storyboard creation stages.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from movie_conceptualizer.agents import (
    ScriptAnalyzerAgent,
    ShotDesignerAgent,
    StoryboardArtistAgent,
)
from movie_conceptualizer.models import Script
from movie_conceptualizer.models.analysis import StoryboardFrame
from movie_conceptualizer.workflows.state import (
    PipelineConfig,
    PipelineResult,
    PipelineState,
    create_initial_state,
)


# ============================================================================
# Node Functions
# ============================================================================


def validate_input(state: PipelineState) -> PipelineState:
    """Validate the input script and configuration.

    Args:
        state: The current pipeline state

    Returns:
        Updated state with validation results
    """
    errors: list[str] = list(state.get("errors", []))

    script = state.get("script")
    if script is None:
        errors.append("No script provided to pipeline")
    elif not script.scenes:
        errors.append("Script has no scenes to process")

    return PipelineState(
        **state,
        errors=errors,
        total_scenes=len(script.scenes) if script else 0,
    )


def analyze_scenes(state: PipelineState) -> PipelineState:
    """Analyze all scenes in the script using the ScriptAnalyzerAgent.

    Args:
        state: The current pipeline state

    Returns:
        Updated state with analyzed scenes
    """
    errors: list[str] = list(state.get("errors", []))
    script = state.get("script")

    if not script or errors:
        return state

    try:
        # Create the analyzer agent with configured settings
        analyzer = ScriptAnalyzerAgent(
            model_name=state.get("model_name", "claude-sonnet-4-20250514"),
            temperature=state.get("temperature", 0.7),
        )

        # Analyze the complete script
        analyzed_script = analyzer.analyze_script(script)

        return PipelineState(
            **state,
            analyzed_scenes=analyzed_script.analyzed_scenes,
            main_characters=analyzed_script.main_characters,
        )

    except Exception as e:
        errors.append(f"Error in scene analysis: {str(e)}")
        return PipelineState(**state, errors=errors)


async def analyze_scenes_async(state: PipelineState) -> PipelineState:
    """Async version of analyze_scenes for concurrent processing.

    Args:
        state: The current pipeline state

    Returns:
        Updated state with analyzed scenes
    """
    errors: list[str] = list(state.get("errors", []))
    script = state.get("script")

    if not script or errors:
        return state

    try:
        analyzer = ScriptAnalyzerAgent(
            model_name=state.get("model_name", "claude-sonnet-4-20250514"),
            temperature=state.get("temperature", 0.7),
        )

        analyzed_script = await analyzer.aanalyze_script(script)

        return PipelineState(
            **state,
            analyzed_scenes=analyzed_script.analyzed_scenes,
            main_characters=analyzed_script.main_characters,
        )

    except Exception as e:
        errors.append(f"Error in scene analysis: {str(e)}")
        return PipelineState(**state, errors=errors)


def design_shots(state: PipelineState) -> PipelineState:
    """Design shot lists for all analyzed scenes using the ShotDesignerAgent.

    Args:
        state: The current pipeline state

    Returns:
        Updated state with shot lists
    """
    errors: list[str] = list(state.get("errors", []))
    analyzed_scenes = state.get("analyzed_scenes", [])

    if not analyzed_scenes or errors:
        return state

    try:
        designer = ShotDesignerAgent(
            model_name=state.get("model_name", "claude-sonnet-4-20250514"),
            temperature=state.get("temperature", 0.7),
        )

        shot_lists = []
        for scene in analyzed_scenes:
            shot_list = designer.design_shot_list(scene)
            shot_lists.append(shot_list)

        return PipelineState(**state, shot_lists=shot_lists)

    except Exception as e:
        errors.append(f"Error in shot design: {str(e)}")
        return PipelineState(**state, errors=errors)


async def design_shots_async(state: PipelineState) -> PipelineState:
    """Async version of design_shots for concurrent processing.

    Args:
        state: The current pipeline state

    Returns:
        Updated state with shot lists
    """
    errors: list[str] = list(state.get("errors", []))
    analyzed_scenes = state.get("analyzed_scenes", [])

    if not analyzed_scenes or errors:
        return state

    try:
        designer = ShotDesignerAgent(
            model_name=state.get("model_name", "claude-sonnet-4-20250514"),
            temperature=state.get("temperature", 0.7),
        )

        # Process all scenes concurrently
        tasks = [designer.adesign_shot_list(scene) for scene in analyzed_scenes]
        shot_lists = list(await asyncio.gather(*tasks))

        return PipelineState(**state, shot_lists=shot_lists)

    except Exception as e:
        errors.append(f"Error in shot design: {str(e)}")
        return PipelineState(**state, errors=errors)


def create_storyboards(state: PipelineState) -> PipelineState:
    """Create storyboards for all scenes using the StoryboardArtistAgent.

    Args:
        state: The current pipeline state

    Returns:
        Updated state with storyboards and frames
    """
    errors: list[str] = list(state.get("errors", []))
    shot_lists = state.get("shot_lists", [])
    analyzed_scenes = state.get("analyzed_scenes", [])

    if not shot_lists or not analyzed_scenes or errors:
        return state

    try:
        artist = StoryboardArtistAgent(
            model_name=state.get("model_name", "claude-sonnet-4-20250514"),
            temperature=state.get("temperature", 0.7),
        )

        style_guide = state.get("style_guide")

        storyboards = artist.create_storyboards(
            shot_lists=shot_lists,
            analyzed_scenes=analyzed_scenes,
            style_guide=style_guide,
        )

        # Flatten all frames into a single list
        all_frames: list[StoryboardFrame] = []
        for storyboard in storyboards:
            all_frames.extend(storyboard.frames)

        return PipelineState(
            **state,
            storyboards=storyboards,
            storyboard_frames=all_frames,
        )

    except Exception as e:
        errors.append(f"Error in storyboard creation: {str(e)}")
        return PipelineState(**state, errors=errors)


async def create_storyboards_async(state: PipelineState) -> PipelineState:
    """Async version of create_storyboards for concurrent processing.

    Args:
        state: The current pipeline state

    Returns:
        Updated state with storyboards and frames
    """
    errors: list[str] = list(state.get("errors", []))
    shot_lists = state.get("shot_lists", [])
    analyzed_scenes = state.get("analyzed_scenes", [])

    if not shot_lists or not analyzed_scenes or errors:
        return state

    try:
        artist = StoryboardArtistAgent(
            model_name=state.get("model_name", "claude-sonnet-4-20250514"),
            temperature=state.get("temperature", 0.7),
        )

        style_guide = state.get("style_guide")

        storyboards = await artist.acreate_storyboards(
            shot_lists=shot_lists,
            analyzed_scenes=analyzed_scenes,
            style_guide=style_guide,
        )

        all_frames: list[StoryboardFrame] = []
        for storyboard in storyboards:
            all_frames.extend(storyboard.frames)

        return PipelineState(
            **state,
            storyboards=storyboards,
            storyboard_frames=all_frames,
        )

    except Exception as e:
        errors.append(f"Error in storyboard creation: {str(e)}")
        return PipelineState(**state, errors=errors)


def human_review_analysis(state: PipelineState) -> PipelineState:
    """Human-in-the-loop checkpoint after scene analysis.

    This node allows human review and potential modification of the
    scene analysis before proceeding to shot design.

    Args:
        state: The current pipeline state

    Returns:
        State (potentially modified by human input)
    """
    analyzed_scenes = state.get("analyzed_scenes", [])

    if not analyzed_scenes:
        return state

    # Interrupt for human review
    # The human can approve, modify, or reject the analysis
    review_result = interrupt(
        {
            "message": "Review scene analysis before proceeding to shot design",
            "scenes_analyzed": len(analyzed_scenes),
            "data": {
                "analyzed_scenes": [
                    {
                        "scene_number": s.scene_number,
                        "heading": s.scene_heading,
                        "tone": s.overall_tone.value,
                        "pacing": s.pacing.value,
                        "summary": s.summary,
                    }
                    for s in analyzed_scenes
                ]
            },
        }
    )

    # If human provided modifications, apply them
    # For now, we just pass through
    return state


def human_review_shots(state: PipelineState) -> PipelineState:
    """Human-in-the-loop checkpoint after shot design.

    This node allows human review of shot lists before
    proceeding to storyboard creation.

    Args:
        state: The current pipeline state

    Returns:
        State (potentially modified by human input)
    """
    shot_lists = state.get("shot_lists", [])

    if not shot_lists:
        return state

    total_shots = sum(len(sl.shots) for sl in shot_lists)

    review_result = interrupt(
        {
            "message": "Review shot lists before proceeding to storyboard creation",
            "total_shots": total_shots,
            "data": {
                "shot_lists": [
                    {
                        "scene_number": sl.scene_number,
                        "heading": sl.scene_heading,
                        "shot_count": len(sl.shots),
                        "coverage_notes": sl.coverage_notes,
                    }
                    for sl in shot_lists
                ]
            },
        }
    )

    return state


# ============================================================================
# Conditional Edge Functions
# ============================================================================


def should_continue_after_validation(
    state: PipelineState,
) -> Literal["analyze_scenes", "end"]:
    """Determine if pipeline should continue after validation.

    Args:
        state: The current pipeline state

    Returns:
        Next node name or "end"
    """
    errors = state.get("errors", [])
    if errors:
        return "end"
    return "analyze_scenes"


def should_continue_after_analysis(
    state: PipelineState,
) -> Literal["design_shots", "human_review_analysis", "end"]:
    """Determine if pipeline should continue after analysis.

    Args:
        state: The current pipeline state

    Returns:
        Next node name
    """
    errors = state.get("errors", [])
    analyzed_scenes = state.get("analyzed_scenes", [])

    if errors:
        return "end"

    if not analyzed_scenes:
        return "end"

    # For now, skip human review by default
    # In production, this could be configurable
    return "design_shots"


def should_continue_after_shots(
    state: PipelineState,
) -> Literal["create_storyboards", "human_review_shots", "end"]:
    """Determine if pipeline should continue after shot design.

    Args:
        state: The current pipeline state

    Returns:
        Next node name
    """
    errors = state.get("errors", [])
    shot_lists = state.get("shot_lists", [])

    if errors:
        return "end"

    if not shot_lists:
        return "end"

    return "create_storyboards"


# ============================================================================
# Graph Construction
# ============================================================================


def create_pipeline_graph(
    enable_human_review: bool = False,
    use_async: bool = False,
) -> StateGraph:
    """Create the LangGraph StateGraph for the pipeline.

    Args:
        enable_human_review: Whether to include human review checkpoints
        use_async: Whether to use async node functions

    Returns:
        A configured StateGraph
    """
    # Create the graph
    graph = StateGraph(PipelineState)

    # Add nodes
    graph.add_node("validate_input", validate_input)

    if use_async:
        graph.add_node("analyze_scenes", analyze_scenes_async)
        graph.add_node("design_shots", design_shots_async)
        graph.add_node("create_storyboards", create_storyboards_async)
    else:
        graph.add_node("analyze_scenes", analyze_scenes)
        graph.add_node("design_shots", design_shots)
        graph.add_node("create_storyboards", create_storyboards)

    if enable_human_review:
        graph.add_node("human_review_analysis", human_review_analysis)
        graph.add_node("human_review_shots", human_review_shots)

    # Add edges
    graph.add_edge(START, "validate_input")

    # Conditional edge after validation
    graph.add_conditional_edges(
        "validate_input",
        should_continue_after_validation,
        {
            "analyze_scenes": "analyze_scenes",
            "end": END,
        },
    )

    # Edges after analysis
    if enable_human_review:
        graph.add_conditional_edges(
            "analyze_scenes",
            should_continue_after_analysis,
            {
                "design_shots": "design_shots",
                "human_review_analysis": "human_review_analysis",
                "end": END,
            },
        )
        graph.add_edge("human_review_analysis", "design_shots")
    else:
        graph.add_conditional_edges(
            "analyze_scenes",
            should_continue_after_analysis,
            {
                "design_shots": "design_shots",
                "human_review_analysis": "design_shots",  # Skip review
                "end": END,
            },
        )

    # Edges after shot design
    if enable_human_review:
        graph.add_conditional_edges(
            "design_shots",
            should_continue_after_shots,
            {
                "create_storyboards": "create_storyboards",
                "human_review_shots": "human_review_shots",
                "end": END,
            },
        )
        graph.add_edge("human_review_shots", "create_storyboards")
    else:
        graph.add_conditional_edges(
            "design_shots",
            should_continue_after_shots,
            {
                "create_storyboards": "create_storyboards",
                "human_review_shots": "create_storyboards",  # Skip review
                "end": END,
            },
        )

    # Final edge
    graph.add_edge("create_storyboards", END)

    return graph


def compile_pipeline(
    enable_human_review: bool = False,
    enable_checkpoints: bool = True,
    use_async: bool = False,
):
    """Compile the pipeline graph into a runnable.

    Args:
        enable_human_review: Whether to include human review checkpoints
        enable_checkpoints: Whether to enable state checkpointing
        use_async: Whether to use async node functions

    Returns:
        A compiled LangGraph runnable
    """
    graph = create_pipeline_graph(
        enable_human_review=enable_human_review,
        use_async=use_async,
    )

    if enable_checkpoints:
        checkpointer = MemorySaver()
        return graph.compile(checkpointer=checkpointer)
    else:
        return graph.compile()


# ============================================================================
# Pipeline Execution Functions
# ============================================================================


def run_pipeline(
    script: Script,
    config: PipelineConfig | None = None,
    enable_human_review: bool = False,
    thread_id: str | None = None,
) -> PipelineResult:
    """Run the complete pipeline on a script.

    Args:
        script: The parsed script to process
        config: Optional pipeline configuration
        enable_human_review: Whether to enable human review checkpoints
        thread_id: Optional thread ID for checkpointing

    Returns:
        A PipelineResult with all outputs
    """
    config = config or PipelineConfig()

    # Create initial state
    initial_state = create_initial_state(script, config)

    # Compile the pipeline
    pipeline = compile_pipeline(
        enable_human_review=enable_human_review,
        enable_checkpoints=config.enable_checkpoints,
        use_async=False,
    )

    # Run the pipeline
    run_config: dict[str, Any] = {}
    if thread_id and config.enable_checkpoints:
        run_config["configurable"] = {"thread_id": thread_id}

    final_state = pipeline.invoke(initial_state, run_config)

    return PipelineResult.from_state(final_state)


async def arun_pipeline(
    script: Script,
    config: PipelineConfig | None = None,
    enable_human_review: bool = False,
    thread_id: str | None = None,
) -> PipelineResult:
    """Async version of run_pipeline.

    Args:
        script: The parsed script to process
        config: Optional pipeline configuration
        enable_human_review: Whether to enable human review checkpoints
        thread_id: Optional thread ID for checkpointing

    Returns:
        A PipelineResult with all outputs
    """
    config = config or PipelineConfig()

    initial_state = create_initial_state(script, config)

    pipeline = compile_pipeline(
        enable_human_review=enable_human_review,
        enable_checkpoints=config.enable_checkpoints,
        use_async=True,
    )

    run_config: dict[str, Any] = {}
    if thread_id and config.enable_checkpoints:
        run_config["configurable"] = {"thread_id": thread_id}

    final_state = await pipeline.ainvoke(initial_state, run_config)

    return PipelineResult.from_state(final_state)


def stream_pipeline(
    script: Script,
    config: PipelineConfig | None = None,
    enable_human_review: bool = False,
    thread_id: str | None = None,
):
    """Stream pipeline execution, yielding state after each node.

    Args:
        script: The parsed script to process
        config: Optional pipeline configuration
        enable_human_review: Whether to enable human review checkpoints
        thread_id: Optional thread ID for checkpointing

    Yields:
        Tuples of (node_name, state) after each node execution
    """
    config = config or PipelineConfig()

    initial_state = create_initial_state(script, config)

    pipeline = compile_pipeline(
        enable_human_review=enable_human_review,
        enable_checkpoints=config.enable_checkpoints,
        use_async=False,
    )

    run_config: dict[str, Any] = {}
    if thread_id and config.enable_checkpoints:
        run_config["configurable"] = {"thread_id": thread_id}

    for event in pipeline.stream(initial_state, run_config):
        yield event


async def astream_pipeline(
    script: Script,
    config: PipelineConfig | None = None,
    enable_human_review: bool = False,
    thread_id: str | None = None,
):
    """Async stream pipeline execution.

    Args:
        script: The parsed script to process
        config: Optional pipeline configuration
        enable_human_review: Whether to enable human review checkpoints
        thread_id: Optional thread ID for checkpointing

    Yields:
        Tuples of (node_name, state) after each node execution
    """
    config = config or PipelineConfig()

    initial_state = create_initial_state(script, config)

    pipeline = compile_pipeline(
        enable_human_review=enable_human_review,
        enable_checkpoints=config.enable_checkpoints,
        use_async=True,
    )

    run_config: dict[str, Any] = {}
    if thread_id and config.enable_checkpoints:
        run_config["configurable"] = {"thread_id": thread_id}

    async for event in pipeline.astream(initial_state, run_config):
        yield event


# Create a default compiled pipeline for convenience
default_pipeline = compile_pipeline(
    enable_human_review=False,
    enable_checkpoints=False,
    use_async=False,
)


__all__ = [
    # Graph construction
    "create_pipeline_graph",
    "compile_pipeline",
    # Execution functions
    "run_pipeline",
    "arun_pipeline",
    "stream_pipeline",
    "astream_pipeline",
    # Default pipeline
    "default_pipeline",
    # Node functions (for testing)
    "validate_input",
    "analyze_scenes",
    "analyze_scenes_async",
    "design_shots",
    "design_shots_async",
    "create_storyboards",
    "create_storyboards_async",
]
