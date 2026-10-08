from src.insta_stories_api import (
    InstaStoriesAPI,
    extract_media_id,
    parse_stories_html,
)

SAMPLE_CARD = """
<div class="col-md-4 position-relative"><div class="p-3"><div class="load">
<img src="https://fr9.anon-viewer.com/media.php?media=https%3A%2F%2Fscontent.cdninstagram.com%2Fv%2Fabc_n.jpg%3Foe%3D1" class="w-100" loading="lazy">
</div></div>
<a href="https://fr9.anon-viewer.com/media2.php?media=https%3A%2F%2Fscontent.cdninstagram.com%2Fv%2Fabc_n.jpg%3Foe%3D1">Download</a>
<div class="d-flex justify-content-center align-items-center"><div class="stats text-sm"><small><i class="far fa-clock"></i> 21 hours ago</small></div></div>
"""

SAMPLE_VIDEO_CARD = """
<div class="col-md-4 position-relative"><div class="p-3"><video poster="https://fr14.anon-viewer.com/media.php?media=x.jpg" controls>
<source src="https://fr11.anon-viewer.com/media.php?media=https%3A%2F%2Fscontent.cdninstagram.com%2Fstory.mp4%3Foe%3D1">
</video></div>
<div class="d-flex justify-content-center align-items-center"><div class="stats"><small>12 minutes ago</small></div></div>
"""


def test_parse_image_card_prefers_download_link():
    items = parse_stories_html(SAMPLE_CARD)
    assert len(items) == 1
    assert "media2.php" in items[0]["u"]
    assert items[0]["kind"] == "image"
    assert items[0]["txt"] == "21 hours ago"


def test_parse_video_card():
    items = parse_stories_html(SAMPLE_VIDEO_CARD)
    assert len(items) == 1
    assert items[0]["kind"] == "video"
    assert items[0]["txt"] == "12 minutes ago"


def test_parse_empty_html_returns_empty():
    assert parse_stories_html("") == []


def test_extract_media_id_stable():
    url = "https://fr9.anon-viewer.com/media.php?media=https%3A%2F%2Fscontent.cdninstagram.com%2Fv%2Fabc_n.jpg%3Foe%3D1"
    assert extract_media_id(url) == "/v/abc_n.jpg"
    assert extract_media_id(None) is None
    assert extract_media_id("") is None


def test_fetch_no_stories_returns_empty_list():
    class FakeResp:
        status_code = 200

        def json(self):
            return {"status": "error", "msg": "The user has no stories. Try Highlights"}

    class FakeSession:
        headers = {}

        def get(self, *args, **kwargs):
            return FakeResp()

    api = InstaStoriesAPI(session=FakeSession())
    assert api.fetch_stories("nouser") == []


def test_fetch_network_error_returns_none():
    class BadSession:
        headers = {}

        def get(self, *args, **kwargs):
            raise ConnectionError("down")

    api = InstaStoriesAPI(session=BadSession())
    assert api.fetch_stories("someuser") is None


def test_extract_pre_download_id_supports_media_param():
    from src.story_downloader import extract_pre_download_id

    url = "https://fr9.anon-viewer.com/media.php?media=https%3A%2F%2Fscontent.cdninstagram.com%2Fv%2Fabc_n.jpg%3Foe%3D1"
    assert extract_pre_download_id(url) == "/v/abc_n.jpg"
    # תאימות לאחור למקור הישן (fastdl עם uri)
    old = "https://media.fastdl.app/get?uri=https%3A%2F%2Fscontent.cdninstagram.com%2Fv%2Fstory.mp4"
    assert extract_pre_download_id(old) == "/v/story.mp4"


def _fake_session(mapping):
    class FakeResp:
        def __init__(self, status_code, body):
            self.status_code = status_code
            self._body = body

        def json(self):
            if isinstance(self._body, Exception):
                raise self._body
            return self._body

    class FakeSession:
        headers = {}

        def get(self, url, params=None, timeout=None):
            key = (url, tuple(sorted((params or {}).items())))
            if key not in mapping:
                raise AssertionError(f"unexpected request: {key}")
            status_code, body = mapping[key]
            if isinstance(body, Exception) and not isinstance(body, dict):
                if status_code == "raise":
                    raise body
            return FakeResp(status_code, body)

    return FakeSession()


PROFILE_URL = "https://insta-stories.io/content.php"
HOME_URL = "https://insta-stories.io/"


def test_diagnose_user_not_found():
    api = InstaStoriesAPI(session=_fake_session({
        (PROFILE_URL, (("url", "ghost"),)): (200, {"status": "error", "msg": "temporarily unavailable"}),
        (HOME_URL, ()): (200, "<html>ok</html>"),
    }))
    # homepage returns text, .json() must fail -> FakeResp.json returns str, not dict
    assert api.diagnose("ghost") == "user_not_found"


