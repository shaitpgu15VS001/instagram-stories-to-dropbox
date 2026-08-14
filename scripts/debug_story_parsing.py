#!/usr/bin/env python3
"""Debug script to check what parse_stories returns."""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.fastdl_api import FastDLStoriesAPI

api = FastDLStoriesAPI()
stories = api.fetch_stories("israel_bidur", timeout=30)

if stories:
    print(f"Success! Got {len(stories)} stories")
    print("\nFirst story keys:")
    if len(stories) > 0:
        first = stories[0]
        print(f"Type: {type(first)}")
        if isinstance(first, dict):
            print(f"Keys: {list(first.keys())}")
            # Check for image/video URLs
            if 'image_versions2' in first:
                print(f"  image_versions2: {type(first['image_versions2'])}")
                if isinstance(first['image_versions2'], dict):
                    print(f"    sub-keys: {list(first['image_versions2'].keys())}")
                    if 'candidates' in first['image_versions2']:
                        print(f"    candidates count: {len(first['image_versions2']['candidates'])}")
            if 'video_versions' in first:
                print(f"  video_versions: type={type(first['video_versions'])}, count={len(first['video_versions']) if isinstance(first['video_versions'], list) else 'N/A'}")
            if 'u' in first:
                print(f"  u (username): {first['u']}")
            if 'kind' in first:
                print(f"  kind: {first['kind']}")
        
        print(f"\nFull first story (first 1000 chars):")
        print(json.dumps(first, indent=2, ensure_ascii=False)[:1000])
else:
    print("ERROR: parse_stories returned None")
