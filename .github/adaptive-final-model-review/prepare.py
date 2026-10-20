#!/usr/bin/env python3
"""Verify paid-review prerequisites before exposing the provider secret."""
import json
import os
from pathlib import Path
import subprocess
import urllib.request

ROOT = Path.cwd()
SOURCE = Path("/tmp/adaptive-final-model-source")
BASE = "026195ab58e2099e81017adbc6b97f33c509c8ba"
HEAD = "a9e2a05f10ecf1a2e8a7b0c3e3025609d9d9c0e9"
TREE = "9a92a08ab85001d30c037811f4546381e22dbeab"
def git(*args, cwd=SOURCE):
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()
if subprocess.run(["pgrep", "-x", "sashiko"], stdout=subprocess.DEVNULL).returncode == 0:
    raise RuntimeError("unexpected running sashiko")
native = json.loads((ROOT / "model-source-artifact/manifest.json").read_text())
perf = json.loads((ROOT / "model-performance-artifact/manifest.json").read_text())
if native["head"] != HEAD or native["tree"] != TREE or native["upstream"] != BASE:
    raise RuntimeError("unexpected native candidate")
for label in ["required-hash-check", "required-message-check"]:
    checks = [check for check in native["checks"] if check["name"] == label]
    if len(checks) != 1 or checks[0]["exit"] != 0:
        raise RuntimeError("required native checks missing")
if (perf["head"] != HEAD or perf["status"] != "PASS"
        or perf["detail"]["status"] != "PASS"
        or perf["detail"]["baseline_commit"] != BASE
        or len(perf["detail"]["samples"]) != 18
        or not all(row["budget_pass"] for row in perf["detail"]["comparisons"])):
    raise RuntimeError("exact-source performance gate missing")
request = urllib.request.Request(
    "https://api.github.com/repos/OllieinCanada/sashiko/actions/runs/39372371968",
    headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"],
             "Accept": "application/vnd.github+json"})
with urllib.request.urlopen(request, timeout=20) as response:
    controls = json.load(response)
if (controls["head_sha"] != "952a343854ab63924687b03996ce3ec97dfbf7c3"
        or controls["status"] != "completed" or controls["conclusion"] != "success"):
    raise RuntimeError("offline budget controls did not pass")
for path in [".github/adaptive-final-model-review/run.py",
             ".github/adaptive-final-model-review/selftest.py"]:
    if git("rev-parse", "HEAD:" + path, cwd=ROOT) != git(
            "rev-parse", "952a343854ab63924687b03996ce3ec97dfbf7c3:" + path, cwd=ROOT):
        raise RuntimeError("review budget code differs from checked controls")
subprocess.run(["git", "clone", "--no-hardlinks", "--no-checkout", str(ROOT), str(SOURCE)],
               check=True, timeout=60)
git("fetch", "--no-tags", "https://github.com/sashiko-dev/sashiko.git", BASE)
git("fetch", str(ROOT / "model-source-artifact/rebased-source.bundle"), "HEAD")
git("checkout", "--detach", HEAD)
if git("rev-parse", "HEAD^{tree}") != TREE or git("status", "--porcelain"):
    raise RuntimeError("review checkout is not the clean exact tree")
paths = git("diff", "--name-only", BASE, HEAD).splitlines()
if any(path.startswith(".github/") for path in paths):
    raise RuntimeError("audit files entered the source-only contribution")
subprocess.run(["make", "sob", "RANGE=" + BASE + "..HEAD"], cwd=SOURCE,
               check=True, timeout=30)
env = os.environ.copy()
env["CARGO_TARGET_DIR"] = str(ROOT / "target")
subprocess.run(["cargo", "clean", "-p", "sashiko"], cwd=SOURCE,
               env=env, check=True, timeout=60)
print(json.dumps({"status": "PASS", "head": HEAD, "tree": TREE,
                  "provider_calls": 0, "maximum_review_usd": "1.00",
                  "maximum_review_seconds": 600}))
