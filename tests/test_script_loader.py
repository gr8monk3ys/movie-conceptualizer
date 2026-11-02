"""Tests for the file-based loaders in ``parsers.script_loader``.

The text-level helpers (``load_text``, ``detect_format``, PDF coercion) are
covered elsewhere; this suite covers the path that reads screenplays from disk:
extension dispatch in ``load_script``, the Fountain/FDX/PDF file loaders, the
PDF text-extraction mode switch, and OCR text cleanup.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from movie_conceptualizer.parsers import script_loader
from movie_conceptualizer.parsers.script_loader import (
    ScriptLoadError,
    UnsupportedFormatError,
    extract_text_from_pdf_bytes,
    load_fdx,
    load_fountain,
    load_pdf,
    load_script,
    preprocess_ocr_text,
)

EXAMPLE_FOUNTAIN = (
    Path(__file__).resolve().parent.parent / "examples" / "sample_screenplay.fountain"
)

SIMPLE_FOUNTAIN = """Title: Loader Test

INT. KITCHEN - NIGHT

Steam rises from a kettle.

MARA
Who's there?
"""

MINIMAL_FDX = """<?xml version="1.0" encoding="UTF-8"?>
<FinalDraft DocumentType="Script" Template="No" Version="5">
  <Content>
    <Paragraph Type="Scene Heading"><Text>INT. LAB - NIGHT</Text></Paragraph>
    <Paragraph Type="Action"><Text>A robot hums quietly.</Text></Paragraph>
    <Paragraph Type="Character"><Text>Ada</Text></Paragraph>
    <Paragraph Type="Dialogue"><Text>It works.</Text></Paragraph>
  </Content>
</FinalDraft>
"""


def _make_pdf(lines: list[str]) -> bytes:
    """Render ``lines`` into a one-page text PDF using ReportLab."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=letter)
    y = 720
    for line in lines:
        pdf.drawString(72, y, line)
        y -= 14
    pdf.save()
    return buf.getvalue()


# --------------------------------------------------------------------------
# load_script dispatch
# --------------------------------------------------------------------------


