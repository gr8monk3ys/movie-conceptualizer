"""Tests for the Fountain screenplay parser."""

import pytest

from movie_conceptualizer.models import (
    ActionBlock,
    DialogueBlock,
    SceneType,
    Script,
    TimeOfDay,
    Transition,
)
from movie_conceptualizer.parsers import (
    FountainParser,
    detect_format,
    get_script_summary,
    load_text,
    parse_fountain,
    validate_script,
)

# Sample screenplay for testing
SAMPLE_SCREENPLAY = """Title: The Test Script
Credit: Written by
Author: Test Author
Draft date: January 2024

FADE IN:

INT. COFFEE SHOP - DAY

A busy COFFEE SHOP. Patrons sit at small tables. The BARISTA wipes down the counter.

JOHN (30s, disheveled) enters, looking around nervously.

JOHN
(hesitant)
Excuse me, is Sarah here?

BARISTA
Who's asking?

JOHN
I'm an old friend.

The barista gestures to a corner booth.

EXT. PARK - LATER

SARAH (30s, elegant) walks through a peaceful park. Birds sing in the trees.

SARAH
(to herself)
What does he want after all these years?

She sits on a bench, lost in thought.

CUT TO:

INT. SARAH'S APARTMENT - NIGHT

A cozy apartment. SARAH enters and drops her keys on the table.

SARAH (V.O.)
Some memories never fade.

She looks at an old photograph.

FADE OUT.
"""


MINIMAL_SCREENPLAY = """INT. ROOM - DAY

A person sits alone.

PERSON
Hello.
"""


TITLE_PAGE_ONLY = """Title: Empty Script
Author: Nobody

"""


MALFORMED_SCREENPLAY = """
random text here

more random text
not a proper screenplay at all

but we should handle it gracefully
"""


