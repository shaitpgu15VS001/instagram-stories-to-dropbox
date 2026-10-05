#!/usr/bin/env python3
"""
חקירה בלבד - השוואת GitHub Actions vs local ללא שינוי production
- דגימות מבוקרות, ללא hammering
- מדידת TAB_TIMEOUT, request_seen, response_seen, request_failed, ERR_FAILED, status, latency
- השוואת אותה קבוצת usernames וגאפ
"""
import time, json, sys, os
from pathlib import Path
from datetime import datetime, timezone
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import requests

VIEWER_URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
STORIES_API_PATH = "/api/v1/instagram/stories"
STORIES_API_TIMEOUT_MS = 35000
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
OUTPUT_DIR = Path(__file__).resolve().parent
USERS = ["kolbarama", "mizrahitpage", "glglz", "israel_bidur", "erevtov"]  # same as GH run + controls
GAP_S = 3

def get_public_ip():
    try:
        r = requests.get("https://api.ipify.org?format=json", timeout=10)
        j = r.json()
        return j.get("ip"), j.get("ip")
    except Exception as e:
        try:
            r = requests.get("https://ifconfig.me/ip", timeout=10)
            return r.text.strip(), r.text.strip()
        except Exception as e2:
            return f"error:{e}", None

def single_attempt(username):
    req_seen = {"value": False}
    resp_seen = {"value": False, "status": None}
    fail_seen = {"value": False, "failure": None}
    t0 = time.time()
    def elapsed(): return round(time.time()-t0,2)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        ctx = browser.new_context(user_agent=USER_AGENT, viewport={"width":1280,"height":900}, locale="en-US")
        page = ctx.new_page()
        page.set_default_timeout(10000)
        def on_req(r):
            if STORIES_API_PATH in r.url and r.method=="POST":
                req_seen["value"]=True
        def on_resp(r):
            if STORIES_API_PATH in r.url and r.request.method=="POST":
                resp_seen["value"]=True
                resp_seen["status"]=r.status
        def on_fail(r):
            if STORIES_API_PATH in r.url and r.method=="POST":
                fail_seen["value"]=True
                fail_seen["failure"]=str(r.failure)
        page.on("request", on_req); page.on("response", on_resp); page.on("requestfailed", on_fail)
        # measure total flow
        flow_start = time.time()
        try:
            page.goto(VIEWER_URL, wait_until="domcontentloaded", timeout=10000)
            page.wait_for_selector("#search-form-input", state="visible", timeout=10000)
            page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
            page.fill("#search-form-input", username)
            page.click("#searchFormButton", force=True, timeout=10000)
            time.sleep(2.5)
            page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
            page.wait_for_selector("button.tabs-component__button", state="visible", timeout=30000)
        except PlaywrightTimeout as e:
            total = round(time.time()-flow_start,2)
            try: browser.close()
            except: pass
            return {
                "username": username,
                "status": "TAB_TIMEOUT",
                "request_seen": req_seen["value"],
                "response_seen": resp_seen["value"],
                "request_failed": fail_seen["value"],
                "err_failed": fail_seen["value"] and "ERR_FAILED" in (fail_seen["failure"] or ""),
                "response_status": resp_seen["status"],
                "request_latency": None,
                "total_latency": total,
                "items": None,
                "type": "TAB_TIMEOUT",
                "failure_reason": fail_seen["failure"]
            }
        except Exception as e:
            total = round(time.time()-flow_start,2)
            try: browser.close()
            except: pass
            return {"username": username, "status": f"EXC:{e}", "total_latency": total, "type": "EXC"}
        # Stories API
        req_t = time.time()
        try:
            with page.expect_response(lambda r: STORIES_API_PATH in r.url and r.request.method=="POST", timeout=STORIES_API_TIMEOUT_MS) as info:
                page.evaluate("""()=>{
                    const bs=Array.from(document.querySelectorAll('button.tabs-component__button'));
                    for(const b of bs){ if(b.innerText.toLowerCase().includes('stories')){ b.scrollIntoView(); b.click(); return true; } }
                    return false;
                }""")
            resp = info.value
            req_lat = round(time.time()-req_t,2)
            total = round(time.time()-flow_start,2)
            body = resp.json()
            sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
            from src.fastdl_api import FastDLStoriesAPI
            items = FastDLStoriesAPI.parse_stories(body)
            if items is None:
                st = "PARSE_NONE"
                n = None
            else:
                n = len(items)
                st = "SUCCESS_EMPTY" if n==0 else "SUCCESS"
            try: browser.close()
            except: pass
            return {
                "username": username,
                "status": st,
                "request_seen": req_seen["value"],
                "response_seen": resp_seen["value"],
                "request_failed": fail_seen["value"],
                "err_failed": False,
                "response_status": resp.status,
                "request_latency": req_lat,
                "total_latency": total,
                "items": n,
                "type": st
            }
        except PlaywrightTimeout as e:
            total = round(time.time()-flow_start,2)
            req_lat = round(time.time()-req_t,2) if req_seen["value"] else None
            if fail_seen["value"]:
                st = "ERR_FAILED"
                t = "ERR_FAILED"
            elif req_seen["value"] and not resp_seen["value"]:
                st = "HANG"
                t = "HANG"
            elif not req_seen["value"]:
                st = "TIMEOUT_BEFORE_REQUEST"
                t = "TIMEOUT_BEFORE_REQUEST"
            else:
                st = "TIMEOUT_OTHER"
                t = "TIMEOUT_OTHER"
            try: browser.close()
            except: pass
            return {
                "username": username,
                "status": st,
                "request_seen": req_seen["value"],
                "response_seen": resp_seen["value"],
                "request_failed": fail_seen["value"],
                "err_failed": fail_seen["value"] and "ERR_FAILED" in (fail_seen["failure"] or ""),
                "response_status": resp_seen["status"],
                "request_latency": req_lat,
                "total_latency": total,
                "items": None,
                "type": t,
                "failure_reason": fail_seen["failure"],
                "exception": str(e)[:300]
            }
        except Exception as e:
            total = round(time.time()-flow_start,2)
            try: browser.close()
            except: pass
            return {"username": username, "status": f"EXC:{e}", "total_latency": total, "type": "EXC"}

