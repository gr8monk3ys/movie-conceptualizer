#!/usr/bin/env python3
"""Download a sample screenplay file to use in demos.

This is intentionally minimal: it only accepts .fountain/.fdx/.txt URLs and
writes the file to a destination path you choose.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ALLOWED_EXTENSIONS = {".fountain", ".fdx", ".txt"}


def _ext_from_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or ""
    return Path(path).suffix.lower()


def download(url: str, dest: Path, timeout: int = 20) -> None:
    req = Request(url, headers={"User-Agent": "movie-conceptualizer-demo/1.0"})
    with urlopen(req, timeout=timeout) as resp:  # nosec - URL provided by user
        data = resp.read()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download a sample .fountain/.fdx/.txt screenplay for demos."
    )
    parser.add_argument("url", help="Direct URL to a .fountain/.fdx/.txt file")
    parser.add_argument(
        "-o",
        "--out",
        default="examples/sample_downloaded.fountain",
        help="Destination path (default: examples/sample_downloaded.fountain)",
    )
    parser.add_argument(
        "--allow-unknown-ext",
        action="store_true",
        help="Allow URLs without recognized extensions (use with care).",
    )
    args = parser.parse_args()

    ext = _ext_from_url(args.url)
    if ext not in ALLOWED_EXTENSIONS and not args.allow_unknown_ext:
        print(
            "Error: URL must end with .fountain, .fdx, or .txt "
            f"(got '{ext or 'none'}').",
            file=sys.stderr,
        )
        return 2

    dest = Path(args.out)
    download(args.url, dest)
    print(f"Downloaded to {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
