import os
import sys
import re
import json
import threading
import atexit
import platform
from datetime import datetime, timezone


class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"


class Logger:

    LEVELS = {
        "debug": 10,
        "info": 20,
        "success": 25,
        "warning": 30,
        "error": 40,
    }

    def __init__(self, level=None):
        level = level or os.environ.get("LOG_LEVEL", "info")
        self.level = self.LEVELS.get(level.lower(), 20)
        self._force_color = False
        # Debug file handling
        self._debug_lock = threading.Lock()
        self.debug_dir = None
        self.debug_full_path = None
        self.debug_summary_path = None
        self._debug_full_fh = None
        self.error_counts = {}
        self.run_id = None

    def set_level(self, level):
        self.level = self.LEVELS.get(level.lower(), 20)

    def _format(self, level, color, icon, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"{color}[{timestamp}] {icon} {message}{Colors.RESET}"

    def _print(self, formatted, level_value):
        if level_value >= self.level:
            try:
                print(formatted, flush=True)
            except UnicodeEncodeError:
                try:
                    safe = formatted.encode("ascii", "backslashreplace").decode("ascii")
                    print(safe, flush=True)
                except Exception:
                    pass
        # Always write to debug file if initialized (redacted)
        try:
            if self._debug_full_fh:
                try:
                    text = self._redact(formatted)
                    with self._debug_lock:
                        self._debug_full_fh.write(text + "\n")
                        self._debug_full_fh.flush()
                except Exception:
                    # Never allow logging failures to crash the app
                    pass
        except Exception:
            pass

    def debug(self, message):
        if message is None:
            message = ""
        self._print(
            self._format("DEBUG", Colors.CYAN, "🔍", message),
            self.LEVELS["debug"],
        )

    def info(self, message, *args):
        if args:
            try:
                message = message % args
            except Exception:
                message = f"{message} {' '.join(str(a) for a in args)}"
        if message is None:
            message = ""
        self._print(
            self._format("INFO", Colors.BLUE, "ℹ️ ", message),
            self.LEVELS["info"],
        )

    def success(self, message):
        if message is None:
            message = ""
        self._print(
            self._format("SUCCESS", Colors.GREEN, "✅", message),
            self.LEVELS["success"],
        )

    def warning(self, message, *args):
        if args:
            try:
                message = message % args
            except Exception:
                message = f"{message} {' '.join(str(a) for a in args)}"
        if message is None:
            message = ""
        self._print(
            self._format("WARNING", Colors.YELLOW, "⚠️ ", message),
            self.LEVELS["warning"],
        )

    def error(self, message, *args):
        if args:
            try:
                message = message % args
            except Exception:
                message = f"{message} {' '.join(str(a) for a in args)}"
        if message is None:
            message = ""
        self._print(
            self._format("ERROR", Colors.RED, "❌", message),
            self.LEVELS["error"],
        )
        # If error message contains an Error ID token, count it
        try:
            if isinstance(message, str):
                m = re.search(r"(E-[A-Z0-9-]{3,})", message)
                if m:
                    eid = m.group(1)
                    self.error_counts[eid] = self.error_counts.get(eid, 0) + 1
        except Exception:
            pass

    def section(self, title):
        line = "=" * 60
        self._print(
            f"{Colors.BOLD}{Colors.MAGENTA}\n{line}\n  {title}\n{line}{Colors.RESET}",
            self.LEVELS["info"],
        )

    def init_debug(self, debug_dir="debug", run_id=None):
        try:
            self.debug_dir = str(debug_dir)
            os.makedirs(self.debug_dir, exist_ok=True)
            self.debug_full_path = os.path.join(self.debug_dir, "debug_full.log")
            self.debug_summary_path = os.path.join(self.debug_dir, "debug_summary.log")
            self._debug_full_fh = open(self.debug_full_path, "a", encoding="utf-8")
            self.run_id = run_id or os.environ.get("GITHUB_RUN_ID") or None
            # record start time for possible early exit summary
            try:
                self._start_time = datetime.now(timezone.utc)
            except Exception:
                self._start_time = None
            # Write a small header
            hdr = f"[DEBUG_START] run_id={self.run_id or 'local'} start_ts={datetime.utcnow().isoformat()}Z"
            try:
                with self._debug_lock:
                    self._debug_full_fh.write(self._redact(hdr) + "\n")
                    self._debug_full_fh.flush()
            except Exception:
                pass
            # Register a safe atexit handler to write a minimal summary on early exit
            try:
                atexit.register(self._atexit_summary)
            except Exception:
                pass
        except Exception:
            # Do not fail startup if debug cannot be initialized
            self._debug_full_fh = None

    def _atexit_summary(self):
        try:
            end = datetime.now(timezone.utc)
            start_iso = None
            duration = None
            if getattr(self, "_start_time", None) is not None:
                start_iso = self._start_time.isoformat()
                duration = int((end - self._start_time).total_seconds())
            summary = {
                "start_iso": start_iso,
                "end_iso": end.isoformat(),
                "duration_seconds": duration,
                "python_version": platform.python_version(),
                "selected_backend": os.environ.get("STORAGE_BACKEND") or os.environ.get("DEFAULT_REMOTE") or None,
                "users_loaded": None,
                "users_processed": None,
                "users_failed": None,
                "files_downloaded": None,
                "files_uploaded": None,
                "files_skipped": None,
                "state_total_uploaded": None,
                "error_counts": getattr(self, "error_counts", {}),
            }
            # write summary safely
            try:
                with self._debug_lock:
                    with open(self.debug_summary_path, "w", encoding="utf-8") as fh:
                        fh.write(self._redact("\n".join([f"Run ID: {self.run_id or 'local'}", f"Start: {summary.get('start_iso')}", f"End: {summary.get('end_iso')}", f"DurationSeconds: {summary.get('duration_seconds')}", f"Python: {summary.get('python_version')}"])) )
            except Exception:
                pass
        except Exception:
            pass

    def _redact(self, text: str) -> str:
        try:
            if not text:
                return text
            t = str(text)
            # redact Authorization headers
            t = re.sub(r"(Authorization\s*[:=]\s*)([^\n\r]+)", r"\1[REDACTED]", t, flags=re.IGNORECASE)
            # redact cookies
            t = re.sub(r"(Cookie\s*[:=]\s*)([^\n\r]+)", r"\1[REDACTED]", t, flags=re.IGNORECASE)
            # redact token-like query params in URLs or bodies
            t = re.sub(r"([?&](?:__sig|_sig|__expires|expires|token|access_token|refresh_token|sig)=)[^&\s]+", r"\1[REDACTED]", t, flags=re.IGNORECASE)
            # redact common key=value secrets first (password, token, access_token, refresh_token)
            t = re.sub(r"(?i)(\b(?:password|pass|pwd|access_token|refresh_token|token)\b\s*[:=]\s*)([^\s,;]+)", r"\1[REDACTED]", t)
            # redact inline Bearer tokens (also handle "Bearer token=...")
            t = re.sub(r"(?i)\bBearer\s+(?:token=)?[A-Za-z0-9\-\._~]+=*", "Bearer [REDACTED]", t)
            # redact signing params that may appear without ? or &
            t = re.sub(r"(?i)(__sig|__t|_sig)\s*[=:]?\s*([^\s,;]+)", r"\1=[REDACTED]", t)
            # redact simple key: value patterns for common secrets
            t = re.sub(r"(rclone_config\s*[:=]\s*)([^\n\r]+)", r"\1[REDACTED]", t, flags=re.IGNORECASE)
            # Truncate excessively large JSON blobs
            if len(t) > 20000:
                return t[:20000] + f"\n[TRUNCATED length={len(t)}]"
            return t
        except Exception:
            return text

    def write_summary(self, summary: dict):
        try:
            # Compose a concise human-readable summary
            lines = []
            lines.append(f"Run ID: {self.run_id or 'local'}")
            lines.append(f"Start: {summary.get('start_iso')}")
            lines.append(f"End: {summary.get('end_iso')}")
            lines.append(f"DurationSeconds: {summary.get('duration_seconds')}")
            lines.append(f"Python: {summary.get('python_version')}")
            lines.append(f"SelectedBackend: {summary.get('selected_backend')}")
            lines.append(f"UsersLoaded: {summary.get('users_loaded')}")
            lines.append(f"UsersProcessed: {summary.get('users_processed')}")
            lines.append(f"UsersFailed: {summary.get('users_failed')}")
            lines.append(f"FilesDownloaded: {summary.get('files_downloaded')}")
            lines.append(f"FilesUploaded: {summary.get('files_uploaded')}")
            lines.append(f"FilesSkipped: {summary.get('files_skipped')}")
            lines.append(f"TotalStateTracked: {summary.get('state_total_uploaded')}")
            lines.append("\nErrors by ID:")
            for k, v in (summary.get('error_counts') or {}).items():
                lines.append(f"  {k} {v}")
            # write both to console and file
            try:
                text = "\n".join(lines)
                try:
                    print(text)
                except UnicodeEncodeError:
                    print(text.encode("ascii", "backslashreplace").decode("ascii"))
                if self.debug_dir:
                    with open(self.debug_summary_path, "w", encoding="utf-8") as fh:
                        fh.write(self._redact(text))
            except Exception:
                pass
        except Exception:
            pass

    def progress(self, current, total, prefix=""):
        percent = (current / total * 100) if total > 0 else 0
        bar_length = 30
        filled = int(bar_length * current / total) if total > 0 else 0
        bar = "█" * filled + "░" * (bar_length - filled)
        msg = f"{prefix} [{bar}] {current}/{total} ({percent:.0f}%)"
        try:
            sys.stdout.write(f"\r{msg}")
            sys.stdout.flush()
        except UnicodeEncodeError:
            try:
                safe = msg.encode("ascii", "backslashreplace").decode("ascii")
                sys.stdout.write(f"\r{safe}")
                sys.stdout.flush()
            except Exception:
                pass
        if current >= total:
            try:
                print()
            except Exception:
                pass


logger = Logger()
