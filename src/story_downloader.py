"""מוריד סטוריז מ-Instagram דרך fastdl.app"""
import re
import shutil
import time
import urllib.parse
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
STORIES_LOAD_TIMEOUT = 20000
DOWNLOAD_TIMEOUT = 60
MEDIA_EXTENSIONS = {".mp4", ".jpg", ".jpeg", ".png", ".webp", ".mov"}


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
            logger.warning(f"@{username}: משתמש פרטי או לא קיים")
            return {"success": False, "files": [], "error": "user_not_found"}
        if not download_urls:
            logger.info(f"@{username}: אין סטוריז פעילים כרגע")
            return {"success": True, "files": [], "error": None}

        files = self._download_files(download_urls, user_dir)
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
                    page.wait_for_selector(
                        ".media-content--story",
                        timeout=STORIES_LOAD_TIMEOUT,
                        state="visible",
                    )
                except PlaywrightTimeout:
                    return []

                urls = page.eval_on_selector_all(
                    ".button__download",
                    "els => els.map(el => el.href).filter(h => h && h.includes('media.fastdl.app'))",
                )
                return list(dict.fromkeys(urls))
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

    def _download_files(self, urls, user_dir):
        downloaded = []
        total = len(urls)
        for idx, url in enumerate(urls, 1):
            try:
                response = requests.get(url, timeout=DOWNLOAD_TIMEOUT)
                response.raise_for_status()
                filename = self._make_filename(url, response, idx)
                filepath = user_dir / filename
                filepath.write_bytes(response.content)
                downloaded.append(filepath)
                logger.debug(f"  [{idx}/{total}] הורד {filename}")
            except requests.RequestException as exc:
                logger.warning(f"  [{idx}/{total}] שגיאת רשת: {exc}")
            except OSError as exc:
                logger.warning(f"  [{idx}/{total}] שגיאת כתיבה: {exc}")
        return downloaded

    def _make_filename(self, url, response, idx):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        ext = self._ext_from_content_type(response.headers.get("content-type", ""))
        if "filename" in params:
            name = urllib.parse.unquote(params["filename"][0])
            if not Path(name).suffix:
                name = f"{name}{ext}"
            return name
        return f"story_{int(time.time())}_{idx}{ext}"

    @staticmethod
    def _ext_from_content_type(content_type):
        ct = (content_type or "").lower()
        if "mp4" in ct or "video" in ct:
            return ".mp4"
        if "png" in ct:
            return ".png"
        if "webp" in ct:
            return ".webp"
        return ".jpg"

    def extract_story_id(self, filename):
        name = Path(filename).stem
        match = re.match(r"^(\d{10,25})$", name)
        if match:
            return match.group(1)
        return name

    def cleanup(self, username=None):
        if username:
            target = self.output_dir / username
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
        else:
            if self.output_dir.exists():
                shutil.rmtree(self.output_dir, ignore_errors=True)
