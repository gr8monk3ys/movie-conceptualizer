"""Storyboard Artist Agent for generating image prompts from shot lists.

This agent takes shot lists and generates detailed image prompts for each shot,
maintaining character consistency through detailed descriptions and considering
composition, lighting, and mood.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from movie_conceptualizer.agents.base import BaseAgent
from movie_conceptualizer.models.analysis import (
    AnalyzedScene,
    CameraAngle,
    CharacterVisualDescription,
    Shot,
    ShotList,
    ShotType,
    Storyboard,
    StoryboardFrame,
)


class StoryboardFrameOutput(BaseModel):
    """Output schema for a single storyboard frame."""

    image_prompt: str = Field(
        description="Detailed prompt for image generation, including all visual details"
    )
    composition_description: str = Field(description="Description of frame composition")
    lighting_description: str = Field(description="Description of lighting")
    mood_description: str = Field(description="Description of mood/atmosphere")
    character_positions: str | None = Field(
        default=None, description="Where characters are positioned in frame"
    )
    action_description: str | None = Field(default=None, description="What action is happening")
    style_keywords: list[str] = Field(
        default_factory=list, description="Style keywords for image generation"
    )
    negative_prompt: str | None = Field(default=None, description="Things to avoid in generation")


class StoryboardFramesOutput(BaseModel):
    """Output schema for multiple storyboard frames."""

    frames: list[StoryboardFrameOutput] = Field(description="List of storyboard frame outputs")
    style_guide: str | None = Field(
        default=None, description="Overall style guide for the storyboard"
    )


class StoryboardArtistAgent(BaseAgent):
    """Agent that generates storyboard frames with image prompts.

    This agent takes shot lists and creates detailed image generation prompts
    for each shot, ensuring visual consistency and professional composition.
    """

    @property
    def agent_name(self) -> str:
        """Return the name of this agent."""
        return "StoryboardArtistAgent"

    @property
    def system_prompt(self) -> str:
        """Return the system prompt for storyboard creation."""
        return """You are an expert storyboard artist and visual designer with extensive experience
in film, animation, and concept art. Your role is to translate shot lists into detailed
visual descriptions that can be used to generate storyboard images.

When creating image prompts, follow these PRINCIPLES:

1. CHARACTER CONSISTENCY:
   - Always include detailed physical descriptions of characters
   - Maintain consistent clothing, features, and styling across frames
   - Describe characters in the same way every time they appear
   - Include distinctive features that make characters recognizable

2. COMPOSITION:
   - Apply the rule of thirds for balanced framing
   - Consider leading lines and visual flow
   - Use negative space intentionally
   - Frame subjects according to shot type (headroom, looking room)
   - For close-ups: tight framing, emphasize features
   - For wide shots: show environment relationship

3. SHOT TYPE TRANSLATION:
   - EXTREME WIDE: Vast environment, small figures, establishing scale
   - WIDE: Full environment visible, characters in context
   - FULL: Character(s) head to toe, some environment
   - MEDIUM: Waist up, conversational distance
   - CLOSE-UP: Face and shoulders, emotional emphasis
   - EXTREME CLOSE-UP: Single feature (eyes, hands), maximum intensity
   - TWO-SHOT: Both characters visible, showing relationship
   - OVER-THE-SHOULDER: One character's back/shoulder, facing the other

4. CAMERA ANGLE VISUALIZATION:
   - EYE LEVEL: Neutral perspective, viewer as observer
   - LOW ANGLE: Looking up at subject, conveys power/threat
   - HIGH ANGLE: Looking down, conveys vulnerability/overview
   - DUTCH ANGLE: Tilted horizon, unease/disorientation
   - BIRD'S EYE: Directly overhead, abstract/omniscient
   - WORM'S EYE: Extreme low, dramatic/imposing

5. LIGHTING DESCRIPTIONS:
   - Specify key light direction and quality (soft/hard)
   - Note fill light and contrast ratios
   - Include practical light sources visible in frame
   - Consider time of day and its effect on light color
   - Use lighting to reinforce mood (low-key for drama, high-key for comedy)

