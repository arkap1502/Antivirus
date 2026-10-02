"""
Dashboard UI - big manual ON/OFF button + status + scan + history + website checker.
Tkinter (built-in) so it runs on any laptop without install.
"""
import json
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from pathlib import Path
from datetime import datetime

from scanner_engine import scan_file, scan_folder
from url_checker import check_url
from notifier import (SEVERITY_COLOR, delete_file, load_history, log_line,
                      quarantine_file, restore_from_quarantine, save_history_entry, set_ui_callback)

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent


class Dashboard(tk.Tk):
    def __init__(self, watcher):
        super().__init__()
        self.watcher = watcher
        self.title("🛡️ Laptop Antivirus - Always ON Protection")
        self.geometry("680x760")
        self.minsize(620, 700)
        self.threat_queue = queue.Queue()
        self.gaming_mode = tk.BooleanVar(value=False)
        self.auto_reenable_job = None

        set_ui_callback(self.threat_queue.put)  # watcher -> this UI thread
        self._build_ui()
        self._poll_threat_queue()
        self._refresh_stats()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------- UI ----------
    def _build_ui(self):
        self.configure(bg="#1e272e")
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        header = tk.Label(self, text="🛡️ LAPTOP ANTIVIRUS", font=("Segoe UI", 20, "bold"),
                          bg="#1e272e", fg="white")
        header.pack(pady=(12, 2))
        sub = tk.Label(self, text="ON when laptop starts • OFF when shutdown • Manual button anytime",
                       bg="#1e272e", fg="#a4b0be", font=("Segoe UI", 9))
        sub.pack()

        # Big ON/OFF button
        self.toggle_btn = tk.Button(self, text="● PROTECTION ON", font=("Segoe UI", 16, "bold"),
                                    bg="#27ae60", fg="white", activebackground="#2ecc71",
                                    relief="flat", padx=20, pady=12, command=self.toggle_protection,
                                    cursor="hand2")
        self.toggle_btn.pack(pady=12, fill="x", padx=30)

        self.status_lbl = tk.Label(self, text="Monitoring apps • websites • images • videos • files • folders",
                                   bg="#1e272e", fg="#dfe4ea", font=("Segoe UI", 10))
        self.status_lbl.pack()
        self.stats_lbl = tk.Label(self, text="Files checked: 0 | Threats blocked: 0 | Last scan: -",
                                  bg="#1e272e", fg="#a4b0be", font=("Segoe UI", 9))
        self.stats_lbl.pack(pady=(2, 8))

        # Buttons row
        row = tk.Frame(self, bg="#1e272e")
        row.pack(pady=4)
        for txt, cmd in [("🔍 Quick Scan", self.quick_scan),
                         ("📁 Full Scan", self.full_scan),
                         ("📂 Custom Scan", self.custom_scan),
                         ("🎮 Gaming: OFF", self.toggle_gaming)]:
            b = tk.Button(row, text=txt, command=cmd, bg="#485460", fg="white",
                          relief="flat", padx=10, pady=6, cursor="hand2")
            b.pack(side="left", padx=4)
            if "Gaming" in txt:
                self.gaming_btn = b

        row2 = tk.Frame(self, bg="#1e272e")
        row2.pack(pady=4)
        for txt, cmd in [("🌐 Check Website", self.check_website_popup),
                         ("🗂️ Quarantine Vault", self.open_vault),
                         ("📜 Threat History", self.show_history),
                         ("🚀 Auto-Start: Install", self.install_autostart)]:
            tk.Button(row2, text=txt, command=cmd, bg="#0fbcf9", fg="black",
                      relief="flat", padx=10, pady=6, cursor="hand2").pack(side="left", padx=4)

        # Log box
        tk.Label(self, text="Live protection log:", bg="#1e272e", fg="white",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=20, pady=(10, 2))
        self.log_box = scrolledtext.ScrolledText(self, height=14, bg="#0a0a0a", fg="#2ecc71",
                                                 font=("Consolas", 9), state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=20, pady=6)
        self.log("Service STARTED - Laptop Power ON detected. Real-time protection ON.")

    # ---------- helpers ----------
    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{ts}] {msg}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def is_gaming(self):
        return self.gaming_btn is not None and self.gaming_mode.get()

    # ---------- ON/OFF ----------
    def toggle_protection(self):
        if self.watcher.enabled:
            # Manual OFF with auto re-enable
            self.watcher.pause()
            self.toggle_btn.config(text="○ PROTECTION OFF - Click to turn ON", bg="#c0392b")
            self.log("Protection PAUSED by user (manual OFF). Auto re-enable in 15 mins.")
            log_line("Protection PAUSED by user (manual OFF).")
            # cancel old + schedule auto ON
            if self.auto_reenable_job:
                try:
                    self.after_cancel(self.auto_reenable_job)
                except Exception:
                    pass
            self.auto_reenable_job = self.after(15 * 60 * 1000, self.auto_reenable)
        else:
            self.watcher.resume()
            self.toggle_btn.config(text="● PROTECTION ON", bg="#27ae60")
            self.log("Protection RESUMED by user (manual ON).")
            if self.auto_reenable_job:
                try:
                    self.after_cancel(self.auto_reenable_job)
                except Exception:
                    pass

    def auto_reenable(self):
        if not self.watcher.enabled:
            self.watcher.resume()
            self.toggle_btn.config(text="● PROTECTION ON", bg="#27ae60")
            self.log("Auto re-enabled protection after 15 mins (so you never stay unprotected).")
            messagebox.showinfo("Laptop Antivirus", "Protection auto turned ON again for your safety.")

    def toggle_gaming(self):
        self.gaming_mode.set(not self.gaming_mode.get())
        on = self.gaming_mode.get()
        self.gaming_btn.config(text=f"🎮 Gaming: {'ON' if on else 'OFF'}",
                               bg="#e84118" if on else "#485460")
        self.log(f"Gaming mode {'ON - non-critical popups muted, protection still ON' if on else 'OFF'}.")
        log_line(f"Gaming mode {'ON' if on else 'OFF'}.")

    # ---------- scans ----------
    def _run_scan_thread(self, kind, target=None):
        def work():
            self.log(f"{kind} started... scanning apps, images, videos, files, folders.")
            if target:
                if Path(target).is_file():
                    results = [scan_file(target)]
                    summary = {"total": 1, "threats": 0 if results[0]['clean'] else 1}
                else:
                    results, summary = scan_folder(target)
            else:
                from file_watcher import resolve_watch_folders
                results, summary = [], {"total": 0, "threats": 0}
                for f in resolve_watch_folders():
                    r, s = scan_folder(str(f), recursive=(kind == "Full Scan"))
                    results += r
                    summary["total"] += s["total"]
                    summary["threats"] += s["threats"]
            threats = [r for r in results if not r["clean"]]
            log_line(f"{kind} finished: {summary['total']} files, {summary['threats']} threats.")
            self.after(0, lambda: self.log(f"{kind} done: {summary['total']} files checked, {summary['threats']} threats."))
            for t in threats[:10]:  # queue max 10 popups to avoid spam
                self.threat_queue.put(t)
            if not threats:
                self.after(0, lambda: messagebox.showinfo("Laptop Antivirus", f"{kind} complete: All clean ✅\n{summary['total']} files checked."))
        threading.Thread(target=work, daemon=True).start()

    def quick_scan(self):
        self._run_scan_thread("Quick Scan")

    def full_scan(self):
        if messagebox.askyesno("Full Scan", "Full scan checks entire laptop (2-10 mins). Start?"):
            self._run_scan_thread("Full Scan")

    def custom_scan(self):
        target = filedialog.askopenfilename(title="Select file to scan")
        if not target:
            target = filedialog.askdirectory(title="Or select folder to scan")
        if target:
            r = scan_file(target) if Path(target).is_file() else None
            if r:
                if r["clean"]:
                    messagebox.showinfo("Clean ✅", f"{target}\nNo threat found.")
                    self.log(f"Custom scan CLEAN: {target}")
                else:
                    self.threat_queue.put(r)
            else:
                self._run_scan_thread("Custom Scan", target)

    # ---------- website ----------
    def check_website_popup(self):
        win = tk.Toplevel(self)
        win.title("Check Website")
        win.geometry("440x220")
        tk.Label(win, text="Paste website URL to check for phishing/malware:", font=("Segoe UI", 10)).pack(pady=10)
        entry = tk.Entry(win, width=50)
        entry.pack(padx=20)
        entry.insert(0, "https://")
        out = tk.Label(win, text="", wraplength=400, font=("Segoe UI", 10, "bold"))
        out.pack(pady=10)

        def go():
            url = entry.get().strip()
            r = check_url(url)
            if r["clean"]:
                out.config(text=f"✅ SAFE: {url}\n{r['reason']}", fg="green")
                self.log(f"Website SAFE: {url}")
            else:
                out.config(text=f"⚠️ {r['severity']} - {r['threat_name']}\n{r['reason']}\nSolution: BLOCK this site.", fg="red")
                self.threat_queue.put(r)
        tk.Button(win, text="Check Now", command=go, bg="#0fbcf9", padx=20, pady=6).pack()

    # ---------- vault / history ----------
    def open_vault(self):
        vault = BASE_DIR / "quarantine"
        vault.mkdir(exist_ok=True)
        files = list(vault.glob("*"))
        if not files:
            messagebox.showinfo("Vault", "Quarantine vault is empty. Nothing blocked yet. 🎉")
            return
        win = tk.Toplevel(self)
        win.title("Quarantine Vault")
        win.geometry("520x360")
        lb = tk.Listbox(win, font=("Consolas", 9))
        lb.pack(fill="both", expand=True, padx=10, pady=10)
        for f in files:
            if not f.name.endswith(".info.json"):
                lb.insert("end", f.name)

        def restore():
            sel = lb.get("active") if lb.size() else None
            if not sel:
                return
            dest = restore_from_quarantine(sel)
            messagebox.showinfo("Restored", f"Restored to:\n{dest}" if dest else "Restore failed.")
            win.destroy()
        tk.Button(win, text="♻️ Restore Selected (false positive)", command=restore, bg="#fbc531").pack(pady=6)

    def show_history(self):
        hist = load_history()
        win = tk.Toplevel(self)
        win.title("Threat History")
        win.geometry("620x420")
        box = scrolledtext.ScrolledText(win, font=("Consolas", 9))
        box.pack(fill="both", expand=True, padx=10, pady=10)
        if not hist:
            box.insert("end", "No threats found yet. Your laptop is clean! 🎉\n")
        for h in reversed(hist[-100:]):
            box.insert("end", f"[{h.get('time')}] [{h.get('severity')}] {h.get('threat')}\n  @ {h.get('location')}\n  Fix: {h.get('action')}\n\n")
        box.configure(state="disabled")

    def install_autostart(self):
        try:
            import autostart
            msg = autostart.install()
            messagebox.showinfo("Auto-Start", msg)
            self.log(msg)
        except Exception as e:
            messagebox.showerror("Auto-Start failed", str(e))

    # ---------- threat popup WITH solution ----------
    def _poll_threat_queue(self):
        try:
            while True:
                result = self.threat_queue.get_nowait()
                self._show_threat_popup(result)
        except queue.Empty:
            pass
        self.after(500, self._poll_threat_queue)

    def _show_threat_popup(self, r):
        sev = r.get("severity", "HIGH")
        color = SEVERITY_COLOR.get(sev, "#E67E22")
        win = tk.Toplevel(self)
        win.title(f"⚠️ THREAT [{sev}] DETECTED")
        win.geometry("500x420")
        win.attributes("-topmost", True)
        tk.Label(win, text=f"⚠️ THREAT DETECTED [{sev}]", bg=color, fg="white",
                 font=("Segoe UI", 13, "bold"), pady=10).pack(fill="x")
        body = (f"Name: {r.get('threat_name')}\n\nLocation: {r.get('location')}\n\n"
                f"Type: {r.get('category')}  |  Risk: {sev}\n\n"
                f"What it can do: {r.get('reason')}\n\n"
                f"✅ Recommended fix: {r.get('recommended_action', 'quarantine').upper()}")
        tk.Label(win, text=body, wraplength=460, justify="left", font=("Segoe UI", 10)).pack(padx=14, pady=10)

        btns = tk.Frame(win)
        btns.pack(pady=8)

        def do(action):
            loc = r.get("location", "")
            if action == "quarantine":
                q = quarantine_file(loc) if Path(loc).exists() else None
                save_history_entry(r, f"quarantine -> {q}" if q else "quarantine (file already gone)")
                self.log(f"THREAT QUARANTINED: {loc}")
                messagebox.showinfo("Safe ✅", "Threat locked in Quarantine vault.\nYour laptop is safe now.")
            elif action == "delete":
                delete_file(loc)
                save_history_entry(r, "delete")
                self.log(f"THREAT DELETED: {loc}")
                messagebox.showinfo("Deleted", "Threat permanently deleted.")
            elif action == "allow":
                save_history_entry(r, "allowed by user (whitelisted in log)")
                self.log(f"Threat ALLOWED by user: {loc} (logged)")
            win.destroy()
            self._refresh_stats()

        tk.Button(btns, text="🛡️ Quarantine (Recommended)", bg="#27ae60", fg="white",
                  command=lambda: do("quarantine"), padx=10, pady=6).pack(side="left", padx=4)
        tk.Button(btns, text="🗑️ Delete", bg="#c0392b", fg="white",
                  command=lambda: do("delete"), padx=10, pady=6).pack(side="left", padx=4)
        tk.Button(btns, text="✔ Allow Once", bg="#7f8c8d", fg="white",
                  command=lambda: do("allow"), padx=10, pady=6).pack(side="left", padx=4)

    def _refresh_stats(self):
        try:
            self.stats_lbl.config(
                text=f"Files checked: {self.watcher.files_checked} | Threats blocked: {self.watcher.threats_blocked} | Last update: {datetime.now().strftime('%H:%M:%S')}")
        except Exception:
            pass
        self.after(2000, self._refresh_stats)

    def on_close(self):
        # Auto OFF at shutdown/close: save logs, stop watcher
        log_line("Service STOPPED - Laptop Shutdown / window closed, logs saved, vault locked.")
        try:
            self.watcher.stop()
        except Exception:
            pass
        self.destroy()
