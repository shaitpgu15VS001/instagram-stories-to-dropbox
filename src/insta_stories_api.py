"""מקור סטוריז ראשי: insta-stories.io (ללא Captcha, ללא דפדפן).

זרימה:
1. `GET /content.php?url=<username>` -> מידע פרופיל (GetProfileInfo).
2. `GET /content.php?url=<username>&method=allstories` -> סטוריז (GetAllStories).

החזרת `fetch_stories`:
- רשימת פריטים [{u, kind, txt}] عند הצלחה.
- [] כאשר אין סטוריז פעילים (תשובת error עם "no stories").
- None כאשר הקריאה נכשלה (רשת/מבנה לא צפוי) כדי שהקורא יעבור לגיבוי.
"""
import re
from html import unescape
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, parse_qs, unquote

import requests

BASE_URL = "https://insta-stories.io"
CONTENT_PATH = "/content.php"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
REFERER = "https://insta-stories.io/"

# חותמות יחסיות כפי שהאתר מציג, למשל "21 hours ago" או "just now".
TIME_PATTERN = re.compile(
    r"(\d+\s*(?:second|minute|hour|day)s?\s*ago|just now)", re.IGNORECASE
)
# כרטיס סטורי בודד ב-HTML (עד תחילת הכרטיס הבא).
CARD_START = '<div class="col-md-4 position-relative">'
IMG_SRC_PATTERN = re.compile(r'<img[^>]+src="([^"]+)"')
VIDEO_SRC_PATTERN = re.compile(r"<source[^>]+src=\"([^\"]+)\"")
# קישור הורדה ישיר מועדף (media2.php), נפילה לתצוגה (media.php).
DL_HREF_PATTERN = re.compile(r'href="(https://fr\d+\.anon-viewer\.com/media2\.php\?media=[^"]+)"')
VIEW_HREF_PATTERN = re.compile(r'href="(https://fr\d+\.anon-viewer\.com/media\.php\?media=[^"]+)"')


def extract_media_id(url: Optional[str]) -> Optional[str]:
    """מזהה יציב למניעת כפילויות מתוך קישור anon-viewer.

    הקישור עוטף כתובת CDN בפרמטר `media`, למשל:
    `https://fr9.anon-viewer.com/media.php?media=https%3A%2F%2F...%2F83393_n.jpg%3F...`
    מוחזר ה-path הפנימי (כולל שם הקובץ הייחודי).
    """
    if not url:
        return None
    try:
        qs = parse_qs(urlparse(url).query)
        inner = (qs.get("media") or [""])[0]
        if not inner:
            return None
        decoded = unquote(inner)
        path = urlparse(decoded).path
        return path or None
    except Exception:
        return None


def _pick_url(card_html: str) -> Optional[str]:
    for pattern in (DL_HREF_PATTERN, VIEW_HREF_PATTERN, VIDEO_SRC_PATTERN, IMG_SRC_PATTERN):
        m = pattern.search(card_html)
        if m:
            return unescape(m.group(1)).replace("&amp;", "&")
    return None


def _pick_kind(card_html: str, url: str) -> str:
    low = (card_html + " " + url).lower()
    if "<video" in low or ".mp4" in low:
        return "video"
    return "image"


def parse_stories_html(html: str) -> List[Dict[str, Any]]:
    """מפענח HTML של GetAllStories לרשימת פריטים מסודרת."""
    if not html:
        return []
    starts = [m.start() for m in re.finditer(re.escape(CARD_START), html)]
    if not starts:
        # נפילה: חיפוש גלובלי אם מבנה הכרטיסים השתנה
        urls = re.findall(r'href="(https://fr\d+\.anon-viewer\.com/media2?\.php\?media=[^"]+)"', html)
        times = TIME_PATTERN.findall(html)
        items = []
        for idx, raw_url in enumerate(urls):
            url = unescape(raw_url).replace("&amp;", "&")
            if "/share" in url or "sharer" in url:
                continue
            items.append({
                "u": url,
                "kind": "video" if ".mp4" in url.lower() else "image",
                "txt": times[idx] if idx < len(times) else None,
            })
        return items
    cards = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(html)
        cards.append(html[start:end])
    items = []
    for card in cards:
        url = _pick_url(card)
        if not url:
            continue
        t = TIME_PATTERN.search(card)
        items.append({
            "u": url,
            "kind": _pick_kind(card, url),
            "txt": t.group(1) if t else None,
        })
    return items


class InstaStoriesAPI:
    """לקוח קל למקור insta-stories.io (requests בלבד, בלי דפדפן)."""

    def __init__(self, session: Optional[requests.Session] = None):
        self.s = session or requests.Session()
        self.s.headers.update({"User-Agent": USER_AGENT, "Referer": REFERER})

    def diagnose(self, username: str, timeout: int = 10) -> str:
        """מבחין בין משתמש לא קיים לבין תקלת מקור.

        נקרא רק כאשר `fetch_stories` נכשל. מחזיר:
        - "user_not_found" כאשר האתר עצמו תקין אבל לא מכיר את המשתמש.
        - "api_error" כאשר יש בעיית רשת או שהאתר עצמו נפל.
        """
        username = (username or "").strip().lstrip("@")
        if not username:
            return "api_error"
        profile_ok = False
        try:
            r = self.s.get(
                BASE_URL + CONTENT_PATH,
                params={"url": username},
                timeout=timeout,
            )
            if r.status_code == 200:
                try:
                    body = r.json()
                except Exception:
                    body = None
                if isinstance(body, dict) and body.get("status") == "ok":
                    profile_ok = True
        except Exception:
            profile_ok = False
        if profile_ok:
            # הפרופיל קיים — הכשל הוא בצד הסטוריז או זמני
            return "api_error"
        try:
            home = self.s.get(BASE_URL + "/", timeout=timeout)
            if home.status_code == 200:
                # האתר תקין אבל לא מכיר את המשתמש
                return "user_not_found"
        except Exception:
            pass
        return "api_error"

    def fetch_stories(self, username: str, timeout: int = 20) -> Optional[List[Dict[str, Any]]]:
        username = (username or "").strip().lstrip("@")
        if not username:
            return None
        try:
            stories_resp = self.s.get(
                BASE_URL + CONTENT_PATH,
                params={"url": username, "method": "allstories"},
                timeout=timeout,
            )
        except Exception:
            return None
        if stories_resp.status_code != 200:
            return None
        try:
            body = stories_resp.json()
        except Exception:
            return None
        if not isinstance(body, dict):
            return None
        if body.get("status") == "error":
            msg = str(body.get("msg") or "").lower()
            if "no stories" in msg or "no stor" in msg:
                return []
            return None
        html = body.get("html") or ""
        if not html.strip():
            return []
        items = parse_stories_html(html)
        if not items:
            # HTML לא ריק אבל לא פוענח ממנו דבר — כנראה מבנה האתר השתנה.
            # להחזיר None (שגיאה) ולא [] כדי לא לדווח בטעות "אין סטוריז".
            return None
        return items