6. MOOD AND ATMOSPHERE:
   - Describe the emotional quality of the image
   - Include environmental elements that reinforce mood
   - Consider color palette and temperature
   - Note any atmospheric effects (fog, rain, dust)

7. IMAGE PROMPT BEST PRACTICES:
   - Start with the most important visual element
   - Be specific and detailed (avoid vague descriptions)
   - Include style references when appropriate
   - Specify what NOT to include (negative prompts)
   - Use consistent terminology across frames

Create prompts that would generate professional, cinematic storyboard frames suitable
for pre-production visualization."""

    def _format_shot_for_prompt(
        self,
        shot: Shot,
        scene_context: str,
        character_descriptions: list[CharacterVisualDescription],
    ) -> str:
        """Format a shot for the image prompt generation.

        Args:
            shot: The Shot to format
            scene_context: Context about the scene
            character_descriptions: Character visual descriptions for consistency

        Returns:
            Formatted string for the prompt
        """
        # Format character descriptions
        char_desc_text = "\n".join(
            f"  - {char.name}: {char.physical_description}"
            + (f" ({char.costume_notes})" if char.costume_notes else "")
            for char in character_descriptions
        )

        return f"""SHOT INFORMATION:
- Shot ID: {shot.shot_id}
- Shot Type: {shot.shot_type.value}
- Camera Angle: {shot.camera_angle.value}
- Camera Movement: {shot.camera_movement.value}
- Subject: {shot.subject}
- Description: {shot.description}
- Emotional Purpose: {shot.emotional_purpose}
{f"- Dialogue: {shot.dialogue_covered}" if shot.dialogue_covered else ""}
{f"- Action: {shot.action_covered}" if shot.action_covered else ""}
{f"- Lighting Notes: {shot.lighting_notes}" if shot.lighting_notes else ""}
{f"- Composition Notes: {shot.composition_notes}" if shot.composition_notes else ""}

SCENE CONTEXT:
{scene_context}

CHARACTER VISUAL REFERENCES:
{char_desc_text if char_desc_text else "No character descriptions provided"}"""

    def _get_shot_type_prompt_guidance(self, shot_type: ShotType) -> str:
        """Get prompt guidance based on shot type.

        Args:
            shot_type: The type of shot

        Returns:
            Guidance text for the shot type
        """
        guidance = {
            ShotType.EXTREME_WIDE: "Show vast environment with tiny figures, emphasize scale and setting",
            ShotType.WIDE: "Show full environment with characters visible, establish location",
            ShotType.FULL: "Show character(s) from head to toe with some environment visible",
            ShotType.MEDIUM_WIDE: "Show characters from knees up, balance character and environment",
            ShotType.MEDIUM: "Frame from waist up, conversational framing, show gestures",
            ShotType.MEDIUM_CLOSE: "Frame from chest up, focus on expression and upper body",
            ShotType.CLOSE_UP: "Frame face and shoulders tightly, maximum emotional connection",
            ShotType.EXTREME_CLOSE_UP: "Frame single feature (eyes, hands, object), intense focus",
            ShotType.TWO_SHOT: "Frame two characters together showing their spatial relationship",
            ShotType.OVER_THE_SHOULDER: "Show one character's back/shoulder with the other facing camera",
            ShotType.POV: "Show what the character sees, first-person perspective",
            ShotType.INSERT: "Close shot of object or detail important to the story",
            ShotType.CUTAWAY: "Shot of something outside the main action, provides context",
        }
        return guidance.get(shot_type, "Standard framing for the shot type")

    def _get_camera_angle_prompt_guidance(self, angle: CameraAngle) -> str:
        """Get prompt guidance based on camera angle.

        Args:
            angle: The camera angle

        Returns:
            Guidance text for the angle
        """
        guidance = {
            CameraAngle.EYE_LEVEL: "Camera at subject's eye level, neutral perspective",
            CameraAngle.LOW_ANGLE: "Camera looking up at subject, makes subject appear powerful/imposing",
            CameraAngle.HIGH_ANGLE: "Camera looking down at subject, makes subject appear vulnerable/small",
            CameraAngle.BIRDS_EYE: "Camera directly overhead looking straight down, abstract view",
            CameraAngle.WORMS_EYE: "Camera at ground level looking straight up, extreme drama",
            CameraAngle.DUTCH_ANGLE: "Camera tilted off-axis, creates unease and tension",
        }
        return guidance.get(angle, "Standard angle for the shot")

    def create_frame(
        self,
        shot: Shot,
        scene_number: int,
        frame_number: int,
        scene_context: str,
        character_descriptions: list[CharacterVisualDescription],
        style_guide: str | None = None,
    ) -> StoryboardFrame:
        """Create a storyboard frame for a single shot.

        Args:
            shot: The Shot to create a frame for
            scene_number: The scene number
            frame_number: The frame number in sequence
            scene_context: Context about the scene (atmosphere, color palette, etc.)
            character_descriptions: Character descriptions for consistency
            style_guide: Optional overall style guide

        Returns:
            A StoryboardFrame with detailed image prompt
        """
        shot_info = self._format_shot_for_prompt(shot, scene_context, character_descriptions)
        shot_type_guidance = self._get_shot_type_prompt_guidance(shot.shot_type)
        angle_guidance = self._get_camera_angle_prompt_guidance(shot.camera_angle)

        prompt = f"""Create a detailed storyboard frame for the following shot.

