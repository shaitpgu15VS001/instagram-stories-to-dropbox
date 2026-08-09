import types
import pytest

from src.rclone_uploader import RcloneUploader, InfrastructureError


class DummyResult:
    def __init__(self, returncode, stderr):
        self.returncode = returncode
        self.stderr = stderr


def test_rclone_infrastructure_error_detection():
    class FakeUploader(RcloneUploader):
        def _run_rclone(self, args, timeout=120):
            return DummyResult(returncode=1, stderr="401 Unauthorized: invalid token")

    fu = FakeUploader()
    import tempfile
    p = tempfile.NamedTemporaryFile(delete=False)
    p.write(b"x")
    p.flush()
    p.close()
    try:
        with pytest.raises(InfrastructureError):
            fu.upload_file(p.name, "some/remote/path")
    finally:
        try:
            import os
            os.unlink(p.name)
        except Exception:
            pass
