"""Tests for PDF export: the builders and the export endpoints.

The endpoint tests override the project-store dependency with a stub project
so they exercise the full route (auth-optional, payload assembly, PDF
rendering, headers) without needing the AI pipeline to have run.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

# NOTE: movie_conceptualizer.api modules are imported lazily inside fixtures
# and tests, and this file is named so it sorts AFTER test_jobs_admin.py.
# Several api modules freeze configuration from environment variables at
# import time, and test_jobs_admin relies on being the first to import them
# (with its own env applied via importlib.reload). Importing the api here at
# collection time, or running these tests first, would break that suite —
# the same ordering contract test_production_features.py already follows.

SHOT_LIST_DATA = {
    "project": {"id": "p1", "title": "Test <Movie> & Co", "genre": "thriller"},
    "shots": [
        {
            "scene_number": 1,
            "shot_number": "1A",
            "shot_type": "wide",
            "camera_movement": "static",
            "duration_seconds": 3.5,
            "description": "Establishing wide of the warehouse, rain streaking the skylights.",
            "notes": "Hold for titles",
        },
        {
            "scene_number": 1,
            "shot_number": "1B",
            "shot_type": "close_up",
            "camera_movement": "push_in",
            "duration_seconds": 2.0,
            "description": "Close on the ledger; <markup> & ampersands must not break rendering.",
            "notes": None,
        },
    ],
    "summary": {"total_shots": 2, "scenes_covered": 1, "estimated_duration_minutes": 0.09},
}

STORYBOARD_DATA = {
    "project": {"id": "p1", "title": "Test Movie"},
    "frames": [
        {
            "scene_number": 1,
            "shot_number": "1A",
            "aspect_ratio": "16:9",
            "composition_notes": "Rule of thirds, subject left",
            "style_reference": "noir",
            "prompt": "Wide shot of a rain-soaked warehouse interior, volumetric light",
            "negative_prompt": "blurry, text",
        }
    ],
    "summary": {"total_frames": 1, "scenes_covered": 1},
    "context": {"overall_tone": "tense", "visual_motifs": ["rain", "neon"]},
}

ANALYSIS_DATA = {
    "project": {"id": "p1", "title": "Test Movie", "genre": "thriller"},
    "overall": {"tone": "tense", "visual_motifs": ["rain"]},
    "scene_analyses": [
        {
            "scene_number": 1,
            "mood": "foreboding",
            "themes": ["betrayal", "loss"],
            "visual_style": "low-key noir",
            "pacing": "building",
            "key_moments": ["the ledger is discovered", "footsteps overhead"],
            "color_palette": ["teal", "amber"],
            "lighting_notes": "single practical source",
        }
    ],
    "summary": {"scenes_analyzed": 1},
}


class TestPdfBuilders:
    def test_shot_list_pdf(self) -> None:
        from movie_conceptualizer.api.pdf_export import build_shot_list_pdf

        pdf = build_shot_list_pdf(SHOT_LIST_DATA)
        assert pdf.startswith(b"%PDF")
        assert len(pdf) > 1000

    def test_storyboard_pdf(self) -> None:
        from movie_conceptualizer.api.pdf_export import build_storyboard_pdf

        pdf = build_storyboard_pdf(STORYBOARD_DATA)
        assert pdf.startswith(b"%PDF")

    def test_analysis_pdf(self) -> None:
        from movie_conceptualizer.api.pdf_export import build_analysis_pdf

        pdf = build_analysis_pdf(ANALYSIS_DATA)
        assert pdf.startswith(b"%PDF")

    def test_empty_payloads_still_render(self) -> None:
        from movie_conceptualizer.api.pdf_export import (
            build_analysis_pdf,
            build_shot_list_pdf,
            build_storyboard_pdf,
        )

        for builder in (build_shot_list_pdf, build_storyboard_pdf, build_analysis_pdf):
            pdf = builder({"project": {"title": "Empty"}})
            assert pdf.startswith(b"%PDF")


def _stub_project() -> SimpleNamespace:
    shot = SimpleNamespace(
        shot_number="1A",
        scene_number=1,
        shot_type="wide",
        camera_movement="static",
        description="Establishing wide.",
        duration_seconds=3.0,
        notes="hold",
    )
    prompt = SimpleNamespace(
        shot_number="1A",
        scene_number=1,
        aspect_ratio="16:9",
        composition_notes="thirds",
        style_reference="noir",
        prompt="wide shot",
        negative_prompt="blurry",
    )
    analysis = SimpleNamespace(
        scene_number=1,
        mood="tense",
        themes=["loss"],
        visual_style="noir",
        pacing="building",
        key_moments=["reveal"],
        color_palette=["teal"],
        lighting_notes="low key",
    )
    return SimpleNamespace(
        id="proj-1",
        title="Stub Movie",
        genre="thriller",
        style_notes=None,
        user_id=None,
        shots=[shot],
        storyboard_prompts=[prompt],
        analyses=[analysis],
        overall_tone="tense",
        visual_motifs=["rain"],
    )


class _StubStore:
    async def get(self, project_id: str) -> SimpleNamespace | None:
        return _stub_project() if project_id == "proj-1" else None


@pytest.fixture
def client():  # type: ignore[no-untyped-def]
    from fastapi.testclient import TestClient

    from movie_conceptualizer.api.main import app

    # Key the overrides by the exact callables the export routes captured at
    # import time (via the routes module), and stub auth as disabled so these
    # tests are independent of any auth state other suites bake into module
    # constants via importlib.reload.
    from movie_conceptualizer.api.routes import export as export_routes

    overrides = {
        export_routes.get_project_store: lambda: _StubStore(),
        export_routes.require_auth_if_enabled: lambda: None,
    }
    app.dependency_overrides.update(overrides)
    try:
        yield TestClient(app)
    finally:
        for key in overrides:
            app.dependency_overrides.pop(key, None)


class TestExportEndpoints:
    @pytest.mark.parametrize("kind", ["shotlist", "storyboard", "analysis"])
    def test_pdf_export(self, client, kind: str) -> None:  # type: ignore[no-untyped-def]
        response = client.get(f"/api/v1/projects/proj-1/export/{kind}?format=pdf")
        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "application/pdf"
        assert "attachment" in response.headers["content-disposition"]
        assert response.content.startswith(b"%PDF")

    @pytest.mark.parametrize("kind", ["shotlist", "storyboard", "analysis"])
    def test_json_export_still_works(self, client, kind: str) -> None:  # type: ignore[no-untyped-def]
        response = client.get(f"/api/v1/projects/proj-1/export/{kind}?format=json")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["format"] == "json"
        assert "not yet implemented" not in str(body)

    def test_pdf_export_missing_project_404(self, client) -> None:  # type: ignore[no-untyped-def]
        response = client.get("/api/v1/projects/nope/export/shotlist?format=pdf")
        assert response.status_code == 404
