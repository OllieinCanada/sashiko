import json
import pathlib
import subprocess
import yaml

ROOT = pathlib.Path.cwd()
BASE = "026195ab58e2099e81017adbc6b97f33c509c8ba"
TESTED = "a9e2a05f10ecf1a2e8a7b0c3e3025609d9d9c0e9"
REVIEW = "d7f7a5516cc805444f23c534199af7e65d51e551"
TREE = "9a92a08ab85001d30c037811f4546381e22dbeab"

def git(*args, cwd=ROOT):
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()

subprocess.run(["git", "diff", "--check", "HEAD~1", "HEAD"], check=True)
parsed = 0
for path in (ROOT / ".github").rglob("*.json"):
    json.loads(path.read_text())
    parsed += 1
evidence = json.loads((ROOT / ".github/adaptive-upstream-refresh-evidence.json").read_text())
current = evidence["current"]
assert current["review_head"] == REVIEW
assert current["tested_source_head"] == TESTED
assert current["source_tree"] == TREE
assert current["native_passed"] == 1126
assert current["native_failed"] == 0
assert current["native_ignored"] == 2
assert not current["ready_for_upstream_pr"]
assert not current["maintainer_agreement"]
assert not current["upstream_pr_opened"]
reports = evidence["extended"]["reports"]
assert len(reports) == 11
for phase, report in reports.items():
    assert report["status"] == "PASS", phase
    assert report["head"] == TESTED, phase
    assert report["tree"] == TREE, phase
assert evidence["maximum"]["report"]["status"] == "PASS"
for comparison in evidence["performance"]["report"]["detail"]["comparisons"]:
    assert comparison["legacy_state_equal"]
    assert comparison["disabled_over_baseline"] <= 1.20
    assert comparison["enabled_over_disabled"] <= 1.50
assert len(evidence["performance"]["report"]["detail"]["samples"]) == 18
assert evidence["model_review"]["report"]["status"] == "INCOMPLETE"
assert evidence["model_review"]["report"]["provider_failure"]["error_type"] == "TimeoutError"
for name in ["adaptive-self-review.yml", "adaptive-final-model-review.yml"]:
    workflow = yaml.safe_load((ROOT / ".github/workflows" / name).read_text())
    for job in workflow["jobs"].values():
        assert str(job.get("if", "")).replace(" ", "") == "${{false}}", name
source = ROOT / "verified-review-source"
subprocess.run(["git", "clone", "--quiet", "https://github.com/OllieinCanada/sashiko.git", str(source)], check=True)
subprocess.run(["git", "checkout", "--quiet", REVIEW], cwd=source, check=True)
assert git("rev-parse", "HEAD^{tree}", cwd=source) == TREE
assert git("rev-parse", TESTED + "^{tree}", cwd=source) == TREE
assert git("diff", "--name-only", TESTED, REVIEW, cwd=source) == ""
assert git("rev-list", "--count", BASE + "..HEAD", cwd=source) == "8"
changed = git("diff", "--name-only", BASE, REVIEW, cwd=source).splitlines()
assert len(changed) == 15
assert not any(path.startswith(".github/") for path in changed)
subprocess.run(["make", "sob", "RANGE=" + BASE + "..HEAD"], cwd=source, check=True)
remote = git("ls-remote", "https://github.com/sashiko-dev/sashiko.git", "refs/heads/main", cwd=source).split()[0]
assert remote == BASE, "Upstream moved: inspect/rebase before publication"
for name in ["ADAPTIVE_UPSTREAM_REFRESH.md", "ADAPTIVE_PR_DRAFT.md"]:
    assert REVIEW in (ROOT / ".github" / name).read_text()
assert git("status", "--porcelain", cwd=source) == ""
report = {"status": "PASS", "audit_head": git("rev-parse", "HEAD"),
          "review_head": REVIEW, "tested_source_head": TESTED,
          "source_tree": TREE, "identical_source": True,
          "upstream": remote, "commits": 8, "changed_paths": 15,
          "json_documents_parsed": parsed, "provider_execution_disabled": True,
          "provider_calls": 0, "upstream_pr_opened": False,
          "rust_rerun": False,
          "reason": "Final changes are audit docs and metadata only; tested source tree unchanged."}
(ROOT / "final-evidence-verification.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
