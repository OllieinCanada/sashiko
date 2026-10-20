#!/usr/bin/env python3
"""Publish only the exact validated native source to a new fork branch."""
import base64
import json
import os
from pathlib import Path
import subprocess
import urllib.request

ROOT = Path.cwd()
DATA = ROOT / "input-refresh"
REPORT = json.loads((DATA / "manifest.json").read_text())
HEAD = REPORT["head"]
BASE = REPORT["upstream"]
BRANCH = "codex/adaptive-cooldown-rebased-20261020"
SOURCE = ROOT / "publish-source"
def git(*args, cwd=SOURCE, env=None):
    return subprocess.check_output(["git", *args], cwd=cwd, env=env,
                                   text=True, stderr=subprocess.STDOUT).strip()
def api(path):
    request = urllib.request.Request(
        "https://api.github.com/repos/OllieinCanada/sashiko/" + path,
        headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"],
                 "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)
def main():
    run = api("actions/runs/39370876283")
    if run["status"] != "completed" or run["conclusion"] != "success":
        raise RuntimeError("remaining validation is not entirely successful")
    jobs = api("actions/runs/39370876283/jobs?per_page=100")["jobs"]
    expected = {"performance", "rollback", "crash", "conflict", "clock",
                "historical", "cancel", "concurrency", "faults", "upstream",
                "deterministic"}
    phases = {job["name"].removeprefix("extended (").removesuffix(")")
              for job in jobs if job["name"].startswith("extended (")}
    if phases != expected or any(job["conclusion"] != "success" for job in jobs):
        raise RuntimeError("incomplete exact-source validation jobs")
    if REPORT["status"] != "CHECKED_OPTIMIZATION_EXTENDED_PENDING":
        raise RuntimeError("unexpected native preparation state")
    for label in ["required-hash-check", "required-message-check"]:
        checks = [check for check in REPORT["checks"] if check["name"] == label]
        if len(checks) != 1 or checks[0]["exit"] != 0:
            raise RuntimeError("required native checks missing")
    maximum = json.loads((ROOT / "input-maximum/manifest.json").read_text())
    if maximum["status"] != "PASS" or maximum["head"] != HEAD or maximum["tree"] != REPORT["tree"]:
        raise RuntimeError("maximum-series checks do not match the exact source")
    subprocess.run(["git", "clone", "--no-checkout",
                    "https://github.com/OllieinCanada/sashiko.git", str(SOURCE)],
                   check=True, timeout=60)
    git("fetch", "--no-tags", "https://github.com/sashiko-dev/sashiko.git", BASE)
    git("fetch", str(DATA / "rebased-source.bundle"), "HEAD")
    git("checkout", "--detach", HEAD)
    if git("rev-parse", "HEAD^{tree}") != REPORT["tree"]:
        raise RuntimeError("checked source tree mismatch")
    if git("status", "--porcelain"):
        raise RuntimeError("source checkout not clean")
    git("merge-base", "--is-ancestor", BASE, HEAD)
    paths = git("diff", "--name-only", BASE, HEAD).splitlines()
    if not paths or any(path.startswith(".github/") for path in paths):
        raise RuntimeError("audit files leaked into contribution")
    if subprocess.run(["pgrep", "-x", "sashiko"],
                      stdout=subprocess.DEVNULL).returncode == 0:
        raise RuntimeError("unexpected running sashiko")
    subprocess.run(["make", "sob", "RANGE=" + BASE + "..HEAD"],
                   cwd=SOURCE, check=True, timeout=30)
    git("diff", "--check", BASE, HEAD)
    existing = git("ls-remote", "--heads", "origin", BRANCH)
    if existing and existing.split()[0] != HEAD:
        raise RuntimeError("destination already exists at another head")
    latest_request = urllib.request.Request(
        "https://api.github.com/repos/sashiko-dev/sashiko/commits/main",
        headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(latest_request, timeout=20) as response:
        latest = json.load(response)["sha"]
    if latest != BASE:
        raise RuntimeError("upstream moved after validation")
    if len(REPORT.get("mutants", [])) != 2 or any(
            mutant["status"] != "KILLED" for mutant in REPORT["mutants"]):
        raise RuntimeError("missing final-source mutation evidence")
    if not existing:
        push_env = os.environ.copy()
        token = push_env.pop("GH_TOKEN")
        for key in list(push_env):
            if key.startswith("GIT_TRACE") or key == "GIT_CURL_VERBOSE":
                push_env.pop(key)
        push_env["GIT_CONFIG_COUNT"] = "1"
        push_env["GIT_CONFIG_KEY_0"] = "http.https://github.com/.extraheader"
        encoded = base64.b64encode(("x-access-token:" + token).encode()).decode()
        push_env["GIT_CONFIG_VALUE_0"] = "AUTHORIZATION: basic " + encoded
        git("push", "--porcelain", "origin", HEAD + ":refs/heads/" + BRANCH,
            env=push_env)
    if git("ls-remote", "--heads", "origin", BRANCH).split()[0] != HEAD:
        raise RuntimeError("published head mismatch")
    result = {"status": "PASS", "source_head": HEAD, "source_tree": REPORT["tree"],
              "upstream_base": BASE, "fork_branch": BRANCH,
              "native_commits_preserved": True,
              "required_checks_run": 39370749173,
              "remaining_validation_run": 39370876283,
              "provider_calls": 0, "upstream_pr_opened": False,
              "maximum_validation_run": 39370876169,
              "model_review_completed": False,
              "model_review_attempt": 39372578093,
              "maintainer_agreement": False}
    (ROOT / "published-source.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
main()