class TestFountainParser:
    """Tests for FountainParser class."""

    def test_parse_returns_script(self):
        """Parser should return a Script object."""
        parser = FountainParser()
        result = parser.parse(SAMPLE_SCREENPLAY)
        assert isinstance(result, Script)

    def test_parse_extracts_title(self):
        """Parser should extract title from title page."""
        parser = FountainParser()
        script = parser.parse(SAMPLE_SCREENPLAY)
        assert script.title == "The Test Script"

    def test_parse_extracts_author(self):
        """Parser should extract author from title page."""
        parser = FountainParser()
        script = parser.parse(SAMPLE_SCREENPLAY)
        assert script.title_page.author == "Test Author"

    def test_parse_extracts_draft_date(self):
        """Parser should extract draft date from title page."""
        parser = FountainParser()
        script = parser.parse(SAMPLE_SCREENPLAY)
        assert script.title_page.draft_date == "January 2024"

    def test_parse_extracts_scenes(self):
        """Parser should extract all scenes."""
        parser = FountainParser()
        script = parser.parse(SAMPLE_SCREENPLAY)
        # Should have 3 scenes: COFFEE SHOP, PARK, SARAH'S APARTMENT
        assert len(script.scenes) == 3

    def test_parse_scene_headings(self):
        """Parser should correctly parse scene headings."""
        parser = FountainParser()
        script = parser.parse(SAMPLE_SCREENPLAY)

        scene1 = script.scenes[0]
        assert scene1.scene_type == SceneType.INTERIOR
        assert "COFFEE SHOP" in scene1.location
        assert scene1.time_of_day == TimeOfDay.DAY

        scene2 = script.scenes[1]
        assert scene2.scene_type == SceneType.EXTERIOR
        assert "PARK" in scene2.location
        assert scene2.time_of_day == TimeOfDay.LATER

        scene3 = script.scenes[2]
        assert scene3.scene_type == SceneType.INTERIOR
        assert "SARAH'S APARTMENT" in scene3.location
        assert scene3.time_of_day == TimeOfDay.NIGHT

    def test_parse_extracts_characters(self):
        """Parser should extract unique characters."""
        parser = FountainParser()
        script = parser.parse(SAMPLE_SCREENPLAY)

        character_names = [c.name for c in script.characters]
        assert "JOHN" in character_names
        assert "SARAH" in character_names
        assert "BARISTA" in character_names

    def test_parse_counts_dialogue(self):
        """Parser should count dialogue per character."""
        parser = FountainParser()
        script = parser.parse(SAMPLE_SCREENPLAY)

        john = script.get_character("JOHN")
        assert john is not None
        assert john.dialogue_count == 2

        sarah = script.get_character("SARAH")
        assert sarah is not None
        assert sarah.dialogue_count == 2  # One regular, one V.O.

    def test_parse_extracts_locations(self):
        """Parser should extract unique locations."""
        parser = FountainParser()
        script = parser.parse(SAMPLE_SCREENPLAY)

        location_names = [loc.name for loc in script.locations]
        assert any("COFFEE SHOP" in name for name in location_names)
        assert any("PARK" in name for name in location_names)
        assert any("SARAH'S APARTMENT" in name for name in location_names)

    def test_parse_extracts_dialogue_content(self):
        """Parser should extract dialogue text."""
        parser = FountainParser()
        script = parser.parse(SAMPLE_SCREENPLAY)

        # Find John's dialogue in first scene
        scene1 = script.scenes[0]
        dialogues = [c for c in scene1.content if isinstance(c, DialogueBlock)]

        john_dialogues = [d for d in dialogues if d.character_name == "JOHN"]
        assert len(john_dialogues) >= 1
        assert "Sarah" in john_dialogues[0].dialogue

    def test_parse_extracts_parentheticals(self):
        """Parser should extract parentheticals."""
        parser = FountainParser()
        script = parser.parse(SAMPLE_SCREENPLAY)

        scene1 = script.scenes[0]
        dialogues = [c for c in scene1.content if isinstance(c, DialogueBlock)]

        # John's first line has (hesitant) parenthetical
        john_dialogue = next((d for d in dialogues if d.character_name == "JOHN"), None)
        assert john_dialogue is not None
        assert john_dialogue.parenthetical == "hesitant"

    def test_parse_extracts_action_blocks(self):
        """Parser should extract action/description blocks."""
        parser = FountainParser()
        script = parser.parse(SAMPLE_SCREENPLAY)

        scene1 = script.scenes[0]
        actions = [c for c in scene1.content if isinstance(c, ActionBlock)]

        assert len(actions) >= 1
        # Check that action contains description
        action_text = " ".join(a.text for a in actions)
        assert "COFFEE SHOP" in action_text or "Patrons" in action_text

    def test_parse_extracts_transitions(self):
        """Parser should extract transitions."""
        parser = FountainParser()
        script = parser.parse(SAMPLE_SCREENPLAY)

        # Find CUT TO: transition
        all_content = []
        for scene in script.scenes:
            all_content.extend(scene.content)

        transitions = [c for c in all_content if isinstance(c, Transition)]
        # The sample screenplay contains a "CUT TO:" transition, so at least
        # one Transition element should be captured during parsing.
        assert len(transitions) >= 1

    def test_parse_character_extension(self):
        """Parser should extract character extensions like V.O."""
        parser = FountainParser()
        script = parser.parse(SAMPLE_SCREENPLAY)

        scene3 = script.scenes[2]
        dialogues = [c for c in scene3.content if isinstance(c, DialogueBlock)]

        vo_dialogue = next((d for d in dialogues if d.character_extension), None)
        assert vo_dialogue is not None
        assert "V.O." in vo_dialogue.character_extension.upper()

    def test_parse_calculates_page_count(self):
        """Parser should calculate approximate page count."""
        parser = FountainParser()
        script = parser.parse(SAMPLE_SCREENPLAY)

        assert script.total_pages > 0
        # This is a short script, should be less than 5 pages
        assert script.total_pages < 5

    def test_parse_scene_numbers(self):
        """Parser should assign sequential scene numbers."""
        parser = FountainParser()
        script = parser.parse(SAMPLE_SCREENPLAY)

        for i, scene in enumerate(script.scenes, start=1):
            assert scene.scene_number == i

    def test_parse_minimal_screenplay(self):
        """Parser should handle minimal valid screenplay."""
        parser = FountainParser()
        script = parser.parse(MINIMAL_SCREENPLAY)

        assert len(script.scenes) == 1
        assert len(script.characters) == 1
        assert script.characters[0].name == "PERSON"

    def test_parse_malformed_input(self):
        """Parser should handle malformed input gracefully."""
        parser = FountainParser()
        script = parser.parse(MALFORMED_SCREENPLAY)

        # Should not raise, should return some result
        assert isinstance(script, Script)
        assert script.title == "Untitled"

    def test_parse_empty_input(self):
        """Parser should handle empty input."""
        parser = FountainParser()
        script = parser.parse("")

        assert isinstance(script, Script)
        assert script.title == "Untitled"
        assert len(script.scenes) == 0

    def test_parse_title_page_only(self):
        """Parser should handle title page with no content."""
        parser = FountainParser()
        script = parser.parse(TITLE_PAGE_ONLY)

        assert script.title == "Empty Script"
        assert script.title_page.author == "Nobody"
        assert len(script.scenes) == 0

    def test_parse_handles_unicode(self):
        """Parser should handle unicode characters."""
        unicode_screenplay = """Title: Test\u2014Unicode

INT. CAF\u00c9 - DAY

\u201cHello,\u201d she said.

MARIE
Bonjour! Comment \u00e7a va?
"""
        parser = FountainParser()
        script = parser.parse(unicode_screenplay)

        assert (
            "CAFE" in script.scenes[0].location.upper()
            or "CAF" in script.scenes[0].location.upper()
        )
        assert script.characters[0].name == "MARIE"

    def test_get_scene_by_number(self):
        """Script should allow getting scene by number."""
        parser = FountainParser()
        script = parser.parse(SAMPLE_SCREENPLAY)

        scene2 = script.get_scene(2)
        assert scene2 is not None
        assert scene2.scene_number == 2
        assert "PARK" in scene2.location

    def test_get_scenes_with_character(self):
        """Script should find scenes containing a character."""
        parser = FountainParser()
        script = parser.parse(SAMPLE_SCREENPLAY)

        sarah_scenes = script.get_scenes_with_character("SARAH")
        assert len(sarah_scenes) == 2  # PARK and SARAH'S APARTMENT

    def test_get_scenes_at_location(self):
        """Script should find scenes at a location."""
        parser = FountainParser()
        script = parser.parse(SAMPLE_SCREENPLAY)

        park_scenes = script.get_scenes_at_location("PARK")
        assert len(park_scenes) == 1