{shot_info}

SHOT TYPE GUIDANCE: {shot_type_guidance}
CAMERA ANGLE GUIDANCE: {angle_guidance}
{f"STYLE GUIDE: {style_guide}" if style_guide else ""}

Generate a comprehensive image prompt that could be used with an AI image generator
to create this storyboard frame. Include:
1. Detailed description of what's visible in the frame
2. Character appearances (using the provided descriptions)
3. Composition and framing details
4. Lighting and atmosphere
5. Style keywords for the image generation
6. A negative prompt listing things to avoid

Make the prompt specific enough to generate a consistent, professional storyboard image."""

        # Generate the frame output
        result = self.generate_structured_output(StoryboardFrameOutput, prompt)

        return StoryboardFrame(
            frame_number=frame_number,
            frame_id=f"F{scene_number}-{shot.shot_id}",
            scene_number=scene_number,
            shot_id=shot.shot_id,
            image_prompt=result.image_prompt,
            composition_description=result.composition_description,
            lighting_description=result.lighting_description,
            mood_description=result.mood_description,
            character_positions=result.character_positions,
            camera_info=f"{shot.shot_type.value}, {shot.camera_angle.value}, {shot.camera_movement.value}",
            action_description=result.action_description or shot.action_covered,
            dialogue_text=shot.dialogue_covered,
            notes=shot.composition_notes,
            style_keywords=result.style_keywords,
            negative_prompt=result.negative_prompt,
        )

    async def acreate_frame(
        self,
        shot: Shot,
        scene_number: int,
        frame_number: int,
        scene_context: str,
        character_descriptions: list[CharacterVisualDescription],
        style_guide: str | None = None,
    ) -> StoryboardFrame:
        """Async version of create_frame.

        Args:
            shot: The Shot to create a frame for
            scene_number: The scene number
            frame_number: The frame number in sequence
            scene_context: Context about the scene
            character_descriptions: Character descriptions for consistency
            style_guide: Optional overall style guide

        Returns:
            A StoryboardFrame with detailed image prompt
        """
        shot_info = self._format_shot_for_prompt(shot, scene_context, character_descriptions)
        shot_type_guidance = self._get_shot_type_prompt_guidance(shot.shot_type)
        angle_guidance = self._get_camera_angle_prompt_guidance(shot.camera_angle)

        prompt = f"""Create a detailed storyboard frame for the following shot.

{shot_info}

SHOT TYPE GUIDANCE: {shot_type_guidance}
CAMERA ANGLE GUIDANCE: {angle_guidance}
{f"STYLE GUIDE: {style_guide}" if style_guide else ""}

Generate a comprehensive image prompt that could be used with an AI image generator
to create this storyboard frame. Include:
1. Detailed description of what's visible in the frame
2. Character appearances (using the provided descriptions)
3. Composition and framing details
4. Lighting and atmosphere
5. Style keywords for the image generation
6. A negative prompt listing things to avoid

