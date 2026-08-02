"""Report run status and failed step names for HEAD. Temporary."""
import json
import subprocess

REPO = "NishantRajiitkgp/AI-agents-OS"


def api(url):
    out = subprocess.run(["curl.exe", "-s", url], capture_output=True).stdout.decode(
        "utf-8", "replace")
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {}


head = subprocess.run(["git", "rev-parse", "HEAD"],
                      capture_output=True, text=True).stdout.strip()
runs = [r for r in api(
    f"https://api.github.com/repos/{REPO}/actions/runs?per_page=30").get("workflow_runs", [])
    if r["head_sha"] == head]

if not runs:
    print("no runs registered for HEAD yet")
for run in runs:
    print(f"{run['name']:<12} {run['status']:<12} {str(run.get('conclusion'))}")
    if run["status"] != "completed" or run.get("conclusion") == "success":
        continue
    for job in api(run["jobs_url"]).get("jobs", []):
        for step in job.get("steps", []):
            if step.get("conclusion") not in ("success", "skipped", None):
                print(f"     failed in {job['name']}: {step['name']}")
