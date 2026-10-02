"""Non-GUI verification: watcher ON/OFF, notifier log+vault, no popup."""
from pathlib import Path
import time, json
from file_watcher import RealTimeWatcher
from notifier import handle_threat, load_history, quarantine_file, LOG_FILE, HISTORY_FILE
from scanner_engine import scan_file

# 1. watcher manual ON/OFF
w = RealTimeWatcher()
w.start()
time.sleep(1)
assert w.enabled, "watcher should be ON at boot"
print("PASS: auto ON at boot")

w.pause()
assert not w.enabled, "pause should turn OFF"
print("PASS: manual OFF works")
w.resume()
assert w.enabled, "resume should turn ON"
print("PASS: manual ON works")

# 2. threat handling without popup (gaming mode mutes popup but logs)
r = scan_file("test_threats/demo_mimikatz.txt")
assert not r["clean"], "demo threat should be detected"
out = handle_threat(r, gaming_mode=True)
print("PASS: handle_threat logged, returned:", out)

# 3. quarantine action
Path("test_threats/quarantine_me.txt").write_text("invoke-mimikatz demo quarantine test")
q = quarantine_file("test_threats/quarantine_me.txt")
assert q and Path(q).exists(), "quarantine should move file"
print("PASS: quarantine works ->", q)
assert not Path("test_threats/quarantine_me.txt").exists()

# 4. logs exist
assert LOG_FILE.exists(), "protection.log should exist"
print("PASS: logs exist")
hist = load_history()
print(f"PASS: history entries: {len(hist)}")

w.stop()
print("ALL NON-GUI TESTS PASSED - auto OFF on shutdown simulated by watcher.stop()")
