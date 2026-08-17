import os
import shutil
import platform

from src import logger


def test_debug_dir_created(tmp_path, monkeypatch):
    d = tmp_path / "debug"
    # ensure no debug dir exists
    if d.exists():
        shutil.rmtree(d)
    # init logger debug
    lg = logger.logger
    lg.init_debug(debug_dir=str(d), run_id="test-run")
    assert d.exists()
    full = d / "debug_full.log"
    summary = d / "debug_summary.log"
    # write a couple of logs
    lg.info("test message from unit test")
    lg.error("E-TEST-001 something failed")
    lg.write_summary({
        "start_iso": "2026-01-01T00:00:00Z",
        "end_iso": "2026-01-01T00:00:10Z",
        "duration_seconds": 10,
        "python_version": platform.python_version(),
        "selected_backend": "none",
        "users_loaded": 0,
        "users_processed": 0,
        "users_failed": 0,
        "files_downloaded": 0,
        "files_uploaded": 0,
        "files_skipped": 0,
        "state_total_uploaded": 0,
        "error_counts": lg.error_counts,
    })
    assert full.exists()
    assert summary.exists()
