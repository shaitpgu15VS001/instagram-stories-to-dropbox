"""מוריד סטוריז מ-Instagram דרך fastdl.app"""
import os
import re
import shutil
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeout, sync_playwright
from urllib.parse import urlparse, parse_qs, unquote
import json

from .logger import logger


VIEWER_URL = "https://fastdl.app/instagram-anonymously-viewer"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
STORIES_DIR = Path("stories")
PAGE_LOAD_TIMEOUT = 60000
PROFILE_LOAD_TIMEOUT = 60000
STORIES_LOAD_TIMEOUT = 30000
DOWNLOAD_TIMEOUT = 60
MEDIA_EXTENSIONS = {".mp4", ".jpg", ".jpeg", ".png", ".webp", ".mov"}
MAX_RETRIES, RETRYABLE, RETRY_DELAY = 3, {502, 503, 504}, 2


def extract_pre_download_id(href):
    if not href:
        return None
    try:
        parsed = urlparse(href)
        qs = parse_qs(parsed.query)
        uri = qs.get('uri', [''])[0]
        if not uri:
            return None
        uri_decoded = unquote(uri)
        inner = urlparse(uri_decoded)
        return inner.path if inner.path else None
    except Exception:
        return None


def _is_jpeg(content: bytes) -> bool:
    return bool(content and content[:2] == b"\xff\xd8")


def _is_mp4(content: bytes) -> bool:
    try:
        return b"ftyp" in content[:4096]
    except Exception:
        return False


def format_taken_at_for_filename(ta):
    """Format unix timestamp `ta` into Israel local time filename fragment."""
    try:
        tz = ZoneInfo("Asia/Jerusalem")
        dt = datetime.fromtimestamp(int(ta), tz=tz)
        return dt.strftime("%Y-%m-%d_%H-%M-%S")
    except Exception:
        return None


def _parse_meta_timestamp(s):
    t = s.get('t') or ''
    txt = s.get('txt') or ''
    if t:
        m = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4}),?\s+(\d{1,2}):(\d{2}):(\d{2})", t)
        if m:
            d, mo, y, h, mi, sec = m.groups()
            try:
                return datetime(int(y), int(mo), int(d), int(h), int(mi), int(sec), tzinfo=timezone.utc)
            except Exception:
                pass
    rm = re.search(r"(\d+)\s*(minute|minutes|hour|hours|day|days)", txt)
    if rm:
        n = int(rm.group(1))
        unit = rm.group(2)
        if unit.startswith('minute'):
            return datetime.now(timezone.utc) - timedelta(minutes=n)
        if unit.startswith('hour'):
            return datetime.now(timezone.utc) - timedelta(hours=n)
        if unit.startswith('day'):
            return datetime.now(timezone.utc) - timedelta(days=n)
    if s.get('u'):
        em = re.search(r'__expires=(\d+)', s.get('u'))
        if em:
            try:
                return datetime.fromtimestamp(int(em[1]), tz=timezone.utc)
            except Exception:
                pass
    return None


def _sort_items_chronologically(items):
    for it in items:
        it['_parsed_ts'] = _parse_meta_timestamp(it)
    if any(it.get('_parsed_ts') for it in items):
        items.sort(key=lambda s: (s.get('_parsed_ts') is None, s.get('_parsed_ts') or datetime.max.replace(tzinfo=timezone.utc)))
        return items
    ROW_TOL = 30.0
    items.sort(key=lambda s: (round(s.get('y', 0) / ROW_TOL), s.get('x', 0)))
    return items


