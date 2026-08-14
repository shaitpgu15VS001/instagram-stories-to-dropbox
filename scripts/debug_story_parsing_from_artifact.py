#!/usr/bin/env python3
"""Load a captured Stories JSON artifact and run FastDLStoriesAPI.parse_stories()

Usage:
  python scripts/debug_story_parsing_from_artifact.py [path/to/stories_response.json]

If no path provided, defaults to the run3 artifact used in earlier investigation.
"""
import sys
import os
import json
from pathlib import Path

DEFAULT = Path(__file__).resolve().parent / "debug_output" / "fastdl_media_test" / "run3" / "stories_response.json"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.fastdl_api import FastDLStoriesAPI


def load_artifact(p: Path):
    data = json.loads(p.read_text(encoding="utf-8"))
    # artifact may embed the actual API body in .stories_response.body_text
    if isinstance(data, dict) and data.get("stories_response"):
        sr = data.get("stories_response")
        # prefer full body_text if present
        body = sr.get("body_text") or sr.get("body_text_sample") or sr.get("body")
        if body and isinstance(body, str):
            try:
                return json.loads(body)
            except Exception:
                # body_text may be already truncated; fall back to stored top-level 'stories_response' dict
                return sr
    # fallback: assume file contains the raw API payload
    return data


def main(argv=None):
    p = Path(argv[0]) if argv else DEFAULT
    if not p.exists():
        print(f"Artifact not found: {p}")
        return 2

    payload = load_artifact(p)
    api = FastDLStoriesAPI()

    print(f"Loaded artifact: {p}")
    print(f"Top-level type: {type(payload)}")

    items = api.parse_stories(payload)

    if items is None:
        print("parse_stories() returned None")
        return 1

    total = len(items)
    print(f"parse_stories() returned {total} normalized items")

    usable = 0
    for idx, it in enumerate(items[:10], 1):
        print(f"\nItem #{idx} normalized keys: {list(it.keys())}")
        u = it.get('u')
        raw = it.get('raw')
        print(f"  u present: {bool(u)}")
        if u:
            print(f"  u: {u}")
            usable += 1
        print("  raw sample keys:", list(raw.keys()) if isinstance(raw, dict) else type(raw))

    print(f"\nUsable items with 'u': {usable} / {total}")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
