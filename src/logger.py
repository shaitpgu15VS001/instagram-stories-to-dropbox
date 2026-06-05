import os
import sys
from datetime import datetime


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

    def set_level(self, level):
        self.level = self.LEVELS.get(level.lower(), 20)

    def _format(self, level, color, icon, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"{color}[{timestamp}] {icon} {message}{Colors.RESET}"

    def _print(self, formatted, level_value):
        if level_value >= self.level:
            print(formatted, flush=True)

    def debug(self, message):
        self._print(
            self._format("DEBUG", Colors.CYAN, "🔍", message),
            self.LEVELS["debug"],
        )

    def info(self, message):
        self._print(
            self._format("INFO", Colors.BLUE, "ℹ️ ", message),
            self.LEVELS["info"],
        )

    def success(self, message):
        self._print(
            self._format("SUCCESS", Colors.GREEN, "✅", message),
            self.LEVELS["success"],
        )

    def warning(self, message):
        self._print(
            self._format("WARNING", Colors.YELLOW, "⚠️ ", message),
            self.LEVELS["warning"],
        )

    def error(self, message):
        self._print(
            self._format("ERROR", Colors.RED, "❌", message),
            self.LEVELS["error"],
        )

    def section(self, title):
        line = "=" * 60
        self._print(
            f"{Colors.BOLD}{Colors.MAGENTA}\n{line}\n  {title}\n{line}{Colors.RESET}",
            self.LEVELS["info"],
        )

    def progress(self, current, total, prefix=""):
        percent = (current / total * 100) if total > 0 else 0
        bar_length = 30
        filled = int(bar_length * current / total) if total > 0 else 0
        bar = "█" * filled + "░" * (bar_length - filled)
        msg = f"{prefix} [{bar}] {current}/{total} ({percent:.0f}%)"
        sys.stdout.write(f"\r{msg}")
        sys.stdout.flush()
        if current >= total:
            print()


logger = Logger()
