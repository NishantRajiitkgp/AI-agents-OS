"""Read check-run annotations for HEAD. Local helper, not part of the repository."""
import json
import subprocess
import sys

REPO = "NishantRajiitkgp/AI-agents-OS"
ONLY = sys.argv[1] if len(sys.argv) > 1 else ""


def api(url):
    out = subprocess.run(["curl.exe", "-s", url], capture_output=True).stdout.decode(
        "utf-8", "replace")
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {}


head = subprocess.run(["git", "rev-parse", "HEAD"],
                      capture_output=True, text=True).stdout.strip()
checks = api(f"https://api.github.com/repos/{REPO}/commits/{head}/check-runs").get(
    "check_runs", [])

if not checks:
    print("no check runs for HEAD yet")

for check in checks:
    if ONLY and ONLY not in check["name"]:
        continue
    print(f"=== {check['name']}: {check['status']} / {check.get('conclusion')} ===")
    if check.get("conclusion") in (None, "success"):
        continue
    for note in api(f"https://api.github.com/repos/{REPO}/check-runs/{check['id']}/annotations"):
        title = note.get("title") or ""
        if "deprecat" in (note.get("message") or "").lower():
            continue
        print(f"--- {title} [{note.get('annotation_level')}] ---")
        print(note.get("message") or "")
    print()
