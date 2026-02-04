"""Script loading utilities for movie conceptualizer.

Provides convenient functions to load screenplays from various sources
including files and raw text strings.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from movie_conceptualizer.models import Script
from movie_conceptualizer.parsers.fountain_parser import FountainParser

if TYPE_CHECKING:
    pass


class ScriptLoadError(Exception):
    """Raised when a script cannot be loaded."""

    pass


class UnsupportedFormatError(ScriptLoadError):
    """Raised when script format is not supported."""

    pass


def load_fountain(path: str | Path) -> Script:
    """Load a Fountain format screenplay from a file.

    Args:
        path: Path to the .fountain file.

    Returns:
        Parsed Script object.

    Raises:
        ScriptLoadError: If the file cannot be read.
        FileNotFoundError: If the file does not exist.

    Example:
        script = load_fountain("screenplay.fountain")
        print(f"Title: {script.title}")
        print(f"Scenes: {script.scene_count}")
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if not path.is_file():
        raise ScriptLoadError(f"Path is not a file: {path}")

    try:
        # Try UTF-8 first (most common)
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Fall back to latin-1 which can read any byte sequence
        try:
            text = path.read_text(encoding="latin-1")
        except Exception as e:
            raise ScriptLoadError(f"Failed to read file: {e}") from e

    parser = FountainParser()
    script = parser.parse(text)

    # Set source file
    script.source_file = str(path.absolute())

    return script


def load_text(text: str, title: str | None = None) -> Script:
    """Load a screenplay from raw text string.

    Attempts to detect the format automatically. Currently supports:
    - Fountain format (default)

    Args:
        text: Raw screenplay text.
        title: Optional title to use if not found in text.

    Returns:
        Parsed Script object.

    Raises:
        ScriptLoadError: If the text cannot be parsed.

    Example:
        text = '''
        Title: My Script

        INT. HOUSE - DAY

        A cozy living room.

        JOHN
        Hello, world!
        '''
        script = load_text(text)
        print(f"Title: {script.title}")
    """
    if not text or not text.strip():
        raise ScriptLoadError("Empty text provided")

    parser = FountainParser()
    script = parser.parse(text)

    # Override title if provided and not found in text
    if title and script.title == "Untitled":
        script.title = title
        script.title_page.title = title

    return script


