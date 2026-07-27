"""Fountain screenplay format parser.

Parses .fountain format screenplays into structured data compatible with
the movie conceptualizer data models.

Fountain format specification: https://fountain.io/syntax
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from movie_conceptualizer.models import (
    ActionBlock,
    Character,
    DialogueBlock,
    Location,
    Scene,
    SceneType,
    Script,
    TimeOfDay,
    TitlePage,
    TitlePageField,
    Transition,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


# Fountain format patterns
# Note: Longer patterns must come first in alternation (INT./EXT. before INT.)
SCENE_HEADING_PATTERN = re.compile(
    r"^(?P<forced>\.)?(?P<prefix>INT\.?/EXT\.?|I/E\.?|INT\.?|EXT\.?|EST\.?)"
    r"[\s.]+(?P<location>.+?)(?:\s*[-\u2013\u2014]\s*(?P<time>.+?))?$",
    re.IGNORECASE | re.MULTILINE,
)

# Alternate pattern for forced scene headings (starting with .)
FORCED_SCENE_PATTERN = re.compile(
    r"^\.\s*(.+)$",
    re.MULTILINE,
)

# Character name pattern: ALL CAPS, optionally with extension in parentheses
# Must be preceded by blank line and followed by dialogue
CHARACTER_PATTERN = re.compile(
    r"^(?P<forced>@)?(?P<name>[A-Z][A-Z0-9\s\'\.\-]+?)"
    r"(?:\s*\((?P<extension>[A-Z\.\'\s]+)\))?$"
)

# Parenthetical pattern
PARENTHETICAL_PATTERN = re.compile(r"^\s*\(([^)]+)\)\s*$")

# Transition patterns
TRANSITION_PATTERN = re.compile(
    r"^(?:>|(?:[A-Z\s]+TO:))$",
    re.MULTILINE,
)
FORCED_TRANSITION_PATTERN = re.compile(r"^>\s*(.+)$")

# Title page key-value pattern
TITLE_PAGE_PATTERN = re.compile(r"^([A-Za-z\s]+):\s*(.*)$")

# Centered text pattern
CENTERED_PATTERN = re.compile(r"^>\s*(.+?)\s*<$")

# Section and synopsis patterns
SECTION_PATTERN = re.compile(r"^(#{1,6})\s*(.+)$")
SYNOPSIS_PATTERN = re.compile(r"^=\s*(.+)$")

# Note pattern
NOTE_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")

# Boneyard (commented out) pattern
BONEYARD_PATTERN = re.compile(r"/\*.*?\*/", re.DOTALL)

# Page break pattern
PAGE_BREAK_PATTERN = re.compile(r"^={3,}\s*$", re.MULTILINE)

# Common character extensions
CHARACTER_EXTENSIONS = frozenset(
    {
        "V.O.",
        "VO",
        "V.O",
        "O.S.",
        "OS",
        "O.S",
        "O.C.",
        "OC",
        "CONT'D",
        "CONT",
        "CONTINUED",
        "PRE-LAP",
        "PRELAP",
        "FILTER",
        "FILTERED",
        "SUBTITLE",
        "SUBTITLED",
    }
)

# Time of day mappings
TIME_OF_DAY_MAPPINGS: dict[str, TimeOfDay] = {
    "DAY": TimeOfDay.DAY,
    "NIGHT": TimeOfDay.NIGHT,
    "DAWN": TimeOfDay.DAWN,
    "DUSK": TimeOfDay.DUSK,
    "MORNING": TimeOfDay.MORNING,
    "AFTERNOON": TimeOfDay.AFTERNOON,
    "EVENING": TimeOfDay.EVENING,
    "CONTINUOUS": TimeOfDay.CONTINUOUS,
    "CONT": TimeOfDay.CONTINUOUS,
    "CONT'D": TimeOfDay.CONTINUOUS,
    "LATER": TimeOfDay.LATER,
    "SAME": TimeOfDay.SAME,
    "SAME TIME": TimeOfDay.SAME,
    "MOMENTS LATER": TimeOfDay.LATER,
}

# Continuity markers: valid TimeOfDay values, but a concrete time of day in
# the same heading ("DAWN - CONTINUOUS") should win over them.
_CONTINUITY_TIMES = frozenset({TimeOfDay.CONTINUOUS, TimeOfDay.LATER, TimeOfDay.SAME})

# Standalone transitions that don't end with "TO:".
_STANDALONE_TRANSITIONS = frozenset({"FADE OUT", "FADE TO BLACK", "CUT TO BLACK"})


@dataclass
class ParserState:
    """Tracks parser state during parsing."""

    in_dialogue: bool = False
    current_character: str | None = None
    current_character_extension: str | None = None
    current_parenthetical: str | None = None
    in_title_page: bool = True
    scene_count: int = 0
    current_page: float = 0.0
    lines_on_page: int = 0
    last_line_blank: bool = True


@dataclass
class ParsedElement:
    """A parsed screenplay element."""

    element_type: str
    content: str
    raw_text: str = ""
    character_name: str | None = None
    character_extension: str | None = None
    parenthetical: str | None = None
    scene_type: SceneType = SceneType.UNKNOWN
    location: str = ""
    time_of_day: TimeOfDay = TimeOfDay.UNKNOWN
    is_forced: bool = False
    is_dual_dialogue: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class FountainParser:
    """Parser for Fountain format screenplays.

    Converts .fountain text into structured Script objects compatible
    with the movie conceptualizer data models.

    Example:
        parser = FountainParser()
        script = parser.parse(fountain_text)
        print(f"Title: {script.title}")
        print(f"Scenes: {script.scene_count}")
    """

    # Lines per page approximation (standard screenplay format)
    LINES_PER_PAGE = 55

    # Average characters per line
    CHARS_PER_LINE = 60

    def __init__(self) -> None:
        """Initialize the parser."""
        self._state = ParserState()
        self._elements: list[ParsedElement] = []
        self._title_page_fields: list[TitlePageField] = []
        self._raw_title_page: str = ""

    def parse(self, text: str) -> Script:
        """Parse Fountain format text into a Script object.

        Args:
            text: Raw Fountain format screenplay text.

        Returns:
            Parsed Script object with all extracted elements.
        """
        # Reset parser state
        self._state = ParserState()
        self._elements = []
        self._title_page_fields = []
        self._raw_title_page = ""

        # Normalize line endings and handle encoding
        text = self._normalize_text(text)

        # Remove boneyards (comments)
        text = self._remove_boneyards(text)

        # Parse title page first
        text = self._parse_title_page(text)

        # Parse the main content
        self._parse_content(text)

        # Build the final Script object
        return self._build_script(text)

    def _normalize_text(self, text: str) -> str:
        """Normalize text for parsing.

        Args:
            text: Raw input text.

        Returns:
            Normalized text with consistent line endings.
        """
        # Handle different line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Remove UTF-8 BOM if present
        if text.startswith("\ufeff"):
            text = text[1:]

        return text

    def _remove_boneyards(self, text: str) -> str:
        """Remove boneyard (comment) sections.

        Args:
            text: Input text.

        Returns:
            Text with boneyard sections removed.
        """
        return BONEYARD_PATTERN.sub("", text)

    def _parse_title_page(self, text: str) -> str:
        """Parse and extract title page metadata.

        Args:
            text: Full screenplay text.

        Returns:
            Text with title page removed.
        """
        lines = text.split("\n")
        title_page_lines: list[str] = []
        content_start = 0
        current_key: str | None = None
        current_value_lines: list[str] = []

        for i, line in enumerate(lines):
            # Empty line ends title page
            if not line.strip():
                # Check if we found any title page fields
                if not self._title_page_fields and not current_key:
                    self._state.in_title_page = False
                    content_start = i
                    break

                # Save current field if any
                if current_key and current_value_lines:
                    value = "\n".join(current_value_lines).strip()
                    self._title_page_fields.append(TitlePageField(key=current_key, value=value))
                    current_key = None
                    current_value_lines = []

                # Another blank line ends title page
                if i > 0 and not lines[i - 1].strip():
                    self._state.in_title_page = False
                    content_start = i + 1
                    break

                title_page_lines.append(line)
                continue

            # Check for key: value pattern
            match = TITLE_PAGE_PATTERN.match(line)
            if match:
                # Save previous field
                if current_key and current_value_lines:
                    value = "\n".join(current_value_lines).strip()
                    self._title_page_fields.append(TitlePageField(key=current_key, value=value))

                current_key = match.group(1).strip()
                value = match.group(2).strip()
                current_value_lines = [value] if value else []
                title_page_lines.append(line)
            elif current_key:
                # Continuation of multi-line value (indented)
                if line.startswith((" ", "\t")):
                    current_value_lines.append(line.strip())
                    title_page_lines.append(line)
                else:
                    # Not a continuation, end title page
                    if current_value_lines:
                        value = "\n".join(current_value_lines).strip()
                        self._title_page_fields.append(TitlePageField(key=current_key, value=value))
                    self._state.in_title_page = False
                    content_start = i
                    break
            else:
                # No title page found, this is content
                self._state.in_title_page = False
                content_start = i
                break

        # Save any remaining field
        if current_key and current_value_lines:
            value = "\n".join(current_value_lines).strip()
            self._title_page_fields.append(TitlePageField(key=current_key, value=value))

        self._raw_title_page = "\n".join(title_page_lines)
        return "\n".join(lines[content_start:])

    def _parse_content(self, text: str) -> None:
        """Parse the main screenplay content.

        Args:
            text: Screenplay text without title page.
        """
        # Split into blocks separated by blank lines
        blocks = self._split_into_blocks(text)

        for block in blocks:
            self._parse_block(block)

    def _split_into_blocks(self, text: str) -> Iterator[str]:
        """Split text into blocks separated by blank lines.

        Args:
            text: Input text.

        Yields:
            Individual text blocks.
        """
        current_block: list[str] = []

        for line in text.split("\n"):
            if not line.strip():
                if current_block:
                    yield "\n".join(current_block)
                    current_block = []
            else:
                current_block.append(line)

        if current_block:
            yield "\n".join(current_block)

    def _parse_block(self, block: str) -> None:
        """Parse a single text block.

        Args:
            block: A block of text (no blank lines within).
        """
        lines = block.split("\n")
        first_line = lines[0].strip()

        # Check for page break
        if PAGE_BREAK_PATTERN.match(first_line):
            self._state.current_page = int(self._state.current_page) + 1
            self._state.lines_on_page = 0
            return

        # Check for forced scene heading
        if first_line.startswith(".") and not first_line.startswith(".."):
            self._parse_scene_heading(first_line[1:].strip(), forced=True)
            # Parse remaining lines as action
            if len(lines) > 1:
                self._parse_action("\n".join(lines[1:]))
            return

        # Check for scene heading
        scene_match = SCENE_HEADING_PATTERN.match(first_line)
        if scene_match:
            self._parse_scene_heading(first_line, match=scene_match)
            # Parse remaining lines as action
            if len(lines) > 1:
                self._parse_action("\n".join(lines[1:]))
            return

        # Check for transition (> prefix or ends with TO:)
        if first_line.startswith(">") and not first_line.endswith("<"):
            self._parse_transition(first_line[1:].strip())
            return
        if first_line.endswith("TO:") and first_line.isupper():
            self._parse_transition(first_line)
            return
        if first_line.upper().rstrip(".").strip() in _STANDALONE_TRANSITIONS:
            self._parse_transition(first_line)
            if len(lines) > 1:
                self._parse_action("\n".join(lines[1:]))
            return

        # Check for centered text
        centered_match = CENTERED_PATTERN.match(first_line)
        if centered_match:
            self._parse_centered(centered_match.group(1))
            return

        # Check for section heading
        section_match = SECTION_PATTERN.match(first_line)
        if section_match:
            # Sections are structural, we skip them for now
            return

        # Check for synopsis
        if first_line.startswith("="):
            # Synopses are metadata, we skip them
            return

        # Check for character cue (potential dialogue)
        if self._is_character_cue(first_line):
            if len(lines) > 1:
                self._parse_dialogue_block(lines)
            else:
                # A lone uppercase line has no dialogue to attach to; Fountain
                # only makes it a cue when dialogue follows. Emitting action
                # keeps lines like "FADE IN:" or "THE END" from vanishing.
                self._parse_action(block)
            return

        # Default to action
        self._parse_action(block)

    def _is_character_cue(self, line: str) -> bool:
        """Check if a line is a character cue.

        Args:
            line: Line to check.

        Returns:
            True if line appears to be a character cue.
        """
        line = line.strip()

        # Forced character cue
        if line.startswith("@"):
            return True

        # Must be uppercase
        # Extract just the name part (before any parenthetical)
        name_part = re.sub(r"\s*\([^)]*\)\s*$", "", line)

        # Check if it's all uppercase and contains at least one letter
        if not name_part:
            return False

        # Must contain at least one letter
        if not any(c.isalpha() for c in name_part):
            return False

        # Character names don't end in terminal punctuation; uppercase
        # exclamations ("BANG!", "NOW WHAT?") are action, not cues.
        if name_part.rstrip().endswith(("!", "?")):
            return False

        # Must be mostly uppercase letters
        letters = [c for c in name_part if c.isalpha()]
        if not letters:
            return False

        uppercase_letters = [c for c in letters if c.isupper()]
        if len(uppercase_letters) / len(letters) < 0.9:
            return False

        # Should not end with common action words
        lower_line = line.lower()
        action_endings = ["the", "and", "but", "or", "is", "are", "was", "were"]
        for ending in action_endings:
            if lower_line.endswith(f" {ending}"):
                return False

        return True

    def _parse_scene_heading(
        self,
        text: str,
        forced: bool = False,
        match: re.Match[str] | None = None,
    ) -> None:
        """Parse a scene heading.

        Args:
            text: Scene heading text.
            forced: Whether this is a forced scene heading.
            match: Regex match object if already matched.
        """
        self._state.scene_count += 1

        if match:
            prefix = match.group("prefix").upper().rstrip(".")
            location = match.group("location").strip()
            time_str = match.group("time")
        else:
            # Try to parse manually
            parts = text.split("-", 1)
            if len(parts) == 2:
                location_part = parts[0].strip()
                time_str = parts[1].strip()
            else:
                # Try en-dash and em-dash
                for sep in ["\u2013", "\u2014"]:
                    if sep in text:
                        parts = text.split(sep, 1)
                        location_part = parts[0].strip()
                        time_str = parts[1].strip()
                        break
                else:
                    location_part = text
                    time_str = None

            # Extract prefix
            prefix_match = re.match(
                r"^(INT\.?|EXT\.?|INT\.?/EXT\.?|I/E\.?|EST\.?)\s*\.?\s*",
                location_part,
                re.IGNORECASE,
            )
            if prefix_match:
                prefix = prefix_match.group(1).upper().rstrip(".")
                location = location_part[prefix_match.end() :].strip()
            else:
                prefix = ""
                location = location_part

        # Determine scene type
        scene_type = SceneType.UNKNOWN
        if prefix:
            prefix_upper = prefix.upper().replace(".", "")
            if prefix_upper in ("INT/EXT", "I/E"):
                scene_type = SceneType.INTERIOR_EXTERIOR
            elif prefix_upper.startswith("INT"):
                scene_type = SceneType.INTERIOR
            elif prefix_upper.startswith("EXT"):
                scene_type = SceneType.EXTERIOR

        # Determine time of day. Headings may carry extra dash-separated
        # modifiers ("ELENA'S APARTMENT - FLASHBACK - NIGHT", "MOUNTAIN PEAK -
        # DAWN - CONTINUOUS", "HOUSE - KITCHEN - DAY"), so the time is not
        # simply "everything after the first dash": the first segment that
        # maps to a known time starts the time region, everything before it
        # is location, and a concrete time (DAY/NIGHT/...) wins over a
        # continuity marker (CONTINUOUS/LATER/SAME) within that region.
        time_of_day = TimeOfDay.UNKNOWN
        if time_str:
            segments = [
                seg.strip()
                for seg in re.split(r"\s*[-–—]\s*", f"{location} - {time_str}")
                if seg.strip()
            ]
            first_time_index = next(
                (i for i, seg in enumerate(segments) if seg.upper() in TIME_OF_DAY_MAPPINGS),
                None,
            )
            if first_time_index is not None and first_time_index > 0:
                location = " - ".join(segments[:first_time_index])
                candidates = [
                    TIME_OF_DAY_MAPPINGS[seg.upper()]
                    for seg in segments[first_time_index:]
                    if seg.upper() in TIME_OF_DAY_MAPPINGS
                ]
                concrete = [c for c in candidates if c not in _CONTINUITY_TIMES]
                time_of_day = concrete[0] if concrete else candidates[0]
            else:
                time_of_day = TIME_OF_DAY_MAPPINGS.get(time_str.upper().strip(), TimeOfDay.UNKNOWN)

        self._elements.append(
            ParsedElement(
                element_type="scene_heading",
                content=text,
                raw_text=text,
                scene_type=scene_type,
                location=location,
                time_of_day=time_of_day,
                is_forced=forced,
            )
        )

        # Reset dialogue state
        self._state.in_dialogue = False
        self._state.current_character = None

    def _parse_dialogue_block(self, lines: list[str]) -> None:
        """Parse a dialogue block (character + dialogue + parentheticals).

        Args:
            lines: Lines of the dialogue block.
        """
        if not lines:
            return

        first_line = lines[0].strip()

        # Parse character name
        is_forced = first_line.startswith("@")
        if is_forced:
            first_line = first_line[1:].strip()

        # Check for dual dialogue marker
        is_dual = first_line.endswith("^")
        if is_dual:
            first_line = first_line[:-1].strip()

        # Extract character extension
        extension = None
        ext_match = re.search(r"\s*\(([^)]+)\)\s*$", first_line)
        if ext_match:
            potential_ext = ext_match.group(1).upper()
            if potential_ext in CHARACTER_EXTENSIONS or "'" in potential_ext:
                extension = ext_match.group(1)
                first_line = first_line[: ext_match.start()].strip()

        character_name = first_line.strip()

        # Parse remaining lines for dialogue and parentheticals
        dialogue_lines: list[str] = []
        current_parenthetical: str | None = None

        for line in lines[1:]:
            stripped = line.strip()

            # Check for parenthetical
            paren_match = PARENTHETICAL_PATTERN.match(stripped)
            if paren_match:
                # A parenthetical modifies the dialogue that FOLLOWS it, so
                # any dialogue accumulated so far is emitted with the
                # previous parenthetical before this one takes effect.
                if dialogue_lines:
                    self._elements.append(
                        ParsedElement(
                            element_type="dialogue",
                            content="\n".join(dialogue_lines),
                            raw_text="\n".join(dialogue_lines),
                            character_name=character_name,
                            character_extension=extension,
                            parenthetical=current_parenthetical,
                            is_dual_dialogue=is_dual,
                        )
                    )
                    dialogue_lines = []
                current_parenthetical = paren_match.group(1)
            else:
                dialogue_lines.append(stripped)

        # Emit remaining dialogue
        if dialogue_lines or current_parenthetical:
            self._elements.append(
                ParsedElement(
                    element_type="dialogue",
                    content="\n".join(dialogue_lines) if dialogue_lines else "",
                    raw_text="\n".join(lines),
                    character_name=character_name,
                    character_extension=extension,
                    parenthetical=current_parenthetical,
                    is_dual_dialogue=is_dual,
                )
            )

        self._state.in_dialogue = True
        self._state.current_character = character_name

    def _parse_action(self, text: str) -> None:
        """Parse an action block.

        Args:
            text: Action text.
        """
        # Remove notes
        text = NOTE_PATTERN.sub("", text)

        # Check for forced action (starting with !)
        is_forced = text.startswith("!")
        if is_forced:
            text = text[1:]

        text = text.strip()
        if not text:
            return

        self._elements.append(
            ParsedElement(
                element_type="action",
                content=text,
                raw_text=text,
                is_forced=is_forced,
            )
        )

        # Reset dialogue state
        self._state.in_dialogue = False
        self._state.current_character = None

    def _parse_transition(self, text: str) -> None:
        """Parse a transition.

        Args:
            text: Transition text.
        """
        self._elements.append(
            ParsedElement(
                element_type="transition",
                content=text.strip(),
                raw_text=text,
            )
        )

        self._state.in_dialogue = False
        self._state.current_character = None

    def _parse_centered(self, text: str) -> None:
        """Parse centered text.

        Args:
            text: Centered text content.
        """
        self._elements.append(
            ParsedElement(
                element_type="action",
                content=text.strip(),
                raw_text=text,
                metadata={"centered": True},
            )
        )

    def _build_script(self, original_text: str) -> Script:
        """Build the final Script object from parsed elements.

        Args:
            original_text: Original screenplay text.

        Returns:
            Complete Script object.
        """
        # Build title page
        title_page = self._build_title_page()

        # Build scenes
        scenes = self._build_scenes()

        # Extract unique characters
        characters = self._extract_characters(scenes)

        # Extract unique locations
        locations = self._extract_locations(scenes)

        # Calculate total pages
        total_pages = sum(scene.page_length for scene in scenes)

        # Get title
        title = title_page.title or "Untitled"

        return Script(
            title=title,
            title_page=title_page,
            scenes=scenes,
            characters=characters,
            locations=locations,
            total_pages=total_pages,
            raw_text=original_text,
            format_type="fountain",
        )

    def _build_title_page(self) -> TitlePage:
        """Build TitlePage from parsed fields.

        Returns:
            TitlePage object.
        """
        title_page = TitlePage()

        for tf in self._title_page_fields:
            key_lower = tf.key.lower().strip()

            if key_lower == "title":
                title_page.title = tf.value
            elif key_lower in ("credit", "credits"):
                title_page.credit = tf.value
            elif key_lower in ("author", "authors", "written by"):
                title_page.author = tf.value
                # Split multiple authors
                if tf.value:
                    authors = re.split(r"\s*[,&]\s*|\s+and\s+", tf.value)
                    title_page.authors = [a.strip() for a in authors if a.strip()]
            elif key_lower == "source":
                title_page.source = tf.value
            elif key_lower in ("draft date", "date", "draft"):
                title_page.draft_date = tf.value
            elif key_lower == "contact":
                title_page.contact = tf.value
            elif key_lower == "copyright":
                title_page.copyright = tf.value
            elif key_lower in ("notes", "note"):
                title_page.notes = tf.value
            elif key_lower == "revision":
                title_page.revision = tf.value
            else:
                title_page.extra_fields.append(tf)

        return title_page

    def _build_scenes(self) -> list[Scene]:
        """Build Scene objects from parsed elements.

        Returns:
            List of Scene objects.
        """
        scenes: list[Scene] = []
        current_scene: Scene | None = None
        current_content: list[ActionBlock | DialogueBlock | Transition] = []
        current_characters: set[str] = set()
        current_raw_lines: list[str] = []
        current_page = 0.0
        scene_number = 0

        for element in self._elements:
            if element.element_type == "scene_heading":
                # Save previous scene
                if current_scene is not None:
                    page_length = self._calculate_page_length(current_raw_lines)
                    current_scene.content = current_content
                    current_scene.characters = list(current_characters)
                    current_scene.raw_text = "\n".join(current_raw_lines)
                    current_scene.page_length = page_length
                    scenes.append(current_scene)
                    current_page += page_length

                # Start new scene
                scene_number += 1
                current_scene = Scene(
                    scene_number=scene_number,
                    heading=element.content,
                    scene_type=element.scene_type,
                    location=element.location,
                    time_of_day=element.time_of_day,
                    page_start=current_page,
                )
                current_content = []
                current_characters = set()
                current_raw_lines = [element.content]

            elif current_scene is not None:
                current_raw_lines.append(element.raw_text)

                if element.element_type == "action":
                    current_content.append(
                        ActionBlock(
                            text=element.content,
                            is_centered=element.metadata.get("centered", False),
                        )
                    )
                elif element.element_type == "dialogue":
                    if element.character_name:
                        current_characters.add(element.character_name)
                    current_content.append(
                        DialogueBlock(
                            character_name=element.character_name or "UNKNOWN",
                            dialogue=element.content,
                            parenthetical=element.parenthetical,
                            character_extension=element.character_extension,
                            is_dual_dialogue=element.is_dual_dialogue,
                        )
                    )
                elif element.element_type == "transition":
                    current_content.append(Transition(text=element.content))

            else:
                # Content before first scene heading
                # Create a synthetic opening scene
                scene_number += 1
                current_scene = Scene(
                    scene_number=scene_number,
                    heading="OPENING",
                    scene_type=SceneType.UNKNOWN,
                    location="",
                    time_of_day=TimeOfDay.UNKNOWN,
                    page_start=0.0,
                )
                current_content = []
                current_characters = set()
                current_raw_lines = []

                if element.element_type == "action":
                    current_content.append(
                        ActionBlock(
                            text=element.content,
                            is_centered=element.metadata.get("centered", False),
                        )
                    )
                    current_raw_lines.append(element.raw_text)
                elif element.element_type == "dialogue":
                    if element.character_name:
                        current_characters.add(element.character_name)
                    current_content.append(
                        DialogueBlock(
                            character_name=element.character_name or "UNKNOWN",
                            dialogue=element.content,
                            parenthetical=element.parenthetical,
                            character_extension=element.character_extension,
                            is_dual_dialogue=element.is_dual_dialogue,
                        )
                    )
                    current_raw_lines.append(element.raw_text)

        # Don't forget the last scene
        if current_scene is not None:
            page_length = self._calculate_page_length(current_raw_lines)
            current_scene.content = current_content
            current_scene.characters = list(current_characters)
            current_scene.raw_text = "\n".join(current_raw_lines)
            current_scene.page_length = page_length
            scenes.append(current_scene)

        return scenes

    def _calculate_page_length(self, lines: list[str]) -> float:
        """Calculate approximate page length for content.

        Args:
            lines: Lines of content.

        Returns:
            Estimated page count (1 page ~ 1 minute).
        """
        total_lines = 0

        for line in lines:
            # Estimate lines this content would take
            # Account for wrapping
            line_count = max(1, len(line) // self.CHARS_PER_LINE + 1)
            total_lines += line_count

        return total_lines / self.LINES_PER_PAGE

    def _extract_characters(self, scenes: list[Scene]) -> list[Character]:
        """Extract unique characters from scenes.

        Args:
            scenes: List of parsed scenes.

        Returns:
            List of unique Character objects.
        """
        character_data: dict[str, dict[str, Any]] = {}

        for scene in scenes:
            for char_name in scene.characters:
                normalized = char_name.upper().strip()

                if normalized not in character_data:
                    character_data[normalized] = {
                        "name": char_name,
                        "normalized_name": normalized,
                        "dialogue_count": 0,
                        "scene_appearances": [],
                        "first_appearance": None,
                    }

                data = character_data[normalized]
                data["scene_appearances"].append(scene.scene_number)

                if data["first_appearance"] is None:
                    data["first_appearance"] = scene.scene_number

            # Count dialogue
            for content in scene.content:
                if isinstance(content, DialogueBlock):
                    normalized = content.character_name.upper().strip()
                    if normalized in character_data:
                        character_data[normalized]["dialogue_count"] += 1

        # Build Character objects
        characters = []
        for data in character_data.values():
            characters.append(
                Character(
                    name=data["name"],
                    normalized_name=data["normalized_name"],
                    dialogue_count=data["dialogue_count"],
                    scene_appearances=sorted(set(data["scene_appearances"])),
                    first_appearance=data["first_appearance"],
                )
            )

        # Sort by dialogue count (most lines first)
        characters.sort(key=lambda c: c.dialogue_count, reverse=True)

        return characters

    def _extract_locations(self, scenes: list[Scene]) -> list[Location]:
        """Extract unique locations from scenes.

        Args:
            scenes: List of parsed scenes.

        Returns:
            List of unique Location objects.
        """
        location_data: dict[str, dict[str, Any]] = {}

        for scene in scenes:
            if not scene.location:
                continue

            normalized = scene.location.upper().strip()

            if normalized not in location_data:
                location_data[normalized] = {
                    "name": scene.location,
                    "normalized_name": normalized,
                    "scene_type": scene.scene_type,
                    "scene_appearances": [],
                }

            location_data[normalized]["scene_appearances"].append(scene.scene_number)

        # Build Location objects
        locations = []
        for data in location_data.values():
            locations.append(
                Location(
                    name=data["name"],
                    normalized_name=data["normalized_name"],
                    scene_type=data["scene_type"],
                    scene_appearances=sorted(set(data["scene_appearances"])),
                )
            )

        # Sort by number of scenes (most used first)
        locations.sort(key=lambda loc: len(loc.scene_appearances), reverse=True)

        return locations


def parse_fountain(text: str) -> Script:
    """Convenience function to parse Fountain text.

    Args:
        text: Fountain format screenplay text.

    Returns:
        Parsed Script object.
    """
    parser = FountainParser()
    return parser.parse(text)
