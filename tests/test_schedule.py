from src.schedule import read_trigger, should_run


def test_default_is_github_when_missing(tmp_path):
    assert read_trigger(str(tmp_path / "nope.txt")) == "github"


def test_read_external(tmp_path):
    p = tmp_path / "SCHEDULE.txt"
    p.write_text("# comment\ntrigger=external\n", encoding="utf-8")
    assert read_trigger(str(p)) == "external"


def test_invalid_falls_back_to_github(tmp_path):
    p = tmp_path / "SCHEDULE.txt"
    p.write_text("trigger=something\n", encoding="utf-8")
    assert read_trigger(str(p)) == "github"


def test_manual_and_local_always_run():
    assert should_run("external", "workflow_dispatch")[0] is True
    assert should_run("github", "workflow_dispatch")[0] is True
    assert should_run("external", "")[0] is True


def test_today_folder_uses_israel_time():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from src.main import get_today_str

    assert get_today_str() == datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%Y-%m-%d")


def test_external_skips_github_schedule():
    run, reason = should_run("external", "schedule")
    assert run is False
    assert "external" in reason


def test_github_runs_schedule():
    run, _ = should_run("github", "schedule")
    assert run is True
