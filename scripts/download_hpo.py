#!/usr/bin/env python3
"""
Download HPO ontology (hp.json) from PURL into data/. MVP Phase 1: hp.json only.
Idempotent: skips download if file exists (optional: skip if recent).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import httpx
except ImportError:
    print("Install httpx: pip install httpx", file=sys.stderr)
    sys.exit(1)

HPO_JSON_URL = "https://purl.obolibrary.org/obo/hp.json"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"


def download_hpo(
    output_dir: Path | str | None = None,
    output_name: str = "hp.json",
    force: bool = False,
    skip_if_newer_than_hours: float | None = None,
) -> Path:
    output_dir = Path(output_dir or DEFAULT_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / output_name

    if not force and out_path.exists():
        if skip_if_newer_than_hours is not None:
            import time
            age_hours = (time.time() - out_path.stat().st_mtime) / 3600
            if age_hours < skip_if_newer_than_hours:
                print(f"Skip: {out_path} is {age_hours:.1f}h old (< {skip_if_newer_than_hours}h)")
                return out_path
        print(f"Exists: {out_path} (use --force to re-download)")
        return out_path

    print(f"Downloading {HPO_JSON_URL} -> {out_path}")
    with httpx.stream("GET", HPO_JSON_URL, follow_redirects=True) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
    print(f"Saved {out_path} ({out_path.stat().st_size:,} bytes)")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Download HPO hp.json into data/")
    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--output-name",
        default="hp.json",
        help="Output filename (default: hp.json)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if file exists",
    )
    parser.add_argument(
        "--skip-if-newer-than",
        type=float,
        metavar="HOURS",
        default=None,
        help="Skip download if existing file is newer than this many hours",
    )
    args = parser.parse_args()
    download_hpo(
        output_dir=args.output_dir,
        output_name=args.output_name,
        force=args.force,
        skip_if_newer_than_hours=args.skip_if_newer_than,
    )


if __name__ == "__main__":
    main()
