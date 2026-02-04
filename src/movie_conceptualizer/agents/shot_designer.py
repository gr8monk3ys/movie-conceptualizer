"""Shot Designer Agent for generating cinematographic shot lists.

This agent takes analyzed scripts/scenes and generates comprehensive shot lists
that apply professional film grammar rules, including:
- Appropriate shot types based on emotional content
- Coverage patterns for multi-character scenes
- 180-degree rule awareness
- Shot/reverse-shot patterns for dialogue
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from movie_conceptualizer.agents.base import BaseAgent
from movie_conceptualizer.models.analysis import (
    AnalyzedScene,
    AnalyzedScript,
    EmotionalTone,
    PacingType,
    Shot,
    ShotList,
)


class ShotListOutput(BaseModel):
    """Output schema for shot list generation."""

    shots: list[Shot] = Field(description="Ordered list of shots for the scene")
    coverage_notes: str = Field(description="Notes about the coverage strategy")
    master_shot_id: str | None = Field(
        default=None, description="ID of the master/establishing shot"
    )
    estimated_screen_time: str | None = Field(
        default=None, description="Estimated screen time"
    )


class ShotDesignerAgent(BaseAgent):
    """Agent that designs shot lists based on analyzed scenes.

    This agent applies professional cinematography principles to generate
    shot lists that effectively convey the emotional and dramatic content
    of each scene.
    """

    @property
    def agent_name(self) -> str:
        """Return the name of this agent."""
        return "ShotDesignerAgent"

    @property
    def system_prompt(self) -> str:
        """Return the system prompt for shot design."""
        return """You are an expert cinematographer and director of photography with decades of
experience in film and television. Your role is to design shot lists that effectively
tell the story visually while adhering to professional filmmaking conventions.

When designing shots, apply these FILM GRAMMAR RULES:

1. THE 180-DEGREE RULE:
   - Establish an imaginary line (axis of action) between characters
   - Keep all cameras on ONE side of this line
   - Crossing the line disorients viewers
   - Exception: deliberate crossing for dramatic effect (note when doing this)

2. SHOT SIZE BASED ON EMOTIONAL CONTENT:
   - EXTREME WIDE/WIDE: Establishing shots, epic moments, isolation, loneliness
   - FULL/MEDIUM WIDE: Character entrances, showing environment relationship
   - MEDIUM: Standard coverage, conversations, neutral emotional state
   - MEDIUM CLOSE: Increased intimacy, important dialogue
   - CLOSE-UP: Emotional moments, reactions, important information
   - EXTREME CLOSE-UP: High intensity, crucial details, extreme emotion

3. COVERAGE PATTERNS FOR DIALOGUE:
   - TWO-SHOT: Establishing both characters, showing relationship
   - OVER-THE-SHOULDER (OTS): Creates depth, shows both characters
   - SHOT/REVERSE-SHOT: Standard dialogue pattern, cut on dialogue
   - SINGLES: Individual close-ups for emotional emphasis

4. CAMERA MOVEMENT:
   - STATIC: Stability, observation, documentary feel
   - PAN/TILT: Following action, revealing information
   - DOLLY/TRACKING: Moving with character, exploration
   - STEADICAM: Fluid following, immersive experience
   - HANDHELD: Energy, tension, documentary realism
   - CRANE: Grand reveals, establishing scale

5. CAMERA ANGLES:
   - EYE LEVEL: Neutral, objective
   - LOW ANGLE: Power, dominance, heroism
   - HIGH ANGLE: Vulnerability, weakness, surveillance
   - DUTCH ANGLE: Unease, disorientation, tension

6. SCENE-TYPE SPECIFIC APPROACHES:
   - ACTION SCENES: Dynamic camera, multiple angles, fast cutting
   - DIALOGUE SCENES: Coverage pattern, reaction shots, rhythm
   - EMOTIONAL SCENES: Close-ups, longer takes, subtle movement
   - ESTABLISHING SCENES: Wide shots, movement to reveal
   - SUSPENSE SCENES: POV shots, slow push-ins, limited information

