"""בדיקת ClipSaver כמקור סטוריז: טוקן, שאילתת משתמש, והורדת מדיה.

שימוש:
    python scripts/probe_clipssaver.py [username ...]
"""
import sys

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
BASE = "https://clipssaver.com"
TOKEN_URL = BASE + "/api/token"
STORIES_URL = BASE + "/api/instagram/instagramDownloader/stories"
REFERER = BASE + "/instagram-story-viewer"


def new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "application/json", "Referer": REFERER})
    return session


def fetch_token(session: requests.Session) -> str:
    response = session.get(TOKEN_URL, timeout=30)
    response.raise_for_status()
    return (response.json() or {}).get("token", "")


def fetch_stories(session: requests.Session, username: str, token: str) -> dict:
    response = session.post(
        STORIES_URL,
        json={"username": username},
        headers={"x-cs-tok": token},
        timeout=120,
    )
    try:
        body = response.json()
    except Exception:
        body = {"raw": (response.text or "")[:200]}
    return {"http_status": response.status_code, "body": body}


def summarize(username: str, result: dict) -> None:
    body = result["body"]
    print(f"--- {username}: http={result['http_status']} status={body.get('status')}")
    data = body.get("data") or {}
    stories = data.get("stories") or []
    if not isinstance(stories, list):
        stories = []
    print(f"    stories={len(stories)}")
    if stories:
        first = stories[0]
        print(
            "    first: isVideo={} takenAt={} expiringAt={} downloadUrl={}".format(
                first.get("isVideo"),
                first.get("takenAt"),
                first.get("expiringAt"),
                str(first.get("downloadUrl"))[:70],
            )
        )
    if not stories:
        print(f"    body={str(body)[:300]}")


def check_media(session: requests.Session, url: str) -> None:
    response = session.get(url, timeout=90, stream=True)
    length = 0
    for chunk in response.iter_content(65536):
        length += len(chunk)
        if length > 2_000_000:
            break
    response.close()
    print(f"    media: status={response.status_code} type={response.headers.get('content-type')} bytes~{length}")


def main() -> int:
    usernames = sys.argv[1:] or ["idfonline", "djyochaiedri", "zzz_no_such_user_zzz_98765"]
    session = new_session()
    token = fetch_token(session)
    print(f"token_len={len(token)}")
    first_media_url = None
    for username in usernames:
        result = fetch_stories(session, username, token)
        summarize(username, result)
        stories = (result["body"].get("data") or {}).get("stories") or []
        if stories and first_media_url is None:
            first_media_url = stories[0].get("downloadUrl")
    if first_media_url:
        check_media(session, first_media_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
