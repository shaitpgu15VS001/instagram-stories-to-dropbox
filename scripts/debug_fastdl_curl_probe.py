import json, os, time
from pathlib import Path
from urllib.parse import urlparse

from curl_cffi import requests as cf_requests
from playwright.sync_api import sync_playwright

API_URL = "https://api-wh.fastdl.app/api/v1/instagram/stories"
VIEWER_URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
USERNAME = "israel_bidur"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

BROWSER_PAYLOAD = {
    "username": "israel_bidur",
    "ts": 1786558828488,
    "_ts": 1785411663296,
    "_tsc": 0,
    "_sv": 2,
    "_s": "b03b0f025363706e0feb8389f3c5bad55610f364e158a259e0a63aebd3a4a61c",
}


def is_cloudflare(resp):
    body = (resp.text or "").lower()
    headers = {k.lower(): str(v).lower() for k, v in resp.headers.items()}
    server = headers.get("server", "")
    cf = any(x in body for x in ["cloudflare", "checking your browser", "please wait", "verify you are human"]) or server == "cloudflare"
    return cf or resp.status_code in (403, 429)


def safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return None


def dump_response(label, resp):
    body = resp.text or ""
    print(f"=== {label} ===")
    print("status:", resp.status_code)
    print("content-type:", resp.headers.get("Content-Type"))
    print("server:", resp.headers.get("Server"))
    print("cf challenge:", is_cloudflare(resp))
    print("json:", safe_json(resp) is not None)
    print("body_sample:", body[:800].replace("\n", " "))
    print()
    return {
        "label": label,
        "status": resp.status_code,
        "content_type": resp.headers.get("Content-Type"),
        "json": safe_json(resp) is not None,
        "cf_challenge": is_cloudflare(resp),
        "body_sample": body[:1000],
        "headers": dict(resp.headers),
    }


def curl_probe(label, payload, cookies=None, impersonate=None, extra_headers=None, use_json=True):
    session = cf_requests.Session()
    if cookies:
        for c in cookies:
            if c.get("name"):
                session.cookies.set(c["name"], c["value"], domain=c.get("domain") or None, path=c.get("path") or "/")
    base_headers = {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US",
        "Referer": "https://fastdl.app/",
        "Origin": "https://fastdl.app",
        "Content-Type": "application/json",
    }
    if extra_headers:
        base_headers.update(extra_headers)
    session.headers.update(base_headers)
    kwargs = {}
    if impersonate:
        kwargs["impersonate"] = impersonate
    if use_json:
        resp = session.post(API_URL, json=payload, timeout=30, **kwargs)
    else:
        resp = session.post(API_URL, data=json.dumps(payload), timeout=30, **kwargs)
    return dump_response(label, resp)