7. TRANSITIONS AND FLOW:
   - Cut on action for seamless editing
   - Match eyelines for continuity
   - Vary shot sizes (don't cut between similar sizes)
   - Build energy through shot progression

For each shot, specify:
- Shot type and size
- Camera angle
- Camera movement
- Subject/framing
- What dialogue/action is covered
- Emotional purpose
- Any special notes (lighting, composition, transitions)

Create professional, shootable shot lists that a film crew could execute."""

    def _format_analyzed_scene(self, scene: AnalyzedScene) -> str:
        """Format an analyzed scene for the shot design prompt.

        Args:
            scene: The AnalyzedScene to format

        Returns:
            Formatted string for the prompt
        """
        emotional_beats_text = "\n".join(
            f"  - {beat.description} (tone: {beat.tone.value}, intensity: {beat.intensity})"
            for beat in scene.emotional_beats
        )

        dramatic_moments_text = "\n".join(
            f"  - {moment.description} (importance: {moment.importance}, "
            f"suggested: {moment.suggested_emphasis})"
            for moment in scene.dramatic_moments
        )

        visual_points_text = "\n".join(
            f"  - {point.element_description}: {point.reason}"
            for point in scene.visual_emphasis_points
        )

        characters_text = "\n".join(
            f"  - {char.name}: {char.physical_description}"
            for char in scene.character_descriptions
        )

        return f"""SCENE {scene.scene_number}: {scene.scene_heading}

SUMMARY: {scene.summary}

OVERALL TONE: {scene.overall_tone.value}
PACING: {scene.pacing.value}
ATMOSPHERE: {scene.scene_atmosphere}
{"COLOR PALETTE: " + scene.suggested_color_palette if scene.suggested_color_palette else ""}

SCENE TYPE:
- Dialogue-heavy: {scene.is_dialogue_heavy}
- Action-heavy: {scene.is_action_heavy}
- Character count: {scene.character_count}

EMOTIONAL BEATS:
{emotional_beats_text if emotional_beats_text else "  - None identified"}

KEY DRAMATIC MOMENTS:
{dramatic_moments_text if dramatic_moments_text else "  - None identified"}

VISUAL EMPHASIS POINTS:
{visual_points_text if visual_points_text else "  - None identified"}

CHARACTERS IN SCENE:
{characters_text if characters_text else "  - No character descriptions"}"""

    def _get_shot_type_guidance(self, scene: AnalyzedScene) -> str:
        """Generate shot type guidance based on scene analysis.

        Args:
            scene: The analyzed scene

        Returns:
            Guidance text for shot selection
        """
        guidance_parts = []

        # Tone-based guidance
        tone_guidance = {
            EmotionalTone.TENSE: "Use tighter shots, low angles for threat, handheld for unease",
            EmotionalTone.ROMANTIC: "Soft lighting, close-ups, two-shots showing connection",
            EmotionalTone.COMEDIC: "Medium shots for timing, wide for physical comedy",
            EmotionalTone.DRAMATIC: "Mix of sizes, building to close-ups for emotional peaks",
            EmotionalTone.ACTION: "Dynamic movement, quick cuts, multiple angles",
            EmotionalTone.SUSPENSEFUL: "POV shots, slow push-ins, obscured information",
            EmotionalTone.MELANCHOLIC: "Wide shots for isolation, slow movements",
            EmotionalTone.HOPEFUL: "Upward angles, bright composition, rising movements",
            EmotionalTone.TERRIFYING: "Dutch angles, shadows, limited visibility",
            EmotionalTone.MYSTERIOUS: "Silhouettes, partial reveals, deep shadows",
        }

        if scene.overall_tone in tone_guidance:
            guidance_parts.append(f"TONE GUIDANCE: {tone_guidance[scene.overall_tone]}")

        # Pacing guidance
        pacing_guidance = {
            PacingType.SLOW: "Longer takes, minimal camera movement, contemplative framing",
            PacingType.MODERATE: "Standard coverage, balanced shot lengths",
            PacingType.FAST: "Quick cuts, dynamic movement, energy in framing",
            PacingType.BUILDING: "Progressive intensification - wider to tighter, slower to faster",
            PacingType.CLIMACTIC: "Maximum intensity shots, extreme close-ups, dramatic angles",
        }

        if scene.pacing in pacing_guidance:
            guidance_parts.append(f"PACING GUIDANCE: {pacing_guidance[scene.pacing]}")

        # Scene type guidance
        if scene.is_dialogue_heavy and scene.character_count >= 2:
            guidance_parts.append(
                "DIALOGUE SCENE: Use shot/reverse-shot pattern, "
                "establish with two-shot, cover both characters"
            )
        elif scene.is_action_heavy:
            guidance_parts.append(
                "ACTION SCENE: Multiple angles on key actions, "
                "wide for geography, tight for impact"
            )

        # Character count guidance
        if scene.character_count == 1:
            guidance_parts.append("SINGLE CHARACTER: POV opportunities, reaction shots to environment")
        elif scene.character_count == 2:
            guidance_parts.append(
                "TWO CHARACTERS: Two-shot master, OTS coverage, singles for emphasis"
            )
        elif scene.character_count > 2:
            guidance_parts.append(
                f"GROUP ({scene.character_count} characters): Establish geography, "
                "identify key speakers, group shots and singles"
            )

        return "\n".join(guidance_parts)

    def design_shot_list(self, scene: AnalyzedScene) -> ShotList:
        """Design a shot list for an analyzed scene.

        Args:
            scene: The AnalyzedScene to create shots for

        Returns:
            A ShotList with all shots for the scene
        """
        scene_text = self._format_analyzed_scene(scene)
        guidance = self._get_shot_type_guidance(scene)

        prompt = f"""Design a comprehensive shot list for the following analyzed scene.

{scene_text}

{guidance}

Create a professional shot list that:
1. Starts with an establishing/master shot
2. Provides complete coverage for dialogue and action
3. Includes reaction shots and cutaways as needed
4. Follows the 180-degree rule
5. Uses shot sizes appropriate to emotional content
6. Includes specific camera angles and movements
7. Notes transitions between shots

Number shots sequentially (1, 2, 3...) and give each a unique ID (1A, 1B for coverage of same moment).
Be thorough - include all shots needed to edit the scene effectively."""

        # Generate the shot list
        result = self.generate_structured_output(ShotListOutput, prompt)

        # Assign shot numbers if not set correctly
        for i, shot in enumerate(result.shots):
            shot.shot_number = i + 1
            if not shot.shot_id:
                shot.shot_id = f"{scene.scene_number}-{i + 1}"

        return ShotList(
            scene_number=scene.scene_number,
            scene_heading=scene.scene_heading,
            shots=result.shots,
            coverage_notes=result.coverage_notes,
            master_shot_id=result.master_shot_id,
            estimated_screen_time=result.estimated_screen_time,
        )

    async def adesign_shot_list(self, scene: AnalyzedScene) -> ShotList:
        """Async version of design_shot_list.

        Args:
            scene: The AnalyzedScene to create shots for

        Returns:
            A ShotList with all shots for the scene
        """
        scene_text = self._format_analyzed_scene(scene)
        guidance = self._get_shot_type_guidance(scene)

        prompt = f"""Design a comprehensive shot list for the following analyzed scene.

{scene_text}

{guidance}

Create a professional shot list that:
1. Starts with an establishing/master shot
2. Provides complete coverage for dialogue and action
3. Includes reaction shots and cutaways as needed
4. Follows the 180-degree rule
5. Uses shot sizes appropriate to emotional content
6. Includes specific camera angles and movements
7. Notes transitions between shots

Number shots sequentially (1, 2, 3...) and give each a unique ID (1A, 1B for coverage of same moment).
Be thorough - include all shots needed to edit the scene effectively."""

        result = await self.agenerate_structured_output(ShotListOutput, prompt)

        for i, shot in enumerate(result.shots):
            shot.shot_number = i + 1
            if not shot.shot_id:
                shot.shot_id = f"{scene.scene_number}-{i + 1}"

        return ShotList(
            scene_number=scene.scene_number,
            scene_heading=scene.scene_heading,
            shots=result.shots,
            coverage_notes=result.coverage_notes,
            master_shot_id=result.master_shot_id,
            estimated_screen_time=result.estimated_screen_time,
        )

    def design_shot_lists_for_script(
        self, analyzed_script: AnalyzedScript
    ) -> list[ShotList]:
        """Design shot lists for all scenes in an analyzed script.

        Args:
            analyzed_script: The complete analyzed script

        Returns:
            List of ShotList objects, one per scene
        """
        shot_lists = []
        for scene in analyzed_script.analyzed_scenes:
            shot_list = self.design_shot_list(scene)
            shot_lists.append(shot_list)
        return shot_lists

    async def adesign_shot_lists_for_script(
        self, analyzed_script: AnalyzedScript
    ) -> list[ShotList]:
        """Async version of design_shot_lists_for_script.

        Args:
            analyzed_script: The complete analyzed script

        Returns:
            List of ShotList objects, one per scene
        """
        import asyncio

        tasks = [
            self.adesign_shot_list(scene)
            for scene in analyzed_script.analyzed_scenes
        ]
        return list(await asyncio.gather(*tasks))

    def process(
        self, analyzed_scene_or_script: AnalyzedScene | AnalyzedScript
    ) -> ShotList | list[ShotList]:
        """Process an analyzed scene or script and return shot list(s).

        Args:
            analyzed_scene_or_script: Either an AnalyzedScene or AnalyzedScript

        Returns:
            A ShotList for a single scene, or list of ShotLists for a script
        """
        if isinstance(analyzed_scene_or_script, AnalyzedScene):
            return self.design_shot_list(analyzed_scene_or_script)
        else:
            return self.design_shot_lists_for_script(analyzed_scene_or_script)

    async def aprocess(
        self, analyzed_scene_or_script: AnalyzedScene | AnalyzedScript
    ) -> ShotList | list[ShotList]:
        """Async version of process.

        Args:
            analyzed_scene_or_script: Either an AnalyzedScene or AnalyzedScript

        Returns:
            A ShotList for a single scene, or list of ShotLists for a script
        """
        if isinstance(analyzed_scene_or_script, AnalyzedScene):
            return await self.adesign_shot_list(analyzed_scene_or_script)
        else:
            return await self.adesign_shot_lists_for_script(analyzed_scene_or_script)


# Convenience functions for direct use
def design_shot_list(
    scene: AnalyzedScene,
    model_name: str = "claude-sonnet-4-20250514",
    temperature: float = 0.7,
) -> ShotList:
    """Design a shot list for an analyzed scene.

    Args:
        scene: The analyzed scene
        model_name: The Claude model to use
        temperature: Sampling temperature

    Returns:
        The shot list for the scene
    """
    agent = ShotDesignerAgent(model_name=model_name, temperature=temperature)
    return agent.design_shot_list(scene)


async def adesign_shot_list(
    scene: AnalyzedScene,
    model_name: str = "claude-sonnet-4-20250514",
    temperature: float = 0.7,
) -> ShotList:
    """Async version of design_shot_list.

    Args:
        scene: The analyzed scene
        model_name: The Claude model to use
        temperature: Sampling temperature

    Returns:
        The shot list for the scene
    """
    agent = ShotDesignerAgent(model_name=model_name, temperature=temperature)
    return await agent.adesign_shot_list(scene)
