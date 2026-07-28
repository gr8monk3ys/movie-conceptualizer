"""Tests for the FDX (Final Draft) parser."""

import pytest

from movie_conceptualizer.models import DialogueBlock
from movie_conceptualizer.parsers.fdx_parser import FDXParseError, parse_fdx

MINIMAL_FDX = """<?xml version="1.0" encoding="UTF-8"?>
<FinalDraft DocumentType="Script" Template="No" Version="5">
  <Content>
    <Paragraph Type="Scene Heading"><Text>INT. LAB - NIGHT</Text></Paragraph>
    <Paragraph Type="Action"><Text>A robot hums quietly.</Text></Paragraph>
    <Paragraph Type="Character"><Text>Ada</Text></Paragraph>
    <Paragraph Type="Parenthetical"><Text>(cheerful)</Text></Paragraph>
    <Paragraph Type="Dialogue"><Text>It works.</Text></Paragraph>
    <Paragraph Type="Action"><Text>She smiles.</Text></Paragraph>
    <Paragraph Type="Character"><Text>Boris</Text></Paragraph>
    <Paragraph Type="Dialogue"><Text>Of course it does.</Text></Paragraph>
  </Content>
</FinalDraft>
"""


def _dialogue_blocks(script):
    return [
        element
        for scene in script.scenes
        for element in scene.content
        if isinstance(element, DialogueBlock)
    ]


def test_parse_fdx_preserves_dialogue_and_characters():
    script = parse_fdx(MINIMAL_FDX)

    assert len(script.scenes) == 1
    names = {c.name for c in script.characters}
    assert names == {"ADA", "BORIS"}

    dialogue = _dialogue_blocks(script)
    assert len(dialogue) == 2
    assert dialogue[0].character_name == "ADA"
    assert "It works." in dialogue[0].dialogue
    assert dialogue[1].character_name == "BORIS"
    assert "Of course it does." in dialogue[1].dialogue


def test_parse_fdx_parenthetical_not_double_wrapped():
    script = parse_fdx(MINIMAL_FDX)

    dialogue = _dialogue_blocks(script)
    parentheticals = [d.parenthetical for d in dialogue if d.parenthetical]
    assert parentheticals == ["cheerful"]


def test_parse_fdx_unwrapped_parenthetical_text():
    fdx = MINIMAL_FDX.replace("(cheerful)", "cheerful")
    script = parse_fdx(fdx)

    dialogue = _dialogue_blocks(script)
    parentheticals = [d.parenthetical for d in dialogue if d.parenthetical]
    assert parentheticals == ["cheerful"]


def test_parse_fdx_sets_format_metadata():
    script = parse_fdx(MINIMAL_FDX)
    assert script.format_type == "fdx"


def test_parse_fdx_invalid_xml_raises():
    with pytest.raises(FDXParseError, match="Invalid FDX XML"):
        parse_fdx("not xml at all <")


def test_parse_fdx_missing_content_raises():
    with pytest.raises(FDXParseError, match="content section"):
        parse_fdx("<FinalDraft></FinalDraft>")
