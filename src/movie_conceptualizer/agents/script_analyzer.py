"""Script Analyzer Agent for analyzing screenplay scenes.

This agent takes a parsed script and analyzes each scene to extract:
- Emotional beats and pacing
- Tone and atmosphere
- Key dramatic moments
- Visual emphasis points
- Character descriptions for visual consistency
"""

from __future__ import annotations

from movie_conceptualizer.agents.base import BaseAgent
from movie_conceptualizer.models import (
    AnalyzedScene,
    AnalyzedScript,
    CharacterVisualDescription,
    DialogueBlock,
    EmotionalTone,
    Scene,
    Script,
)


class ScriptAnalyzerAgent(BaseAgent):
    """Agent that analyzes screenplay scenes for emotional and visual content.

    This agent processes a parsed screenplay and extracts detailed analysis
    for each scene, including emotional beats, pacing, dramatic moments,
    and suggestions for visual emphasis.
    """

    @property
    def agent_name(self) -> str:
        """Return the name of this agent."""
        return "ScriptAnalyzerAgent"

    @property
    def system_prompt(self) -> str:
        """Return the system prompt for script analysis."""
        return """You are an expert script analyst and film dramaturg with deep knowledge of
screenwriting, visual storytelling, and cinematic language. Your role is to analyze
screenplay scenes to extract emotional, dramatic, and visual elements that will guide
the filmmaking process.

When analyzing a scene, you should:

1. EMOTIONAL BEATS: Identify the emotional shifts and moments within the scene.
   Each beat represents a change in emotional state, tension, or energy.
   - Note the intensity (0.0 to 1.0) of each beat
   - Identify the specific tone (tense, romantic, comedic, dramatic, action,
     suspenseful, melancholic, hopeful, terrifying, mysterious, joyful, somber, neutral)
   - Mark where in the scene each beat occurs

2. PACING: Determine the overall pacing of the scene:
   - slow: Contemplative, character-driven moments
   - moderate: Standard dramatic scenes
   - fast: Action sequences, rapid-fire dialogue
   - building: Tension mounting toward climax
   - climactic: Peak dramatic moments

3. DRAMATIC MOMENTS: Identify the key moments that deserve special visual attention:
   - Revelations, confrontations, decisions
   - Moments of high emotional impact
   - Suggest visual emphasis techniques (close-ups, slow motion, etc.)

4. VISUAL EMPHASIS POINTS: Note specific elements that should be visually highlighted:
   - Props that are important to the story
   - Physical actions that convey meaning
   - Environmental details that set mood

5. CHARACTER DESCRIPTIONS: Provide detailed physical descriptions for characters
   appearing in the scene to ensure visual consistency in storyboards:
   - Physical attributes (age, build, hair, distinguishing features)
   - Costume/wardrobe notes relevant to the scene
   - Distinctive features that aid in recognition

6. ATMOSPHERE: Describe the overall visual atmosphere:
   - Lighting quality and direction
   - Color palette suggestions
   - Mood and tone conveyed through visuals

Be thorough, precise, and creative in your analysis. Your insights will directly
inform shot design and storyboard creation."""

    def _format_scene_for_analysis(self, scene: Scene) -> str:
        """Format a scene for analysis prompt.

        Args:
            scene: The Scene to format

        Returns:
            A formatted string representation of the scene
        """
        parts = [
            f"SCENE {scene.scene_number}",
            f"Heading: {scene.heading}",
            f"Location: {scene.location}",
            f"Time: {scene.time_of_day.value if scene.time_of_day else 'UNKNOWN'}",
            f"Characters: {', '.join(scene.characters) if scene.characters else 'None specified'}",
            "",
            "SCENE CONTENT:",
            "=" * 40,
        ]

        # Add scene content
        for element in scene.content:
            if isinstance(element, DialogueBlock):
                parts.append(f"\n{element.character_name}")
                if element.parenthetical:
                    parts.append(f"({element.parenthetical})")
                parts.append(element.dialogue)
            else:  # ActionBlock or Transition
                parts.append(f"\n{element.text}")

        # Also include raw text if content is empty
        if not scene.content and scene.raw_text:
            parts.append(scene.raw_text)

        return "\n".join(parts)

    def analyze_scene(self, scene: Scene, script_context: str = "") -> AnalyzedScene:
        """Analyze a single scene for emotional and visual content.

        Args:
            scene: The Scene object to analyze
            script_context: Optional context about the overall script

        Returns:
            An AnalyzedScene with full analysis
        """
        scene_text = self._format_scene_for_analysis(scene)

        # Count characters and determine dialogue/action heaviness
        dialogue_count = sum(
            1 for el in scene.content if isinstance(el, DialogueBlock)
        )
        action_count = len(scene.content) - dialogue_count
        is_dialogue_heavy = dialogue_count > action_count
        is_action_heavy = action_count > dialogue_count

        prompt = f"""Analyze the following screenplay scene in detail.

{f"SCRIPT CONTEXT: {script_context}" if script_context else ""}

{scene_text}

Additional information:
- Number of characters in scene: {len(scene.characters)}
- Scene appears to be {"dialogue-heavy" if is_dialogue_heavy else "action-heavy" if is_action_heavy else "balanced"}

Provide a comprehensive analysis including emotional beats, pacing, dramatic moments,
visual emphasis points, character descriptions, and overall atmosphere. Be specific
and detailed in your analysis."""

        # Generate structured output
        result = self.generate_structured_output(AnalyzedScene, prompt)

        # Ensure scene metadata is correct
        result.scene_number = scene.scene_number
        result.scene_heading = scene.heading
        result.character_count = len(scene.characters)
        result.is_dialogue_heavy = is_dialogue_heavy
        result.is_action_heavy = is_action_heavy

        return result

    async def aanalyze_scene(
        self, scene: Scene, script_context: str = ""
    ) -> AnalyzedScene:
        """Async version of analyze_scene.

        Args:
            scene: The Scene object to analyze
            script_context: Optional context about the overall script

        Returns:
            An AnalyzedScene with full analysis
        """
        scene_text = self._format_scene_for_analysis(scene)

        dialogue_count = sum(
            1 for el in scene.content if isinstance(el, DialogueBlock)
        )
        action_count = len(scene.content) - dialogue_count
        is_dialogue_heavy = dialogue_count > action_count
        is_action_heavy = action_count > dialogue_count

        prompt = f"""Analyze the following screenplay scene in detail.

{f"SCRIPT CONTEXT: {script_context}" if script_context else ""}

{scene_text}

Additional information:
- Number of characters in scene: {len(scene.characters)}
- Scene appears to be {"dialogue-heavy" if is_dialogue_heavy else "action-heavy" if is_action_heavy else "balanced"}

Provide a comprehensive analysis including emotional beats, pacing, dramatic moments,
visual emphasis points, character descriptions, and overall atmosphere. Be specific
and detailed in your analysis."""

        result = await self.agenerate_structured_output(AnalyzedScene, prompt)

        result.scene_number = scene.scene_number
        result.scene_heading = scene.heading
        result.character_count = len(scene.characters)
        result.is_dialogue_heavy = is_dialogue_heavy
        result.is_action_heavy = is_action_heavy

        return result

    def analyze_script(self, script: Script) -> AnalyzedScript:
        """Analyze an entire script, scene by scene.

        Args:
            script: The complete Script object to analyze

        Returns:
            An AnalyzedScript with all scenes analyzed
        """
        # First, get overall script context
        script_context = self._generate_script_context(script)

        # Analyze each scene
        analyzed_scenes: list[AnalyzedScene] = []
        for scene in script.scenes:
            analyzed_scene = self.analyze_scene(scene, script_context)
            analyzed_scenes.append(analyzed_scene)

        # Determine overall tone from scene analyses
        overall_tone = self._determine_overall_tone(analyzed_scenes)

        # Extract main characters with consolidated descriptions
        main_characters = self._consolidate_character_descriptions(
            script, analyzed_scenes
        )

        # Detect genre hints
        genre_hints = self._detect_genre_hints(script, analyzed_scenes)

        return AnalyzedScript(
            title=script.title,
            analyzed_scenes=analyzed_scenes,
            main_characters=main_characters,
            overall_tone=overall_tone,
            genre_hints=genre_hints,
        )

    async def aanalyze_script(self, script: Script) -> AnalyzedScript:
        """Async version of analyze_script.

        Args:
            script: The complete Script object to analyze

        Returns:
            An AnalyzedScript with all scenes analyzed
        """
        import asyncio

        script_context = self._generate_script_context(script)

        # Analyze all scenes concurrently
        tasks = [
            self.aanalyze_scene(scene, script_context) for scene in script.scenes
        ]
        analyzed_scenes = await asyncio.gather(*tasks)

        overall_tone = self._determine_overall_tone(list(analyzed_scenes))
        main_characters = self._consolidate_character_descriptions(
            script, list(analyzed_scenes)
        )
        genre_hints = self._detect_genre_hints(script, list(analyzed_scenes))

        return AnalyzedScript(
            title=script.title,
            analyzed_scenes=list(analyzed_scenes),
            main_characters=main_characters,
            overall_tone=overall_tone,
            genre_hints=genre_hints,
        )

    def _generate_script_context(self, script: Script) -> str:
        """Generate a brief context summary of the script.

        Args:
            script: The script to summarize

        Returns:
            A brief context string
        """
        character_names = [c.name for c in script.characters[:10]]  # Top 10 characters
        locations = list({s.location for s in script.scenes})[:10]  # Top 10 locations

        return f"""Title: {script.title}
Total Scenes: {len(script.scenes)}
Main Characters: {', '.join(character_names)}
Key Locations: {', '.join(locations)}"""

    def _determine_overall_tone(
        self, analyzed_scenes: list[AnalyzedScene]
    ) -> EmotionalTone:
        """Determine the overall tone of the script from scene analyses.

        Args:
            analyzed_scenes: List of analyzed scenes

        Returns:
            The dominant EmotionalTone
        """
        if not analyzed_scenes:
            return EmotionalTone.NEUTRAL

        # Count tone occurrences
        tone_counts: dict[EmotionalTone, int] = {}
        for scene in analyzed_scenes:
            tone = scene.overall_tone
            tone_counts[tone] = tone_counts.get(tone, 0) + 1

        # Return the most common tone
        return max(tone_counts, key=lambda t: tone_counts[t])

    def _consolidate_character_descriptions(
        self, script: Script, analyzed_scenes: list[AnalyzedScene]
    ) -> list[CharacterVisualDescription]:
        """Consolidate character descriptions from all scenes.

        Args:
            script: The original script with character data
            analyzed_scenes: All analyzed scenes

        Returns:
            List of consolidated character descriptions
        """
        # Collect all character descriptions
        char_descriptions: dict[str, list[CharacterVisualDescription]] = {}

        for scene in analyzed_scenes:
            for char_desc in scene.character_descriptions:
                name = char_desc.name.upper()
                if name not in char_descriptions:
                    char_descriptions[name] = []
                char_descriptions[name].append(char_desc)

        # Consolidate into single descriptions per character
        consolidated: list[CharacterVisualDescription] = []

        for name, descriptions in char_descriptions.items():
            if descriptions:
                # Use the most detailed description (longest physical_description)
                best = max(descriptions, key=lambda d: len(d.physical_description))

                # Merge distinctive features from all descriptions
                all_features = set()
                for d in descriptions:
                    all_features.update(d.distinctive_features)

                consolidated.append(
                    CharacterVisualDescription(
                        name=best.name,
                        physical_description=best.physical_description,
                        costume_notes=best.costume_notes,
                        distinctive_features=list(all_features),
                    )
                )

        return consolidated

    def _detect_genre_hints(
        self, script: Script, analyzed_scenes: list[AnalyzedScene]
    ) -> list[str]:
        """Detect genre hints from the script and analyses.

        Args:
            script: The original script
            analyzed_scenes: All analyzed scenes

        Returns:
            List of detected genre hints
        """
        hints: set[str] = set()

        # Analyze tone distribution
        tone_map = {
            EmotionalTone.TENSE: ["thriller", "drama"],
            EmotionalTone.ROMANTIC: ["romance", "romantic comedy"],
            EmotionalTone.COMEDIC: ["comedy"],
            EmotionalTone.DRAMATIC: ["drama"],
            EmotionalTone.ACTION: ["action", "adventure"],
            EmotionalTone.SUSPENSEFUL: ["thriller", "mystery"],
            EmotionalTone.MELANCHOLIC: ["drama", "indie"],
            EmotionalTone.TERRIFYING: ["horror", "thriller"],
            EmotionalTone.MYSTERIOUS: ["mystery", "noir"],
        }

        for scene in analyzed_scenes:
            if scene.overall_tone in tone_map:
                hints.update(tone_map[scene.overall_tone])

        # Check for action-heavy scenes
        action_scenes = sum(1 for s in analyzed_scenes if s.is_action_heavy)
        if action_scenes > len(analyzed_scenes) * 0.3:
            hints.add("action")

        return list(hints)

    def process(self, script: Script) -> AnalyzedScript:
        """Process a script and return the analysis.

        Args:
            script: The Script to analyze

        Returns:
            An AnalyzedScript with complete analysis
        """
        return self.analyze_script(script)

    async def aprocess(self, script: Script) -> AnalyzedScript:
        """Async version of process.

        Args:
            script: The Script to analyze

        Returns:
            An AnalyzedScript with complete analysis
        """
        return await self.aanalyze_script(script)


# Convenience function for direct use
def analyze_script(
    script: Script,
    model_name: str = "claude-sonnet-4-20250514",
    temperature: float = 0.7,
) -> AnalyzedScript:
    """Analyze a script using the ScriptAnalyzerAgent.

    Args:
        script: The script to analyze
        model_name: The Claude model to use
        temperature: Sampling temperature

    Returns:
        The analyzed script
    """
    agent = ScriptAnalyzerAgent(model_name=model_name, temperature=temperature)
    return agent.analyze_script(script)


async def aanalyze_script(
    script: Script,
    model_name: str = "claude-sonnet-4-20250514",
    temperature: float = 0.7,
) -> AnalyzedScript:
    """Async version of analyze_script.

    Args:
        script: The script to analyze
        model_name: The Claude model to use
        temperature: Sampling temperature

    Returns:
        The analyzed script
    """
    agent = ScriptAnalyzerAgent(model_name=model_name, temperature=temperature)
    return await agent.aanalyze_script(script)
