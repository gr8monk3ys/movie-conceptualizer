#!/usr/bin/env python3
"""Build a previs prompt pack from storyboard exports."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def load_frames(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("Unexpected storyboard format")
    payload = data.get("data") or {}
    frames = payload.get("frames") or []
    if not isinstance(frames, list):
        raise ValueError("Storyboard frames missing or invalid")
    return frames


def normalize_frame(frame: dict[str, Any]) -> dict[str, Any]:
    return {
        "shot_number": frame.get("shot_number"),
        "scene_number": frame.get("scene_number"),
        "aspect_ratio": frame.get("aspect_ratio"),
        "composition_notes": frame.get("composition_notes"),
        "style_reference": frame.get("style_reference"),
        "prompt": frame.get("prompt"),
        "negative_prompt": frame.get("negative_prompt"),
    }


def write_json(path: Path, rows: list[dict[str, Any]]) -> None:
    payload = {
        "format": "previs_prompt_pack_v1",
        "count": len(rows),
        "items": rows,
    }
    path.write_text(json.dumps(payload, indent=2))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "shot_number",
        "scene_number",
        "aspect_ratio",
        "composition_notes",
        "style_reference",
        "prompt",
        "negative_prompt",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--storyboard",
        type=Path,
        default=Path("output/storyboard.json"),
        help="Path to storyboard export JSON",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=Path("output/previs_prompts.json"),
        help="Output JSON prompt pack",
    )
    parser.add_argument(
        "--out-csv",
        type=Path,
        default=Path("output/previs_prompts.csv"),
        help="Output CSV prompt pack",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max number of prompts to emit (0 = all)",
    )
    args = parser.parse_args()

    frames = load_frames(args.storyboard)
    rows = [normalize_frame(frame) for frame in frames]
    if args.limit:
        rows = rows[: args.limit]

    write_json(args.out_json, rows)
    write_csv(args.out_csv, rows)


if __name__ == "__main__":
    main()
