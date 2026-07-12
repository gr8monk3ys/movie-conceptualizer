"""Tests for coercing raw PDF/OCR text into Fountain-like structure.

These exercise ``coerce_pdf_text_to_fountain``, which prepares unstructured
PDF text for the Fountain parser. The function has three branches:

1. Text that already contains scene headings is normalized and returned as-is.
2. Text with all-caps "slugline" style headings (no INT/EXT) is wrapped as
   ``INT. <heading>`` scenes.
3. Text with no detectable headings is chunked into synthetic scenes.
"""

from movie_conceptualizer.parsers import (
    coerce_pdf_text_to_fountain,
    load_text,
)


class TestCoercePdfTextToFountain:
    """Tests for coerce_pdf_text_to_fountain."""

    def test_empty_text_returned_unchanged(self):
        """Empty input is passed through untouched."""
        assert coerce_pdf_text_to_fountain("") == ""

    def test_existing_scene_headings_take_passthrough_branch(self):
        """Text with INT/EXT headings is normalized, not chunked.

        We assert on the location/body content rather than exact heading
        punctuation, since heading normalization is handled separately.
        """
        text = "INT. KITCHEN - DAY\n\nJohn pours coffee.\n"
        result = coerce_pdf_text_to_fountain(text)
        # Real heading is kept (not replaced by the synthetic placeholder).
        assert "KITCHEN - DAY" in result
        assert "INT. UNKNOWN - DAY" not in result
        assert "John pours coffee." in result

    def test_sluglines_without_int_ext_are_wrapped(self):
        """All-caps time-coded sluglines become INT. scenes."""
        text = (
            "KITCHEN - DAY\n"
            "John pours coffee and stares out the window.\n"
            "\n"
            "ROOFTOP - NIGHT\n"
            "Sarah looks at the city below.\n"
        )
        result = coerce_pdf_text_to_fountain(text)

        # Each slugline should be promoted to an INT. scene heading.
        assert "INT. KITCHEN - DAY" in result
        assert "INT. ROOFTOP - NIGHT" in result
        # Body text is retained.
        assert "John pours coffee" in result
        assert "Sarah looks at the city below" in result

    def test_sluglines_produce_parseable_scenes(self):
        """Wrapped sluglines round-trip into a Script with scenes."""
        text = "KITCHEN - DAY\nJohn pours coffee.\n\nROOFTOP - NIGHT\nSarah looks at the city.\n"
        result = coerce_pdf_text_to_fountain(text)
        script = load_text(result, title="Coerced")

        assert len(script.scenes) == 2

    def test_unstructured_text_is_chunked_into_scenes(self):
        """Plain prose with no headings becomes synthetic INT. scenes."""
        paragraphs = "\n\n".join(f"Paragraph number {i} of the body text." for i in range(6))
        result = coerce_pdf_text_to_fountain(paragraphs)

        # Fallback synthesizes placeholder scene headings.
        assert "INT. UNKNOWN - DAY" in result
        # All the original paragraph content survives.
        assert "Paragraph number 0" in result
        assert "Paragraph number 5" in result

    def test_chunk_size_is_configurable(self, monkeypatch):
        """MOVIECON_PDF_SCENE_CHUNK controls paragraphs per synthetic scene."""
        monkeypatch.setenv("MOVIECON_PDF_SCENE_CHUNK", "1")
        paragraphs = "\n\n".join(f"Para {i}." for i in range(3))
        result = coerce_pdf_text_to_fountain(paragraphs)

        # One paragraph per scene -> three headings.
        assert result.count("INT. UNKNOWN - DAY") == 3
