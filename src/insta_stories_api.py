"""מקור סטוריז משני: insta-stories.io (ללא דפדפן).

משמש כגיבוי כאשר המקור הראשי (ClipSaver) נכשל.

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
        # סיבת הכשל האחרונה (אבחון בלבד, לא משפיע על זרימת הקריאה)
        self.last_error: Optional[str] = None

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
        self.last_error = None
        username = (username or "").strip().lstrip("@")
        if not username:
            self.last_error = "username ריק"
            return None
        try:
            stories_resp = self.s.get(
                BASE_URL + CONTENT_PATH,
                params={"url": username, "method": "allstories"},
                timeout=timeout,
            )
        except Exception as exc:
            self.last_error = f"request_failed: {exc}"
            return None
        if stories_resp.status_code != 200:
            self.last_error = f"http_status={stories_resp.status_code}"
            return None
        try:
            body = stories_resp.json()
        except Exception as exc:
            self.last_error = f"invalid_json: {exc}"
            return None
        if not isinstance(body, dict):
            self.last_error = f"unexpected_body_type={type(body).__name__}"
            return None
        status = str(body.get("status") or "").strip().lower()
        msg = str(body.get("msg") or "")
        if status == "error":
            low_msg = msg.lower()
            if "no stories" in low_msg or "no stor" in low_msg:
                # תשובת "אין סטוריז פעילים" מפורשת — תוצאה תקינה, לא כשל.
                return []
            self.last_error = f"status=error msg={msg}"
            return None
        if status != "ok":
            # תשובה לא מוכרת (למשל status=Refresh / Captcha) — זה כשל מקור,
            # אסור להחזיר [] כי זה מדווח בטעות "אין סטוריז" ומבטל גיבוי/אבחון.
            self.last_error = f"unexpected_status={body.get('status')} msg={msg}"
            return None
        html = body.get("html") or ""
        if not html.strip():
            # status=ok אך ללא html — נשמר כפי שהיה: "אין סטוריז".
            # (האות המוצהר של האתר ל"אין סטוריז" הוא status=error.)
            return []
        items = parse_stories_html(html)
        if not items:
            # HTML לא ריק אבל לא פוענח ממנו דבר — כנראה מבנה האתר השתנה.
            # להחזיר None (שגיאה) ולא [] כדי לא לדווח בטעות "אין סטוריז".
            self.last_error = "html_parsed_to_zero_items (layout changed?)"
            return None
        return items
