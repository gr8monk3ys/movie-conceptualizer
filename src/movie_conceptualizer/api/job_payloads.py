"""Job payload schemas and helpers."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field


class AnalysisJobPayload(BaseModel):
    scene_numbers: list[int] | None = Field(default=None)


class ShotsJobPayload(BaseModel):
    scene_numbers: list[int] | None = Field(default=None)
    style: str | None = Field(default=None)
    shots_per_scene: int | None = Field(default=None, ge=1, le=50)


class StoryboardJobPayload(BaseModel):
    scene_numbers: list[int] | None = Field(default=None)
    style: str | None = Field(default=None)
    aspect_ratio: str = Field(default="16:9")


class PipelineJobPayload(BaseModel):
    scene_numbers: list[int] | None = Field(default=None)
    style: str | None = Field(default=None)
    skip_analysis: bool = Field(default=False)
    skip_shots: bool = Field(default=False)
    skip_storyboard: bool = Field(default=False)


def encode_payload(payload: BaseModel) -> str:
    return payload.model_dump_json()


def decode_payload(payload: str | None) -> dict[str, Any]:
    if not payload:
        return {}
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return {}
