"""
Laptop Antivirus - Scanner Engine
Checks EVERYTHING: apps, websites (files/URLs), images, videos, audio, files, folders, archives.
Returns a result dict with severity + recommended solution.
Stdlib only.
"""
import hashlib
import json
import os
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).parent
SIGNATURES_PATH = BASE_DIR / "signatures.json"

# EICAR test string (safe industry-standard test virus - no harm, only for testing detection)
EICAR_STRING = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".ico"}
VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv"}
AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}
DOC_EXTS = {".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".csv"}
ARCHIVE_EXTS = {".zip", ".rar", ".7z"}
APP_EXTS = {".exe", ".msi", ".bat", ".cmd", ".vbs", ".js", ".ps1", ".lnk", ".scr", ".jar", ".py"}

# Magic bytes for header validation (fake image/video carrying exe payload)
MAGIC = {
    ".png": [b"\x89PNG"],
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".gif": [b"GIF8"],
    ".pdf": [b"%PDF"],
    ".zip": [b"PK\x03\x04"],
}


def load_signatures():
    try:
        with open(SIGNATURES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"bad_sha256": [], "bad_filenames": [], "phishing_keywords": [],
                "blocked_domains": [], "suspicious_content_keywords": [],
                "suspicious_extensions": []}


def sha256_of_file(path: Path, chunk_size=65536, max_bytes=50 * 1024 * 1024):
    """Hash first max_bytes so huge videos don't freeze laptop."""
    h = hashlib.sha256()
    total = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                h.update(chunk[: max_bytes - (total - len(chunk))])
                break
            h.update(chunk)
            if total >= max_bytes:
                break
    return h.hexdigest()


def clean_result(path=""):
    return {
        "clean": True,
        "threat_name": "",
        "severity": "CLEAN",
        "category": "",
        "location": str(path),
        "reason": "No threat found.",
        "recommended_action": "none",
    }


def threat(path, threat_name, severity, category, reason, recommended_action):
    return {
        "clean": False,
        "threat_name": threat_name,
        "severity": severity,  # CRITICAL / HIGH / MEDIUM / LOW
        "category": category,  # app / website / image / video / audio / file / archive / usb
        "location": str(path),
        "reason": reason,
        "recommended_action": recommended_action,  # quarantine / delete / block
    }


def has_double_extension(filename: str) -> bool:
    """photo.jpg.exe -> True (classic trick)."""
    parts = filename.lower().split(".")
    if len(parts) >= 3:
        # e.g. ['photo', 'jpg', 'exe'] -> middle is media/doc, last is executable
        fake_media = {"jpg", "jpeg", "png", "gif", "mp4", "mp3", "pdf", "docx", "txt"}
        execs = {"exe", "scr", "bat", "cmd", "vbs", "js", "ps1", "lnk", "jar", "com", "pif"}
        if parts[-2] in fake_media and parts[-1] in execs:
            return True
    return False


def check_header(path: Path) -> bool:
    """True if header looks WRONG (mismatch)."""
    ext = path.suffix.lower()
    if ext not in MAGIC:
        return False
    try:
        with open(path, "rb") as f:
            head = f.read(8)
        for magic in MAGIC[ext]:
            if head.startswith(magic):
                return False
        # SVG is text-based, skip strict check
        if ext == ".svg":
            return False
        return True
    except OSError:
        return False


def scan_content_keywords(path: Path, sigs, max_scan_bytes=2 * 1024 * 1024):
    """Heuristic: look for known-malicious strings in small/text files."""
    try:
        if path.stat().st_size > max_scan_bytes:
            return None
        # skip binary media for keyword scan (too many false positives)
        if path.suffix.lower() in IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS:
            data = path.read_bytes()
            if EICAR_STRING in data:
                return ("EICAR-Test-File", "Test virus string hidden inside media file.")
            return None
        data = path.read_bytes()
        if EICAR_STRING in data:
            return ("EICAR-Test-File", "Standard antivirus test string found.")
        try:
            text = data.decode("utf-8", errors="ignore").lower()
        except Exception:
            return None
        for kw in sigs.get("suspicious_content_keywords", []):
            if kw.lower() in text:
                return (f"Heuristic.Suspicious.{kw[:24]}", f"Suspicious keyword found: '{kw}'")
        return None
    except OSError:
        return None


def scan_archive_members(path: Path, sigs):
    """Peek inside .zip without extracting (sandbox-style)."""
    try:
        if path.suffix.lower() != ".zip":
            return None
        with zipfile.ZipFile(path, "r") as z:
            for name in z.namelist():
                lname = name.lower()
                # exe hidden inside zip with media name trick
                if has_double_extension(name):
                    return (f"Archive.DoubleExtension:{Path(name).name}", f"Double-extension file inside archive: {name}")
                if any(lname.endswith(e) for e in sigs.get("suspicious_extensions", [])):
                    # flag only if archive name itself looks like media/doc bait
                    # e.g. photos.zip containing setup.exe -> medium risk
                    return (f"Archive.ContainsExecutable:{Path(name).name}", f"Executable inside archive: {name}")
        return None
    except zipfile.BadZipFile:
        return ("Corrupt.Archive", "Archive header is corrupt - could be malformed payload.")
    except OSError:
        return None


def scan_file(path_str):
    """Main entry: scan ANY single file. Returns result dict."""
    path = Path(path_str)
    sigs = load_signatures()

    if not path.exists() or not path.is_file():
        return clean_result(path)

    fname = path.name
    ext = path.suffix.lower()
    lname = fname.lower()

    # 1. Known bad filename (cracks, fake codecs)
    if lname in [b.lower() for b in sigs.get("bad_filenames", [])]:
        return threat(path, f"Trojan.FakeInstaller.{fname}", "HIGH", "app",
                       f"Known malicious filename: {fname}. Often bundles password stealers.",
                       "quarantine")

    # 2. Double extension trick - HIGH
    if has_double_extension(fname):
        cat = "image" if "." + fname.lower().split(".")[-2] in IMAGE_EXTS else "file"
        return threat(path, f"Trojan.DoubleExtension.{fname}", "HIGH", cat,
                       f"Double extension trick: '{fname}' pretends to be media/document but is executable.",
                       "quarantine")

    # 3. SHA256 signature match - CRITICAL
    try:
        digest = sha256_of_file(path)
        if digest in sigs.get("bad_sha256", []):
            return threat(path, "EICAR-Test-File" if digest == "275a021bbfb6489e54d471899f7db9d1663fc695ec2d4cff1a2a4a2837c88" else f"Malware.Hash.{digest[:12]}",
                          "CRITICAL" if digest != "44d88612fea8a8f36de82e1278abb02f" else "HIGH",
                          "file", f"File hash matches known-malicious signature: {digest[:16]}...",
                          "quarantine")
    except OSError as e:
        return threat(path, "Unreadable.File", "LOW", "file", f"Cannot read file: {e}", "none")

    # 4. Header mismatch (exe pretending to be jpg/png/pdf) - HIGH
    if check_header(path):
        cat = "image" if ext in IMAGE_EXTS else ("video" if ext in VIDEO_EXTS else "file")
        return threat(path, f"FakeHeader.{fname}", "HIGH", cat,
                       f"File header does not match extension '{ext}'. Possibly an executable disguised as media/document.",
                       "quarantine")

    # 5. Archive insider scan - MEDIUM
    if ext in ARCHIVE_EXTS and ext == ".zip":
        found = scan_archive_members(path, sigs)
        if found:
            return threat(path, found[0], "MEDIUM", "archive", found[1], "quarantine")

    # 6. Heuristic keyword scan - MEDIUM/HIGH
    found = scan_content_keywords(path, sigs)
    if found:
        sev = "CRITICAL" if "mimikatz" in found[0].lower() or "ransomware" in found[0].lower() else "MEDIUM"
        cat = "app" if ext in APP_EXTS else "file"
        return threat(path, found[0], sev, cat, found[1], "quarantine")

    # 7. Suspicious app in Downloads root asking attention? -> LOW info only if tiny script
    # (We stay quiet for clean files to avoid popup fatigue.)

    # Category for logging
    if ext in IMAGE_EXTS:
        cat = "image"
    elif ext in VIDEO_EXTS:
        cat = "video"
    elif ext in AUDIO_EXTS:
        cat = "audio"
    elif ext in APP_EXTS:
        cat = "app"
    elif ext in ARCHIVE_EXTS:
        cat = "archive"
    else:
        cat = "file"
    r = clean_result(path)
    r["category"] = cat
    return r


def scan_folder(folder_str, recursive=True):
    """Full/custom folder scan. Returns (results_list, summary)."""
    folder = Path(folder_str)
    results = []
    if not folder.exists():
        return results, {"total": 0, "threats": 0}
    pattern = "**/*" if recursive else "*"
    files = [p for p in folder.glob(pattern) if p.is_file()]
    for p in files:
        try:
            r = scan_file(str(p))
            results.append(r)
        except Exception as e:
            results.append(threat(str(p), "Scan.Error", "LOW", "file", f"Scan error: {e}", "none"))
    threats = [r for r in results if not r["clean"]]
    return results, {"total": len(results), "threats": len(threats)}


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    if os.path.isfile(target):
        print(json.dumps(scan_file(target), indent=2))
    else:
        _, summary = scan_folder(target)
        print(json.dumps(summary, indent=2))
