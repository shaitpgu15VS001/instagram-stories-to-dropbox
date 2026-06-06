"""מוריד סטוריז מ-Instagram דרך fastdl.app"""
import re
import shutil
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeout, sync_playwright

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

    def download_stories(self, username):
        username = username.strip().lstrip("@")
        if not username:
            return {"success": False, "files": [], "error": "שם משתמש ריק"}

        user_dir = self.output_dir / username
        user_dir.mkdir(parents=True, exist_ok=True)
        for item in user_dir.iterdir():
            try:
                if item.is_file():
                    item.unlink()
            except OSError as exc:
                logger.warning(f"לא ניתן למחוק {item}: {exc}")

        logger.info(f"מוריד סטוריז עבור @{username}...")
        try:
            download_urls = self._fetch_story_urls(username)
        except PlaywrightTimeout:
            logger.warning(f"@{username}: timeout בחיפוש - מנסה שוב פעם אחת")
            try:
                download_urls = self._fetch_story_urls(username)
            except PlaywrightTimeout:
                logger.error(f"@{username}: timeout חוזר - מדלג")
                return {"success": False, "files": [], "error": "timeout"}
            except Exception as exc:
                logger.error(f"שגיאה בגלישה ל-fastdl.app עבור @{username}: {exc}")
                return {"success": False, "files": [], "error": str(exc)}
        except Exception as exc:
            logger.error(f"שגיאה בגלישה ל-fastdl.app עבור @{username}: {exc}")
            return {"success": False, "files": [], "error": str(exc)}

        if download_urls is None:
            logger.warning(f"@{username}: לא נמצא מידע (פרטי/לא קיים/טעינה איטית)")
            return {"success": False, "files": [], "error": "user_not_found"}
        if not download_urls:
            logger.info(f"@{username}: אין סטוריז פעילים כרגע")
            return {"success": True, "files": [], "error": None}

        files = self._download_files(download_urls, user_dir, username)
        if not files:
            return {"success": False, "files": [], "error": "download_failed"}
        logger.success(f"@{username}: הורדו {len(files)} קבצים")
        return {"success": True, "files": files, "error": None}

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

                items = page.evaluate("""() => Array.from(document.querySelectorAll('.profile-media-list__item'))
                    .map(li => {
                        const r = li.getBoundingClientRect();
                        const t = li.querySelector('.media-content__meta-time');
                        return {u: li.querySelector('.button__download')?.href, x: r.x, y: r.y, t: t?.title, txt: t?.innerText?.trim()};
                    })
                    .filter(s => s.u)""")
                items.sort(key=lambda s: (-s['x'], s['y']))
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
                    downloaded.append(p)
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

    def cleanup(self, username=None):
        if username:
            target = self.output_dir / username
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
        else:
            if self.output_dir.exists():
                shutil.rmtree(self.output_dir, ignore_errors=True)
