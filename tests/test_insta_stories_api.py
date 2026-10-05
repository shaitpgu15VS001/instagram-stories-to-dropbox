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