def collect_browser_session():
    browser_info = {
        "url": None,
        "cookies": [],
        "user_agent": UA,
        "origin": "https://fastdl.app",
        "referer": "https://fastdl.app/",
        "api_request": None,
        "story_count": None,
        "api_response": None,
        "media_urls": [],
    }
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=UA, viewport={"width": 1400, "height": 1000}, locale="en-US")
        page = context.new_page()
        api_request = {}
        api_response = {}

        def on_request(req):
            if "api/v1/instagram/stories" in req.url and req.method == "POST":
                api_request = {
                    "url": req.url,
                    "method": req.method,
                    "headers": dict(req.headers),
                    "post_data": req.post_data,
                    "ts_ms": int(time.time() * 1000),
                }
                browser_info["api_request"] = api_request

        def on_response(resp):
            if "api/v1/instagram/stories" in resp.url and resp.request.method == "POST":
                try:
                    body = resp.text()
                except Exception:
                    body = ""
                try:
                    payload = resp.json()
                except Exception:
                    payload = None
                api_response = {
                    "url": resp.url,
                    "status": resp.status,
                    "headers": dict(resp.headers),
                    "json": payload,
                    "body_sample": body[:1000],
                }
                browser_info["api_response"] = api_response
                if isinstance(payload, dict):
                    result = payload.get("result")
                    if isinstance(result, list):
                        browser_info["story_count"] = len(result)

        page.on("request", on_request)
        page.on("response", on_response)
        page.goto(VIEWER_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(2)
        page.locator('#search-form-input').wait_for(state='visible', timeout=30000)
        page.evaluate("""
        () => {
            document.querySelectorAll('.fc-dialog-overlay, .fc-consent-root, .fc-cookie-banner, [role=dialog], .modal, .cookie-banner').forEach(el => el.remove());
        }
        """)
        page.locator('#search-form-input').fill(USERNAME)
        page.locator('#searchFormButton').click(force=True)
        page.wait_for_timeout(4000)
        try:
            buttons = page.locator('button.tabs-component__button')
            for i in range(buttons.count()):
                b = buttons.nth(i)
                txt = b.inner_text(timeout=2000)
                if 'stories' in txt.lower():
                    b.click()
                    break
        except Exception:
            pass
        page.wait_for_timeout(5000)
        browser_info["url"] = page.url
        browser_info["cookies"] = [
            {"name": c["name"], "value": c["value"], "domain": c.get("domain"), "path": c.get("path")} for c in context.cookies()
        ]
        browser_info["user_agent"] = page.evaluate("() => navigator.userAgent")
        browser_info["referer"] = page.url
        browser_info["origin"] = urlparse(page.url).scheme + "://" + urlparse(page.url).netloc
        print("=== Browser session ===")
        print("page_url:", browser_info["url"])
        print("story_count:", browser_info["story_count"])
        print("api_request:", browser_info["api_request"])
        print("api_status:", browser_info["api_response"].get("status") if browser_info["api_response"] else None)
        print("cookie_count:", len(browser_info["cookies"]))
        print("first_cookie:", browser_info["cookies"][:3])
        print()
        browser.close()
    return browser_info


def main():
    print("Starting curl_cffi no-cookie probe...\n")
    result_no_cookie = curl_probe("curl_cffi_no_cookie_chrome120", BROWSER_PAYLOAD, impersonate="chrome120")
    result_no_cookie2 = curl_probe("curl_cffi_no_cookie_chrome131", BROWSER_PAYLOAD, impersonate="chrome131")

    browser_info = collect_browser_session()
    cookies = browser_info.get("cookies") or []
    if cookies:
        print("Starting curl_cffi + browser cookies probes...\n")
        result_with_cookie = curl_probe("curl_cffi_with_browser_cookies_chrome120", BROWSER_PAYLOAD, cookies=cookies, impersonate="chrome120")
        result_with_cookie2 = curl_probe("curl_cffi_with_browser_cookies_chrome131", BROWSER_PAYLOAD, cookies=cookies, impersonate="chrome131")
        result_with_cookie_headers = curl_probe(
            "curl_cffi_with_browser_cookies_headers",
            BROWSER_PAYLOAD,
            cookies=cookies,
            impersonate="chrome120",
            extra_headers={
                "Sec-Fetch-Site": "same-site",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Dest": "empty",
                "Accept-Encoding": "gzip, deflate, br",
            },
        )
    else:
        result_with_cookie = {"label": "curl_cffi_with_browser_cookies_chrome120", "status": None, "cf_challenge": None, "json": False, "body_sample": "no cookies"}
        result_with_cookie2 = {"label": "curl_cffi_with_browser_cookies_chrome131", "status": None, "cf_challenge": None, "json": False, "body_sample": "no cookies"}
        result_with_cookie_headers = {"label": "curl_cffi_with_browser_cookies_headers", "status": None, "cf_challenge": None, "json": False, "body_sample": "no cookies"}

    out = {
        "browser_info": browser_info,
        "results": [
            result_no_cookie,
            result_no_cookie2,
            result_with_cookie,
            result_with_cookie2,
            result_with_cookie_headers,
        ],
    }
    out_path = Path("scripts") / "debug_fastdl_curl_probe.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Saved results to", out_path)


if __name__ == "__main__":
    main()