Make the prompt specific enough to generate a consistent, professional storyboard image."""

        result = await self.agenerate_structured_output(StoryboardFrameOutput, prompt)

        return StoryboardFrame(
            frame_number=frame_number,
            frame_id=f"F{scene_number}-{shot.shot_id}",
            scene_number=scene_number,
            shot_id=shot.shot_id,
            image_prompt=result.image_prompt,
            composition_description=result.composition_description,
            lighting_description=result.lighting_description,
            mood_description=result.mood_description,
            character_positions=result.character_positions,
            camera_info=f"{shot.shot_type.value}, {shot.camera_angle.value}, {shot.camera_movement.value}",
            action_description=result.action_description or shot.action_covered,
            dialogue_text=shot.dialogue_covered,
            notes=shot.composition_notes,
            style_keywords=result.style_keywords,
            negative_prompt=result.negative_prompt,
        )

    def create_storyboard_for_scene(
        self,
        shot_list: ShotList,
        analyzed_scene: AnalyzedScene,
        style_guide: str | None = None,
    ) -> Storyboard:
        """Create a complete storyboard for a scene.

        Args:
            shot_list: The shot list for the scene
            analyzed_scene: The analyzed scene for context
            style_guide: Optional overall style guide

        Returns:
            A Storyboard with all frames
        """
        # Build scene context from analyzed scene
        scene_context = f"""Atmosphere: {analyzed_scene.scene_atmosphere}
Tone: {analyzed_scene.overall_tone.value}
Pacing: {analyzed_scene.pacing.value}
{f"Color Palette: {analyzed_scene.suggested_color_palette}" if analyzed_scene.suggested_color_palette else ""}"""

        # Get character descriptions
        character_descriptions = analyzed_scene.character_descriptions

        # Create frames for each shot
        frames: list[StoryboardFrame] = []
        for i, shot in enumerate(shot_list.shots):
            frame = self.create_frame(
                shot=shot,
                scene_number=shot_list.scene_number,
                frame_number=i + 1,
                scene_context=scene_context,
                character_descriptions=character_descriptions,
                style_guide=style_guide,
            )
            frames.append(frame)

        # Build character reference notes
        char_ref_notes = "\n".join(
            f"- {char.name}: {char.physical_description}" for char in character_descriptions
        )

        return Storyboard(
            title=f"Storyboard - Scene {shot_list.scene_number}",
            scene_number=shot_list.scene_number,
            frames=frames,
            style_guide=style_guide,
            character_reference_notes=char_ref_notes if char_ref_notes else None,
        )

    async def acreate_storyboard_for_scene(
        self,
        shot_list: ShotList,
        analyzed_scene: AnalyzedScene,
        style_guide: str | None = None,
    ) -> Storyboard:
        """Async version of create_storyboard_for_scene.

        Args:
            shot_list: The shot list for the scene
            analyzed_scene: The analyzed scene for context
            style_guide: Optional overall style guide

        Returns:
            A Storyboard with all frames
        """
        import asyncio

        scene_context = f"""Atmosphere: {analyzed_scene.scene_atmosphere}
