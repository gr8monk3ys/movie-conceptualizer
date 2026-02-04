"""LangGraph workflows for the movie conceptualizer pipeline.

This module provides the complete workflow for processing screenplays
through analysis, shot design, and storyboard creation.

Example usage:
    from movie_conceptualizer.workflows import run_pipeline, PipelineConfig
    from movie_conceptualizer.models import Script

    # Create or parse a script
    script = Script(title="My Movie", scenes=[...])

    # Run the pipeline
    result = run_pipeline(script)

    # Access results
    print(f"Processed {result.scenes_processed} scenes")
    print(f"Generated {result.total_shots} shots")
    print(f"Created {result.total_frames} storyboard frames")

For async usage:
    result = await arun_pipeline(script)

For streaming results:
    for event in stream_pipeline(script):
        print(f"Completed: {event}")
"""

from movie_conceptualizer.workflows.pipeline import (
    arun_pipeline,
    astream_pipeline,
    compile_pipeline,
    create_pipeline_graph,
    default_pipeline,
    run_pipeline,
    stream_pipeline,
)
from movie_conceptualizer.workflows.state import (
    PipelineConfig,
    PipelineResult,
    PipelineState,
    create_initial_state,
)

__all__ = [
    # State
    "PipelineState",
    "PipelineConfig",
    "PipelineResult",
    "create_initial_state",
    # Graph construction
    "create_pipeline_graph",
    "compile_pipeline",
    # Execution
    "run_pipeline",
    "arun_pipeline",
    "stream_pipeline",
    "astream_pipeline",
    # Default pipeline
    "default_pipeline",
]