def load_script(path: str | Path) -> Script:
    """Load a screenplay from file, auto-detecting format.

    Supports the following formats based on file extension:
    - .fountain, .ftn, .txt - Fountain format

    Args:
        path: Path to the screenplay file.

    Returns:
        Parsed Script object.

    Raises:
        UnsupportedFormatError: If the file format is not supported.
        ScriptLoadError: If the file cannot be read or parsed.
        FileNotFoundError: If the file does not exist.

    Example:
        script = load_script("screenplay.fountain")
        print(f"Title: {script.title}")
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    extension = path.suffix.lower()

    # Map extensions to loaders
    fountain_extensions = {".fountain", ".ftn", ".txt", ".spmd"}

    if extension in fountain_extensions:
        return load_fountain(path)

    raise UnsupportedFormatError(
        f"Unsupported file format: {extension}. "
        f"Supported formats: {', '.join(sorted(fountain_extensions))}"
    )


def detect_format(text: str) -> str:
    """Attempt to detect the screenplay format from text content.

    Args:
        text: Raw screenplay text.

    Returns:
        Format identifier string ("fountain", "unknown").
    """
    # Check for Fountain-style title page
    lines = text.strip().split("\n")

    # Look for title page key: value pattern
    for line in lines[:20]:  # Check first 20 lines
        if ":" in line:
            key = line.split(":")[0].strip().lower()
            if key in ("title", "author", "credit", "source", "draft date"):
                return "fountain"

    # Look for scene headings
    for line in lines[:50]:  # Check first 50 lines
        stripped = line.strip().upper()
        if any(
            stripped.startswith(prefix)
            for prefix in ("INT.", "EXT.", "INT/EXT.", "I/E.")
        ):
            return "fountain"

    # Check for character cues (all caps followed by dialogue)
    for i, line in enumerate(lines[:-1]):
        stripped = line.strip()
        if (
            stripped.isupper()
            and len(stripped) > 1
            and stripped[0].isalpha()
            and not any(c.isdigit() for c in stripped)
        ):
            next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if next_line and not next_line.isupper():
                return "fountain"

    return "unknown"


def validate_script(script: Script) -> list[str]:
    """Validate a parsed script and return any warnings.

    Args:
        script: Parsed Script object.

    Returns:
        List of warning messages (empty if valid).

    Example:
        script = load_fountain("screenplay.fountain")
        warnings = validate_script(script)
        for warning in warnings:
            print(f"Warning: {warning}")
    """
    warnings: list[str] = []

    # Check for title
    if script.title == "Untitled":
        warnings.append("No title found in screenplay")

    # Check for scenes
    if not script.scenes:
        warnings.append("No scenes found in screenplay")
    elif len(script.scenes) < 3:
        warnings.append(f"Only {len(script.scenes)} scene(s) found - very short screenplay")

    # Check for characters
    if not script.characters:
        warnings.append("No characters found in screenplay")

    # Check for dialogue
    total_dialogue = sum(c.dialogue_count for c in script.characters)
    if total_dialogue == 0:
        warnings.append("No dialogue found in screenplay")

    # Check page count
    if script.total_pages < 1:
        warnings.append("Screenplay is less than 1 page")
    elif script.total_pages > 200:
        warnings.append(f"Screenplay is {script.total_pages:.0f} pages - unusually long")

    # Check for scenes without locations
    scenes_without_location = [
        s for s in script.scenes
        if not s.location or s.location.strip() == ""
    ]
    if scenes_without_location:
        warnings.append(
            f"{len(scenes_without_location)} scene(s) missing location information"
        )

    # Check for empty scenes
    empty_scenes = [s for s in script.scenes if not s.content]
    if empty_scenes:
        warnings.append(f"{len(empty_scenes)} scene(s) have no content")

    return warnings


def get_script_summary(script: Script) -> dict:
    """Generate a summary of the parsed script.

    Args:
        script: Parsed Script object.

    Returns:
        Dictionary containing script statistics.

    Example:
        script = load_fountain("screenplay.fountain")
        summary = get_script_summary(script)
        print(f"Pages: {summary['total_pages']}")
    """
    # Count dialogue blocks
    dialogue_count = 0
    action_count = 0
    transition_count = 0

    for scene in script.scenes:
        for content in scene.content:
            if hasattr(content, "dialogue"):
                dialogue_count += 1
            elif hasattr(content, "text") and not hasattr(content, "dialogue"):
                # ActionBlock has text but not dialogue
                action_count += 1
            else:
                transition_count += 1

    # Get main characters (top 5 by dialogue)
    main_characters = [c.name for c in script.characters[:5]]

    # Get most used locations (top 5)
    top_locations = [loc.name for loc in script.locations[:5]]

    # Count interior vs exterior scenes
    int_scenes = sum(
        1 for s in script.scenes
        if s.scene_type in (SceneType.INTERIOR, SceneType.INTERIOR_EXTERIOR)
    )
    ext_scenes = sum(
        1 for s in script.scenes
        if s.scene_type in (SceneType.EXTERIOR, SceneType.INTERIOR_EXTERIOR)
    )

    return {
        "title": script.title,
        "total_pages": round(script.total_pages, 1),
        "estimated_runtime_minutes": round(script.total_pages),
        "scene_count": script.scene_count,
        "character_count": script.character_count,
        "location_count": script.location_count,
        "dialogue_blocks": dialogue_count,
        "action_blocks": action_count,
        "transitions": transition_count,
        "main_characters": main_characters,
        "top_locations": top_locations,
        "interior_scenes": int_scenes,
        "exterior_scenes": ext_scenes,
        "has_title_page": script.title_page.title is not None,
        "authors": script.title_page.authors,
    }


# Import SceneType for summary function
from movie_conceptualizer.models import SceneType
