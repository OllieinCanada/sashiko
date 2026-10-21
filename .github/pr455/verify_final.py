"""Check final evidence and published source without Rust/model reruns."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import yaml

ROOT = Path.cwd()
evidence = json.loads((ROOT / ".github/pr455/evidence.json").read_text())
for path in (ROOT / ".github/pr455").rglob("*.py"):
    ast.parse(path.read_text(), filename=str(path))
assert evidence["tests"] == {"passed": 1085, "failed": 0, "ignored": 2,
                             "focused_passed": 13, "mutants_killed": 4}
assert evidence["production_changes"] == 0
required = evidence["required_check_pr"]
assert required["status"] == "PASS"
assert required["head"] == evidence["head"] and required["base"] == evidence["base"]
assert required["tests"] == {"passed": 1085, "failed": 0, "ignored": 2}
assert required["environment"]["RUSTUP_TOOLCHAIN"] == "1.90.0"
assert required["environment"]["CARGO_NET_OFFLINE"] == "true"
assert len(required["passed_checks"]) == 8
assert evidence["model_review"]["attempts_run"] == 2
review = evidence["model_review"]["report"]
assert review["status"] == "INCOMPLETE"
assert review["provider_failure"]["http_status"] == 503
assert len(review["calls"]) == 1
assert review["head"] == evidence["head"]
workflow = yaml.safe_load((ROOT / ".github/workflows/pr455-publish-review.yml").read_text())
events = workflow.get("on", workflow.get(True))
assert set(events) == {"workflow_dispatch"}
for name in ["publish", "review"]:
    assert str(workflow["jobs"][name]["if"]).replace(" ", "") == "${{false}}"
retry_workflow = yaml.safe_load((ROOT / ".github/workflows/pr455-pinned-gates.yml").read_text())
retry_events = retry_workflow.get("on", retry_workflow.get(True))
assert set(retry_events) == {"workflow_dispatch"}
for name in ["checks", "review"]:
    assert str(retry_workflow["jobs"][name]["if"]).replace(" ", "") == "${{false}}"
# Check recorded conclusions against the public job metadata.
import urllib.request
for job_id, conclusion in [(required["job"], "success"),
                           (evidence["model_review"]["job"], "failure")]:
    url = "https://api.github.com/repos/OllieinCanada/sashiko/actions/jobs/" + str(job_id)
    with urllib.request.urlopen(url, timeout=20) as response:
        job = json.load(response)
    assert job["conclusion"] == conclusion
    assert job["run_id"] == 39673050262
source = Path("/tmp/pr455-final-source")
subprocess.run(["git", "clone", "--quiet", "--branch", evidence["branch"],
                "https://github.com/OllieinCanada/sashiko.git", str(source)], check=True)
def git(*args):
    return subprocess.check_output(["git", *args], cwd=source, text=True).strip()
assert git("rev-parse", "HEAD") == evidence["head"]
assert git("rev-parse", "HEAD^{tree}") == evidence["tree"]
assert git("rev-list", "--count", evidence["base"] + "..HEAD") == "1"
assert git("diff", "--name-only", evidence["base"], "HEAD") == "src/workflows/sashiko_patch_review.rs"
content = (source / "src/workflows/sashiko_patch_review.rs").read_bytes()
assert hashlib.sha256(content).hexdigest() == evidence["native"]["report"]["source_sha256"]
original = git("show", evidence["base"] + ":src/workflows/sashiko_patch_review.rs")
assert original.split("#[cfg(test)]", 1)[0] == content.decode().split("#[cfg(test)]", 1)[0]
assert not git("status", "--porcelain")
subprocess.run(["git", "diff", "--check", evidence["base"], "HEAD"], cwd=source, check=True)
subprocess.run(["make", "sob", "RANGE=" + evidence["base"] + "..HEAD"], cwd=source, check=True)
upstream = subprocess.check_output(
    ["git", "ls-remote", "https://github.com/sashiko-dev/sashiko.git", "refs/heads/main"],
    text=True).split()[0]
assert upstream == evidence["base"], "Upstream moved; reassess before PR"
report = {"status": "PASS", "head": evidence["head"], "tree": evidence["tree"],
          "upstream": upstream, "source_unchanged": True, "production_changes": 0,
          "required_checks": "PASS_RUST_1_90_0",
          "required_model_review": "BLOCKED_HTTP_503", "provider_execution_disabled": True,
          "provider_calls": 0, "rust_rerun": False, "pr_opened": False}
(ROOT / "pr455-final-metadata.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
