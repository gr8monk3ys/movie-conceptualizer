"""Smoke tests for the command-line interface.

These tests drive the Typer app end-to-end via ``CliRunner`` with the LLM
agents mocked, so they exercise CLI wiring (argument parsing, agent calls,
result display, and file output) without requiring an API key or network.

They exist specifically to catch the class of bug where a CLI command calls
an agent method or model attribute that no longer exists - failures that the
type checker flags but that previously went undetected at runtime because no
test ever invoked the commands.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from movie_conceptualizer.cli import app

# NOTE: the agents operate on the analysis-layer models, not the comprehensive
# shot-planning models re-exported as ``Shot``/``ShotList`` from the package root.
from movie_conceptualizer.models.analysis import (
    AnalyzedScene,
    CameraAngle,
    CameraMovement,
    EmotionalTone,
    PacingType,
    Shot,
    ShotList,
    ShotType,
    Storyboard,
    StoryboardFrame,
)

runner = CliRunner()

EXAMPLE_SCRIPT = Path(__file__).parent.parent / "examples" / "sample_screenplay.fountain"


def _analyzed_scene(scene_number: int = 1) -> AnalyzedScene:
    return AnalyzedScene(
        scene_number=scene_number,
        scene_heading="INT. ROOM - DAY",
        summary="A short scene.",
        overall_tone=EmotionalTone.TENSE,
        pacing=PacingType.MODERATE,
        scene_atmosphere="Dim and quiet.",
        is_dialogue_heavy=True,
        is_action_heavy=False,
        character_count=1,
    )


def _shot_list(scene_number: int = 1) -> ShotList:
    return ShotList(
        scene_number=scene_number,
        scene_heading="INT. ROOM - DAY",
        coverage_notes="Standard coverage.",
        shots=[
            Shot(
                shot_number=1,
                shot_id=f"{scene_number}-1",
                shot_type=ShotType.WIDE,
                camera_angle=CameraAngle.EYE_LEVEL,
                camera_movement=CameraMovement.STATIC,
                subject="The room",
                description="Establishing wide of the room.",
                emotional_purpose="Orient the viewer.",
            )
        ],
    )


def _storyboard(scene_number: int = 1) -> Storyboard:
    return Storyboard(
        title=f"Storyboard - Scene {scene_number}",
        scene_number=scene_number,
        frames=[
            StoryboardFrame(
                frame_number=1,
                frame_id=f"{scene_number}-1",
                scene_number=scene_number,
                shot_id=f"{scene_number}-1",
                image_prompt="A dim room, wide shot, cinematic.",
                composition_description="Centered.",
                lighting_description="Low key.",
                mood_description="Tense.",
                camera_info="Wide, static, eye level.",
            )
        ],
    )


@pytest.fixture
def mock_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch agent methods so commands run without an LLM / API key."""
    monkeypatch.setattr(
        "movie_conceptualizer.agents.ScriptAnalyzerAgent.analyze_scene",
        lambda self, scene, *a, **k: _analyzed_scene(scene.scene_number),
    )
    monkeypatch.setattr(
        "movie_conceptualizer.agents.ShotDesignerAgent.design_shot_list",
        lambda self, analyzed, *a, **k: _shot_list(analyzed.scene_number),
    )
    monkeypatch.setattr(
        "movie_conceptualizer.agents.StoryboardArtistAgent.create_storyboard_for_scene",
        lambda self, shot_list, analyzed, *a, **k: _storyboard(shot_list.scene_number),
    )


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "Movie Conceptualizer" in result.stdout


def test_parse(tmp_path: Path) -> None:
    out = tmp_path / "script.json"
    result = runner.invoke(app, ["parse", str(EXAMPLE_SCRIPT), "-o", str(out), "-v"])
    assert result.exit_code == 0, result.stdout
    assert out.exists()
    data = json.loads(out.read_text())
    assert "scenes" in data


def test_parse_missing_file() -> None:
    result = runner.invoke(app, ["parse", "/no/such/file.fountain"])
    assert result.exit_code == 1


def test_analyze(tmp_path: Path, mock_agents: None) -> None:
    out = tmp_path / "analysis.json"
    result = runner.invoke(app, ["analyze", str(EXAMPLE_SCRIPT), "-o", str(out)])
    assert result.exit_code == 0, result.stdout
    assert out.exists()
    assert "scenes" in json.loads(out.read_text())


def test_shots(tmp_path: Path, mock_agents: None) -> None:
    out = tmp_path / "shots.json"
    result = runner.invoke(app, ["shots", str(EXAMPLE_SCRIPT), "-o", str(out)])
    assert result.exit_code == 0, result.stdout
    assert out.exists()
    assert "shot_lists" in json.loads(out.read_text())


def test_storyboard(tmp_path: Path, mock_agents: None) -> None:
    out = tmp_path / "storyboard.json"
    result = runner.invoke(app, ["storyboard", str(EXAMPLE_SCRIPT), "-o", str(out)])
    assert result.exit_code == 0, result.stdout
    assert out.exists()
    assert "frames" in json.loads(out.read_text())


def test_pipeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    analyzed = [_analyzed_scene(1)]
    shot_lists = [_shot_list(1)]
    storyboards = [_storyboard(1)]
    fake_result = SimpleNamespace(
        analyzed_scenes=analyzed,
        shot_lists=shot_lists,
        storyboards=storyboards,
        scenes_processed=1,
        total_shots=1,
        total_frames=1,
    )
    monkeypatch.setattr(
        "movie_conceptualizer.workflows.run_pipeline",
        lambda script, config: fake_result,
    )

    out_dir = tmp_path / "output"
    result = runner.invoke(app, ["pipeline", str(EXAMPLE_SCRIPT), "-o", str(out_dir)])
    assert result.exit_code == 0, result.stdout
    assert (out_dir / "script.json").exists()
    assert (out_dir / "analysis.json").exists()
    assert (out_dir / "shots.json").exists()
    assert (out_dir / "storyboard.json").exists()
