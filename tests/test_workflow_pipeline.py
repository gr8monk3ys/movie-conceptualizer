"""Tests that execute the LangGraph pipeline end-to-end with mocked agents.

These exist because the CLI tests mock ``run_pipeline`` itself, which means
graph wiring bugs (state-merge errors, checkpointer configuration) are
invisible to them. Everything here runs offline: the agent LLM methods are
monkeypatched at the class level, so the graph, conditional edges, and state
handling are exercised for real.
"""

from movie_conceptualizer.agents import (
    ScriptAnalyzerAgent,
    ShotDesignerAgent,
    StoryboardArtistAgent,
)
from movie_conceptualizer.models import Script
from movie_conceptualizer.models.analysis import (
    AnalyzedScene,
    AnalyzedScript,
    CharacterVisualDescription,
    EmotionalTone,
    PacingType,
    Shot,
    ShotList,
    Storyboard,
    StoryboardFrame,
)
from movie_conceptualizer.parsers import parse_fountain
from movie_conceptualizer.workflows import PipelineConfig, run_pipeline
from movie_conceptualizer.workflows.pipeline import arun_pipeline

SAMPLE_FOUNTAIN = """\
Title: Graph Test

INT. LAB - NIGHT

A robot hums quietly.

ADA
It works.

EXT. ROOFTOP - DAWN

The city wakes.
"""


def _fake_analyzed_scene(number: int, heading: str) -> AnalyzedScene:
    return AnalyzedScene(
        scene_number=number,
        scene_heading=heading,
        summary=f"Summary of scene {number}",
        overall_tone=EmotionalTone.NEUTRAL,
        pacing=PacingType.MODERATE,
        scene_atmosphere="quiet and clinical",
        is_dialogue_heavy=False,
        is_action_heavy=False,
        character_count=1,
    )


def _fake_shot(scene_number: int) -> Shot:
    return Shot(
        shot_number=1,
        shot_id=f"{scene_number}A",
        shot_type="wide",
        camera_angle="eye_level",
        camera_movement="static",
        subject="the room",
        description="Establishing shot",
        emotional_purpose="orientation",
    )


def _fake_frame(scene_number: int) -> StoryboardFrame:
    return StoryboardFrame(
        frame_number=1,
        frame_id=f"F{scene_number}-1",
        scene_number=scene_number,
        shot_id=f"{scene_number}A",
        image_prompt="A quiet lab at night",
        composition_description="Wide symmetrical composition",
        lighting_description="Cool practical lighting",
        mood_description="Still",
        camera_info="Wide, eye level, static",
    )


def _install_fake_agents(monkeypatch) -> None:
    def fake_analyze_script(self, script: Script) -> AnalyzedScript:
        return AnalyzedScript(
            title=script.title,
            analyzed_scenes=[
                _fake_analyzed_scene(s.scene_number, s.heading) for s in script.scenes
            ],
            main_characters=[
                CharacterVisualDescription(name="ADA", physical_description="An engineer")
            ],
            overall_tone=EmotionalTone.NEUTRAL,
        )

    def fake_design_shot_list(self, scene: AnalyzedScene) -> ShotList:
        return ShotList(
            scene_number=scene.scene_number,
            scene_heading=scene.scene_heading,
            shots=[_fake_shot(scene.scene_number)],
            coverage_notes="Single master",
        )

    def fake_create_storyboards(self, shot_lists, analyzed_scenes, style_guide=None):
        return [
            Storyboard(
                title=f"Scene {sl.scene_number}",
                scene_number=sl.scene_number,
                frames=[_fake_frame(sl.scene_number)],
            )
            for sl in shot_lists
        ]

    async def fake_aanalyze_script(self, script: Script) -> AnalyzedScript:
        return fake_analyze_script(self, script)

    async def fake_adesign_shot_list(self, scene: AnalyzedScene) -> ShotList:
        return fake_design_shot_list(self, scene)

    async def fake_acreate_storyboards(self, shot_lists, analyzed_scenes, style_guide=None):
        return fake_create_storyboards(self, shot_lists, analyzed_scenes, style_guide)

    monkeypatch.setattr(ScriptAnalyzerAgent, "analyze_script", fake_analyze_script)
    monkeypatch.setattr(ScriptAnalyzerAgent, "aanalyze_script", fake_aanalyze_script)
    monkeypatch.setattr(ShotDesignerAgent, "design_shot_list", fake_design_shot_list)
    monkeypatch.setattr(ShotDesignerAgent, "adesign_shot_list", fake_adesign_shot_list)
    monkeypatch.setattr(StoryboardArtistAgent, "create_storyboards", fake_create_storyboards)
    monkeypatch.setattr(StoryboardArtistAgent, "acreate_storyboards", fake_acreate_storyboards)


def test_run_pipeline_default_config_completes(monkeypatch):
    """The default config (checkpoints on, no thread_id) must not crash."""
    _install_fake_agents(monkeypatch)
    script = parse_fountain(SAMPLE_FOUNTAIN)

    result = run_pipeline(script, PipelineConfig())

    assert result.success, result.errors
    assert result.errors == []
    assert result.scenes_processed == len(script.scenes)
    assert result.total_shots == len(script.scenes)
    assert result.total_frames == len(script.scenes)


def test_run_pipeline_without_checkpoints(monkeypatch):
    _install_fake_agents(monkeypatch)
    script = parse_fountain(SAMPLE_FOUNTAIN)

    result = run_pipeline(script, PipelineConfig(enable_checkpoints=False))

    assert result.success, result.errors
    assert result.scenes_processed == len(script.scenes)


def test_run_pipeline_explicit_thread_id(monkeypatch):
    _install_fake_agents(monkeypatch)
    script = parse_fountain(SAMPLE_FOUNTAIN)

    result = run_pipeline(script, PipelineConfig(), thread_id="test-thread")

    assert result.success, result.errors


async def test_arun_pipeline_completes(monkeypatch):
    _install_fake_agents(monkeypatch)
    script = parse_fountain(SAMPLE_FOUNTAIN)

    result = await arun_pipeline(script, PipelineConfig())

    assert result.success, result.errors
    assert result.scenes_processed == len(script.scenes)
    assert result.total_frames == len(script.scenes)


def test_run_pipeline_empty_script_reports_validation_error(monkeypatch):
    _install_fake_agents(monkeypatch)

    result = run_pipeline(Script(title="Empty"), PipelineConfig())

    assert not result.success
    assert any("no scenes" in e.lower() for e in result.errors)
    assert result.scenes_processed == 0


def test_run_pipeline_agent_failure_is_recorded_not_raised(monkeypatch):
    _install_fake_agents(monkeypatch)

    def boom(self, script: Script) -> AnalyzedScript:
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(ScriptAnalyzerAgent, "analyze_script", boom)
    script = parse_fountain(SAMPLE_FOUNTAIN)

    result = run_pipeline(script, PipelineConfig())

    assert not result.success
    assert any("LLM unavailable" in e for e in result.errors)
    assert result.total_shots == 0
