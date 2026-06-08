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

    lines: list[str] = []
    for paragraph in content.findall("Paragraph"):
        para_type = (paragraph.get("Type") or "").strip().lower()
        value = _paragraph_text(paragraph)
        if not value:
            continue

        if para_type in ("scene heading", "slugline"):
            lines.append(value.upper())
        elif para_type == "action":
            lines.append(value)
        elif para_type == "character":
            lines.append(value.upper())
        elif para_type == "dialogue":
            lines.append(value)
        elif para_type == "parenthetical":
            lines.append(f"({value})")
        elif para_type == "transition":
            lines.append(value.upper())
        elif para_type == "shot":
            lines.append(value.upper())
        else:
            # Fallback: treat as action
            lines.append(value)

        lines.append("")  # Add blank line between paragraphs

    fountain_text = "\n".join(lines).strip()
    parser = FountainParser()
    script = parser.parse(fountain_text)
    script.format_type = "fdx"
    script.raw_text = fountain_text
    return script
