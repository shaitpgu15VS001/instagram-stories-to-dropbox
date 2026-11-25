"""בדיקות לקליינט ClipSaver: פיענוח תשובות, טוקן, ומקרי כשל."""
from src.clipssaver_api import ClipSaverAPI


class FakeResp:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class FakeSession:
    """סשן מדומה: token get + stories post, עם תור תשובות."""

    def __init__(self, token_bodies=None, story_responses=None):
        self.headers = {}
        self.token_bodies = token_bodies or [{"ok": True, "token": "tok-1"}]
        self.story_responses = story_responses or []
        self.get_calls = 0
        self.posts = []

    def get(self, url, timeout=None):
        index = min(self.get_calls, len(self.token_bodies) - 1)
        self.get_calls += 1
        body = self.token_bodies[index]
        if isinstance(body, Exception):
            raise body
        return FakeResp(200, body)

    def post(self, url, json=None, headers=None, timeout=None):
        self.posts.append({"url": url, "json": json, "headers": headers or {}})
        index = min(len(self.posts) - 1, len(self.story_responses) - 1)
        status_code, body = self.story_responses[index]
        if isinstance(body, Exception):
            raise body
        return FakeResp(status_code, body)


def _story(story_id="123", is_video=False, **overrides):
    item = {
        "id": story_id,
        "displayUrl": "https://cdn.example/img.jpg?src=abc",
        "downloadUrl": "https://cdn.example/media.mp4" if is_video else "https://cdn.example/img.jpg",
        "videoUrl": "https://cdn.example/media.mp4" if is_video else None,
        "isVideo": is_video,
        "mediaType": "2" if is_video else "1",
        "takenAt": "1795532772",
        "expiringAt": "1795619172",
    }
    item.update(overrides)
    return item


def test_fetch_stories_success_normalizes_items():
    session = FakeSession(story_responses=[(200, {"status": "success", "data": {"stories": [_story(), _story("456", is_video=True)]}})])
    api = ClipSaverAPI(session=session)

    items = api.fetch_stories("@someuser")

    assert [i["kind"] for i in items] == ["image", "video"]
    assert items[0]["u"] == "https://cdn.example/img.jpg"
    assert items[1]["u"] == "https://cdn.example/media.mp4"
    assert items[0]["ta"] == 1795532772
    assert items[0]["id"] == "123"
    assert session.posts[0]["json"] == {"username": "someuser"}
    assert session.posts[0]["headers"]["x-cs-tok"] == "tok-1"
    assert api.last_error is None


def test_empty_stories_returns_empty_list():
    session = FakeSession(story_responses=[(200, {"status": "success", "data": {"stories": []}, "isAuthorized": False})])
    api = ClipSaverAPI(session=session)

    assert api.fetch_stories("nobody") == []
    assert api.last_error is None


def test_upstream_unavailable_returns_none_not_empty():
    body = {
        "status": "success",
        "data": {"stories": [], "reason": "upstream_unavailable", "retryable": True, "retryAfter": 10},
    }
    api = ClipSaverAPI(session=FakeSession(story_responses=[(200, body)]))

    assert api.fetch_stories("someuser") is None
    assert "upstream_unavailable" in api.last_error


def test_unsuccessful_status_returns_none():
    api = ClipSaverAPI(session=FakeSession(story_responses=[(200, {"status": "error", "msg": "rate limited"})]))

    assert api.fetch_stories("someuser") is None
    assert "rate limited" in api.last_error


def test_http_error_returns_none():
    api = ClipSaverAPI(session=FakeSession(story_responses=[(429, {"status": "error"})]))

    assert api.fetch_stories("someuser") is None
    assert "429" in api.last_error


def test_network_error_returns_none():
    api = ClipSaverAPI(session=FakeSession(story_responses=[(0, ConnectionError("down"))]))

    assert api.fetch_stories("someuser") is None
    assert "request_failed" in api.last_error


def test_stories_without_usable_url_returns_none():
    broken = _story(downloadUrl=None, videoUrl=None, displayUrl=None)
    api = ClipSaverAPI(session=FakeSession(story_responses=[(200, {"status": "success", "data": {"stories": [broken]}})]))

    assert api.fetch_stories("someuser") is None
    assert "no_usable_media_url" in api.last_error


def test_token_refreshed_after_403():
    session = FakeSession(
        token_bodies=[{"token": "old-token"}, {"token": "new-token"}],
        story_responses=[
            (403, {"status": "error"}),
            (200, {"status": "success", "data": {"stories": [_story()]}}),
        ],
    )
    api = ClipSaverAPI(session=session)

    items = api.fetch_stories("someuser")

    assert items is not None and len(items) == 1
    assert session.get_calls == 2
    assert [p["headers"]["x-cs-tok"] for p in session.posts] == ["old-token", "new-token"]


def test_token_missing_returns_none():
    api = ClipSaverAPI(session=FakeSession(token_bodies=[{"ok": False}]))

    assert api.fetch_stories("someuser") is None
    assert api.last_error == "token_missing"


def test_empty_username_returns_none():
    api = ClipSaverAPI(session=FakeSession())

    assert api.fetch_stories("  @  ") is None
    assert api.last_error == "username ריק"


def test_clipssaver_media_id_used_for_state_dedup(tmp_path, monkeypatch):
    from src.story_downloader import StoryDownloader
    from src.state_manager import StateManager

    sm = StateManager(state_path=str(tmp_path / "state.json"))
    sm.mark_uploaded(
        username="alice",
        story_id="legacy",
        filename="a.jpg",
        dropbox_path="/x/a.jpg",
        pre_download_id="123",
    )

    dl = StoryDownloader(output_dir=tmp_path / "stories")
    dl.state_manager = sm
    # פריט כמו שמקור ClipSaver מחזיר: אין פרמטר media/uri בכתובת, רק מזהה מדיה.
    monkeypatch.setattr(
        StoryDownloader,
        "_fetch_story_urls",
        lambda self, u: [
            {"u": "https://cdn.example/img.jpg", "ta": 1795532772, "txt": None, "pre_download_id": "123"}
        ],
    )

    res = dl.download_stories("alice")

    assert res["success"] is True
    assert res["outcome"] == "no_new_stories"
    assert res["files"] == []