def _collect_items_with_scroll(page, max_scrolls=25, wait_ms=500):
    """Scroll the page to load more `.profile-media-list__item` elements.

    This function intentionally does not change behavior; it only performs
    scrolling and returns the collected items. Debug logging can be enabled by
    setting the env var `SCROLL_DEBUG=1`.
    """
    debug = os.environ.get('SCROLL_DEBUG') == '1'
    # Unconditional diagnostic log: helps verify this function is reached in CI
    logger.info("scroll-collector: entered (SCROLL_DEBUG=%s)" % ("1" if debug else "0"))

    # attach a lightweight network request capture for audit (non-intrusive)
    requests_seen = []
    try:
        def _on_request(req):
            try:
                requests_seen.append(req.url)
            except Exception:
                pass

        try:
            page.on("request", _on_request)
        except Exception:
            pass
    except Exception:
        requests_seen = []

    prev = -1
    iter_count = 0
    stop_reason = None

    for i in range(1, max_scrolls + 1):
        iter_count = i
        # record request count before this iteration
        try:
            req_count_before = len(requests_seen)
        except Exception:
            req_count_before = 0

        try:
            pre = page.evaluate(
                "() => { const items = document.querySelectorAll('.profile-media-list__item'); const count = items.length; const winY = window.scrollY || window.pageYOffset; const docH = document.documentElement ? document.documentElement.scrollHeight : 0; const bodyH = document.body ? document.body.scrollHeight : 0; let container = null; if (items.length) { let el = items[0]; while (el) { const s = window.getComputedStyle(el); if (s.overflowY === 'auto' || s.overflowY === 'scroll') { container = {tag: el.tagName, class: el.className, scrollTop: el.scrollTop, scrollHeight: el.scrollHeight, clientHeight: el.clientHeight}; break; } el = el.parentElement; } } return {count, winY, docH, bodyH, container}; }"
            )
        except Exception:
            pre = {'count': 0, 'winY': None, 'docH': None, 'bodyH': None, 'container': None}

        count = pre.get('count', 0)

        try:
            last_rect_before = page.evaluate(
                "() => { const items = document.querySelectorAll('.profile-media-list__item'); if (!items.length) return null; const r = items[items.length-1].getBoundingClientRect(); return {x: r.x, y: r.y, width: r.width, height: r.height}; }"
            )
        except Exception:
            last_rect_before = None

        if debug:
            logger.info(f"scroll-debug iter={i} pre_count={count} pre_winY={pre.get('winY')} pre_docH={pre.get('docH')} pre_bodyH={pre.get('bodyH')} container={'yes' if pre.get('container') else 'no'} last_rect={last_rect_before}")

        if count == prev:
            stop_reason = 'count_stable'
            break

        prev = count

        found_last = False
        scrolled = False
        try:
            found_last = page.evaluate("() => { const items = document.querySelectorAll('.profile-media-list__item'); return items.length > 0; }")
            if found_last:
                scrolled = page.evaluate(
                    "() => { const items = document.querySelectorAll('.profile-media-list__item'); if (items.length) { const before = {winY: window.scrollY || window.pageYOffset, docH: document.documentElement ? document.documentElement.scrollHeight : 0, bodyH: document.body ? document.body.scrollHeight : 0}; items[items.length-1].scrollIntoView(); const after = {winY: window.scrollY || window.pageYOffset, docH: document.documentElement ? document.documentElement.scrollHeight : 0, bodyH: document.body ? document.body.scrollHeight : 0}; return {before, after}; } return null; }"
                )
        except Exception:
            scrolled = False

        if debug:
            logger.info(f"scroll-debug iter={i} found_last={found_last} scrolled={'yes' if scrolled else 'no'})")

        try:
            post = page.evaluate(
                "() => { const items = document.querySelectorAll('.profile-media-list__item'); const count = items.length; const winY = window.scrollY || window.pageYOffset; const docH = document.documentElement ? document.documentElement.scrollHeight : 0; const bodyH = document.body ? document.body.scrollHeight : 0; let container = null; if (items.length) { let el = items[0]; while (el) { const s = window.getComputedStyle(el); if (s.overflowY === 'auto' || s.overflowY === 'scroll') { container = {tag: el.tagName, class: el.className, scrollTop: el.scrollTop, scrollHeight: el.scrollHeight, clientHeight: el.clientHeight}; break; } el = el.parentElement; } } return {count, winY, docH, bodyH, container}; }"
            )
        except Exception:
            post = {'count': 0, 'winY': None, 'docH': None, 'bodyH': None, 'container': None}

        try:
            last_rect_after = page.evaluate(
                "() => { const items = document.querySelectorAll('.profile-media-list__item'); if (!items.length) return null; const r = items[items.length-1].getBoundingClientRect(); return {x: r.x, y: r.y, width: r.width, height: r.height}; }"
            )
        except Exception:
            last_rect_after = None

        if debug:
            logger.info(f"scroll-debug iter={i} post_count_after_scroll={post.get('count')} post_winY={post.get('winY')} post_docH={post.get('docH')} post_bodyH={post.get('bodyH')} container={'yes' if post.get('container') else 'no'} last_rect={last_rect_after}")

        try:
            page.wait_for_timeout(wait_ms)
        except Exception:
            time.sleep(wait_ms / 1000.0)

        try:
            waited = page.evaluate(
                "() => { const items = document.querySelectorAll('.profile-media-list__item'); const count = items.length; const winY = window.scrollY || window.pageYOffset; const docH = document.documentElement ? document.documentElement.scrollHeight : 0; const bodyH = document.body ? document.body.scrollHeight : 0; let container = null; if (items.length) { let el = items[0]; while (el) { const s = window.getComputedStyle(el); if (s.overflowY === 'auto' || s.overflowY === 'scroll') { container = {tag: el.tagName, class: el.className, scrollTop: el.scrollTop, scrollHeight: el.scrollHeight, clientHeight: el.clientHeight}; break; } el = el.parentElement; } } return {count, winY, docH, bodyH, container}; }"
            )
        except Exception:
            waited = {'count': 0, 'winY': None, 'docH': None, 'bodyH': None, 'container': None}

        try:
            req_count_after_wait = len(requests_seen)
        except Exception:
            req_count_after_wait = 0

        if debug:
            try:
                reqs_before = req_count_before if 'req_count_before' in locals() else 0
                new_reqs = requests_seen[reqs_before:req_count_after_wait]
            except Exception:
                new_reqs = []
            logger.info(f"scroll-debug iter={i} waited_count={waited.get('count')} waited_winY={waited.get('winY')} waited_docH={waited.get('docH')} waited_bodyH={waited.get('bodyH')} container={'yes' if waited.get('container') else 'no'} new_requests={len(new_reqs)} sample_requests={new_reqs[:5]}")

        if waited.get('count') == prev:
            stop_reason = 'count_stable'
            break

    else:
        stop_reason = 'max_scrolls'

    items = page.evaluate("""() => Array.from(document.querySelectorAll('.profile-media-list__item'))
        .map(li => {
            const r = li.getBoundingClientRect();
            const t = li.querySelector('.media-content__meta-time');
            return {u: li.querySelector('.button__download')?.href, x: r.x, y: r.y, t: t?.title, txt: t?.innerText?.trim()};
        })
        .filter(s => s.u)""")

    final_count = len(items) if isinstance(items, list) else page.evaluate("() => document.querySelectorAll('.profile-media-list__item').length")
    # Unconditional final diagnostic log so CI always records whether scrolling returned items
    logger.info(f"scroll-collector: finished iter_count={iter_count} stop_reason={stop_reason} final_count={final_count}")
    if debug:
        logger.info(f"scroll-debug finished iter_count={iter_count} stop_reason={stop_reason} final_count={final_count}")
    return items