Tone: {analyzed_scene.overall_tone.value}
Pacing: {analyzed_scene.pacing.value}
{f"Color Palette: {analyzed_scene.suggested_color_palette}" if analyzed_scene.suggested_color_palette else ""}"""

        character_descriptions = analyzed_scene.character_descriptions

        # Create all frames concurrently
        tasks = [
            self.acreate_frame(
                shot=shot,
                scene_number=shot_list.scene_number,
                frame_number=i + 1,
                scene_context=scene_context,
                character_descriptions=character_descriptions,
                style_guide=style_guide,
            )
            for i, shot in enumerate(shot_list.shots)
        ]
        frames = list(await asyncio.gather(*tasks))

        char_ref_notes = "\n".join(
            f"- {char.name}: {char.physical_description}" for char in character_descriptions
        )

        return Storyboard(
            title=f"Storyboard - Scene {shot_list.scene_number}",
            scene_number=shot_list.scene_number,
            frames=frames,
            style_guide=style_guide,
            character_reference_notes=char_ref_notes if char_ref_notes else None,
        )

    def create_storyboards(
        self,
        shot_lists: list[ShotList],
        analyzed_scenes: list[AnalyzedScene],
        style_guide: str | None = None,
    ) -> list[Storyboard]:
        """Create storyboards for multiple scenes.

        Args:
            shot_lists: List of shot lists
            analyzed_scenes: List of analyzed scenes (must match shot_lists order)
            style_guide: Optional overall style guide

        Returns:
            List of Storyboard objects
        """
        # Match shot lists with analyzed scenes by scene number
        scene_map = {s.scene_number: s for s in analyzed_scenes}

        storyboards = []
        for shot_list in shot_lists:
            analyzed_scene = scene_map.get(shot_list.scene_number)
            if analyzed_scene:
                storyboard = self.create_storyboard_for_scene(
                    shot_list, analyzed_scene, style_guide
                )
                storyboards.append(storyboard)

        return storyboards

    async def acreate_storyboards(
        self,
        shot_lists: list[ShotList],
        analyzed_scenes: list[AnalyzedScene],
        style_guide: str | None = None,
    ) -> list[Storyboard]:
        """Async version of create_storyboards.

        Args:
            shot_lists: List of shot lists
            analyzed_scenes: List of analyzed scenes
            style_guide: Optional overall style guide

        Returns:
            List of Storyboard objects
        """
        import asyncio

        scene_map = {s.scene_number: s for s in analyzed_scenes}

        tasks = []
        for shot_list in shot_lists:
            analyzed_scene = scene_map.get(shot_list.scene_number)
            if analyzed_scene:
                tasks.append(
                    self.acreate_storyboard_for_scene(shot_list, analyzed_scene, style_guide)
                )

        return list(await asyncio.gather(*tasks))

    def process(
        self,
        shot_list: ShotList,
        analyzed_scene: AnalyzedScene,
        style_guide: str | None = None,
    ) -> Storyboard:
        """Process a shot list and analyzed scene to create a storyboard.

        Args:
            shot_list: The shot list for the scene
            analyzed_scene: The analyzed scene for context
            style_guide: Optional style guide

        Returns:
            A Storyboard for the scene
        """
        return self.create_storyboard_for_scene(shot_list, analyzed_scene, style_guide)

    async def aprocess(
        self,
        shot_list: ShotList,
        analyzed_scene: AnalyzedScene,
        style_guide: str | None = None,
    ) -> Storyboard:
        """Async version of process.

        Args:
            shot_list: The shot list for the scene
            analyzed_scene: The analyzed scene for context
            style_guide: Optional style guide

        Returns:
            A Storyboard for the scene
        """
        return await self.acreate_storyboard_for_scene(shot_list, analyzed_scene, style_guide)


# Convenience functions for direct use
def create_storyboard(
    shot_list: ShotList,
    analyzed_scene: AnalyzedScene,
    model_name: str = "claude-sonnet-4-20250514",
    temperature: float = 0.7,
    style_guide: str | None = None,
) -> Storyboard:
    """Create a storyboard for a scene.

    Args:
        shot_list: The shot list for the scene
        analyzed_scene: The analyzed scene for context
        model_name: The Claude model to use
        temperature: Sampling temperature
        style_guide: Optional style guide

    Returns:
        The storyboard for the scene
    """
    agent = StoryboardArtistAgent(model_name=model_name, temperature=temperature)
    return agent.create_storyboard_for_scene(shot_list, analyzed_scene, style_guide)


async def acreate_storyboard(
    shot_list: ShotList,
    analyzed_scene: AnalyzedScene,
    model_name: str = "claude-sonnet-4-20250514",
    temperature: float = 0.7,
    style_guide: str | None = None,
) -> Storyboard:
    """Async version of create_storyboard.

    Args:
        shot_list: The shot list for the scene
        analyzed_scene: The analyzed scene for context
        model_name: The Claude model to use
        temperature: Sampling temperature
        style_guide: Optional style guide

    Returns:
        The storyboard for the scene
    """
    agent = StoryboardArtistAgent(model_name=model_name, temperature=temperature)
    return await agent.acreate_storyboard_for_scene(shot_list, analyzed_scene, style_guide)
