from src.story_downloader import _decide_ext, _is_heic, _unique_path

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 100
MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00" + b"\x00" * 100
HEIC = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00" + b"\x00" * 100


def test_is_heic_detects_brand():
    assert _is_heic(HEIC) is True
    assert _is_heic(MP4) is False
    assert _is_heic(JPEG) is False
    assert _is_heic(b"") is False
    assert _is_heic(None) is False


def test_heic_content_type_with_jpeg_data_gives_jpg():
    # מקרה אמיתי מהשטח: השרת טוען image/heic אבל התוכן JPEG תקין
    assert _decide_ext(JPEG, "image/heic", "https://fr4.anon-viewer.com/media2.php?media=abc") == ".jpg"


def test_real_heic_data_gives_heic():
    assert _decide_ext(HEIC, "image/heic", "https://example.com/media.php?media=abc") == ".heic"


def test_known_types_unchanged():
    assert _decide_ext(MP4, "video/mp4", "https://example.com/x") == ".mp4"
    assert _decide_ext(b"data", "image/png", "https://example.com/x") == ".png"
    assert _decide_ext(JPEG, "image/jpeg", "https://example.com/x") == ".jpg"
    assert _decide_ext(b"????", "text/html", "https://example.com/x") == ".bin"


def test_unique_path_adds_suffix_on_collision(tmp_path):
    seen = set()
    first = _unique_path(tmp_path, "user", "2026-10-05_12-00-00", ".mp4", seen)
    assert first.name == "user-2026-10-05_12-00-00.mp4"
    first.touch()
    second = _unique_path(tmp_path, "user", "2026-10-05_12-00-00", ".mp4", seen)
    assert second.name == "user-2026-10-05_12-00-00_2.mp4"
    assert second.name not in {first.name}
    # extract_story_id עדיין מזהה את חותמת הזמן עם הסיומת
    from src.story_downloader import StoryDownloader

    assert StoryDownloader(output_dir=tmp_path).extract_story_id(second.name) == "2026-10-05_12-00-00"


def test_transient_aborted_error_is_retried(tmp_path, monkeypatch):
    from src.story_downloader import StoryDownloader

    jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 100
    calls = {"n": 0}

    def flaky(url, timeout_seconds=60):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("APIRequestContext.get: aborted")
        return {"content": jpeg, "content_type": "image/jpeg", "final_url": url, "status": 200}

    monkeypatch.setattr("time.sleep", lambda s: None)
    sd = StoryDownloader(output_dir=tmp_path / "stories")
    sd._download_media_via_browser_context = flaky
    user_dir = tmp_path / "stories" / "u"
    user_dir.mkdir(parents=True, exist_ok=True)
    out = sd._download_files(
        [{"u": "https://example.com/x", "ta": None, "txt": "5 minutes ago", "pre_download_id": "p1"}],
        user_dir,
        "u",
    )
    assert len(out) == 1
    assert calls["n"] == 2


def test_non_transient_error_not_retried(tmp_path, monkeypatch):
    from src.story_downloader import StoryDownloader

    calls = {"n": 0}

    def always_fails(url, timeout_seconds=60):
        calls["n"] += 1
        raise RuntimeError("boom: unexpected bug")

    monkeypatch.setattr("time.sleep", lambda s: None)
    sd = StoryDownloader(output_dir=tmp_path / "stories")
    sd._download_media_via_browser_context = always_fails
    out = sd._download_files(
        [{"u": "https://example.com/x", "ta": None, "txt": "5 minutes ago", "pre_download_id": "p1"}],
        tmp_path / "stories" / "u",
        "u",
    )
    assert out == []
    assert calls["n"] == 1


def test_retry_backoff_grows():
    from src.story_downloader import _retry_delay

    assert _retry_delay(1) == 2
    assert _retry_delay(2) == 4
    assert _retry_delay(3) == 8
    assert _retry_delay(99) == 30


def _dl_with_status(tmp_path, monkeypatch, status, content=b"x"):
    import requests
    from src.story_downloader import StoryDownloader

    calls = {"n": 0}

    def fake_dl(url, timeout_seconds=60):
        calls["n"] += 1
        raise requests.HTTPError(f"media fetch failed: status={status}")

    monkeypatch.setattr("time.sleep", lambda s: None)
    sd = StoryDownloader(output_dir=tmp_path / "stories")
    sd._download_media_via_browser_context = fake_dl
    user_dir = tmp_path / "stories" / "u"
    user_dir.mkdir(parents=True, exist_ok=True)
    out = sd._download_files(
        [{"u": "https://example.com/x", "ta": None, "txt": "5 minutes ago", "pre_download_id": "p1"}],
        user_dir,
        "u",
    )
    return out, calls["n"]


def test_504_is_retried_until_max(tmp_path, monkeypatch):
    out, n = _dl_with_status(tmp_path, monkeypatch, 504)
    assert out == []
    assert n == 4


def test_404_not_retried(tmp_path, monkeypatch):
    out, n = _dl_with_status(tmp_path, monkeypatch, 404)
    assert out == []
    assert n == 1


def test_content_validation_error_not_retried(tmp_path, monkeypatch):
    from src.story_downloader import StoryDownloader

    calls = {"n": 0}

    def fake_dl(url, timeout_seconds=60):
        calls["n"] += 1
        return {"content": b"not an image at all" * 10, "content_type": "image/jpeg", "final_url": url, "status": 200}

    monkeypatch.setattr("time.sleep", lambda s: None)
    sd = StoryDownloader(output_dir=tmp_path / "stories")
    sd._download_media_via_browser_context = fake_dl
    user_dir = tmp_path / "stories" / "u"
    user_dir.mkdir(parents=True, exist_ok=True)
    out = sd._download_files(
        [{"u": "https://example.com/x.jpg", "ta": None, "txt": "5 minutes ago", "pre_download_id": "p1"}],
        user_dir,
        "u",
    )
    assert out == []
    assert calls["n"] == 1