class StoryDownloader:

    def __init__(self, output_dir=STORIES_DIR):
        self.output_dir = Path(output_dir)
        self._playwright = None
        self._browser = None
        self._context = None

    def _ensure_browser_context(self):
        if self._context is not None:
            return self._context
        try:
            self._playwright = __import__('playwright.sync_api', fromlist=['sync_playwright']).sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            self._context = self._browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 900},
                locale="en-US",
            )
            return self._context
        except Exception as exc:
            logger.error(f"FastDL browser context init failed: {type(exc).__name__}: {exc}")
            raise

    def _close_browser_context(self):
        try:
            if self._context is not None:
                self._context.close()
                self._context = None
        except Exception:
            pass
        try:
            if self._browser is not None:
                self._browser.close()
                self._browser = None
        except Exception:
            pass
        try:
            if self._playwright is not None:
                self._playwright.stop()
                self._playwright = None
        except Exception:
            pass

    def _download_media_via_browser_context(self, url, timeout_seconds=60):
        context = self._ensure_browser_context()
        try:
            response = context.request.get(
                url,
                timeout=timeout_seconds * 1000,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "*/*",
                    "Referer": "https://fastdl.app/",
                },
            )
            status = getattr(response, "status", None)
            if status is None or status >= 400:
                raise requests.HTTPError(f"fastdl browser-context media fetch failed: status={status}")
            content = response.body()
            if not content:
                raise ValueError("empty response body from browser-context download")
            headers = getattr(response, "headers", {}) or {}
            return {
                "content": content,
                "content_type": headers.get("content-type") or "",
                "final_url": getattr(response, "url", url),
                "status": status,
            }
        except Exception:
            logger.warning("FastDL browser-context media download failed for url=%s; no requests fallback is attempted by default", url)
            raise

    def check_binary(self):
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                p.chromium.launch(headless=True, args=["--no-sandbox"])
            return True
        except Exception as exc:
            logger.error(
                f"Playwright לא מותקן כראוי. "
                f"הרץ: pip install playwright && playwright install chromium. שגיאה: {exc}"
            )
            return False

    def download_stories(self, username, folder_name=None):
        state = None
        username = username.strip().lstrip("@")
        if not username:
            return {"success": False, "files": [], "error": "שם משתמש ריק"}

        target_name = folder_name or username
        logger.info(f"DOWNLOAD REQUEST username={username} folder_name={folder_name} target_dir={self.output_dir / target_name}")
        user_dir = self.output_dir / target_name
        user_dir.mkdir(parents=True, exist_ok=True)
        existing_files = [p for p in sorted(user_dir.iterdir()) if p.is_file()] if user_dir.exists() else []

        logger.info(f"מוריד סטוריז עבור @{username}...")
        try:
            download_urls = self._fetch_story_urls(username)
            logger.info(f"items_found_before_state_filter username={username} count={len(download_urls) if download_urls is not None else 'None'}")
        except PlaywrightTimeout:
            logger.warning(f"@{username}: timeout בחיפוש - מנסה שוב פעם אחת")
            try:
                download_urls = self._fetch_story_urls(username)
            except PlaywrightTimeout:
                logger.error(f"@{username}: timeout חוזר - מדלג")
                logger.error(f"@{username} FASTDL bridge timeout E-FDL-001")
                if existing_files:
                    return {"success": True, "files": existing_files, "error": None}
                return {"success": False, "files": [], "error": "timeout"}
            except Exception as exc:
                logger.error(f"שגיאה בגלישה ל-fastdl.app עבור @{username}: {exc}")
                if existing_files:
                    return {"success": True, "files": existing_files, "error": None}
                return {"success": False, "files": [], "error": str(exc)}
        except Exception as exc:
            logger.error(f"שגיאה בגלישה ל-fastdl.app עבור @{username}: {exc} E-FDL-001")
            if existing_files:
                return {"success": True, "files": existing_files, "error": None}
            return {"success": False, "files": [], "error": str(exc)}

        if download_urls is None:
            logger.warning(
                f"@{username}: FastDL API/bridge failed or returned no usable stories. "
                "DOM extraction remains archived in src/story_downloader.py and docs/FASTDL_STORIES_ARCHITECTURE.md; "
                "it is not executed automatically from the API-first flow."
            )
            logger.error(
                f"FastDL API bridge failure username={username} stage=api_bridge_result "
                "exception_type=api_error exception_message=No usable stories returned from API bridge; "
                "returning api_error and leaving DOM archived as maintenance-only knowledge."
            )
            if existing_files:
                return {"success": True, "files": existing_files, "error": None}
            return {"success": False, "files": [], "error": "api_error"}

        if not download_urls:
            logger.info(f"@{username}: אין סטוריז פעילים כרגע")
            if existing_files:
                return {"success": True, "files": existing_files, "error": None}
            return {"success": True, "files": [], "error": None}

        new_files_meta = {}
        state = getattr(self, "state_manager", None)
        summary = {
            "found": 0,
            "skipped": 0,
            "matched_by_pre_download_id": 0,
            "matched_by_instagram_id": 0,
            "new": 0,
        }
        if state:
            filtered = []
            for s in download_urls:
                url = s.get("u")
                pre_id = extract_pre_download_id(url)
                if pre_id:
                    matched_type, item = state.find_uploaded_entry(username, pre_id)
                    if item is not None:
                        summary["found"] += 1
                        summary["skipped"] += 1
                        summary[f"matched_by_{matched_type}"] += 1
                        logger.info(
                            f"[SKIP] username={username} pre_download_id={pre_id} matched_by={matched_type} "
                            f"state_value={item.get(matched_type)} filename={item.get('filename')} uploaded_at={item.get('uploaded_at')}"
                        )
                        continue
                    logger.info(f"[NEW] Story not found in state: {pre_id}")
                else:
                    logger.warning("[WARN] Could not extract pre-download ID; using legacy flow")
                s["pre_download_id"] = pre_id
                filtered.append(s)
                summary["new"] += 1
            to_download = filtered
        else:
            to_download = download_urls

        # Diagnostic log: number of items after applying state filter
        logger.info(f"items_after_state_filter username={username} count={len(to_download) if to_download else 0}")
        if state:
            logger.info(
                f"summary username={username} found={summary['found']} skipped={summary['skipped']} "
                f"matched_by_pre_download_id={summary['matched_by_pre_download_id']} "
                f"matched_by_instagram_id={summary['matched_by_instagram_id']} new={summary['new']}"
            )

        if state and download_urls and not to_download:
            if existing_files:
                return {"success": True, "files": existing_files, "error": None}
            return {"success": True, "files": [], "error": None}

        new_files = self._download_files(to_download, user_dir, username)
        if new_files is None:
            if existing_files:
                return {"success": True, "files": existing_files, "error": None}
            return {"success": False, "files": [], "error": "download_failed"}

        files_return = []
        meta_map = {}
        for nf in new_files:
            if isinstance(nf, dict):
                p = nf.get("path")
                pid = nf.get("pre_download_id")
            else:
                p = nf
                pid = None
            files_return.append(p)
            if p:
                meta_map[p.name] = pid

        existing_names = {p.name for p in existing_files}
        combined = list(existing_files) + [p for p in files_return if p.name not in existing_names]
        if not combined:
            return {"success": False, "files": [], "error": "download_failed"}
        logger.success(f"@{username}: הורדו {len(files_return)} קבצים (קיימים: {len(existing_files)})")
        return {"success": True, "files": combined, "meta": meta_map, "error": None}

    def _fetch_story_urls(self, username):
        # API-first: try FastDL Stories API. Do not automatically run the DOM
        # fallback if the API fails or returns no usable items.
        try:
            from .fastdl_api import FastDLStoriesAPI
            api = FastDLStoriesAPI()
            api_items = api.fetch_stories(username)
            if api_items is not None:
                logger.info(f"FastDL Stories API success with stories, items={len(api_items)}")
                normalized = []
                for it in api_items:
                    # Preserve API publish time when available so filenames
                    # are deterministic and unique. The API provides
                    # `taken_at` as a unix timestamp inside `raw`.
                    taken = None
                    ta_val = None
                    try:
                        raw = it.get('raw') or {}
                        ta = raw.get('taken_at')
                        if isinstance(ta, (int, float)):
                            ta_val = int(ta)
                    except Exception:
                        ta_val = None
                    # Preserve raw unix timestamp as 'ta' when available. Formatting
                    # to a human string is deferred until filename generation so
                    # timezone handling can be explicit and reversible.
                    normalized.append({
                        'u': it.get('u'),
                        'ta': ta_val,
                        'txt': None,
                    })
                if normalized:
                    return normalized
                logger.warning(
                    "FastDL Stories API success but 0 usable stories returned. "
                    "DOM extraction remains archived and is not executed automatically. "
                    "DOM archive path: src/story_downloader.py::_fetch_story_urls; docs/FASTDL_STORIES_ARCHITECTURE.md."
                )
                return None
            logger.warning(
                "FastDL Stories API/bridge error or empty response. "
                "DOM extraction remains archived and is not executed automatically. "
                "DOM archive path: src/story_downloader.py::_fetch_story_urls; docs/FASTDL_STORIES_ARCHITECTURE.md."
            )
            return None
        except Exception as exc:
            stage = "waiting_for_response" if isinstance(exc, PlaywrightTimeout) else "api_bridge"
            timeout_value = 20 if isinstance(exc, PlaywrightTimeout) else None
            logger.error(
                "FastDL API bridge failure username=%s stage=%s exception_type=%s exception_message=%s%s "
                "DOM extraction remains archived and is not executed automatically. "
                "DOM archive path: src/story_downloader.py::_fetch_story_urls; docs/FASTDL_STORIES_ARCHITECTURE.md.",
                username,
                stage,
                type(exc).__name__,
                str(exc),
                f" timeout_seconds={timeout_value}" if timeout_value is not None else "",
            )
            return None

        logger.warning(
            "FastDL Stories API/bridge error. DOM extraction remains archived and is not executed automatically. "
            "DOM archive path: src/story_downloader.py::_fetch_story_urls; docs/FASTDL_STORIES_ARCHITECTURE.md."
        )
        return None

        # The DOM extraction logic is intentionally preserved below for future
        # reference, but it is not executed automatically from the API-first path.
        if False:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                )
                try:
                    context = browser.new_context(
                        user_agent=USER_AGENT,
                        viewport={"width": 1280, "height": 720},
                        locale="en-US",
                    )
                    page = context.new_page()
                    page.goto(VIEWER_URL, timeout=PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded")
                    page.wait_for_selector(
                        "#search-form-input",
                        timeout=PROFILE_LOAD_TIMEOUT,
                        state="visible",
                    )
                    page.fill("#search-form-input", username)
                    page.click("#searchFormButton")
                    try:
                        page.wait_for_selector(
                            ".user-info", timeout=PROFILE_LOAD_TIMEOUT, state="visible"
                        )
                    except PlaywrightTimeout:
                        return None

                    stories_tab = page.locator(
                        "button.tabs-component__button"
                    ).filter(has_text="Stories")
                    if stories_tab.count() == 0:
                        return []
                    self._close_popups(page)
                    page.evaluate(
                        """() => {
                            const bs = document.querySelectorAll('button.tabs-component__button');
                            for (const b of bs) {
                                if (b.innerText.toLowerCase().includes('stories')) {
                                    b.scrollIntoView();
                                    b.click();
                                    return true;
                                }
                            }
                            return false;
                        }"""
                    )
                    self._close_popups(page)
                    try:
                        page.wait_for_selector(".media-content--story", timeout=STORIES_LOAD_TIMEOUT, state="visible")
                        page.wait_for_selector(".media-content__meta-time", timeout=STORIES_LOAD_TIMEOUT, state="visible")
                    except PlaywrightTimeout:
                        return []

                    items = _collect_items_with_scroll(page, max_scrolls=25, wait_ms=500)
                    items = _sort_items_chronologically(items)
                    return items
                finally:
                    browser.close()

    def _close_popups(self, page):
        for sel in [
            "button[aria-label='Close']",
            "button[aria-label='close']",
            ".browser-extension__close",
            ".modal-close",
            ".popup-close",
        ]:
            try:
                loc = page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible(timeout=1000):
                    loc.first.click(force=True, timeout=2000)
                    logger.debug(f"סגרתי פופאפ: {sel}")
                    time.sleep(0.5)
            except Exception:
                pass
        try:
            removed = page.evaluate("""() => {
                const cands = document.querySelectorAll('[class*="hook_panel"], [class*="popup"], [class*="overlay"]');
                for (const c of cands) {
                    const r = c.getBoundingClientRect();
                    if (r.width > window.innerWidth * 0.7 && r.height > window.innerHeight * 0.7) {
                        c.remove();
                        return c.className;
                    }
                }
                return null;
            }""")
            if removed:
                logger.debug(f"הסרתי שכבת-על: {removed}")
        except Exception:
            pass

    def _download_files(self, stories, user_dir, username):
        downloaded = []
        for idx, s in enumerate(stories, 1):
            url = s['u']
            for attempt in range(1, MAX_RETRIES + 1):
                start_ts = time.time()
                try:
                    media = self._download_media_via_browser_context(url, timeout_seconds=DOWNLOAD_TIMEOUT)
                    content = media["content"]
                    ct = (media["content_type"] or "").lower()
                    # Prefer content-type and signatures over URL extension
                    if "video" in ct or ".mp4" in url.lower() or "video/mp4" in ct:
                        ext = ".mp4"
                    elif "png" in ct or url.lower().endswith(".png"):
                        ext = ".png"
                    elif "webp" in ct or url.lower().endswith(".webp"):
                        ext = ".webp"
                    elif "jpeg" in ct or "jpg" in ct or url.lower().endswith((".jpg", ".jpeg")):
                        ext = ".jpg"
                    else:
                        ext = ".bin"
                    ts = None
                    # Prefer raw unix timestamp if available; format in Israel timezone
                    if s.get('ta'):
                        ts = format_taken_at_for_filename(s.get('ta'))
                    # Fallbacks: relative text like '3 minutes ago'
                    if not ts and (rm := re.search(r'(\d+)\s*(minute|hour|day)', s.get('txt') or '')):
                        n, u = int(rm[1]), rm[2]
                        delta = timedelta(minutes=n) if u.startswith('minute') else (timedelta(hours=n) if u.startswith('hour') else timedelta(days=n))
                        ts = (datetime.now(ZoneInfo('Asia/Jerusalem')) - delta).strftime("%Y-%m-%d_%H-%M-%S")
                    # Fallback: use expires param in url (UTC -> convert to Israel timezone)
                    if not ts and (em := re.search(r'__expires=(\d+)', url)):
                        try:
                            ts = format_taken_at_for_filename(int(em[1]))
                        except Exception:
                            ts = None
                    if not ts:
                        ts = f"unknown_{int(time.time())}_{idx}"

                    filename = f"{username}-{ts}{ext}"
                    p = user_dir / filename

                    # Validate content matches expected media type before saving
                    if ext == '.jpg' and not _is_jpeg(content):
                        raise ValueError(f"content validation failed: expected JPEG but signature missing for url={url}")
                    if ext == '.mp4' and not _is_mp4(content):
                        raise ValueError(f"content validation failed: expected MP4 but 'ftyp' not found for url={url}")

                    p.write_bytes(content)
                    downloaded.append({"path": p, "pre_download_id": s.get("pre_download_id")})
                    logger.info(
                        "FASTDL_MEDIA_DOWNLOAD username=%s story_index=%s status=%s content_type=%s final_url=%s bytes=%s path=%s",
                        username,
                        idx,
                        media["status"],
                        media["content_type"],
                        media["final_url"],
                        len(content),
                        str(p),
                    )
                    logger.debug(f"  [{idx}/{len(stories)}] הורד {filename}")
                    break
                except (requests.HTTPError, ValueError, OSError, PlaywrightTimeout) as exc:
                    # Compute duration and extract minimal signed-url info for diagnostics
                    duration_ms = int((time.time() - start_ts) * 1000)
                    try:
                        parsed = urlparse(url)
                        host = parsed.hostname
                        qs = parse_qs(parsed.query)
                        signed = any(k in parsed.query for k in ("__sig", "token", "access_token", "refresh_token"))
                        expires_vals = qs.get("__expires") or qs.get("expires")
                        expires_in = None
                        if expires_vals:
                            try:
                                expires_ts = int(expires_vals[0])
                                expires_in = int(expires_ts - time.time())
                            except Exception:
                                expires_in = None
                    except Exception:
                        host = None
                        signed = False
                        expires_in = None
                    logger.info(
                        "MEDIA_DOWNLOAD_DEBUG username=%s story_index=%s attempt=%s duration_ms=%s exception_type=%s timeout_seconds=%s signed_url=%s expires_in_seconds=%s host=%s",
                        username,
                        idx,
                        attempt,
                        duration_ms,
                        type(exc).__name__,
                        DOWNLOAD_TIMEOUT,
                        str(signed).lower(),
                        expires_in,
                        host,
                    )
                    if attempt == MAX_RETRIES:
                        logger.warning(f"  [{idx}/{len(stories)}] שגיאת הורדה ב/browser context: {exc} E-DL-001")
                        break
                    time.sleep(RETRY_DELAY)
                except Exception as exc:
                    # General exception: log debug info and break (not retryable)
                    duration_ms = int((time.time() - start_ts) * 1000)
                    try:
                        parsed = urlparse(url)
                        host = parsed.hostname
                        qs = parse_qs(parsed.query)
                        signed = any(k in parsed.query for k in ("__sig", "token", "access_token", "refresh_token"))
                        expires_vals = qs.get("__expires") or qs.get("expires")
                        expires_in = None
                        if expires_vals:
                            try:
                                expires_ts = int(expires_vals[0])
                                expires_in = int(expires_ts - time.time())
                            except Exception:
                                expires_in = None
                    except Exception:
                        host = None
                        signed = False
                        expires_in = None
                    logger.info(
                        "MEDIA_DOWNLOAD_DEBUG username=%s story_index=%s attempt=%s duration_ms=%s exception_type=%s timeout_seconds=%s signed_url=%s expires_in_seconds=%s host=%s",
                        username,
                        idx,
                        attempt,
                        duration_ms,
                        type(exc).__name__,
                        DOWNLOAD_TIMEOUT,
                        str(signed).lower(),
                        expires_in,
                        host,
                    )
                    logger.warning(f"  [{idx}/{len(stories)}] שגיאה כללית בהורדה: {exc} E-DL-001")
                    break
        return downloaded

    def extract_story_id(self, filename):
        m = re.search(r"-(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})", filename)
        if m:
            return m.group(1)
        return Path(filename).stem

    def cleanup(self, username=None, folder_name=None):
        target_name = folder_name or username
        if target_name:
            target = self.output_dir / target_name
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
        else:
            if self.output_dir.exists():
                shutil.rmtree(self.output_dir, ignore_errors=True)
        self._close_browser_context()
