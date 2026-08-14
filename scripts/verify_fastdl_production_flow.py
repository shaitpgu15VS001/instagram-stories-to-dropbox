#!/usr/bin/env python3
"""
Test script to verify the fixed production flow in src/fastdl_api.py.

Purpose: Verify that the Stories tab click fix enables successful Stories API retrieval.
Usage: python scripts/verify_fastdl_production_flow.py
"""

import sys
import os
import json
import time
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.fastdl_api import FastDLStoriesAPI


def run_test_flow(username: str, run_id: int = 1) -> dict:
    """Run the production flow and capture detailed metrics."""
    
    print(f"\n{'='*80}")
    print(f"PRODUCTION FLOW TEST - Run {run_id}")
    print(f"Username: {username}")
    print(f"Start time: {datetime.now().isoformat()}")
    print(f"{'='*80}\n")
    
    start_time = time.time()
    result = {
        "run_id": run_id,
        "username": username,
        "start_time": datetime.now().isoformat(),
        "success": False,
        "failure_reason": None,
        "duration_seconds": None,
        "story_count": 0,
        "media_url_count": 0,
        "stories": None,
    }
    
    try:
        api = FastDLStoriesAPI()
        print(f"[1/3] Initializing FastDLStoriesAPI...")
        
        print(f"[2/3] Calling fetch_stories('{username}')...")
        stories = api.fetch_stories(username, timeout=30)
        
        if stories is None:
            result["failure_reason"] = "API returned None"
            result["success"] = False
            print(f"[!] ERROR: API returned None")
        else:
            result["success"] = True
            result["stories"] = stories
            result["story_count"] = len(stories)
            
            # Count media URLs
            media_url_count = 0
            for story in stories:
                if isinstance(story, dict):
                    # Count all URLs in story (image_versions2, video_versions, etc.)
                    if "image_versions2" in story and isinstance(story["image_versions2"], dict):
                        candidates = story["image_versions2"].get("candidates", [])
                        if isinstance(candidates, list):
                            media_url_count += len(candidates)
                    if "video_versions" in story and isinstance(story["video_versions"], list):
                        media_url_count += len(story["video_versions"])
            
            result["media_url_count"] = media_url_count
            
            print(f"[3/3] Parsing complete")
            print(f"[✓] SUCCESS")
            print(f"    - Stories: {result['story_count']}")
            print(f"    - Media URLs: {result['media_url_count']}")
    
    except Exception as exc:
        result["success"] = False
        result["failure_reason"] = f"{type(exc).__name__}: {str(exc)}"
        print(f"[✗] EXCEPTION: {type(exc).__name__}")
        print(f"    Message: {str(exc)}")
    
    finally:
        duration = time.time() - start_time
        result["duration_seconds"] = round(duration, 2)
        result["end_time"] = datetime.now().isoformat()
    
    print(f"\nDuration: {result['duration_seconds']}s")
    print(f"End time: {result['end_time']}")
    
    return result


def main():
    """Run verification tests."""
    
    print("\n" + "="*80)
    print("FASTDL PRODUCTION FLOW VERIFICATION")
    print("Testing fixed src/fastdl_api.py with Stories tab click")
    print("="*80)
    
    username = "israel_bidur"
    results = []
    
    # Run twice as per requirements
    for run_id in [1, 2]:
        result = run_test_flow(username, run_id=run_id)
        results.append(result)
        
        # Small delay between runs
        if run_id == 1:
            print("\nWaiting 3 seconds before second run...")
            time.sleep(3)
    
    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}\n")
    
    for result in results:
        run_label = f"Run {result['run_id']}"
        status = "✓ PASS" if result["success"] else "✗ FAIL"
        print(f"{run_label}: {status}")
        print(f"  Duration: {result['duration_seconds']}s")
        print(f"  Stories: {result['story_count']}")
        print(f"  Media URLs: {result['media_url_count']}")
        if result["failure_reason"]:
            print(f"  Error: {result['failure_reason']}")
        print()
    
    # Overall result
    all_passed = all(r["success"] for r in results)
    print(f"Overall result: {'✓ ALL TESTS PASSED' if all_passed else '✗ SOME TESTS FAILED'}")
    
    # Save results to JSON
    output_file = "scripts/verify_fastdl_production_flow_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {output_file}")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

