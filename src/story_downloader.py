"""מוריד סטוריז מ-Instagram דרך fastdl.app"""
import re
import shutil
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeout, sync_playwright
from urllib.parse import urlparse, parse_qs, unquote
import json


def extract_pre_download_id(href):
    """Extract canonical uri_path from a FastDL download href before downloading.

    Returns the path component of the decoded `uri` query parameter, or None.
    """
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


def _parse_meta_timestamp(s):
    """Parse timestamp from an item dict (tries absolute t, relative txt, __expires in url)."""
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
    # Attach parsed timestamp if available
    for it in items:
        it['_parsed_ts'] = _parse_meta_timestamp(it)
    # If any item has a parsed timestamp, sort by it ascending (oldest first)
    if any(it.get('_parsed_ts') for it in items):
        items.sort(key=lambda s: (s.get('_parsed_ts') is None, s.get('_parsed_ts') or datetime.max.replace(tzinfo=timezone.utc)))
        return items
    # Fallback: group by row (y) then x (left->right)
    ROW_TOL = 30.0
    items.sort(key=lambda s: (round(s.get('y', 0) / ROW_TOL), s.get('x', 0)))
    return items


def _collect_items_with_scroll(page, max_scrolls=25, wait_ms=500):
    prev = -1
    for _ in range(max_scrolls):
        try:
            count = page.evaluate("() => document.querySelectorAll('.profile-media-list__item').length")
        except Exception:
            count = 0
        if count == prev:
            break
        prev = count
        try:
            page.evaluate(
                "() => { const items = document.querySelectorAll('.profile-media-list__item'); if (items.length) { items[items.length-1].scrollIntoView(); return true; } return false; }"
            )
        except Exception:
            pass
        try:
            page.wait_for_timeout(wait_ms)
        except Exception:
            time.sleep(wait_ms / 1000.0)

    items = page.evaluate("""() => Array.from(document.querySelectorAll('.profile-media-list__item'))
        .map(li => {
            const r = li.getBoundingClientRect();
            const t = li.querySelector('.media-content__meta-time');
            return {u: li.querySelector('.button__download')?.href, x: r.x, y: r.y, t: t?.title, txt: t?.innerText?.trim()};
        })
        .filter(s => s.u)""")
    return items


