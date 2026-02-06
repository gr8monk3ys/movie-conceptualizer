#!/usr/bin/env python3
"""Generate pre-vis images from a storyboard prompt pack using OpenAI Images API."""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx


ENV_FILE_CANDIDATES = (".env",)


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        os.environ.setdefault(key, value)


def load_env() -> None:
    for candidate in ENV_FILE_CANDIDATES:
        load_env_file(Path(candidate))


def sanitize_token(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", value)
    return cleaned.strip("_") or "shot"


def load_prompt_pack(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text())
    if isinstance(data, dict) and "items" in data:
        items = data["items"]
    else:
        items = data
    if not isinstance(items, list):
        raise ValueError("Prompt pack must contain a list of items")
    return items


def build_prompt(item: dict[str, Any]) -> str:
    prompt = item.get("prompt") or item.get("image_prompt") or ""
    composition = item.get("composition_notes")
    aspect = item.get("aspect_ratio")
    negative = item.get("negative_prompt")

    parts = [prompt.strip()]
    if composition:
        parts.append(f"Composition: {composition.strip()}")
    if aspect:
        parts.append(f"Aspect ratio: {aspect.strip()}")
    if negative:
        parts.append(f"Avoid: {negative.strip()}")

    return "\n".join(p for p in parts if p)


def fetch_image(
    client: httpx.Client,
    api_key: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    response = client.post(
        "https://api.openai.com/v1/images/generations",
        headers=headers,
        json=payload,
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def save_image_bytes(path: Path, image_bytes: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(image_bytes)


def download_url(client: httpx.Client, url: str) -> bytes:
    resp = client.get(url, timeout=120)
    resp.raise_for_status()
    return resp.content


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--prompts",
        type=Path,
        default=Path("output/previs_prompts.json"),
        help="Prompt pack JSON file",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("output/previs_frames"),
        help="Directory to save generated images",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("output/previs_manifest.json"),
        help="Output manifest JSON file",
    )
    parser.add_argument("--limit", type=int, default=0, help="Limit shots processed")
    parser.add_argument("--start", type=int, default=0, help="Start index")
    parser.add_argument("--sleep", type=float, default=0.0, help="Sleep between calls")
    parser.add_argument(
        "--model",
        default=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1"),
        help="OpenAI image model name",
    )
    parser.add_argument(
        "--size",
        default=os.getenv("OPENAI_IMAGE_SIZE", "1536x1024"),
        help="Image size (e.g., 1024x1024, 1536x1024)",
    )
    parser.add_argument(
        "--quality",
        default=os.getenv("OPENAI_IMAGE_QUALITY", "high"),
        help="Image quality (low, medium, high, auto)",
    )
    parser.add_argument(
        "--background",
        default=os.getenv("OPENAI_IMAGE_BACKGROUND", "opaque"),
        help="Background (opaque or transparent)",
    )
    parser.add_argument(
        "--output-format",
        default=os.getenv("OPENAI_IMAGE_OUTPUT_FORMAT", "png"),
        help="Output format (png, jpeg, webp)",
    )
    parser.add_argument(
        "--output-compression",
        type=int,
        default=int(os.getenv("OPENAI_IMAGE_OUTPUT_COMPRESSION", "0")),
        help="Output compression for jpeg/webp (0-100)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print prompts without calling the API",
    )
    args = parser.parse_args()

    load_env()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key and not args.dry_run:
        raise SystemExit("OPENAI_API_KEY is not set")

    items = load_prompt_pack(args.prompts)
    items = items[args.start :]
    if args.limit:
        items = items[: args.limit]

    manifest: list[dict[str, Any]] = []

    with httpx.Client() as client:
        for idx, item in enumerate(items, start=1 + args.start):
            prompt = build_prompt(item)
            if not prompt:
                continue

            scene_number = item.get("scene_number") or 0
            shot_number = str(item.get("shot_number") or f"shot_{idx}")
            shot_token = sanitize_token(shot_number)
            filename = f"scene_{int(scene_number):03d}_shot_{shot_token}.{args.output_format}"
            out_path = args.out_dir / filename

            record = {
                "index": idx,
                "scene_number": scene_number,
                "shot_number": shot_number,
                "prompt": prompt,
                "output_path": str(out_path),
                "model": args.model,
                "size": args.size,
                "quality": args.quality,
                "background": args.background,
                "output_format": args.output_format,
            }

            if args.dry_run:
                manifest.append({**record, "status": "dry_run"})
                print(f"[dry-run] {shot_number}: {prompt[:80]}...")
                continue

            payload: dict[str, Any] = {
                "model": args.model,
                "prompt": prompt,
                "size": args.size,
                "quality": args.quality,
                "background": args.background,
                "output_format": args.output_format,
            }
            if args.output_format in {"jpeg", "webp"} and args.output_compression > 0:
                payload["output_compression"] = args.output_compression

            response = fetch_image(client, api_key, payload)
            images = response.get("data") or []
            if not images:
                manifest.append({**record, "status": "empty"})
                continue

            image = images[0]
            if "b64_json" in image:
                image_bytes = base64.b64decode(image["b64_json"])
            elif "url" in image:
                image_bytes = download_url(client, image["url"])
            else:
                manifest.append({**record, "status": "unknown_format"})
                continue

            save_image_bytes(out_path, image_bytes)
            manifest.append({**record, "status": "ok"})

            if args.sleep:
                time.sleep(args.sleep)

    args.manifest.write_text(json.dumps({"items": manifest}, indent=2))


if __name__ == "__main__":
    main()
