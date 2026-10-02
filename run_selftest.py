from scanner_engine import scan_file, scan_folder
from url_checker import check_url
import json

tests = [
    "test_threats/demo_mimikatz.txt",
    "test_threats/photo.jpg.exe",
    "test_threats/clean_notes.txt",
]
for t in tests:
    print("=" * 60)
    print("FILE:", t)
    print(json.dumps(scan_file(t), indent=2))

print("=" * 60)
print("URL phish:", json.dumps(check_url("http://fakelogin-paypal.com/verify-account-urgent"), indent=2))
print("URL safe:", json.dumps(check_url("https://google.com"), indent=2))

print("=" * 60)
_, summary = scan_folder("test_threats")
print("folder summary:", summary)