class TestParseFunction:
    """Tests for the parse_fountain convenience function."""

    def test_parse_fountain_function(self):
        """parse_fountain should work like FountainParser.parse."""
        script = parse_fountain(SAMPLE_SCREENPLAY)
        assert isinstance(script, Script)
        assert script.title == "The Test Script"


class TestLoadText:
    """Tests for the load_text function."""

    def test_load_text_parses_fountain(self):
        """load_text should parse Fountain format."""
        script = load_text(SAMPLE_SCREENPLAY)
        assert isinstance(script, Script)
        assert script.title == "The Test Script"

    def test_load_text_with_title_override(self):
        """load_text should allow title override."""
        script = load_text(MINIMAL_SCREENPLAY, title="Override Title")
        # Title should be overridden since original is "Untitled"
        assert script.title == "Override Title"

    def test_load_text_empty_raises(self):
        """load_text should raise on empty input."""
        from movie_conceptualizer.parsers import ScriptLoadError

        with pytest.raises(ScriptLoadError):
            load_text("")

        with pytest.raises(ScriptLoadError):
            load_text("   \n\n   ")


class TestDetectFormat:
    """Tests for format detection."""

    def test_detect_fountain_by_title_page(self):
        """Should detect Fountain by title page fields."""
        text = "Title: My Script\nAuthor: Me\n\nINT. ROOM - DAY"
        assert detect_format(text) == "fountain"

    def test_detect_fountain_by_scene_heading(self):
        """Should detect Fountain by scene headings."""
        text = "INT. ROOM - DAY\n\nAction here."
        assert detect_format(text) == "fountain"

    def test_detect_fountain_by_character_cue(self):
        """Should detect Fountain by character cues."""
        text = "Some action.\n\nJOHN\nHello there."
        assert detect_format(text) == "fountain"

    def test_detect_unknown_format(self):
        """Should return unknown for unrecognized format."""
        text = "this is just plain text\nwith no structure"
        assert detect_format(text) == "unknown"


