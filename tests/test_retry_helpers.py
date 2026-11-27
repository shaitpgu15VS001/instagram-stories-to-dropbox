"""בדיקות לריצת ההשלמה: רשימת כשלים זמניים + קובץ משתמשים חלופי."""
import pathlib

from src import main


def test_write_retry_users_only_transient(tmp_path):
    failed = [
        ("api_user", "API_ERROR", "E-FDL-001"),
        ("dl_user", "DOWNLOAD_ERROR", "download_failed"),
        ("dead_user", "USER_NOT_FOUND", "E-USR-001"),
        ("up_user", "UPLOAD_ERROR", "up"),
        ("api_user", "API_ERROR", "E-FDL-001"),  # כפילות
    ]
    out = tmp_path / "retry.txt"
    names = main.write_retry_users(failed, path=str(out))
    assert names == ["api_user", "dl_user", "up_user"]
    assert "dead_user" not in out.read_text(encoding="utf-8")


def test_write_retry_users_empty(tmp_path):
    out = tmp_path / "retry.txt"
    names = main.write_retry_users([("dead", "USER_NOT_FOUND", "x")], path=str(out))
    assert names == []
    assert out.read_text(encoding="utf-8") == ""


def test_usernames_override(monkeypatch, tmp_path):
    f = tmp_path / "retry.txt"
    f.write_text("Display One|user_one\nuser_two\n", encoding="utf-8")
    monkeypatch.setenv("USERNAMES_OVERRIDE", str(f))
    monkeypatch.chdir(tmp_path)
    entries, stats = main.load_usernames()
    usernames = [u for _, u in entries]
    assert usernames == ["user_one", "user_two"]
    assert "OVERRIDE" in stats["sources"]


def test_clipssaver_exposes_retry_after(monkeypatch):
    from src.clipssaver_api import ClipSaverAPI

    class Resp:
        def __init__(self, body):
            self.status_code = 200
            self._body = body

        def json(self):
            return self._body

    class Sess:
        headers = {}

        def get(self, *a, **k):
            return Resp({"ok": True, "token": "tok"})

        def post(self, *a, **k):
            return Resp({
                "status": "success",
                "data": {"stories": [], "reason": "upstream_unavailable", "retryable": True, "retryAfter": 10},
            })

    api = ClipSaverAPI(session=Sess())
    assert api.fetch_stories("someuser") is None
    assert api.last_retry_after == 10
