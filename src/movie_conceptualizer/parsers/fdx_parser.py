"""Minimal Final Draft (.fdx) parser.

Converts FDX XML into Fountain-like text and reuses the Fountain parser.
This is a best-effort implementation for common paragraph types.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from movie_conceptualizer.models import Script
from movie_conceptualizer.parsers.fountain_parser import FountainParser


class FDXParseError(Exception):
    """Raised when an FDX document cannot be parsed."""

    pass


def _paragraph_text(paragraph: ET.Element) -> str:
    text = "".join(paragraph.itertext()).strip()
    return text


def parse_fdx(text: str) -> Script:
    """Parse Final Draft FDX XML and return a Script."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise FDXParseError(f"Invalid FDX XML: {exc}") from exc

    content = root.find(".//Content")
    if content is None:
        raise FDXParseError("FDX content section not found")

    paragraphs: list[tuple[str, str]] = []
    for paragraph in content.findall("Paragraph"):
        para_type = (paragraph.get("Type") or "").strip().lower()
        value = _paragraph_text(paragraph)
        if not value:
            continue

        if para_type in ("scene heading", "slugline"):
            rendered = value.upper()
        elif para_type == "action":
            rendered = value
        elif para_type == "character":
            rendered = value.upper()
        elif para_type == "dialogue":
            rendered = value
        elif para_type == "parenthetical":
            # FDX may or may not include the parentheses in the text itself.
            already_wrapped = value.startswith("(") and value.endswith(")")
            rendered = value if already_wrapped else f"({value})"
        elif para_type == "transition":
            rendered = value.upper()
        elif para_type == "shot":
            rendered = value.upper()
        else:
            # Fallback: treat as action
            rendered = value

        paragraphs.append((para_type, rendered))

    lines: list[str] = []
    dialogue_members = ("character", "parenthetical", "dialogue")
    for index, (para_type, rendered) in enumerate(paragraphs):
        lines.append(rendered)
        next_type = paragraphs[index + 1][0] if index + 1 < len(paragraphs) else None
        # Fountain treats a blank line as the end of a dialogue block, so a
        # Character/Parenthetical/Dialogue run must stay contiguous or the
        # cue is re-parsed as action and the dialogue is lost.
        continues_dialogue = para_type in dialogue_members and next_type in (
            "parenthetical",
            "dialogue",
        )
        if not continues_dialogue:
            lines.append("")

    fountain_text = "\n".join(lines).strip()
    parser = FountainParser()
    script = parser.parse(fountain_text)
    script.format_type = "fdx"
    script.raw_text = fountain_text
    return script