class TestValidateScript:
    """Tests for script validation."""

    def test_validate_valid_script(self):
        """Valid script should have few or no warnings."""
        script = parse_fountain(SAMPLE_SCREENPLAY)
        warnings = validate_script(script)

        # Should not have critical warnings
        assert not any("No scenes" in w for w in warnings)
        assert not any("No characters" in w for w in warnings)

    def test_validate_empty_script(self):
        """Empty script should generate warnings."""
        script = parse_fountain("")
        warnings = validate_script(script)

        assert any("No scenes" in w for w in warnings)
        assert any("No title" in w for w in warnings)

    def test_validate_short_script(self):
        """Very short script should generate warning."""
        script = parse_fountain(MINIMAL_SCREENPLAY)
        warnings = validate_script(script)

        assert any("short" in w.lower() or "Only" in w for w in warnings)


class TestGetScriptSummary:
    """Tests for script summary generation."""

    def test_summary_contains_basic_info(self):
        """Summary should contain basic script information."""
        script = parse_fountain(SAMPLE_SCREENPLAY)
        summary = get_script_summary(script)

        assert "title" in summary
        assert summary["title"] == "The Test Script"
        assert "scene_count" in summary
        assert summary["scene_count"] == 3
        assert "character_count" in summary
        assert summary["character_count"] >= 3
        assert "total_pages" in summary
        assert summary["total_pages"] > 0

    def test_summary_contains_main_characters(self):
        """Summary should list main characters."""
        script = parse_fountain(SAMPLE_SCREENPLAY)
        summary = get_script_summary(script)

        assert "main_characters" in summary
        assert len(summary["main_characters"]) > 0

    def test_summary_contains_scene_breakdown(self):
        """Summary should contain INT/EXT breakdown."""
        script = parse_fountain(SAMPLE_SCREENPLAY)
        summary = get_script_summary(script)

        assert "interior_scenes" in summary
        assert "exterior_scenes" in summary
        assert summary["interior_scenes"] == 2  # Coffee shop and apartment
        assert summary["exterior_scenes"] == 1  # Park


class TestSceneTypeDetection:
    """Tests for scene type detection."""

    def test_interior_scene(self):
        """Should detect interior scenes."""
        text = "INT. ROOM - DAY\n\nAction."
        script = parse_fountain(text)
        assert script.scenes[0].scene_type == SceneType.INTERIOR

    def test_exterior_scene(self):
        """Should detect exterior scenes."""
        text = "EXT. STREET - NIGHT\n\nAction."
        script = parse_fountain(text)
        assert script.scenes[0].scene_type == SceneType.EXTERIOR

    def test_interior_exterior_scene(self):
        """Should detect INT/EXT scenes."""
        text = "INT./EXT. CAR - DAY\n\nAction."
        script = parse_fountain(text)
        assert script.scenes[0].scene_type == SceneType.INTERIOR_EXTERIOR

    def test_ie_abbreviation(self):
        """Should detect I/E abbreviation."""
        text = "I/E. DOORWAY - DAY\n\nAction."
        script = parse_fountain(text)
        assert script.scenes[0].scene_type == SceneType.INTERIOR_EXTERIOR


