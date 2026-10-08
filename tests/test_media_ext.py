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