class StoryDownloader:

    def __init__(self, output_dir=STORIES_DIR):
        self.output_dir = Path(output_dir)

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
        # Backwards-compatible signature: if caller wants pre-download skipping, pass a `state` via keyword
        # New callers may call: download_stories(username, folder_name=..., state=state_manager)
        state = None
        # allow state passed as kw in older-style calls; inspect kwargs if present
        # (function kept simple; callers pass state explicitly)
        username = username.strip().lstrip("@")
        if not username:
            return {"success": False, "files": [], "error": "שם משתמש ריק"}

        target_name = folder_name or username
        logger.info(f"DOWNLOAD REQUEST username={username} folder_name={folder_name} target_dir={self.output_dir / target_name}")
        user_dir = self.output_dir / target_name
        user_dir.mkdir(parents=True, exist_ok=True)
        # Preserve existing files from previous runs. Do not delete them here.
        existing_files = [p for p in sorted(user_dir.iterdir()) if p.is_file()] if user_dir.exists() else []

        logger.info(f"מוריד סטוריז עבור @{username}...")
        try:
            # support optional state parameter passed by caller
            # callers using keyword args will pass `state` to this function
            # (we can't access kwargs here, so allow caller to call with attribute set)
            download_urls = self._fetch_story_urls(username)
        except PlaywrightTimeout:
            logger.warning(f"@{username}: timeout בחיפוש - מנסה שוב פעם אחת")
            try:
                download_urls = self._fetch_story_urls(username)
            except PlaywrightTimeout:
                logger.error(f"@{username}: timeout חוזר - מדלג")
                # If there are existing files, return them as pending for upload
                if existing_files:
                    return {"success": True, "files": existing_files, "error": None}
                return {"success": False, "files": [], "error": "timeout"}
            except Exception as exc:
                logger.error(f"שגיאה בגלישה ל-fastdl.app עבור @{username}: {exc}")
                if existing_files:
                    return {"success": True, "files": existing_files, "error": None}
                return {"success": False, "files": [], "error": str(exc)}
        except Exception as exc:
            logger.error(f"שגיאה בגלישה ל-fastdl.app עבור @{username}: {exc}")
            if existing_files:
                return {"success": True, "files": existing_files, "error": None}
            return {"success": False, "files": [], "error": str(exc)}

        if download_urls is None:
            logger.warning(f"@{username}: לא נמצא מידע (פרטי/לא קיים/טעינה איטית)")
            if existing_files:
                return {"success": True, "files": existing_files, "error": None}
            return {"success": False, "files": [], "error": "user_not_found"}

        if not download_urls:
            logger.info(f"@{username}: אין סטוריז פעילים כרגע")
            # If there are existing files from a previous run, return them for processing
            if existing_files:
                return {"success": True, "files": existing_files, "error": None}
            return {"success": True, "files": [], "error": None}

        # Default: no pre-download skipping
        new_files_meta = {}

        # If caller provided an attached state on this instance, it should be set as attribute
        state = getattr(self, "state_manager", None)

        # If state is present, perform pre-download check and skip items before downloading
        if state:
            filtered = []
            for s in download_urls:
                url = s.get("u")
                pre_id = extract_pre_download_id(url)
                if pre_id:
                    # check per-username + pre_download_id
                    if state.is_uploaded(username, pre_id):
                        logger.info(f"[SKIP] Story already uploaded: {pre_id}")
                        continue
                    else:
                        logger.info(f"[NEW] Story not found in state: {pre_id}")
                else:
                    logger.warning("[WARN] Could not extract pre-download ID; using legacy flow")
                # include story for download
                s["pre_download_id"] = pre_id
                filtered.append(s)
            to_download = filtered
        else:
            to_download = download_urls

        # If state filtering removed all available stories, treat this as success
        # (no downloads required) rather than a download failure. This specifically
        # handles the case where `download_urls` was non-empty but every item was
        # skipped due to `state.is_uploaded(...)`.
        if state and download_urls and not to_download:
            if existing_files:
                return {"success": True, "files": existing_files, "error": None}
            return {"success": True, "files": [], "error": None}

        new_files = self._download_files(to_download, user_dir, username)
        # new_files is list of dicts {'path': Path, 'pre_download_id': str}
        if new_files is None:
            # download failed; if existing files exist, return them, else report failure
            if existing_files:
                return {"success": True, "files": existing_files, "error": None}
            return {"success": False, "files": [], "error": "download_failed"}

        # new_files may be returned as list of dicts with metadata
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

        # Combine existing files and new files, avoiding duplicates by name
        existing_names = {p.name for p in existing_files}
        combined = list(existing_files) + [p for p in files_return if p.name not in existing_names]
        if not combined:
            return {"success": False, "files": [], "error": "download_failed"}
        logger.success(f"@{username}: הורדו {len(files_return)} קבצים (קיימים: {len(existing_files)})")
        return {"success": True, "files": combined, "meta": meta_map, "error": None}

    def _fetch_story_urls(self, username):
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

                # Ensure we load more items by scrolling until the count stabilizes
                def _collect_items_with_scroll(page, max_scrolls=25, wait_ms=500):
                    prev = -1
                    for _ in range(max_scrolls):
                        try:
                            count = page.evaluate("() => document.querySelectorAll('.profile-media-list__item').length")
                        except Exception:
                            count = 0
                        if count == prev:
                            break
                        prev = count
                        # Scroll the last item into view to trigger lazy loading
                        try:
                            page.evaluate(
                                "() => { const items = document.querySelectorAll('.profile-media-list__item'); if (items.length) { items[items.length-1].scrollIntoView(); return true; } return false; }"
                            )
                        except Exception:
                            pass
                        # wait a bit for network / render
                        try:
                            page.wait_for_timeout(wait_ms)
                        except Exception:
                            time.sleep(wait_ms / 1000.0)

                    # After scrolling, collect all items
                    items = page.evaluate("""() => Array.from(document.querySelectorAll('.profile-media-list__item'))
                        .map(li => {
                            const r = li.getBoundingClientRect();
                            const t = li.querySelector('.media-content__meta-time');
                            return {u: li.querySelector('.button__download')?.href, x: r.x, y: r.y, t: t?.title, txt: t?.innerText?.trim()};
                        })
                        .filter(s => s.u)""")
                    return items

                def _parse_meta_timestamp(s):
                    # Try absolute timestamp in t (e.g., '1.2.2023, 12:34:56' or '01.02.2023, 12:34:56')
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
                    # Try relative times in txt like '5 minutes ago' or '5 minute'
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
                    # Try expires param in URL if present
                    if s.get('u'):
                        em = re.search(r'__expires=(\d+)', s.get('u'))
                        if em:
                            try:
                                return datetime.fromtimestamp(int(em[1]), tz=timezone.utc)
                            except Exception:
                                pass
                    return None

                def _sort_items_chronologically(items):
                    # Attach parsed timestamp if available
                    for it in items:
                        it['_parsed_ts'] = _parse_meta_timestamp(it)
                    # If any item has a parsed timestamp, sort by it ascending (oldest first)
                    if any(it.get('_parsed_ts') for it in items):
                        # Items without timestamp go to the end; stable sort
                        items.sort(key=lambda s: (s.get('_parsed_ts') is None, s.get('_parsed_ts') or datetime.max.replace(tzinfo=timezone.utc)))
                        return items
                    # Fallback: group by row (y) then x (left->right)
                    ROW_TOL = 30.0
                    items.sort(key=lambda s: (round(s.get('y', 0) / ROW_TOL), s.get('x', 0)))
                    return items

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
                const cands = document.querySelectorAll('[class*=\"hook_panel\"], [class*=\"popup\"], [class*=\"overlay\"]');
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
                try:
                    r = requests.get(url, timeout=DOWNLOAD_TIMEOUT)
                    r.raise_for_status()
                    ct = r.headers.get("content-type", "").lower()
                    ext = ".mp4" if "mp4" in ct or "video" in ct else ".png" if "png" in ct else ".webp" if "webp" in ct else ".jpg"
                    ts = None
                    m = re.match(r"(\d+)\.(\d+)\.(\d+),?\s+(\d+):(\d+):(\d+)", s.get('t') or "")
                    if m:
                        d, mo, y, h, mi, sec = m.groups()
                        ts = f"{y}-{int(mo):02d}-{int(d):02d}_{int(h):02d}-{int(mi):02d}-{int(sec):02d}"
                    if not ts and (rm := re.search(r'(\d+)\s*(minute|hour|day)', s.get('txt') or '')):
                        n, u = int(rm[1]), rm[2]
                        ts = (datetime.now(timezone.utc) - {"m": timedelta(minutes=n), "h": timedelta(hours=n), "d": timedelta(days=n)}[u[0]]).strftime("%Y-%m-%d_%H-%M-%S")
                    if not ts and (em := re.search(r'__expires=(\d+)', url)):
                        ts = datetime.fromtimestamp(int(em[1]), tz=timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
                    if not ts:
                        ts = f"unknown_{int(time.time())}_{idx}"
                    filename = f"{username}-{ts}{ext}"
                    p = user_dir / filename
                    p.write_bytes(r.content)
                    # Return path along with optional pre_download_id if present
                    downloaded.append({"path": p, "pre_download_id": s.get("pre_download_id")})
                    logger.debug(f"  [{idx}/{len(stories)}] הורד {filename}")
                    break
                except requests.HTTPError as exc:
                    code = exc.response.status_code if exc.response else 0
                    if code not in RETRYABLE or attempt == MAX_RETRIES:
                        logger.warning(f"  [{idx}/{len(stories)}] שגיאת רשת: {exc}")
                        break
                    time.sleep(RETRY_DELAY)
                except (requests.RequestException, OSError) as exc:
                    logger.warning(f"  [{idx}/{len(stories)}] שגיאה: {exc}")
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