class TestTimeOfDayDetection:
    """Tests for time of day detection."""

    def test_day_detection(self):
        """Should detect DAY time."""
        text = "INT. ROOM - DAY\n\nAction."
        script = parse_fountain(text)
        assert script.scenes[0].time_of_day == TimeOfDay.DAY

    def test_night_detection(self):
        """Should detect NIGHT time."""
        text = "INT. ROOM - NIGHT\n\nAction."
        script = parse_fountain(text)
        assert script.scenes[0].time_of_day == TimeOfDay.NIGHT

    def test_dawn_detection(self):
        """Should detect DAWN time."""
        text = "EXT. FIELD - DAWN\n\nAction."
        script = parse_fountain(text)
        assert script.scenes[0].time_of_day == TimeOfDay.DAWN

    def test_continuous_detection(self):
        """Should detect CONTINUOUS time."""
        text = "INT. HALLWAY - CONTINUOUS\n\nAction."
        script = parse_fountain(text)
        assert script.scenes[0].time_of_day == TimeOfDay.CONTINUOUS

    def test_later_detection(self):
        """Should detect LATER time."""
        text = "INT. ROOM - LATER\n\nAction."
        script = parse_fountain(text)
        assert script.scenes[0].time_of_day == TimeOfDay.LATER


class TestForcedElements:
    """Tests for forced Fountain elements (prefixed with special characters)."""

    def test_forced_scene_heading(self):
        """Should handle forced scene headings with period prefix."""
        text = ".FLASHBACK\n\nAction in flashback."
        script = parse_fountain(text)
        assert len(script.scenes) == 1
        assert "FLASHBACK" in script.scenes[0].heading

    def test_forced_character(self):
        """Should handle forced character with @ prefix."""
        text = """INT. ROOM - DAY

Action.

@McCLANE
Yippee ki-yay!
"""
        script = parse_fountain(text)
        assert any(c.name == "McCLANE" for c in script.characters)


class TestDualDialogue:
    """Tests for dual dialogue detection."""

    def test_dual_dialogue_marker(self):
        """Should detect dual dialogue marker (^)."""
        text = """INT. ROOM - DAY

JOHN
Hello!

MARY ^
Hi there!
"""
        script = parse_fountain(text)
        scene = script.scenes[0]
        dialogues = [c for c in scene.content if isinstance(c, DialogueBlock)]

        # Mary's dialogue should be marked as dual
        mary_dialogue = next((d for d in dialogues if d.character_name == "MARY"), None)
        assert mary_dialogue is not None
        assert mary_dialogue.is_dual_dialogue


class TestBoneyardRemoval:
    """Tests for boneyard (comment) removal."""

    def test_boneyard_removed(self):
        """Should remove boneyard comments."""
        text = """INT. ROOM - DAY

/* This is a comment
that spans multiple lines */

JOHN
Hello!
"""
        script = parse_fountain(text)
        scene = script.scenes[0]

        # Comment should not appear in content
        raw_text = scene.raw_text
        assert "This is a comment" not in raw_text


class TestCharacterSceneAppearances:
    """Tests for character scene appearance tracking."""

    def test_character_scene_appearances(self):
        """Should track which scenes characters appear in."""
        script = parse_fountain(SAMPLE_SCREENPLAY)

        sarah = script.get_character("SARAH")
        assert sarah is not None
        assert 2 in sarah.scene_appearances  # PARK scene
        assert 3 in sarah.scene_appearances  # SARAH'S APARTMENT

    def test_character_first_appearance(self):
        """Should track first appearance scene."""
        script = parse_fountain(SAMPLE_SCREENPLAY)

        john = script.get_character("JOHN")
        assert john is not None
        assert john.first_appearance == 1  # Coffee shop scene


class TestLocationSceneAppearances:
    """Tests for location scene tracking."""

    def test_location_scene_appearances(self):
        """Should track which scenes use each location."""
        script = parse_fountain(SAMPLE_SCREENPLAY)

        # Find coffee shop location
        coffee_shop = next((loc for loc in script.locations if "COFFEE" in loc.name.upper()), None)
        assert coffee_shop is not None
        assert 1 in coffee_shop.scene_appearances
