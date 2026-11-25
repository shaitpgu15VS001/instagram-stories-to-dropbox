"""מקור סטוריז ראשי: ClipSaver (clipssaver.com) — API בלבד, בלי דפדפן.

זרימה:
1. `GET /api/token` -> {"ok": true, "token": "v1..."}
2. `POST /api/instagram/instagramDownloader/stories`
   גוף: {"username": "<user>"} , כותרת: `x-cs-tok: <token>`

החזרת `fetch_stories`:
- רשימת פריטים [{u, kind, ta, id}] כאשר נמצאו סטוריז.
- [] כאשר אין סטוריז פעילים (תשובה מוצהרת של המקור).
- None כאשר הקריאה נכשלה או שהתשובה אינה מוכרת (כולל עומס זמני),
  כדי שהקורא יעבור למקור הבא ולא ידווח בטעות "אין סטוריז".
"""
from typing import Any, Dict, List, Optional

import requests

BASE_URL = "https://clipssaver.com"
TOKEN_URL = BASE_URL + "/api/token"
STORIES_URL = BASE_URL + "/api/instagram/instagramDownloader/stories"
REFERER = BASE_URL + "/instagram-story-viewer"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class ClipSaverAPI:
    """לקוח קל למקור clipssaver.com (requests בלבד)."""

    def __init__(self, session: Optional[requests.Session] = None):
        self.s = session or requests.Session()
        self.s.headers.update(
            {"User-Agent": USER_AGENT, "Accept": "application/json", "Referer": REFERER}
        )
        # סיבת הכשל האחרונה (אבחון בלבד, לא משפיע על זרימת הקריאה)
        self.last_error: Optional[str] = None
        self._token: Optional[str] = None

    def _fetch_token(self, timeout: int = 20) -> Optional[str]:
        try:
            resp = self.s.get(TOKEN_URL, timeout=timeout)
        except Exception as exc:
            self.last_error = f"token_request_failed: {exc}"
            return None
        if resp.status_code != 200:
            self.last_error = f"token_http_status={resp.status_code}"
            return None
        try:
            body = resp.json()
        except Exception as exc:
            self.last_error = f"token_invalid_json: {exc}"
            return None
        token = body.get("token") if isinstance(body, dict) else None
        if not isinstance(token, str) or not token:
            self.last_error = "token_missing"
            return None
        self._token = token
        return token

    @staticmethod
    def _normalize(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        is_video = bool(raw.get("isVideo")) or str(raw.get("mediaType") or "") == "2"
        url = raw.get("downloadUrl") or raw.get("videoUrl") or raw.get("displayUrl")
        if not isinstance(url, str) or not url:
            return None
        story_id = raw.get("id")
        return {
            "u": url,
            "kind": "video" if is_video else "image",
            "ta": _as_int(raw.get("takenAt")),
            "id": str(story_id) if story_id not in (None, "") else None,
        }

    def _handle_body(self, body: Any) -> Optional[List[Dict[str, Any]]]:
        if not isinstance(body, dict):
            self.last_error = f"unexpected_body_type={type(body).__name__}"
            return None
        status = str(body.get("status") or "").strip().lower()
        if status != "success":
            msg = body.get("msg") or body.get("message") or ""
            self.last_error = f"status={status or 'missing'} msg={msg}".strip()
            return None
        data = body.get("data")
        if not isinstance(data, dict):
            self.last_error = "missing_data_object"
            return None
        raw_stories = data.get("stories")
        if not isinstance(raw_stories, list):
            self.last_error = "missing_stories_list"
            return None
        # עומס זמני בצד המקור: stories ריק לצד reason/retryable — כשל, לא "אין סטוריז".
        if data.get("retryable") or data.get("reason"):
            self.last_error = (
                f"upstream_unavailable reason={data.get('reason')} "
                f"retry_after={data.get('retryAfter')}"
            )
            return None
        items = []
        for raw in raw_stories:
            if not isinstance(raw, dict):
                continue
            item = self._normalize(raw)
            if item:
                items.append(item)
        if raw_stories and not items:
            self.last_error = "stories_present_but_no_usable_media_url"
            return None
        return items

    def fetch_stories(self, username: str, timeout: int = 30) -> Optional[List[Dict[str, Any]]]:
        self.last_error = None
        username = (username or "").strip().lstrip("@")
        if not username:
            self.last_error = "username ריק"
            return None
        for attempt in (1, 2):
            token = self._token or self._fetch_token(timeout=timeout)
            if not token:
                return None
            try:
                resp = self.s.post(
                    STORIES_URL,
                    json={"username": username},
                    headers={"x-cs-tok": token},
                    timeout=timeout,
                )
            except Exception as exc:
                self.last_error = f"request_failed: {exc}"
                return None
            if resp.status_code in (401, 403) and attempt == 1:
                # טוקן שפג — מרעננים פעם אחת ומנסים שוב.
                self._token = None
                continue
            if resp.status_code != 200:
                self.last_error = f"http_status={resp.status_code}"
                return None
            try:
                body = resp.json()
            except Exception as exc:
                self.last_error = f"invalid_json: {exc}"
                return None
            return self._handle_body(body)
        return None
