"""מוריד סטוריז מ-Instagram דרך viewsocials.com (עם cookies של הדפדפן)"""
import re
import shutil
import time
import urllib.parse
from pathlib import Path

from curl_cffi import requests as cc_requests
from playwright.sync_api import TimeoutError as PlaywrightTimeout, sync_playwright

from .logger import logger

PROFILE_URL = "https://www.viewsocials.com/profile/{username}"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
STORIES_DIR = Path("stories")
PAGE_LOAD_TIMEOUT = 60000
STORIES_LOAD_TIMEOUT = 30000
DOWNLOAD_TIMEOUT = 120
MEDIA_EXTENSIONS = {".mp4", ".jpg", ".jpeg", ".png", ".webp", ".mov"}
DOWNLOAD_BTN = 'a[href*="download-action"]'
POPUP_DIALOG = '[role="dialog"]'
POPUP_CLOSE = 'button[aria-label="Close"]'


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
        files = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]
                )
                try:
                    context = browser.new_context(
                        user_agent=USER_AGENT, viewport={"width": 1280, "height": 720}, locale="en-US"
                    )
                    page = context.new_page()
                    try:
                        urls = self._fetch_story_urls(page, username)
                    except PlaywrightTimeout:
                        logger.error(f"פג הזמן בטעינת viewsocials.com עבור @{username}")
                        return {"success": False, "files": [], "error": "timeout"}
                    if urls is None:
                        return {"success": False, "files": [], "error": "user_not_found"}
                    if not urls:
                        logger.info(f"@{username}: אין סטוריז פעילים כרגע")
                        return {"success": True, "files": [], "error": None}
                    files = self._download_files(urls, user_dir, page, context)
                finally:
                    browser.close()
        except Exception as exc:
            logger.error(f"שגיאה בגלישה ל-viewsocials.com עבור @{username}: {exc}")
            return {"success": False, "files": [], "error": str(exc)}

        if not files:
            return {"success": False, "files": [], "error": "download_failed"}
        logger.success(f"@{username}: הורדו {len(files)} קבצים")
        return {"success": True, "files": files, "error": None}

    def _fetch_story_urls(self, page, username):
        page.goto(
            PROFILE_URL.format(username=username),
            timeout=PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded",
        )
        body_text = page.inner_text("body")
        if "404" in body_text and "NOT FOUND" in body_text:
            logger.warning(f"@{username}: משתמש פרטי או לא קיים")
            return None
        self._close_popup(page)
        try:
            page.wait_for_selector(DOWNLOAD_BTN, timeout=STORIES_LOAD_TIMEOUT, state="visible")
        except PlaywrightTimeout:
            return None
        urls = page.eval_on_selector_all(
            DOWNLOAD_BTN,
            "els => els.map(el => el.href).filter(h => h && h.includes('download-action'))",
        )
        return list(dict.fromkeys(urls))

    def _close_popup(self, page):
        try:
            dialog = page.locator(POPUP_DIALOG)
            if dialog.count() == 0:
                return
            if not dialog.first.is_visible(timeout=2000):
                return
            try:
                page.click(POPUP_CLOSE, force=True, timeout=2000)
            except Exception:
                dialog.first.evaluate("el => el.remove()")
        except Exception as exc:
            logger.debug(f"סגירת פופאפ נכשלה (לא קריטי): {exc}")

    def _download_files(self, urls, user_dir, page, context):
        downloaded = []
        total = len(urls)
        for idx, url in enumerate(urls, 1):
            result = (self._download_via_click(page, url)
                      or self._download_via_curl_cffi(context, url)
                      or self._download_via_context(context, url))
            if result is None:
                logger.warning(f"  [{idx}/{total}] כל השיטות נכשלו")
                continue
            body, headers = result
            filename = self._make_filename(url, headers, idx)
            filepath = user_dir / filename
            filepath.write_bytes(body)
            downloaded.append(filepath)
            logger.debug(f"  [{idx}/{total}] הורד {filename}")
        return downloaded

    def _download_via_context(self, context, url):
        try:
            response = context.request.get(url, timeout=DOWNLOAD_TIMEOUT * 1000)
            logger.debug(f"context.request: status={response.status}")
            if response.status != 200:
                return None
            return response.body(), dict(response.headers)
        except Exception as exc:
            logger.debug(f"context.request exc: {type(exc).__name__}: {exc}")
            return None

    def _download_via_click(self, page, url):
        try:
            with page.expect_download(timeout=DOWNLOAD_TIMEOUT * 1000) as dl_info:
                page.evaluate(
                    """(u) => {
                        const ls = document.querySelectorAll('a[href*="download-action"]');
                        for (const l of ls) if (l.href === u) { l.click(); break; }
                    }""", url)
            download = dl_info.value
            return Path(download.path()).read_bytes(), {}
        except Exception as exc:
            logger.debug(f"click exc: {type(exc).__name__}: {exc}")
            return None

    def _download_via_curl_cffi(self, context, url):
        try:
            cookies = {c["name"]: c["value"] for c in context.cookies()}
            headers = {"User-Agent": USER_AGENT,
                "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
                "Referer": "https://www.viewsocials.com/"}
            response = cc_requests.get(url, cookies=cookies, headers=headers,
                impersonate="chrome", timeout=DOWNLOAD_TIMEOUT)
            logger.debug(f"curl_cffi: status={response.status_code}")
            if response.status_code != 200: return None
            return response.content, dict(response.headers)
        except Exception as exc:
            logger.debug(f"curl_cffi exc: {type(exc).__name__}: {exc}")
            return None

    def _make_filename(self, url, headers, idx):
        ig_name = self._extract_instagram_filename(url)
        if ig_name:
            return ig_name
        cd = headers.get("content-disposition", "")
        match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';\r\n]+)', cd, re.IGNORECASE)
        ext = self._ext_from_content_type(headers.get("content-type", ""))
        if match:
            name = urllib.parse.unquote(match.group(1).strip())
            return name if Path(name).suffix.lower() in MEDIA_EXTENSIONS else f"{name}{ext}"
        return f"story_{int(time.time())}_{idx}{ext}"

    def _extract_instagram_filename(self, url):
        try:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            inner = qs.get("url", [""])[0]
            if not inner:
                return None
            decoded = urllib.parse.unquote(inner)
            qs2 = urllib.parse.parse_qs(urllib.parse.urlparse(decoded).query)
            final = urllib.parse.unquote(qs2.get("url", [""])[0] or decoded)
            return Path(urllib.parse.urlparse(final).path).name
        except Exception:
            return None

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
        match = re.match(r"^(\d+)_\d+_\d+_n$", name)
        if match:
            return f"{match.group(1)}_{name.split('_')[1]}_{name.split('_')[2]}"
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
