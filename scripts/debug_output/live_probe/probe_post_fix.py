#!/usr/bin/env python3
"""Probe after E-FDL-002 fix: uses production FastDLStoriesAPI.fetch_stories.

Tests:
- kolbarama (empty -> NO_ACTIVE_STORIES)
- israel_bidur (has stories)
- erevtov (has stories)
- batch of 3 with 2-3s gaps like production
Logs distinguish NO_ACTIVE_STORIES vs timeout before/after request vs requestfailed.
"""
import time, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from src.fastdl_api import FastDLStoriesAPI, STORIES_API_TIMEOUT_MS

print(f"STORIES_API_TIMEOUT_MS={STORIES_API_TIMEOUT_MS}")

def test_one(username):
    print(f"\n{'='*60}\nTesting @{username}\n{'='*60}")
    api = FastDLStoriesAPI()
    t0 = time.time()
    items = api.fetch_stories(username, timeout=10)
    dt = round(time.time()-t0,1)
    if items is None:
        print(f"  result: None (api_error/timeout) dt={dt}s")
        print(f"  -> status: API_ERROR (E-FDL-001)")
        return {"username":username, "status":"API_ERROR", "items":None, "dt":dt}
    elif len(items)==0:
        print(f"  result: [] empty dt={dt}s")
        print(f"  -> status: NO_ACTIVE_STORIES")
        return {"username":username, "status":"NO_ACTIVE_STORIES", "items":0, "dt":dt}
    else:
        print(f"  result: {len(items)} items dt={dt}s")
        print(f"  sample u={items[0].get('u','')[:80]}")
        print(f"  -> status: STORIES_FOUND")
        return {"username":username, "status":"STORIES_FOUND", "items":len(items), "dt":dt}

# Single tests
r1 = test_one("kolbarama")
time.sleep(2)
r2 = test_one("israel_bidur")
time.sleep(2)
r3 = test_one("erevtov")

# Batch test like production run_id=32456347593 order
print(f"\n{'='*60}\nBatch test: kolbarama,mizrahitpage,glglz (with 2s gaps)\n{'='*60}")
batch=[]
for u in ["kolbarama","mizrahitpage","glglz"]:
    r = test_one(u)
    batch.append(r)
    time.sleep(2)

print("\n=== SUMMARY ===")
for r in [r1,r2,r3]+batch:
    print(f" {r['username']}: {r['status']} items={r['items']} dt={r['dt']}s")

# Check NO_ACTIVE_STORIES vs timeout distinction
print("\n=== DISTINCTION CHECK ===")
print(f"kolbarama should be NO_ACTIVE_STORIES (empty list), not API_ERROR: {r1['status']}")
print(f"israel_bidur should be STORIES_FOUND: {r2['status']}")
print(f"Check logging fields: expect_response_timeout_ms={STORIES_API_TIMEOUT_MS} configured_page_timeout_s=10 request_seen/response_seen/request_failed/page_url should appear in logs above")

out = {"STORIES_API_TIMEOUT_MS": STORIES_API_TIMEOUT_MS, "single":[r1,r2,r3], "batch":batch}
Path(__file__).with_name("probe_post_fix_results.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\nWrote probe_post_fix_results.json")
