"""
Notifier - gives notification WITH solution for every threat.
- Logs to logs/protection.log + logs/threat-history.json
- Windows toast (PowerShell, no dependency) + Tkinter popup with buttons:
  [Quarantine - Recommended] [Delete] [Allow Once] [Details]
Thread-safe: watcher thread can call `handle_threat()`; popup is shown in Tk-safe way.
"""
import json
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
LOG_FILE = BASE_DIR / "logs" / "protection.log"
HISTORY_FILE = BASE_DIR / "logs" / "threat-history.json"
QUARANTINE_DIR = BASE_DIR / "quarantine"

SEVERITY_COLOR = {
    "CRITICAL": "#C0392B",
    "HIGH": "#E67E22",
    "MEDIUM": "#F1C40F",
    "LOW": "#3498DB",
    "CLEAN": "#27AE60",
}

_ui_callback = None  # dashboard registers popup handler so popups run on main thread


def set_ui_callback(fn):
    """Dashboard sets this so popups appear on Tk main thread."""
    global _ui_callback
    _ui_callback = fn


def ensure_dirs():
    LOG_FILE.parent.mkdir(exist_ok=True)
    QUARANTINE_DIR.mkdir(exist_ok=True)
    if not HISTORY_FILE.exists():
        HISTORY_FILE.write_text("[]", encoding="utf-8")


def log_line(msg: str):
    ensure_dirs()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


def load_history():
    ensure_dirs()
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_history_entry(result: dict, action_taken: str):
    ensure_dirs()
    hist = load_history()
    hist.append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "threat": result.get("threat_name"),
        "severity": result.get("severity"),
        "category": result.get("category"),
        "location": result.get("location"),
        "reason": result.get("reason"),
        "action": action_taken,
    })
    # keep last 500
    hist = hist[-500:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(hist, f, indent=2)


def quarantine_file(path_str: str):
    """Move file to encrypted-style vault (rename + metadata). Returns new path or None."""
    ensure_dirs()
    src = Path(path_str)
    if not src.exists():
        return None
    dest = QUARANTINE_DIR / (src.name + f".quarantined-{int(time.time())}")
    try:
        shutil.move(str(src), str(dest))
        (dest.with_suffix(dest.suffix + ".info.json")).write_text(
            json.dumps({"original": str(src), "time": datetime.now().isoformat()}, indent=2),
            encoding="utf-8")
        log_line(f"QUARANTINED: {src} -> {dest}")
        return str(dest)
    except Exception as e:
        log_line(f"QUARANTINE FAILED {src}: {e}")
        return None


def delete_file(path_str: str):
    try:
        Path(path_str).unlink(missing_ok=True)
        log_line(f"DELETED: {path_str}")
        return True
    except Exception as e:
        log_line(f"DELETE FAILED {path_str}: {e}")
        return False


def windows_toast(title: str, message: str):
    """Best-effort Windows 10/11 toast via PowerShell. Never crashes."""
    try:
        ps = (
            "$ErrorActionPreference='SilentlyContinue';"
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] > $null;"
            "$tpl=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
            f"$tpl.GetElementsByTagName('text')[0].AppendChild($tpl.CreateTextNode(@'\n{title}\n'@')) > $null;"
            f"$tpl.GetElementsByTagName('text')[1].AppendChild($tpl.CreateTextNode(@'\n{message[:140]}\n'@')) > $null;"
            "$t=[Windows.UI.Notifications.ToastNotification]::new($tpl);"
            "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Laptop Antivirus').Show($t);"
        )
        subprocess.run(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                       timeout=8, capture_output=True)
    except Exception:
        pass


def _fallback_popup_blocking(result: dict):
    """Standalone Tk popup when dashboard is NOT running (runs in its own thread)."""
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        sev = result.get("severity", "HIGH")
        msg = (f"{result.get('threat_name')}\n\nLocation: {result.get('location')}\n"
               f"Risk: {sev}\nReason: {result.get('reason')}\n\n"
               f"Recommended: {result.get('recommended_action', 'quarantine').upper()}\n\n"
               "Click YES = Quarantine (recommended), NO = Delete, Cancel = Ignore")
        ans = messagebox.askyesnocancel("⚠️ THREAT DETECTED - Laptop Antivirus", msg)
        root.destroy()
        if ans is True:
            quarantine_file(result.get("location", ""))
            save_history_entry(result, "quarantine (toast fallback)")
        elif ans is False:
            delete_file(result.get("location", ""))
            save_history_entry(result, "delete (toast fallback)")
        else:
            save_history_entry(result, "ignored (toast fallback)")
    except Exception:
        pass


def handle_threat(result: dict, gaming_mode: bool = False):
    """
    Central entry point. Called by watcher / scanner / url checker.
    - Always logs + saves history skeleton
    - Shows Windows toast + UI popup with solution buttons
    - Returns immediately (popup handled on UI thread or background thread)
    """
    if result.get("clean"):
        return "none"
    ensure_dirs()
    sev = result.get("severity", "HIGH")
    loc = result.get("location", "")
    name = result.get("threat_name", "Unknown")

    log_line(f"THREAT [{sev}] {name} at {loc} | Reason: {result.get('reason')} | Solution offered: {result.get('recommended_action')}")
    windows_toast(f"⚠️ THREAT [{sev}] - {name}", f"{loc} | Recommended: {result.get('recommended_action', 'quarantine').upper()}")

    # Optional beep for critical (Windows only)
    if sev == "CRITICAL":
        try:
            import winsound
            winsound.Beep(880, 400)
        except Exception:
            pass

    if gaming_mode and sev in ("LOW", "MEDIUM"):
        # mute non-critical popups in gaming mode, still log
        save_history_entry(result, "auto-logged (gaming mode muted)")
        return "muted"

    # If dashboard is running, let it show rich popup on main thread
    if _ui_callback is not None:
        try:
            _ui_callback(result)
            return "ui-queued"
        except Exception:
            pass

    # Otherwise fallback popup in background so watcher never blocks
    t = threading.Thread(target=_fallback_popup_blocking, args=(result,), daemon=True)
    t.start()
    return "fallback-popup"


def restore_from_quarantine(quarantined_name: str):
    """One-click false-positive recovery."""
    src = QUARANTINE_DIR / quarantined_name
    info = src.with_suffix(src.suffix + ".info.json")
    original = None
    try:
        if info.exists():
            original = json.loads(info.read_text(encoding="utf-8")).get("original")
    except Exception:
        pass
    dest = Path(original) if original else (BASE_DIR / "restored" / src.name.replace(".quarantined", ""))
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        try:
            info.unlink(missing_ok=True)
        except Exception:
            pass
        log_line(f"RESTORED from quarantine: {quarantined_name} -> {dest}")
        return str(dest)
    except Exception as e:
        log_line(f"RESTORE FAILED {quarantined_name}: {e}")
        return None