class TestLoadScriptDispatch:
    @pytest.mark.parametrize("suffix", [".fountain", ".ftn", ".txt", ".spmd", ".FOUNTAIN"])
    def test_fountain_extensions_parse_as_fountain(self, tmp_path: Path, suffix: str) -> None:
        path = tmp_path / f"script{suffix}"
        path.write_text(SIMPLE_FOUNTAIN, encoding="utf-8")

        script = load_script(path)

        assert script.title == "Loader Test"
        assert [s.heading for s in script.scenes] == ["INT. KITCHEN - NIGHT"]
        assert script.source_file == str(path.absolute())

    def test_fdx_extension_uses_fdx_parser(self, tmp_path: Path) -> None:
        path = tmp_path / "script.fdx"
        path.write_text(MINIMAL_FDX, encoding="utf-8")

        script = load_script(path)

        assert [s.heading for s in script.scenes] == ["INT. LAB - NIGHT"]
        assert {c.name for c in script.characters} == {"ADA"}
        assert script.source_file == str(path.absolute())

    def test_pdf_extension_uses_pdf_loader(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "script.pdf"
        path.write_bytes(b"%PDF-stub")
        monkeypatch.setattr(
            script_loader,
            "extract_text_from_pdf_bytes",
            lambda data: "INT. GARAGE - DAY\n\nA car idles.",
        )

        script = load_script(path)

        assert script.format_type == "pdf"
        assert [s.heading for s in script.scenes] == ["INT. GARAGE - DAY"]

    def test_unsupported_extension_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "script.docx"
        path.write_text("whatever", encoding="utf-8")

        with pytest.raises(UnsupportedFormatError, match=r"\.docx") as excinfo:
            load_script(path)

        # The message advertises every supported extension.
        for ext in (".fdx", ".fountain", ".ftn", ".pdf", ".spmd", ".txt"):
            assert ext in str(excinfo.value)
        # And it is catchable as the base loader error.
        assert isinstance(excinfo.value, ScriptLoadError)

    def test_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_script(tmp_path / "nope.fountain")

    def test_loads_bundled_example(self) -> None:
        script = load_script(EXAMPLE_FOUNTAIN)

        assert script.title == "THE LAST SUNRISE"
        assert script.scene_count > 0
        assert "EXT. MOUNTAIN PEAK - DAWN" in [s.heading for s in script.scenes]


# --------------------------------------------------------------------------
# Individual file loaders
# --------------------------------------------------------------------------


class TestFileLoaders:
    @pytest.mark.parametrize("loader", [load_fountain, load_fdx, load_pdf])
    def test_missing_file(self, tmp_path: Path, loader) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(FileNotFoundError):
            loader(tmp_path / "missing")

    @pytest.mark.parametrize("loader", [load_fountain, load_fdx, load_pdf])
    def test_directory_is_rejected(self, tmp_path: Path, loader) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(ScriptLoadError, match="not a file"):
            loader(tmp_path)

    def test_load_fountain_falls_back_to_latin1(self, tmp_path: Path) -> None:
        path = tmp_path / "latin1.fountain"
        text = "Title: Café Noir\n\nINT. CAFÉ - NIGHT\n\nRain on the glass.\n"
        path.write_bytes(text.encode("latin-1"))
        # Sanity: this byte sequence is not valid UTF-8.
        with pytest.raises(UnicodeDecodeError):
            path.read_bytes().decode("utf-8")

        script = load_fountain(path)

        assert script.title == "Café Noir"
        assert script.scenes[0].heading == "INT. CAFÉ - NIGHT"

    def test_load_fdx_falls_back_to_latin1(self, tmp_path: Path) -> None:
        path = tmp_path / "latin1.fdx"
        xml = MINIMAL_FDX.replace('encoding="UTF-8"', 'encoding="ISO-8859-1"').replace(
            "A robot hums quietly.", "A robot hums à la mode."
        )
        path.write_bytes(xml.encode("latin-1"))

        script = load_fdx(path)

        assert script.scenes[0].heading == "INT. LAB - NIGHT"
        assert script.source_file == str(path.absolute())

    def test_load_pdf_real_text_pdf(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MOVIECON_PDF_OCR", "never")
        path = tmp_path / "my_short.pdf"
        path.write_bytes(_make_pdf(["INT. DINER - NIGHT", "", "Neon hums over an empty counter."]))

        script = load_pdf(path)

        assert script.format_type == "pdf"
        assert script.source_file == str(path.absolute())
        # No title page in the PDF, so the file stem becomes the title.
        assert script.title == "my_short"
        # A heading that is already well-formed survives normalization intact.
        assert [s.heading for s in script.scenes] == ["INT. DINER - NIGHT"]


# --------------------------------------------------------------------------
# extract_text_from_pdf_bytes mode switch
# --------------------------------------------------------------------------


class TestExtractTextFromPdfBytes:
    @pytest.fixture
    def calls(self, monkeypatch: pytest.MonkeyPatch) -> list[str]:
        recorded: list[str] = []

        def fake_pypdf(data: bytes) -> str:
            recorded.append("pypdf")
            return "INT. ROOM - DAY\nshort"

        def fake_ocr(data: bytes) -> str:
            recorded.append("ocr")
            return "OCR TEXT"

        monkeypatch.setattr(script_loader, "_extract_pdf_text_pypdf", fake_pypdf)
        monkeypatch.setattr(script_loader, "_extract_pdf_text_ocr", fake_ocr)
        monkeypatch.setenv("MOVIECON_PDF_PREPROCESS", "false")
        return recorded

    def test_never_skips_ocr(self, calls: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MOVIECON_PDF_OCR", "never")

        assert extract_text_from_pdf_bytes(b"") == "INT. ROOM - DAY\nshort"
        assert calls == ["pypdf"]

    def test_always_skips_pypdf(self, calls: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MOVIECON_PDF_OCR", "always")

        assert extract_text_from_pdf_bytes(b"") == "OCR TEXT"
        assert calls == ["ocr"]

    def test_auto_falls_back_to_ocr_when_text_is_sparse(
        self, calls: list[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MOVIECON_PDF_OCR", "auto")

        assert extract_text_from_pdf_bytes(b"") == "OCR TEXT"
        assert calls == ["pypdf", "ocr"]

    def test_invalid_mode_behaves_like_auto(
        self, calls: list[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MOVIECON_PDF_OCR", "sometimes")

        extract_text_from_pdf_bytes(b"")
        assert calls == ["pypdf", "ocr"]

    def test_auto_keeps_dense_pypdf_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        dense = "word " * 3000
        monkeypatch.setattr(script_loader, "_extract_pdf_text_pypdf", lambda data: dense)

        def boom(data: bytes) -> str:
            raise AssertionError("OCR should not run for dense text")

        monkeypatch.setattr(script_loader, "_extract_pdf_text_ocr", boom)
        monkeypatch.setenv("MOVIECON_PDF_OCR", "auto")
        monkeypatch.setenv("MOVIECON_PDF_PREPROCESS", "false")

        assert extract_text_from_pdf_bytes(b"") == dense

    def test_ocr_failure_returns_pypdf_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(script_loader, "_extract_pdf_text_pypdf", lambda data: "sparse")

        def fail(data: bytes) -> str:
            raise ScriptLoadError("no tesseract")

        monkeypatch.setattr(script_loader, "_extract_pdf_text_ocr", fail)
        monkeypatch.setenv("MOVIECON_PDF_OCR", "auto")

        assert extract_text_from_pdf_bytes(b"") == "sparse"

    def test_unreadable_pdf_raises_script_load_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MOVIECON_PDF_OCR", "never")

        with pytest.raises(ScriptLoadError, match="Failed to read PDF"):
            extract_text_from_pdf_bytes(b"this is not a pdf")


# --------------------------------------------------------------------------
# preprocess_ocr_text
# --------------------------------------------------------------------------


class TestPreprocessOcrText:
    def test_empty_passthrough(self) -> None:
        assert preprocess_ocr_text("") == ""

    def test_normalizes_line_endings_and_blank_runs(self) -> None:
        raw = "INT. HALL - DAY\r\n\r\n\r\n\r\nFootsteps echo.\rDoors slam."
        assert preprocess_ocr_text(raw) == "INT. HALL - DAY\n\nFootsteps echo. Doors slam."

    def test_strips_repeated_page_headers(self) -> None:
        pages = [f"MY SCRIPT DRAFT\n\nAction on page {i}." for i in range(5)]
        cleaned = preprocess_ocr_text("\n\n".join(pages))

        assert "MY SCRIPT DRAFT" not in cleaned
        assert "Action on page 4." in cleaned

    def test_dehyphenates_wrapped_words(self) -> None:
        assert preprocess_ocr_text("An extra-\nordinary day.") == "An extraordinary day."

    def test_merges_wrapped_action_but_keeps_cues_and_headings(self) -> None:
        raw = "EXT. FIELD - DAY\nWind moves\nthrough the wheat.\nJONAH"
        cleaned = preprocess_ocr_text(raw)

        assert cleaned.split("\n") == [
            "EXT. FIELD - DAY",
            "Wind moves through the wheat.",
            "JONAH",
        ]


# --------------------------------------------------------------------------
# PDF heading normalization (regression: "INT. X" used to become "INT.. X")
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("INT. DINER - NIGHT", "INT. DINER - NIGHT"),
        ("int. diner - night", "INT. DINER - NIGHT"),
        ("INT DINER - NIGHT", "INT. DINER - NIGHT"),
        ("EXT- ROOF - DAY", "EXT. ROOF - DAY"),
        ("INT.DINER - NIGHT", "INT. DINER - NIGHT"),
        ("INT/EXT. CAR - DAY", "INT/EXT. CAR - DAY"),
        ("INT/EXT CAR - DAY", "INT/EXT. CAR - DAY"),
        ("I/E CAR - DAY", "I/E. CAR - DAY"),
    ],
)
def test_pdf_scene_headings_get_exactly_one_period(raw: str, expected: str) -> None:
    coerced = script_loader.coerce_pdf_text_to_fountain(f"{raw}\n\nAction.\n")
    assert coerced.splitlines()[0] == expected
