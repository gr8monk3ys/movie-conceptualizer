"""Round-trip tests for shot persistence.

Guards the seam between `api.schemas.ShotData` and the storage-layer
`ShotData`: `save_shots` serializes whatever model it is given, and
`get_shots` re-validates into the storage model — any field missing from
the storage model is silently dropped on read.
"""

import os
import tempfile

import pytest

from movie_conceptualizer.storage import Database, GenerationRepository, ProjectRepository
from movie_conceptualizer.storage.repositories import ShotData


@pytest.fixture
async def db_and_project():
    """Create a temporary database with one project."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(os.path.join(tmpdir, "test.db"))
        await db.initialize()
        project = await ProjectRepository(db).create(title="Shot Round-Trip", description="fixture")
        yield db, project
        await db.close()


FULL_SHOT_FIELDS = {
    "scene_number": 1,
    "shot_number": "1A",
    "shot_type": "wide",
    "camera_movement": "static",
    "camera_angle": "eye_level",
    "description": "Establishing shot of the lab",
    "duration_seconds": 4.5,
    "characters": ["ADA"],
    "dialogue": "It works.",
    "action": "The robot powers on.",
    "notes": "Hold for two beats",
    "framing_notes": "Symmetrical, door center frame",
    "lens_suggestion": "24mm",
}


@pytest.mark.asyncio
async def test_storage_shot_round_trip_preserves_all_fields(db_and_project):
    db, project = db_and_project
    repo = GenerationRepository(db)

    await repo.save_shots(project.id, [ShotData(**FULL_SHOT_FIELDS)], style="noir")
    loaded = await repo.get_shots(project.id)

    assert len(loaded) == 1
    assert loaded[0].model_dump() == ShotData(**FULL_SHOT_FIELDS).model_dump()


@pytest.mark.asyncio
async def test_api_shot_round_trip_preserves_all_fields(db_and_project):
    """Shots saved through the API schema must survive a storage read."""
    # Lazy import: api modules must not be imported at test-module level
    # (see the test-ordering contract in CLAUDE.md).
    from movie_conceptualizer.api import schemas

    db, project = db_and_project
    repo = GenerationRepository(db)

    api_shot = schemas.ShotData(
        shot_number="1A",
        scene_number=1,
        shot_type="wide",
        camera_movement="static",
        description="Establishing shot of the lab",
        duration_seconds=4.5,
        characters=["ADA"],
        dialogue="It works.",
        action="The robot powers on.",
        notes="Hold for two beats",
        framing_notes="Symmetrical, door center frame",
        lens_suggestion="24mm",
    )

    await repo.save_shots(project.id, [api_shot], style="noir")  # type: ignore[list-item]
    loaded = await repo.get_shots(project.id)

    assert len(loaded) == 1
    stored = loaded[0]
    assert stored.dialogue == "It works."
    assert stored.action == "The robot powers on."
    assert stored.framing_notes == "Symmetrical, door center frame"
    assert stored.lens_suggestion == "24mm"
    assert stored.notes == "Hold for two beats"