def main():
    print("=== Probe GitHub vs Local (controlled, no hammering) ===", flush=True)
    ip, raw = get_public_ip()
    print(f"Local public IP: {ip}", flush=True)
    # Historical GitHub data from run 32456347593 description
    github_historical = [
        {"username": "kolbarama", "status": "HANG", "request_seen": True, "response_seen": False, "request_failed": False, "items": None, "note": "no stories but hang, run 32456347593 06:56:41"},
        {"username": "mizrahitpage", "status": "HANG", "request_seen": True, "response_seen": False, "request_failed": False, "items": None, "note": "has stories but hang"},
        {"username": "glglz", "status": "HANG", "request_seen": True, "response_seen": False, "request_failed": False, "items": None, "note": "has stories but hang"},
    ]
    print(f"GitHub historical: 3 samples from run 32456347593: all HANG (request_seen true, response_seen false)", flush=True)

    # Local controlled samples: 12 attempts, gap 3s, same users
    local_results = []
    # Use same users as GH + controls, gap 3s
    for i in range(12):
        u = USERS[i % len(USERS)]
        print(f"\n--- Local {i+1}/12 @{u} gap {GAP_S}s ---", flush=True)
        r = single_attempt(u)
        print(f"  -> {r['status']} req={r['request_seen']} resp={r['response_seen']} failed={r['request_failed']} err_failed={r.get('err_failed')} resp_status={r.get('response_status')} req_lat={r.get('request_latency')} total={r.get('total_latency')} items={r.get('items')}", flush=True)
        local_results.append(r)
        if i < 11:
            time.sleep(GAP_S)

    # Save
    out = OUTPUT_DIR / "probe_github_vs_local_results.json"
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "local_ip": ip,
        "gap_s": GAP_S,
        "users": USERS,
        "local_samples": local_results,
        "github_historical": github_historical,
        "github_run_id": "32456347593",
        "note": "GitHub samples are historical from issue description (3 users), not live parallel run. No additional IP environment available without new infra."
    }
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {out}", flush=True)

    # Analysis
    from collections import Counter
    local_types = Counter(r["type"] for r in local_results)
    print("\n=== LOCAL COUNTS ===", flush=True)
    for k,v in local_types.items():
        print(f"  {k}: {v}/12 ({v/12*100:.1f}%)", flush=True)
    gh_types = Counter(r["status"] for r in github_historical)
    print("\n=== GITHUB COUNTS (historical, n=3) ===", flush=True)
    for k,v in gh_types.items():
        print(f"  {k}: {v}/3", flush=True)

    # Latency comparison
    local_success = [r for r in local_results if r["type"].startswith("SUCCESS")]
    if local_success:
        avg_lat = sum(r["total_latency"] for r in local_success)/len(local_success)
        avg_req = sum((r["request_latency"] or 0) for r in local_success)/len(local_success)
        print(f"\nLocal SUCCESS latency avg total {avg_lat:.2f}s req {avg_req:.2f}s n={len(local_success)}", flush=True)
        for r in local_success:
            print(f"  {r['username']}: total {r['total_latency']}s req {r['request_latency']} items {r['items']}", flush=True)
    print(f"GitHub historical latency: not measured (log only shows timeout 35s)", flush=True)

    # ERR_FAILED / TAB_TIMEOUT comparison
    local_err = sum(1 for r in local_results if r["err_failed"])
    local_tab = sum(1 for r in local_results if r["type"]=="TAB_TIMEOUT")
    print(f"\nLocal ERR_FAILED: {local_err}/12, TAB_TIMEOUT: {local_tab}/12", flush=True)
    print(f"GitHub ERR_FAILED: 0/3 (all HANG, no ERR_FAILED flagged), TAB_TIMEOUT: 0/3 (all reached Stories API)", flush=True)

if __name__ == "__main__":
    main()
