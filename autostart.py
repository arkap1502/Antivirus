"""
Autostart - makes antivirus AUTO ON when laptop powers on.
Windows: Startup folder + Task Scheduler (on logon).
Run once:  python autostart.py
"""
import os
import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MAIN_PY = BASE_DIR / "main.py"
PY = sys.executable


def install_windows():
    msgs = []
    # 1. Startup folder .bat (simplest, works without admin)
    try:
        startup = Path(os.getenv("APPDATA")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        launcher = startup / "LaptopAntivirus.bat"
        launcher.write_text(f'@echo off\nstart "" /min "{PY}" "{MAIN_PY}"\n', encoding="utf-8")
        msgs.append(f"✅ Added to Startup folder: {launcher}")
    except Exception as e:
        msgs.append(f"⚠️ Startup folder failed: {e}")

    # 2. Task Scheduler (needs no admin for /sc onlogon current user)
    try:
        r = subprocess.run(
            ["schtasks", "/create", "/tn", "LaptopAntivirus", "/tr",
             f"'{PY}' '{MAIN_PY}'", "/sc", "onlogon", "/rl", "limited", "/f"],
            capture_output=True, text=True, timeout=15)
        if r.returncode == 0:
            msgs.append("✅ Task Scheduler: runs at every logon (auto ON at boot).")
        else:
            msgs.append(f"⚠️ Task Scheduler skipped: {(r.stderr or r.stdout)[:200]}")
    except Exception as e:
        msgs.append(f"⚠️ Task Scheduler failed: {e}")
    return "\n".join(msgs)


def install_linux():
    service = f"""[Unit]
Description=Laptop Antivirus - auto ON at boot
After=graphical-session.target

[Service]
ExecStart={PY} {MAIN_PY}
Restart=on-failure

[Install]
WantedBy=default.target
"""
    p = Path.home() / ".config" / "systemd" / "user" / "laptop-antivirus.service"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(service, encoding="utf-8")
    os.system("systemctl --user daemon-reload; systemctl --user enable laptop-antivirus 2>/dev/null; true")
    return f"✅ Installed user service: {p}\nRun: systemctl --user start laptop-antivirus"


def install():
    if os.name == "nt":
        return install_windows() + "\n\nRestart your laptop - antivirus will auto-start (green ON)."
    return install_linux()


if __name__ == "__main__":
    print(install())
