"""
Web Shield - checks every website / URL before you open it.
Stdlib only. Offline-first (local blocklist + heuristic).
"""
from urllib.parse import urlparse
from scanner_engine import load_signatures


def check_url(url: str):
    url = url.strip()
    if not url:
        return {"clean": True, "threat_name": "", "severity": "CLEAN",
                "location": url, "reason": "Empty URL.", "recommended_action": "none"}

    sigs = load_signatures()
    low = url.lower()
    if not low.startswith(("http://", "https://")):
        low_url = "http://" + low
    else:
        low_url = low
    try:
        parsed = urlparse(low_url)
        domain = parsed.netloc.lower()
        path = parsed.path.lower()
    except Exception:
        domain, path = low_url, ""

    # 1. Explicit blocklist - HIGH, recommend block
    for d in sigs.get("blocked_domains", []):
        if d.lower() in domain:
            return {"clean": False, "threat_name": f"Phishing.BlockedDomain:{d}",
                    "severity": "HIGH", "category": "website", "location": url,
                    "reason": f"Domain '{d}' is in local blocklist (known phishing/malware).",
                    "recommended_action": "block"}

    # 2. Phishing keywords in URL - HIGH
    for kw in sigs.get("phishing_keywords", []):
        if kw.lower() in low:
            return {"clean": False, "threat_name": f"Phishing.SuspiciousURL:{kw}",
                    "severity": "HIGH", "category": "website", "location": url,
                    "reason": f"URL contains phishing keyword '{kw}'. Often fake login pages.",
                    "recommended_action": "block"}

    # 3. Look-alike / punycode tricks - MEDIUM
    if "xn--" in domain or domain.count("-") >= 4:
        return {"clean": False, "threat_name": "Phishing.LookAlikeDomain",
                "severity": "MEDIUM", "category": "website", "location": url,
                "reason": "Domain looks like an IDN / look-alike trick (e.g. paypa1, rn vs m).",
                "recommended_action": "block"}

    # 4. No HTTPS on login/bank page - MEDIUM warning
    if low_url.startswith("http://") and any(k in low for k in ["login", "bank", "pay", "otp", "verify", "account"]):
        return {"clean": False, "threat_name": "Risk.NoHTTPSLogin",
                "severity": "MEDIUM", "category": "website", "location": url,
                "reason": "Login/payment page without HTTPS. Password can be stolen.",
                "recommended_action": "block"}

    # 5. Executable direct download link - MEDIUM
    if any(path.endswith(e) for e in [".exe", ".scr", ".bat", ".ps1", ".vbs"]):
        return {"clean": False, "threat_name": "Risk.DirectExecutableDownload",
                "severity": "MEDIUM", "category": "website", "location": url,
                "reason": "Link directly downloads an executable. Scan it after download.",
                "recommended_action": "block"}

    # 6. URL shortener hiding destination - LOW
    shorteners = ["bit.ly", "tinyurl", "t.co", "goo.gl", "is.gd"]
    if any(s in domain for s in shorteners):
        return {"clean": False, "threat_name": "Risk.ShortenedURL",
                "severity": "LOW", "category": "website", "location": url,
                "reason": "Shortened URL hides real destination. Preview before opening.",
                "recommended_action": "block"}

    return {"clean": True, "threat_name": "", "severity": "CLEAN",
            "category": "website", "location": url,
            "reason": "No phishing/malware pattern matched.", "recommended_action": "none"}


if __name__ == "__main__":
    import sys, json
    print(json.dumps(check_url(sys.argv[1] if len(sys.argv) > 1 else "https://google.com"), indent=2))
