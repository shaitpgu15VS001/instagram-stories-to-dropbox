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
            # Preserve the distinction between `None` (parse/error) and
            # an empty list (valid response with no usable stories). If
            # `parse_stories` returns an empty list we should return it so
            # callers can treat "no stories" as a valid outcome.
            if items is not None:
                return items

        return self._fetch_stories_with_playwright(username, timeout=timeout)

    def _fetch_stories_with_playwright(self, username: str, timeout: int = 10) -> Optional[List[Dict[str, Any]]]:
        def log_failure(stage: str, exc: Exception, timeout_seconds: Optional[int] = None, response: Optional[Any] = None):
            exc_type = type(exc).__name__
            exc_message = str(exc)
            details = [
                f"username={username}",
                f"stage={stage}",
                f"exception_type={exc_type}",
                f"exception_message={exc_message}",
            ]
            if timeout_seconds is not None:
                details.append(f"timeout_seconds={timeout_seconds}")
            if response is not None:
                status = getattr(response, "status", None)
                url = getattr(response, "url", None)
                headers = getattr(response, "headers", {}) or {}
                content_type = headers.get("content-type") or headers.get("Content-Type")
                if status is not None:
                    details.append(f"http_status={status}")
                if url:
                    details.append(f"response_url={url}")
                if content_type:
                    details.append(f"content_type={content_type}")
            logger = __import__("src.logger", fromlist=["logger"]).logger
            # Include an Error ID for FastDL bridge failures
            logger.error("FastDL API bridge failure: " + "; ".join(details) + " E-FDL-001")

        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            except Exception as exc:
                log_failure("browser_launch", exc, timeout_seconds=timeout)
                return None
            try:
                context = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 900}, locale="en-US")
                page = context.new_page()
                page.set_default_timeout(timeout * 1000)

                request_seen = {"value": False, "method": None, "url": None}
                response_seen = {"value": False, "status": None, "url": None, "content_type": None}
                listener_attached = False
                search_click_started = False
                search_click_completed = False
                page_url_before_search = None
                page_url_after_search = None

                def on_request(req):
                    nonlocal listener_attached
                    listener_attached = True
                    if STORIES_API_PATH in req.url and req.method == "POST":
                        request_seen["value"] = True
                        request_seen["method"] = req.method
                        request_seen["url"] = req.url

                def on_response(resp):
                    nonlocal listener_attached
                    listener_attached = True
                    if STORIES_API_PATH in resp.url and resp.request.method == "POST":
                        response_seen["value"] = True
                        response_seen["status"] = resp.status
                        response_seen["url"] = resp.url
                        response_seen["content_type"] = (resp.headers.get("content-type") or resp.headers.get("Content-Type"))

                page.on("request", on_request)
                page.on("response", on_response)
                listener_attached = True

                __import__("src.logger", fromlist=["logger"]).logger.info("API_BRIDGE_STAGE page.goto start")
                page.goto(VIEWER_URL, wait_until="domcontentloaded", timeout=timeout * 1000)
                __import__("src.logger", fromlist=["logger"]).logger.info("API_BRIDGE_STAGE page.goto done")
                page_url_before_search = page.url
                page.wait_for_selector("#search-form-input", state="visible", timeout=timeout * 1000)
                page.evaluate(
                    """
                    () => {
                        const selectors = ['.fc-dialog-overlay', '.fc-consent-root', '.overlay', '.modal', '.cookie-banner', '.fc__dialog', '.fc-cookie-banner', '[role=dialog]'];
                        selectors.forEach(sel => document.querySelectorAll(sel).forEach(el => el.remove()));
                    }
                    """
                )
                __import__("src.logger", fromlist=["logger"]).logger.info("API_BRIDGE_STAGE page.fill start")
                page.fill("#search-form-input", username)
                __import__("src.logger", fromlist=["logger"]).logger.info("API_BRIDGE_STAGE page.fill done")
                search_click_started = True
                __import__("src.logger", fromlist=["logger"]).logger.info("API_BRIDGE_STAGE page.click start")
                try:
                    page.click("#searchFormButton", force=True, timeout=timeout * 1000)
                    search_click_completed = True
                except Exception as exc:
                    __import__("src.logger", fromlist=["logger"]).logger.error(
                        "NETWORK_DIAGNOSTIC: "
                        f"LISTENER_ATTACHED={str(listener_attached).lower()} "
                        f"SEARCH_CLICK_STARTED={str(search_click_started).lower()} "
                        f"SEARCH_CLICK_COMPLETED={str(search_click_completed).lower()} "
                        f"STORIES_API_REQUEST_SEEN={str(request_seen['value']).lower()} "
                        f"STORIES_API_RESPONSE_SEEN={str(response_seen['value']).lower()} "
                        f"PAGE_URL_BEFORE_SEARCH={page_url_before_search} "
                        f"PAGE_URL_AFTER_SEARCH={page.url} "
                        f"exception_type={type(exc).__name__} exception_message={exc}"
                    )
                    raise
                __import__("src.logger", fromlist=["logger"]).logger.info("API_BRIDGE_STAGE page.click done")

                # Wait for page to stabilize after search click (as verified by diagnostic)
                time.sleep(2.5)
                __import__("src.logger", fromlist=["logger"]).logger.info("API_BRIDGE_STAGE post-search sleep done")

                # Clean up overlay/popup elements that may appear after search
                page.evaluate(
                    """
                    () => {
                        const selectors = ['.fc-dialog-overlay', '.fc-consent-root', '.overlay', '.modal', '.cookie-banner', '.fc__dialog', '.fc-cookie-banner', '[role=dialog]'];
                        selectors.forEach(sel => document.querySelectorAll(sel).forEach(el => el.remove()));
                    }
                    """
                )
                __import__("src.logger", fromlist=["logger"]).logger.info("API_BRIDGE_STAGE post-search overlay cleanup done")

                # Wait for Stories tab to become visible (critical for triggering Stories API)
                __import__("src.logger", fromlist=["logger"]).logger.info("API_BRIDGE_STAGE wait_for_stories_tab start")
                page.wait_for_selector("button.tabs-component__button", state="visible", timeout=30000)
                __import__("src.logger", fromlist=["logger"]).logger.info("API_BRIDGE_STAGE wait_for_stories_tab done")

                # Now start listening for Stories API response and click the Stories tab
                __import__("src.logger", fromlist=["logger"]).logger.info("API_BRIDGE_STAGE response_waiter create start")
                with page.expect_response(
                    lambda response: STORIES_API_PATH in response.url and response.request.method == "POST",
                    timeout=20000,
                ) as response_info:
                    __import__("src.logger", fromlist=["logger"]).logger.info("API_BRIDGE_STAGE click_stories_tab start")
                    # Click Stories tab using JavaScript (matches proven diagnostic flow)
                    stories_tab_clicked = page.evaluate(
                        """
                        () => {
                            const buttons = Array.from(document.querySelectorAll('button.tabs-component__button'));
                            for (const button of buttons) {
                                if (button.innerText && button.innerText.toLowerCase().includes('stories')) {
                                    button.scrollIntoView();
                                    button.click();
                                    return true;
                                }
                            }
                            return false;
                        }
                        """
                    )
                    if not stories_tab_clicked:
                        __import__("src.logger", fromlist=["logger"]).logger.error("API_BRIDGE_STAGE stories_tab_not_found via evaluate")
                    __import__("src.logger", fromlist=["logger"]).logger.info("API_BRIDGE_STAGE click_stories_tab done")
                __import__("src.logger", fromlist=["logger"]).logger.info("API_BRIDGE_STAGE response_waiter create done")
                page_url_after_search = page.url

                if request_seen["value"]:
                    __import__("src.logger", fromlist=["logger"]).logger.info(
                        f"STORIES_API_REQUEST_METHOD={request_seen['method']} STORIES_API_REQUEST_URL={request_seen['url']}"
                    )
                if response_seen["value"]:
                    __import__("src.logger", fromlist=["logger"]).logger.info(
                        f"STORIES_API_RESPONSE_STATUS={response_seen['status']} STORIES_API_RESPONSE_CONTENT_TYPE={response_seen['content_type']}"
                    )

                __import__("src.logger", fromlist=["logger"]).logger.info("API_BRIDGE_STAGE wait_for_response start")
                try:
                    response = response_info.value
                except Exception as exc:
                    __import__("src.logger", fromlist=["logger"]).logger.error(
                        "NETWORK_DIAGNOSTIC: "
                        f"LISTENER_ATTACHED={str(listener_attached).lower()} "
                        f"SEARCH_CLICK_STARTED={str(search_click_started).lower()} "
                        f"SEARCH_CLICK_COMPLETED={str(search_click_completed).lower()} "
                        f"STORIES_API_REQUEST_SEEN={str(request_seen['value']).lower()} "
                        f"STORIES_API_RESPONSE_SEEN={str(response_seen['value']).lower()} "
                        f"PAGE_URL_BEFORE_SEARCH={page_url_before_search} "
                        f"PAGE_URL_AFTER_SEARCH={page_url_after_search} "
                        f"exception_type={type(exc).__name__} exception_message={exc}"
                    )
                    raise
                __import__("src.logger", fromlist=["logger"]).logger.info("API_BRIDGE_STAGE wait_for_response done")

                if response.status != 200:
                    __import__("src.logger", fromlist=["logger"]).logger.error(
                        "NETWORK_DIAGNOSTIC: "
                        f"LISTENER_ATTACHED={str(listener_attached).lower()} "
                        f"SEARCH_CLICK_STARTED={str(search_click_started).lower()} "
                        f"SEARCH_CLICK_COMPLETED={str(search_click_completed).lower()} "
                        f"STORIES_API_REQUEST_SEEN={str(request_seen['value']).lower()} "
                        f"STORIES_API_RESPONSE_SEEN={str(response_seen['value']).lower()} "
                        f"PAGE_URL_BEFORE_SEARCH={page_url_before_search} "
                        f"PAGE_URL_AFTER_SEARCH={page_url_after_search} "
                        f"STORIES_API_REQUEST_METHOD={request_seen['method']} STORIES_API_REQUEST_URL={request_seen['url']} "
                        f"STORIES_API_RESPONSE_STATUS={response_seen['status']} STORIES_API_RESPONSE_CONTENT_TYPE={response_seen['content_type']} E-FDL-002"
                    )
                    log_failure(
                        "waiting_for_response",
                        TimeoutError(
                            f"API bridge timeout stage=waiting_for_response timeout_seconds={20000}"
                        ),
                        timeout_seconds=20000,
                        response=response,
                    )
                    return None
                body = response.json()
                items = self.parse_stories(body)
                if items is None:
                    __import__("src.logger", fromlist=["logger"]).logger.error(
                        "NETWORK_DIAGNOSTIC: "
                        f"LISTENER_ATTACHED={str(listener_attached).lower()} "
                        f"SEARCH_CLICK_STARTED={str(search_click_started).lower()} "
                        f"SEARCH_CLICK_COMPLETED={str(search_click_completed).lower()} "
                        f"STORIES_API_REQUEST_SEEN={str(request_seen['value']).lower()} "
                        f"STORIES_API_RESPONSE_SEEN={str(response_seen['value']).lower()} "
                        f"PAGE_URL_BEFORE_SEARCH={page_url_before_search} "
                        f"PAGE_URL_AFTER_SEARCH={page_url_after_search} "
                        f"STORIES_API_REQUEST_METHOD={request_seen['method']} STORIES_API_REQUEST_URL={request_seen['url']} "
                        f"STORIES_API_RESPONSE_STATUS={response_seen['status']} STORIES_API_RESPONSE_CONTENT_TYPE={response_seen['content_type']}"
                    )
                    log_failure("parsing", ValueError("API response parsed to no usable stories"), timeout_seconds=timeout, response=response)
                    return None
                __import__("src.logger", fromlist=["logger"]).logger.info(
                    "NETWORK_DIAGNOSTIC: "
                    f"LISTENER_ATTACHED={str(listener_attached).lower()} "
                    f"SEARCH_CLICK_STARTED={str(search_click_started).lower()} "
                    f"SEARCH_CLICK_COMPLETED={str(search_click_completed).lower()} "
                    f"STORIES_API_REQUEST_SEEN={str(request_seen['value']).lower()} "
                    f"STORIES_API_RESPONSE_SEEN={str(response_seen['value']).lower()} "
                    f"PAGE_URL_BEFORE_SEARCH={page_url_before_search} "
                    f"PAGE_URL_AFTER_SEARCH={page_url_after_search} "
                    f"STORIES_API_REQUEST_METHOD={request_seen['method']} STORIES_API_REQUEST_URL={request_seen['url']} "
                    f"STORIES_API_RESPONSE_STATUS={response_seen['status']} STORIES_API_RESPONSE_CONTENT_TYPE={response_seen['content_type']}"
                )
                return items
            except PlaywrightTimeout as exc:
                __import__("src.logger", fromlist=["logger"]).logger.error(
                    "NETWORK_DIAGNOSTIC: "
                    f"LISTENER_ATTACHED={str('true' if listener_attached else 'false').lower()} "
                    f"SEARCH_CLICK_STARTED={str(search_click_started).lower()} "
                    f"SEARCH_CLICK_COMPLETED={str(search_click_completed).lower()} "
                    f"STORIES_API_REQUEST_SEEN={str(request_seen['value']).lower()} "
                    f"STORIES_API_RESPONSE_SEEN={str(response_seen['value']).lower()} "
                    f"PAGE_URL_BEFORE_SEARCH={page_url_before_search} "
                    f"PAGE_URL_AFTER_SEARCH={page_url_after_search} "
                    f"STORIES_API_REQUEST_METHOD={request_seen['method']} STORIES_API_REQUEST_URL={request_seen['url']} "
                    f"STORIES_API_RESPONSE_STATUS={response_seen['status']} STORIES_API_RESPONSE_CONTENT_TYPE={response_seen['content_type']} "
                    f"exception_type={type(exc).__name__} exception_message={exc} timeout_seconds={timeout}"
                )
                log_failure("waiting_for_response", exc, timeout_seconds=timeout)
                return None
            except Exception as exc:
                stage = "search"
                if "wait_for_event" in str(exc) or "wait_for_response" in str(exc):
                    stage = "waiting_for_response"
                elif "page.goto" in str(exc):
                    stage = "page_navigation"
                elif "querySelector" in str(exc) or "input" in str(exc):
                    stage = "search"
                elif "response.json" in str(exc) or "parse_stories" in str(exc):
                    stage = "parsing"
                __import__("src.logger", fromlist=["logger"]).logger.error(
                    "NETWORK_DIAGNOSTIC: "
                    f"LISTENER_ATTACHED={str('true' if listener_attached else 'false').lower()} "
                    f"SEARCH_CLICK_STARTED={str(search_click_started).lower()} "
                    f"SEARCH_CLICK_COMPLETED={str(search_click_completed).lower()} "
                    f"STORIES_API_REQUEST_SEEN={str(request_seen['value']).lower()} "
                    f"STORIES_API_RESPONSE_SEEN={str(response_seen['value']).lower()} "
                    f"PAGE_URL_BEFORE_SEARCH={page_url_before_search} "
                    f"PAGE_URL_AFTER_SEARCH={page_url_after_search} "
                    f"STORIES_API_REQUEST_METHOD={request_seen['method']} STORIES_API_REQUEST_URL={request_seen['url']} "
                    f"STORIES_API_RESPONSE_STATUS={response_seen['status']} STORIES_API_RESPONSE_CONTENT_TYPE={response_seen['content_type']} "
                    f"exception_type={type(exc).__name__} exception_message={exc} stage={stage} timeout_seconds={timeout}"
                )
                log_failure(stage, exc, timeout_seconds=timeout)
                return None
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
        result = resp_json.get("result")
        if result is None:
            result = resp_json.get("data")
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
                # Prefer video_versions when present (video should win over thumbnail)
                if not url and isinstance(it.get("video_versions"), list) and it.get("video_versions"):
                    v0 = it.get("video_versions")[0]
                    if isinstance(v0, dict):
                        for key in ("url_downloadable", "url_wrapped", "url"):
                            if key in v0:
                                url = v0[key]
                                break
                # Fallback to image versions only if no video url was found
                if not url and isinstance(it.get("image_versions2"), dict):
                    c = it["image_versions2"].get("candidates")
                    if isinstance(c, list) and c:
                        for key in ("url_downloadable", "url_wrapped", "url"):
                            if key in c[0]:
                                url = c[0][key]
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
