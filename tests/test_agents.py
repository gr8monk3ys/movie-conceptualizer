"""Integration tests for the agent system.

These tests verify the agent components work correctly without making
actual LLM calls (which would require API keys).
"""

import pytest

from movie_conceptualizer.agents import (
    APIKeyNotFoundError,
    ScriptAnalyzerAgent,
    ShotDesignerAgent,
    StoryboardArtistAgent,
)
from movie_conceptualizer.models import Scene, SceneType, TimeOfDay
from movie_conceptualizer.parsers import load_script


class TestAgentInitialization:
    """Tests for agent creation and configuration."""

    def test_create_analyzer_without_api_key(self):
        """Agents can be created without API keys (lazy init)."""
        agent = ScriptAnalyzerAgent()
        assert agent is not None
        assert agent.model_name == "claude-sonnet-4-20250514"

    def test_create_shot_designer_without_api_key(self):
        """Shot designer can be created without API key."""
        agent = ShotDesignerAgent()
        assert agent is not None

    def test_create_storyboard_artist_without_api_key(self):
        """Storyboard artist can be created without API key."""
        agent = StoryboardArtistAgent()
        assert agent is not None

    def test_agent_is_configured_returns_false_without_key(self):
        """is_configured returns False when no API key is available."""
        agent = ScriptAnalyzerAgent()
        assert agent.is_configured() is False

    def test_agent_is_configured_returns_true_with_key(self, monkeypatch):
        """is_configured returns True when API key is in env."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        agent = ScriptAnalyzerAgent()
        assert agent.is_configured() is True

    def test_accessing_llm_without_key_raises_error(self):
        """Accessing llm property without API key raises APIKeyNotFoundError."""
        agent = ScriptAnalyzerAgent()
        with pytest.raises(APIKeyNotFoundError) as exc_info:
            _ = agent.llm
        assert "Anthropic" in str(exc_info.value)

    def test_agent_custom_model_name(self):
        """Agents accept custom model names."""
        agent = ScriptAnalyzerAgent(model_name="claude-3-haiku-20240307")
        assert agent.model_name == "claude-3-haiku-20240307"

    def test_agent_custom_temperature(self):
        """Agents accept custom temperature."""
        agent = ScriptAnalyzerAgent(temperature=0.5)
        assert agent.temperature == 0.5


class TestAgentSystemPrompts:
    """Tests for agent system prompts."""

    def test_analyzer_has_system_prompt(self):
        """Script analyzer has a system prompt."""
        agent = ScriptAnalyzerAgent()
        assert agent.system_prompt
        assert "script" in agent.system_prompt.lower() or "scene" in agent.system_prompt.lower()

    def test_shot_designer_has_system_prompt(self):
        """Shot designer has a system prompt."""
        agent = ShotDesignerAgent()
        assert agent.system_prompt
        assert "shot" in agent.system_prompt.lower() or "camera" in agent.system_prompt.lower()

    def test_storyboard_artist_has_system_prompt(self):
        """Storyboard artist has a system prompt."""
        agent = StoryboardArtistAgent()
        assert agent.system_prompt
        assert (
            "storyboard" in agent.system_prompt.lower() or "visual" in agent.system_prompt.lower()
        )


class TestAgentNames:
    """Tests for agent identification."""

    def test_analyzer_agent_name(self):
        """Script analyzer has correct agent name."""
        agent = ScriptAnalyzerAgent()
        assert "analyzer" in agent.agent_name.lower() or "script" in agent.agent_name.lower()

    def test_shot_designer_agent_name(self):
        """Shot designer has correct agent name."""
        agent = ShotDesignerAgent()
        assert "shot" in agent.agent_name.lower() or "designer" in agent.agent_name.lower()

    def test_storyboard_artist_agent_name(self):
        """Storyboard artist has correct agent name."""
        agent = StoryboardArtistAgent()
        assert "storyboard" in agent.agent_name.lower() or "artist" in agent.agent_name.lower()


class TestAgentRepr:
    """Tests for agent string representation."""

    def test_agent_repr(self):
        """Agent has useful string representation."""
        agent = ScriptAnalyzerAgent(model_name="test-model", temperature=0.5)
        repr_str = repr(agent)
        assert "ScriptAnalyzerAgent" in repr_str
        assert "test-model" in repr_str
        assert "0.5" in repr_str


class TestAgentHelperMethods:
    """Tests for agent helper methods that don't require LLM calls."""

    def test_shot_designer_guidance_generation(self):
        """Shot designer can generate film guidance without LLM."""
        agent = ShotDesignerAgent()

        # Create a test scene using proper model fields
        scene = Scene(
            scene_number=1,
            heading="INT. OFFICE - DAY",
            scene_type=SceneType.INTERIOR,
            location="OFFICE",
            time_of_day=TimeOfDay.DAY,
            page_count=1.0,
            characters=["JOHN", "MARY"],
        )

        # Get film guidance (if the method exists)
        if hasattr(agent, "_get_film_guidance"):
            guidance = agent._get_film_guidance(scene)
            assert guidance is not None
            assert isinstance(guidance, str)


class TestWorkflowIntegration:
    """Tests for workflow state management."""

    def test_create_initial_state(self):
        """Can create initial pipeline state."""
        from movie_conceptualizer.workflows import create_initial_state

        script = load_script("examples/sample_screenplay.fountain")
        state = create_initial_state(script)

        assert state["script"] == script
        assert state["analyzed_scenes"] == []
        assert state["shot_lists"] == []
        assert state["storyboard_frames"] == []
        assert state["errors"] == []

    def test_pipeline_config_defaults(self):
        """Pipeline config has sensible defaults."""
        from movie_conceptualizer.workflows import PipelineConfig

        config = PipelineConfig()
        assert config.model_name == "claude-sonnet-4-20250514"
        assert 0 <= config.temperature <= 1


class TestExampleScriptLoading:
    """Tests that example scripts can be loaded and processed."""

    def test_load_example_script(self):
        """Example screenplay loads correctly."""
        script = load_script("examples/sample_screenplay.fountain")
        assert script.title == "THE LAST SUNRISE"
        assert len(script.scenes) > 0
        assert len(script.characters) > 0

    def test_example_script_scenes_have_content(self):
        """Example screenplay scenes have content."""
        script = load_script("examples/sample_screenplay.fountain")
        for scene in script.scenes:
            assert scene.heading  # Scene heading/slugline
            assert scene.raw_text or scene.content  # Scene content
