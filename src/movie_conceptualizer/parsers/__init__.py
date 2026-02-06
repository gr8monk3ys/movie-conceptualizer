"""Screenplay parsers for movie conceptualizer.

This module provides parsers for various screenplay formats,
with Fountain format as the primary supported format.
"""

from movie_conceptualizer.parsers.fountain_parser import (
    FountainParser,
    parse_fountain,
)
from movie_conceptualizer.parsers.fdx_parser import (
    FDXParseError,
    parse_fdx,
)
from movie_conceptualizer.parsers.script_loader import (
    ScriptLoadError,
    UnsupportedFormatError,
    coerce_pdf_text_to_fountain,
    detect_format,
    extract_text_from_pdf_bytes,
    preprocess_ocr_text,
    get_script_summary,
    load_fdx,
    load_fountain,
    load_pdf,
    load_script,
    load_text,
    validate_script,
)

__all__ = [
    # Parser classes
    "FountainParser",
    # Convenience functions
    "parse_fountain",
    "parse_fdx",
    "load_fountain",
    "load_fdx",
    "load_pdf",
    "load_text",
    "load_script",
    "extract_text_from_pdf_bytes",
    "coerce_pdf_text_to_fountain",
    "preprocess_ocr_text",
    "detect_format",
    "validate_script",
    "get_script_summary",
    # Exceptions
    "ScriptLoadError",
    "UnsupportedFormatError",
    "FDXParseError",
]
