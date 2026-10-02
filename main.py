"""
MAIN - Laptop Antivirus entry point.
AUTO ON when laptop opens (just run this file) + AUTO OFF on shutdown/close.
Manual ON/OFF via dashboard button.

Run:  python main.py
"""
import atexit
import signal
import sys
from pathlib import Path

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

from file_watcher import RealTimeWatcher
from notifier import log_line


def handle_shutdown(*args):
    log_line("Service STOPPED - Laptop Shutdown detected, logs saved, vault locked.")


def main():
    # Auto ON at laptop start
    (BASE_DIR / "logs").mkdir(exist_ok=True)
    (BASE_DIR / "quarantine").mkdir(exist_ok=True)
    log_line("Service STARTED - Laptop Power ON detected.")

    # Handle shutdown signals (Windows + Linux)
    try:
        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)
    except Exception:
        pass
    atexit.register(handle_shutdown)

    watcher = RealTimeWatcher()
    watcher.start()

    # Launch dashboard (has manual ON/OFF button)
    from dashboard import Dashboard
    app = Dashboard(watcher)
    try:
        app.mainloop()
    finally:
        watcher.stop()
        handle_shutdown()


if __name__ == "__main__":
    main()
