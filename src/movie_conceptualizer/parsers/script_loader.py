"""Script loading utilities for movie conceptualizer.

Provides convenient functions to load screenplays from various sources
including files and raw text strings.
"""

from __future__ import annotations

import io
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

from movie_conceptualizer.models import SceneType, Script
from movie_conceptualizer.parsers.fountain_parser import FountainParser
from movie_conceptualizer.parsers.fdx_parser import parse_fdx

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


def load_fdx(path: str | Path) -> Script:
    """Load a Final Draft (.fdx) screenplay from a file."""
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if not path.is_file():
        raise ScriptLoadError(f"Path is not a file: {path}")

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            text = path.read_text(encoding="latin-1")
        except Exception as e:
            raise ScriptLoadError(f"Failed to read file: {e}") from e

    script = parse_fdx(text)
    script.source_file = str(path.absolute())
    return script


def _extract_pdf_text_pypdf(data: bytes) -> str:
    """Extract text using pypdf (fast, best-effort)."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ScriptLoadError(
            "PDF support requires 'pypdf'. Install it or add the pdf extra."
        ) from exc

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise ScriptLoadError(f"Failed to read PDF: {exc}") from exc

    pages_text: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        pages_text.append(text)

    return "\n\n".join(pages_text).strip()


def _extract_pdf_text_ocr(data: bytes) -> str:
    """Extract text via OCR using pdf2image + pytesseract."""
    try:
        from pdf2image import convert_from_bytes
    except ImportError as exc:
        raise ScriptLoadError(
            "PDF OCR requires 'pdf2image'. Install it to enable OCR."
        ) from exc
    try:
        import pytesseract
    except ImportError as exc:
        raise ScriptLoadError(
            "PDF OCR requires 'pytesseract'. Install it to enable OCR."
        ) from exc

    dpi = int(os.environ.get("MOVIECON_PDF_OCR_DPI", "200"))
    max_pages_env = os.environ.get("MOVIECON_PDF_OCR_MAX_PAGES")
    max_pages = int(max_pages_env) if max_pages_env else None

    images = convert_from_bytes(data, dpi=dpi)
    if max_pages is not None:
        images = images[:max_pages]

    ocr_pages: list[str] = []
    for image in images:
        ocr_pages.append(pytesseract.image_to_string(image))

    return "\n\n".join(ocr_pages).strip()


def extract_text_from_pdf_bytes(data: bytes) -> str:
    """Extract text from a PDF byte stream with OCR fallback."""
    ocr_mode = os.environ.get("MOVIECON_PDF_OCR", "auto").lower()
    if ocr_mode not in ("auto", "always", "never"):
        ocr_mode = "auto"

    text = ""
    if ocr_mode != "always":
        text = _extract_pdf_text_pypdf(data)

    if ocr_mode == "never":
        return text

    # Heuristic: if extraction is too short, fall back to OCR
    non_ws = len("".join(text.split()))
    preprocess = os.environ.get("MOVIECON_PDF_PREPROCESS", "true").lower() in (
        "true",
        "1",
        "yes",
    )

    if ocr_mode == "always" or non_ws < 2000:
        try:
            ocr_text = _extract_pdf_text_ocr(data)
        except ScriptLoadError:
            # If OCR fails, fall back to whatever we extracted
            return text
        return preprocess_ocr_text(ocr_text) if preprocess else (ocr_text or text)

    return preprocess_ocr_text(text) if preprocess else text


def load_pdf(path: str | Path) -> Script:
    """Load a screenplay from a PDF file (best-effort text extraction)."""
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if not path.is_file():
        raise ScriptLoadError(f"Path is not a file: {path}")

    try:
        data = path.read_bytes()
    except Exception as e:
        raise ScriptLoadError(f"Failed to read file: {e}") from e

    text = extract_text_from_pdf_bytes(data)
    text = coerce_pdf_text_to_fountain(text)
    script = load_text(text, title=path.stem)
    script.format_type = "pdf"
    script.source_file = str(path.absolute())
    return script


def preprocess_ocr_text(text: str) -> str:
    """Clean OCR text to improve parsing."""
    if not text:
        return text

    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Fix common OCR confusions for scene headings
    text = _normalize_scene_heading_tokens(text)

    # Remove obvious page headers/footers (repeated lines)
    lines = [line.strip() for line in text.split("\n")]
    line_counts: dict[str, int] = {}
    for line in lines:
        if not line:
            continue
        if len(line) > 80:
            continue
        line_counts[line] = line_counts.get(line, 0) + 1

    repeated = {line for line, count in line_counts.items() if count >= 5}
    cleaned_lines: list[str] = []
    for line in lines:
        if line in repeated:
            continue
        cleaned_lines.append(line)

    # De-hyphenate line breaks: "exam-\nple" -> "example"
    joined = "\n".join(cleaned_lines)
    joined = re.sub(r"(\w)-\n(\w)", r"\1\2", joined)

    # Merge wrapped lines into paragraphs while preserving blank lines
    merged_lines: list[str] = []
    for line in joined.split("\n"):
        stripped = line.strip()
        if not stripped:
            merged_lines.append("")
            continue
        if not merged_lines or merged_lines[-1] == "":
            merged_lines.append(stripped)
            continue
        # If previous line looks like a scene heading, keep as new line
        prev = merged_lines[-1]
        if prev.upper().startswith(("INT.", "EXT.", "INT/EXT.", "I/E.")):
            merged_lines.append(stripped)
            continue
        # If this line is all caps and short, keep separate (likely character cue)
        if stripped.isupper() and len(stripped) <= 40:
            merged_lines.append(stripped)
            continue
        # Otherwise, append to previous paragraph
        merged_lines[-1] = prev + " " + stripped

    # Collapse excessive blank lines
    normalized: list[str] = []
    blank = False
    for line in merged_lines:
        if not line:
            if blank:
                continue
            blank = True
            normalized.append("")
            continue
        blank = False
        normalized.append(line)

    return "\n".join(normalized).strip()


def coerce_pdf_text_to_fountain(text: str) -> str:
    """Coerce raw PDF text into Fountain-like structure if no scene headings exist."""
    if not text:
        return text

    # If we already have scene headings, keep original text
    for line in text.splitlines():
        if _is_scene_heading(line):
            return _normalize_scene_headings(text)

    # Try to detect sluglines without INT/EXT
    slug_scenes = _split_by_sluglines(text)
    if slug_scenes:
        scenes = []
        for heading, body in slug_scenes:
            scenes.append(f"INT. {heading}\n\n{body}\n")
        return "\n".join(scenes)

    # No scene headings detected: synthesize simple scenes from paragraphs
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return text

    chunk_size = int(os.environ.get("MOVIECON_PDF_SCENE_CHUNK", "3"))
    chunk_size = max(1, min(chunk_size, 10))

    scenes: list[str] = []
    scene_num = 1
    for i in range(0, len(paragraphs), chunk_size):
        chunk = "\n\n".join(paragraphs[i : i + chunk_size])
        scenes.append(f"INT. UNKNOWN - DAY\n\n{chunk}\n")
        scene_num += 1

    return "\n".join(scenes)


def _normalize_scene_heading_tokens(text: str) -> str:
    """Normalize common OCR errors in INT/EXT headings."""
    replacements = {
        "1NT.": "INT.",
        "1NT ": "INT ",
        "lNT.": "INT.",
        "lNT ": "INT ",
        "INT/EXT": "INT/EXT",
        "I/E": "I/E",
        "EX T.": "EXT.",
        "EX T ": "EXT ",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    # Normalize leading tokens like "INT-" or "EXT-"
    text = re.sub(r"^(INT|EXT|INT/EXT|I/E)[\s\-]+", r"\1. ", text, flags=re.MULTILINE)
    return text


def _is_scene_heading(line: str) -> bool:
    """Heuristic to detect scene headings."""
    stripped = line.strip()
    if not stripped:
        return False
    upper = stripped.upper()
    if upper.startswith(("INT.", "EXT.", "INT/EXT.", "I/E.")):
        return True
    if re.match(r"^(INT|EXT|INT/EXT|I/E)\b", upper):
        return True
    return False


def _normalize_scene_headings(text: str) -> str:
    """Ensure scene headings use standard formatting."""
    lines = text.splitlines()
    normalized_lines: list[str] = []
    for line in lines:
        if _is_scene_heading(line):
            upper = line.strip().upper()
            upper = re.sub(r"^(INT|EXT|INT/EXT|I/E)\b", r"\1.", upper)
            normalized_lines.append(upper)
        else:
            normalized_lines.append(line)
    return "\n".join(normalized_lines)


def _split_by_sluglines(text: str) -> list[tuple[str, str]]:
    """Split text into scenes using heuristic sluglines."""
    time_tokens = ("DAY", "NIGHT", "MORNING", "EVENING", "DUSK", "DAWN", "LATER", "CONTINUOUS")
    lines = [l.rstrip() for l in text.splitlines()]
    scenes: list[tuple[str, str]] = []
    current_heading: str | None = None
    current_body: list[str] = []

    def flush() -> None:
        nonlocal current_heading, current_body
        if current_heading and current_body:
            scenes.append((current_heading, "\n".join(current_body).strip()))
        current_heading = None
        current_body = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            current_body.append("")
            continue
        upper = stripped.upper()
        looks_slug = (
            len(upper) <= 80
            and "-" in upper
            and any(token in upper for token in time_tokens)
            and upper == stripped
        )
        if looks_slug:
            flush()
            current_heading = upper
        else:
            current_body.append(stripped)

    flush()
    return scenes


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

    if extension == ".fdx":
        return load_fdx(path)
    if extension == ".pdf":
        return load_pdf(path)

    raise UnsupportedFormatError(
        f"Unsupported file format: {extension}. "
        f"Supported formats: {', '.join(sorted(fountain_extensions | {'.fdx', '.pdf'}))}"
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
