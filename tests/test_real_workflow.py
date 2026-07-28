"""Tests for RealWorkflow's agent orchestration.

Guards two behaviors:
- persisted analyses are reused, never regenerated (the full pipeline used
  to run scene analysis up to three times per generation);
- the async agent variants are used, so LLM calls don't block the event loop.

API modules are imported lazily inside tests per the ordering contract in
CLAUDE.md.
"""

from movie_conceptualizer.agents import (
    ScriptAnalyzerAgent,
    ShotDesignerAgent,
    StoryboardArtistAgent,
)
from movie_conceptualizer.models.analysis import (
    AnalyzedScript,
    CameraAngle,
    CameraMovement,
    EmotionalTone,
    Shot,
    ShotList,
    ShotType,
    Storyboard,
    StoryboardFrame,
)


def _fake_shot_list(scene_number: int, heading: str) -> ShotList:
    return ShotList(
        scene_number=scene_number,
        scene_heading=heading,
        shots=[
            Shot(
                shot_number=1,
                shot_id=f"{scene_number}A",
                shot_type=ShotType.WIDE,
                camera_angle=CameraAngle.EYE_LEVEL,
                camera_movement=CameraMovement.STATIC,
                subject="the room",
                description="Establishing shot",
                emotional_purpose="orientation",
            )
        ],
        coverage_notes="Single master",
    )


def _make_scene_and_analysis():
    from movie_conceptualizer.api.schemas import SceneAnalysis, SceneData

    scene = SceneData(
        scene_number=1,
        heading="INT. LAB - NIGHT",
        description="A robot hums quietly.",
        characters=["ADA"],
        dialogue=[{"character": "ADA", "dialogue": "It works."}],
        raw_content="A robot hums quietly.",
    )
    analysis = SceneAnalysis(
        scene_number=1,
        mood="tense",
        visual_style="clinical fluorescents",
        pacing="slow",
        key_moments=["The robot wakes"],
        color_palette=["teal and grey"],
    )
    return scene, analysis


def _forbid_analysis(monkeypatch) -> None:
    async def fail(self, script):
        raise AssertionError("analyzer must not run when analyses are provided")

    monkeypatch.setattr(ScriptAnalyzerAgent, "aanalyze_script", fail)
    monkeypatch.setattr(
        ScriptAnalyzerAgent,
        "analyze_script",
        lambda self, script: (_ for _ in ()).throw(
            AssertionError("sync analyzer must not run inside the API workflow")
        ),
    )


async def test_generate_shots_reuses_provided_analyses(monkeypatch):
    from movie_conceptualizer.api.dependencies import RealWorkflow

    _forbid_analysis(monkeypatch)

    async def fake_design(self, scene):
        return _fake_shot_list(scene.scene_number, scene.scene_heading)

    monkeypatch.setattr(ShotDesignerAgent, "adesign_shot_list", fake_design)

    scene, analysis = _make_scene_and_analysis()
    shots = await RealWorkflow().generate_shots([scene], analyses=[analysis])

    assert len(shots) == 1
    assert shots[0].scene_number == 1
    assert shots[0].shot_number == "1A"


async def test_generate_shots_analyzes_when_no_analyses(monkeypatch):
    from movie_conceptualizer.api.dependencies import (
        RealWorkflow,
        _script_from_scene_data,
    )
    from tests.test_workflow_pipeline import _fake_analyzed_scene

    calls = {"analyze": 0}

    async def fake_analyze(self, script):
        calls["analyze"] += 1
        return AnalyzedScript(
            title=script.title,
            analyzed_scenes=[
                _fake_analyzed_scene(s.scene_number, s.heading) for s in script.scenes
            ],
            overall_tone=EmotionalTone.NEUTRAL,
        )

    async def fake_design(self, scene):
        return _fake_shot_list(scene.scene_number, scene.scene_heading)

    monkeypatch.setattr(ScriptAnalyzerAgent, "aanalyze_script", fake_analyze)
    monkeypatch.setattr(ShotDesignerAgent, "adesign_shot_list", fake_design)

    scene, _ = _make_scene_and_analysis()
    assert _script_from_scene_data([scene]).scenes  # sanity: conversion works

    shots = await RealWorkflow().generate_shots([scene], analyses=None)

    assert calls["analyze"] == 1
    assert len(shots) == 1


async def test_generate_storyboard_prompts_reuses_provided_analyses(monkeypatch):
    from movie_conceptualizer.api.dependencies import RealWorkflow
    from movie_conceptualizer.api.schemas import ShotData

    _forbid_analysis(monkeypatch)

    captured = {}

    def _storyboard_for(sl):
        return Storyboard(
            title=f"Scene {sl.scene_number}",
            scene_number=sl.scene_number,
            frames=[
                StoryboardFrame(
                    frame_number=1,
                    frame_id=f"F{sl.scene_number}-1",
                    scene_number=sl.scene_number,
                    shot_id=sl.shots[0].shot_id,
                    image_prompt="A quiet lab at night",
                    composition_description="Wide symmetrical composition",
                    lighting_description="Cool practical lighting",
                    mood_description="Still",
                    camera_info="Wide, eye level, static",
                )
            ],
        )

    async def fake_storyboards(self, shot_lists, analyzed_scenes, style_guide=None):
        captured["analyzed_scenes"] = analyzed_scenes
        return [_storyboard_for(sl) for sl in shot_lists]

    monkeypatch.setattr(StoryboardArtistAgent, "acreate_storyboards", fake_storyboards)

    scene, analysis = _make_scene_and_analysis()
    shot = ShotData(
        shot_number="1A",
        scene_number=1,
        shot_type="wide",
        description="Establishing shot",
    )

    prompts = await RealWorkflow().generate_storyboard_prompts(
        [shot], scenes=[scene], analyses=[analysis]
    )

    assert len(prompts) == 1
    assert prompts[0].prompt == "A quiet lab at night"
    # The analyzed scene fed to the artist is rebuilt from the stored
    # analysis, not regenerated by the analyzer.
    rebuilt = captured["analyzed_scenes"][0]
    assert rebuilt.scene_heading == "INT. LAB - NIGHT"
    assert rebuilt.overall_tone == EmotionalTone.TENSE
    assert rebuilt.scene_atmosphere == "clinical fluorescents"
