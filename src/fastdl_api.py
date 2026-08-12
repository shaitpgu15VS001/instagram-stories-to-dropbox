"""Minimal FastDL Stories API client and parser.

This module provides a small, well-contained API-first layer for fetching and
parsing Stories from fastdl.app. It is intentionally conservative: if the
remote API doesn't respond or returns an unexpected shape, callers should
fall back to the DOM-based collector in `story_downloader.py`.

The implementation avoids aggressive assumptions about required signed
parameters; it first tries a simple `POST` with `username` and falls back to
not breaking caller flow.
"""
from typing import List, Dict, Any, Optional
import time
import json
from urllib.parse import urlparse, parse_qs

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

STORIES_API = "https://api-wh.fastdl.app/api/v1/instagram/stories"
VIEWER_URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
STORIES_API_PATH = "/api/v1/instagram/stories"


class FastDLStoriesAPI:
    """Small helper for fetching and normalizing Stories API responses.

    Methods should be safe to call from production code: they return `None`
    on failure so callers can fallback to DOM logic.
    """

    def __init__(self, session: Optional[requests.Session] = None):
        self.s = session or requests.Session()
        self.s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})

    def fetch_stories(self, username: str, timeout: int = 10) -> Optional[List[Dict[str, Any]]]:
        """Attempt to POST to the FastDL Stories API and return normalized items.

        Returns a list of normalized items (dicts with at least 'u' and 'kind'),
        or `None` if the API call fails or response shape is unexpected.
        """
        username = username.strip().lstrip("@")
        if not username:
            return None

        # Try a minimal payload first. Some observed requests include timestamps
        # and derived signature fields; we avoid fabricating signatures.
        payloads = [
            {"username": username},
            {"username": username, "ts": int(time.time() * 1000), "_sv": 2},
        ]

        for payload in payloads:
            try:
                r = self.s.post(STORIES_API, json=payload, timeout=timeout)
            except Exception:
                continue
            if r.status_code != 200:
                continue
            try:
                body = r.json()
            except Exception:
                continue
            items = self.parse_stories(body)
            if items:
                return items

        return self._fetch_stories_with_playwright(username, timeout=timeout)

    def _fetch_stories_with_playwright(self, username: str, timeout: int = 10) -> Optional[List[Dict[str, Any]]]:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            try:
                context = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 900}, locale="en-US")
                page = context.new_page()
                page.set_default_timeout(timeout * 1000)
                page.goto(VIEWER_URL, wait_until="domcontentloaded", timeout=timeout * 1000)
                page.wait_for_selector("#search-form-input", state="visible", timeout=timeout * 1000)
                page.evaluate(
                    """
                    () => {
                        const selectors = ['.fc-dialog-overlay', '.fc-consent-root', '.overlay', '.modal', '.cookie-banner', '.fc__dialog', '.fc-cookie-banner', '[role=dialog]'];
                        selectors.forEach(sel => document.querySelectorAll(sel).forEach(el => el.remove()));
                    }
                    """
                )
                page.evaluate(
                    """
                    (data) => {
                        const input = document.querySelector(data.sel);
                        if (!input) return false;
                        input.focus();
                        input.value = data.val;
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                        return input.value === data.val;
                    }
                    """,
                    {"sel": "#search-form-input", "val": username},
                )
                response_future = page.wait_for_event(
                    "response",
                    predicate=lambda r: STORIES_API_PATH in r.url and r.request.method == "POST",
                    timeout=20000,
                )
                page.click("#searchFormButton", force=True, timeout=timeout * 1000)

                response = response_future
                if response.status != 200:
                    return None
                body = response.json()
                return self.parse_stories(body)
            finally:
                browser.close()

    @staticmethod
    def parse_stories(resp_json: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """Parse the API response and return a normalized list of items.

        Normalized item shape: { 'u': <download_url>, 'kind': 'image'|'video', 'raw': <original> }
        """
        if not isinstance(resp_json, dict):
            return None
        # Common observed shape: {'result': [ ... ]}
        result = resp_json.get("result") or resp_json.get("data")
        if not isinstance(result, list):
            return None

        normalized = []
        for it in result:
            url = None
            kind = None
            # video_versions or video field
            if isinstance(it, dict):
                # nested places where downloadable url may exist
                for path in ("url_downloadable", "url_wrapped", "url"):
                    # try top-level
                    if path in it and isinstance(it[path], str):
                        url = it[path]
                        break
                # candidates inside image_versions2
                if not url and isinstance(it.get("image_versions2"), dict):
                    c = it["image_versions2"].get("candidates")
                    if isinstance(c, list) and c:
                        for key in ("url_downloadable", "url_wrapped", "url"):
                            if key in c[0]:
                                url = c[0][key]
                                break
                if not url and isinstance(it.get("video_versions"), list) and it.get("video_versions"):
                    v0 = it.get("video_versions")[0]
                    if isinstance(v0, dict):
                        for key in ("url_downloadable", "url_wrapped", "url"):
                            if key in v0:
                                url = v0[key]
                                break

            if url:
                lower = url.lower()
                if any(x in lower for x in (".mp4", "video")):
                    kind = "video"
                else:
                    kind = "image"
                normalized.append({"u": url, "kind": kind, "raw": it})

        return normalized

    @staticmethod
    def url_has_sig_expires(url: str) -> bool:
        try:
            qs = parse_qs(urlparse(url).query)
            return any(k in qs for k in ("__sig", "__expires", "_sig", "expires"))
        except Exception:
            return False
