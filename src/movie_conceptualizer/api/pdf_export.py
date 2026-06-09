"""PDF generation for export endpoints.

Renders the same export payloads the JSON endpoints produce into printable
PDFs (shot lists, storyboard prompt packets, and scene analyses) using
ReportLab's platypus layout engine.
"""

from __future__ import annotations

import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_styles = getSampleStyleSheet()

_TITLE = _styles["Title"]
_HEADING = _styles["Heading2"]
_BODY = ParagraphStyle("Body", parent=_styles["BodyText"], fontSize=9, leading=12)
_CELL = ParagraphStyle("Cell", parent=_styles["BodyText"], fontSize=8, leading=10)
_META = ParagraphStyle(
    "Meta", parent=_styles["BodyText"], fontSize=9, leading=12, textColor=colors.grey
)

_TABLE_STYLE = TableStyle(
    [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b0b0b0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6f7")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
)


def _escape(text: object) -> str:
    raw = "" if text is None else str(text)
    return raw.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _para(text: object, style: ParagraphStyle = _CELL) -> Paragraph:
    """Build a paragraph from arbitrary export data, escaping markup."""
    return Paragraph(_escape(text), style)


def _project_header(export_data: dict[str, Any], subtitle: str) -> list[Any]:
    project = export_data.get("project", {})
    title = project.get("title") or "Untitled"
    flow: list[Any] = [Paragraph(_escape(title), _TITLE), Paragraph(subtitle, _META)]
    meta_bits = [
        f"Genre: {project['genre']}" if project.get("genre") else None,
        f"Project ID: {project['id']}" if project.get("id") else None,
    ]
    meta = " &nbsp;|&nbsp; ".join(bit for bit in meta_bits if bit)
    if meta:
        flow.append(Paragraph(meta, _META))
    flow.append(Spacer(1, 0.25 * inch))
    return flow


def _render(flow: list[Any], pagesize: tuple[float, float]) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
    )
    doc.build(flow)
    return buffer.getvalue()


def build_shot_list_pdf(export_data: dict[str, Any]) -> bytes:
    """Render a shot-list export payload as a landscape PDF table."""
    flow = _project_header(export_data, "Shot List")

    summary = export_data.get("summary", {})
    summary_bits = [f"Total shots: {summary.get('total_shots', 0)}"]
    if summary.get("scenes_covered") is not None:
        summary_bits.append(f"Scenes covered: {summary['scenes_covered']}")
    if summary.get("estimated_duration_minutes") is not None:
        summary_bits.append(f"Estimated duration: {summary['estimated_duration_minutes']} min")
    flow.append(Paragraph(" &nbsp;|&nbsp; ".join(summary_bits), _BODY))
    flow.append(Spacer(1, 0.15 * inch))

    header = ["Scene", "Shot", "Type", "Movement", "Duration (s)", "Description", "Notes"]
    rows: list[list[Any]] = [header]
    for shot in export_data.get("shots", []):
        rows.append(
            [
                _para(shot.get("scene_number")),
                _para(shot.get("shot_number")),
                _para(shot.get("shot_type")),
                _para(shot.get("camera_movement")),
                _para(shot.get("duration_seconds")),
                _para(shot.get("description")),
                _para(shot.get("notes") or shot.get("framing_notes")),
            ]
        )

    table = Table(
        rows,
        colWidths=[
            0.6 * inch,
            0.6 * inch,
            1.0 * inch,
            1.0 * inch,
            0.9 * inch,
            4.3 * inch,
            1.6 * inch,
        ],
        repeatRows=1,
    )
    table.setStyle(_TABLE_STYLE)
    flow.append(table)

    return _render(flow, landscape(letter))


def build_storyboard_pdf(export_data: dict[str, Any]) -> bytes:
    """Render a storyboard export payload as a frame-per-block PDF packet."""
    flow = _project_header(export_data, "Storyboard Prompt Packet")

    context = export_data.get("context") or {}
    if context.get("overall_tone"):
        flow.append(Paragraph(f"Overall tone: {context['overall_tone']}", _BODY))
    motifs = context.get("visual_motifs") or []
    if motifs:
        flow.append(Paragraph("Visual motifs: " + ", ".join(str(m) for m in motifs), _BODY))
    flow.append(Spacer(1, 0.15 * inch))

    for frame in export_data.get("frames", []):
        block: list[Any] = [
            Paragraph(
                f"Scene {frame.get('scene_number', '?')} — Shot {frame.get('shot_number', '?')}",
                _HEADING,
            )
        ]
        for label, key in (
            ("Aspect ratio", "aspect_ratio"),
            ("Composition", "composition_notes"),
            ("Style reference", "style_reference"),
            ("Prompt", "prompt"),
            ("Negative prompt", "negative_prompt"),
        ):
            value = frame.get(key)
            if value:
                block.append(Paragraph(f"<b>{label}:</b> {_escape(value)}", _BODY))
        block.append(Spacer(1, 0.2 * inch))
        flow.append(KeepTogether(block))

    return _render(flow, letter)


def build_analysis_pdf(export_data: dict[str, Any]) -> bytes:
    """Render a scene-analysis export payload as a PDF report."""
    flow = _project_header(export_data, "Script Analysis")

    overall = export_data.get("overall") or {}
    if overall.get("tone"):
        flow.append(Paragraph(f"Overall tone: {overall['tone']}", _BODY))
    motifs = overall.get("visual_motifs") or []
    if motifs:
        flow.append(Paragraph("Visual motifs: " + ", ".join(str(m) for m in motifs), _BODY))
    flow.append(Spacer(1, 0.15 * inch))

    for analysis in export_data.get("scene_analyses", []):
        block: list[Any] = [Paragraph(f"Scene {analysis.get('scene_number', '?')}", _HEADING)]
        for label, key in (
            ("Mood", "mood"),
            ("Pacing", "pacing"),
            ("Visual style", "visual_style"),
            ("Lighting", "lighting_notes"),
        ):
            value = analysis.get(key)
            if value:
                block.append(Paragraph(f"<b>{label}:</b> {_escape(value)}", _BODY))
        themes = analysis.get("themes") or []
        if themes:
            block.append(
                Paragraph("<b>Themes:</b> " + _escape(", ".join(str(t) for t in themes)), _BODY)
            )
        moments = analysis.get("key_moments") or []
        if moments:
            block.append(Paragraph("<b>Key moments:</b>", _BODY))
            for moment in moments:
                block.append(_para(f"• {moment}", _BODY))
        palette = analysis.get("color_palette") or []
        if palette:
            block.append(
                Paragraph(
                    "<b>Color palette:</b> " + _escape(", ".join(str(c) for c in palette)), _BODY
                )
            )
        block.append(Spacer(1, 0.2 * inch))
        flow.append(KeepTogether(block))

    return _render(flow, letter)
