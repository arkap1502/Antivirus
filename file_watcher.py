"""
Real-time File Watcher - checks EVERY new/changed file instantly.
Polling-based (stdlib only) so it works without installing watchdog.
Watches: Desktop, Documents, Downloads, Pictures, Videos + USB drives.
Pause/Resume = Manual OFF/ON button.
"""
import json
import os
import string
import threading
import time
from pathlib import Path

from scanner_engine import scan_file
from notifier import handle_threat, log_line

BASE_DIR = Path(__file__).parent


def load_config():
    try:
        with open(BASE_DIR / "config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"poll_interval_seconds": 2, "watch_folders": ["Desktop", "Documents", "Downloads", "Pictures", "Videos"]}


def resolve_watch_folders():
    cfg = load_config()
    home = Path.home()
    folders = []
    for name in cfg.get("watch_folders", []):
        p = home / name
        # OneDrive Desktop/Documents redirect on many Indian laptops
        if not p.exists():
            alt = home / "OneDrive" / name
            if alt.exists():
                p = alt
        if p.exists():
            folders.append(p)
    # Always watch project folder itself (demo + self-protection)
    folders.append(BASE_DIR)
    return folders


def get_usb_drives():
    """Detect removable drives on Windows (D:, E:, ...)."""
    drives = []
    if os.name != "nt":
        # Linux/mac: check /media + /Volumes
        for base in [Path("/media"), Path(f"/media/{os.getenv('USER', '')}"), Path("/Volumes")]:
            if base.exists():
                for d in base.iterdir():
                    if d.is_dir():
                        drives.append(d)
        return drives
    try:
        import ctypes
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for i in string.ascii_uppercase:
            if bitmask & 1:
                p = Path(f"{i}:\\")
                if p.exists():
                    dtype = ctypes.windll.kernel32.GetDriveTypeW(str(p))
                    if dtype == 2:  # DRIVE_REMOVABLE
                        drives.append(p)
            bitmask >>= 1
    except Exception:
        pass
    return drives


class RealTimeWatcher(threading.Thread):
    def __init__(self, on_stats=None, gaming_mode_fn=None):
        super().__init__(daemon=True)
        self._stop = threading.Event()
        self._enabled = threading.Event()
        self._enabled.set()  # ON by default (auto ON at boot)
        self.seen = {}  # path -> (mtime, size)
        self.files_checked = 0
        self.threats_blocked = 0
        self.on_stats = on_stats
        self.gaming_mode_fn = gaming_mode_fn or (lambda: False)
        self._bootstrapped = False

    # --- Manual ON/OFF ---
    def pause(self):
        self._enabled.clear()
        log_line("Protection PAUSED by user (manual OFF).")

    def resume(self):
        self._enabled.set()
        log_line("Protection RESUMED by user (manual ON).")

    @property
    def enabled(self):
        return self._enabled.is_set()

    def stop(self):
        self._stop.set()

    def _snapshot_file(self, p: Path):
        try:
            st = p.stat()
            return (st.st_mtime, st.st_size)
        except OSError:
            return None

    def _check_one(self, p: Path):
        try:
            # skip our own logs/vault + demo threats + python cache to stay fast
            if "quarantine" in p.parts or p.parent.name == "logs":
                return
            if "test_threats" in p.parts or "__pycache__" in p.parts:
                return
            if p.suffix.lower() in {".log", ".json"} and p.parent == BASE_DIR / "logs":
                return
            result = scan_file(str(p))
            self.files_checked += 1
            if not result["clean"]:
                self.threats_blocked += 1
                handle_threat(result, gaming_mode=self.gaming_mode_fn())
            if self.on_stats:
                try:
                    self.on_stats(self.files_checked, self.threats_blocked)
                except Exception:
                    pass
        except Exception as e:
            log_line(f"Watcher error on {p}: {e}")

    def run(self):
        log_line("Real-time protection ENABLED - Watching apps, web files, media, docs, USB.")
        while not self._stop.is_set():
            try:
                if not self.enabled:
                    time.sleep(1)
                    continue
                folders = resolve_watch_folders()
                folders += get_usb_drives()
                for folder in folders:
                    if self._stop.is_set() or not self.enabled:
                        break
                    try:
                        if not folder.exists():
                            continue
                        # non-recursive for root drives, recursive for user folders
                        recursive = folder not in get_usb_drives()
                        if recursive:
                            it = folder.rglob("*")
                        else:
                            it = folder.iterdir()
                        for p in it:
                            if self._stop.is_set() or not self.enabled:
                                break
                            if not p.is_file():
                                continue
                            # skip giant files > 500MB for speed (still check name/extension tricks)
                            try:
                                if p.stat().st_size > 500 * 1024 * 1024:
                                    # only quick name check
                                    if ".exe" in p.name.lower() and p.suffix.lower() in {".jpg", ".mp4", ".pdf"}:
                                        self._check_one(p)
                                    continue
                            except OSError:
                                continue
                            snap = self._snapshot_file(p)
                            if snap is None:
                                continue
                            key = str(p)
                            if not self._bootstrapped:
                                # first pass: baseline silently, but still scan NEW executables created in last 10 min
                                self.seen[key] = snap
                                try:
                                    age = time.time() - p.stat().st_mtime
                                    if age < 600 and p.suffix.lower() in {".exe", ".bat", ".ps1", ".vbs", ".js"}:
                                        self._check_one(p)
                                except OSError:
                                    pass
                                continue
                            old = self.seen.get(key)
                            if old != snap:
                                self.seen[key] = snap
                                self._check_one(p)
                    except (PermissionError, OSError):
                        continue
                self._bootstrapped = True
                interval = load_config().get("poll_interval_seconds", 2)
                time.sleep(max(1, int(interval)))
            except Exception as e:
                log_line(f"Watcher loop error: {e}")
                time.sleep(2)
