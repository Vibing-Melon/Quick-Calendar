"""Where the app keeps its files, optional config.env, and logging."""
import logging
import logging.handlers
import os
import sys
import threading

APP_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(APP_DIR, "snap2cal.log")
FIRST_RUN_FLAG = os.path.join(APP_DIR, ".autostart_initialized")
CONFIG_FILE = os.path.join(APP_DIR, "config.env")


def load_env():
    """Read KEY=VALUE lines from config.env (does not override real environment variables)."""
    if not os.path.exists(CONFIG_FILE):
        return
    with open(CONFIG_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def setup_logging():
    """Errors only go to snap2cal.log. Screenshot contents are never logged."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    handler = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=200_000, backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    sys.excepthook = lambda *exc: logging.error("Uncaught", exc_info=exc)
    threading.excepthook = lambda a: logging.error("Thread error", exc_info=(a.exc_type, a.exc_value, a.exc_traceback))