def test_diagnose_api_error_when_profile_exists():
    api = InstaStoriesAPI(session=_fake_session({
        (PROFILE_URL, (("url", "realuser"),)): (200, {"status": "ok", "html": "<div/>", "username": "realuser"}),
    }))
    assert api.diagnose("realuser") == "api_error"


def test_diagnose_api_error_when_site_down():
    class DownSession:
        headers = {}

        def get(self, *args, **kwargs):
            raise ConnectionError("down")

    assert InstaStoriesAPI(session=DownSession()).diagnose("anyone") == "api_error"


def test_download_stories_user_not_found_outcome(tmp_path, monkeypatch, capsys):
    from src.story_downloader import StoryDownloader
    import src.insta_stories_api as mod

    monkeypatch.setattr(mod.InstaStoriesAPI, "fetch_stories", lambda self, username, timeout=20: None)
    monkeypatch.setattr(mod.InstaStoriesAPI, "diagnose", lambda self, username, timeout=10: "user_not_found")
    sd = StoryDownloader(output_dir=tmp_path / "stories")
    res = sd.download_stories("ghostuser")
    assert res["success"] is False
    assert res["outcome"] == "user_not_found"
    assert "user_not_found" in res["error"]
    out = capsys.readouterr().out
    assert "user_not_found" in out
    assert "E-USR-001" in out


def test_transient_failure_retried_once(tmp_path, monkeypatch):
    from src.story_downloader import StoryDownloader
    import src.insta_stories_api as mod

    calls = {"n": 0}

    def flaky_fetch(self, username, timeout=20):
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return [{"u": "https://fr1.anon-viewer.com/media2.php?media=abc", "kind": "image", "txt": "5 minutes ago"}]

    monkeypatch.setattr(mod.InstaStoriesAPI, "fetch_stories", flaky_fetch)
    monkeypatch.setattr("time.sleep", lambda s: None)
    sd = StoryDownloader(output_dir=tmp_path / "stories")
    urls = sd._fetch_story_urls("someuser")
    assert calls["n"] == 2
    assert isinstance(urls, list) and len(urls) == 1


def test_unparseable_html_returns_none_not_empty():
    class FakeResp:
        status_code = 200

        def json(self):
            return {"status": "ok", "source": "GetAllStories", "html": "<div>new layout</div>"}

    class FakeSession:
        headers = {}

        def get(self, *args, **kwargs):
            return FakeResp()

    api = InstaStoriesAPI(session=FakeSession())
    assert api.fetch_stories("someuser") is None


def test_html_error_page_not_saved_as_media(tmp_path, monkeypatch):
    from src.story_downloader import StoryDownloader

    monkeypatch.setattr("time.sleep", lambda s: None)
    sd = StoryDownloader(output_dir=tmp_path / "stories")
    sd._download_media_via_browser_context = lambda url, timeout_seconds=60: {
        "content": b"<html><body>error</body></html>",
        "content_type": "text/html",
        "final_url": url,
        "status": 200,
    }
    out = sd._download_files(
        [{"u": "https://example.com/x", "ta": None, "txt": "5 minutes ago", "pre_download_id": "p1"}],
        tmp_path / "stories" / "u",
        "u",
    )
    assert out == []
    assert list((tmp_path / "stories" / "u").glob("*")) == []


def test_sanitize_folder_name():
    from src.main import _sanitize_folder_name

    assert _sanitize_folder_name("a/b:c", "fb") == "a_b_c"
    assert _sanitize_folder_name("  name... ", "fb") == "name"
    assert _sanitize_folder_name("", "fb") == "fb"
    assert _sanitize_folder_name(None, "fb") == "fb"
    assert len(_sanitize_folder_name("x" * 200, "fb")) <= 100


def test_parse_seconds_and_just_now():
    items = parse_stories_html(
        '<div class="col-md-4 position-relative">'
        '<a href="https://fr1.anon-viewer.com/media2.php?media=abc">Download</a>'
        '<small>45 seconds ago</small></div>'
        '<div class="col-md-4 position-relative">'
        '<a href="https://fr1.anon-viewer.com/media2.php?media=def">Download</a>'
        '<small>just now</small></div>'
    )
    assert [it["txt"] for it in items] == ["45 seconds ago", "just now"]


def test_meta_timestamp_seconds_and_just_now():
    from src.story_downloader import _parse_meta_timestamp
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    assert _parse_meta_timestamp({"txt": "45 seconds ago"}) is not None
    assert abs((now - _parse_meta_timestamp({"txt": "45 seconds ago"})).total_seconds() - 45) < 10
    assert abs((now - _parse_meta_timestamp({"txt": "just now"})).total_seconds()) < 10
