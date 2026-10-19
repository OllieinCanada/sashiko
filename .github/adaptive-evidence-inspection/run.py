#!/usr/bin/env python3
"""Inspect completed evidence without rebuilding or contacting a model."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path.cwd()
SOURCE = ROOT / "evidence-input/source"
MUTATION = ROOT / "evidence-input/mutation"
CANDIDATE = "bd59059f1864aea81b11b5de0eb97e5d2ec53667"
HEAD = "6667a81cd25a69feca76e65d94aacb4c83b2ce72"
TREE = "d38b668f511e2e0972aa4588174a2c55f3582b30"
PATHS = ["src", "docs", "designs", "MAINTAINERS_GUIDE.md", "Cargo.toml", "Cargo.lock"]
report = {"candidate": CANDIDATE, "source_only_head": HEAD, "source_only_tree": TREE,
          "status": "RUNNING", "mutants": [], "source_checks": []}

def git(*args, cwd=ROOT):
    return subprocess.check_output(["git", *args], cwd=cwd, text=True,
                                   stderr=subprocess.STDOUT).strip()

source = json.loads((SOURCE / "manifest.json").read_text())
mutation = json.loads((MUTATION / "manifest.json").read_text())
assert source["candidate_checkpoint"] == "010274b4d10a4db39cb7de2bcef0108a92bdc82b"
assert source["base"] == "f6e2e172e1e669b6767a4c74fe91d062b41fd71c"
assert source["head"] == HEAD and source["tree"] == TREE
assert len(source["commits"]) == 3
assert all(c["status"] == "PASS" for c in source["checks"])
assert mutation["candidate_commit"] == CANDIDATE and mutation["status"] == "PASS"
bundle = (SOURCE / "source-only.bundle").resolve()
git("bundle", "verify", str(bundle))
with tempfile.TemporaryDirectory(prefix="source-evidence-") as tmp:
    checkout = Path(tmp) / "source"
    git("clone", "--no-hardlinks", "--no-checkout", str(ROOT), str(checkout))
    git("fetch", str(bundle), "HEAD", cwd=checkout)
    assert git("rev-parse", "FETCH_HEAD", cwd=checkout) == HEAD
    assert git("rev-parse", HEAD + "^{tree}", cwd=checkout) == TREE
    assert not git("diff", "--name-only", CANDIDATE, HEAD, "--", *PATHS, cwd=checkout)
    for commit in source["commits"]:
        message = git("show", "-s", "--format=%B", commit["sha"], cwd=checkout)
        assert "Signed-off-by: Ollie Slapinski <oliverslapinski@hotmail.com>" in message
    report["source_equivalence"] = "PASS: complete production paths match"
assert source["patches"] == {"0001-server-allow-concrete-extractor-rejection-response-s.patch":"8fcd73ae828189badd815813e5f0554ae1b4bf57226a476f79cc8130dabfd959","0003-mail-add-opt-in-per-author-publication-cooldowns.patch":"1a47b118f01d8c007d04582da3c305eb68105ef43adaa2ebf475c624c1d77cc7","0002-db-retire-superseded-series-reviews-awaiting-publica.patch":"3f155172449cbd52dc42f8ac42c27e8ec734008736798cc93cbee67ae472a89b"}
for name, digest in source["patches"].items():
    path = SOURCE / "patches" / name
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
report["patch_hashes"] = source["patches"]
for phase in ["response-lint", "prerequisite", "adaptive"]:
    text = (SOURCE / ("check-pr-before-" + phase + ".log")).read_text()
    summaries = [line for line in text.splitlines()
                 if "test result:" in line or "Signed-off-by" in line]
    assert any("test result: ok" in line for line in summaries)
    report["source_checks"].append({"phase": phase, "summaries": summaries})
    print("SOURCE-CHECK " + json.dumps(report["source_checks"][-1]), flush=True)
for mutant in mutation["mutants"]:
    name = mutant["name"]
    text = (MUTATION / ("negative-" + name + ".log")).read_text()
    assert "running 1 test" in text and "0 passed; 1 failed" in text
    lines = text.splitlines()
    contexts = []
    for index, line in enumerate(lines):
        if "panicked at" in line or "assertion" in line or "Error:" in line:
            contexts.extend(lines[max(0, index - 1):index + 7])
    assert contexts, "missing semantic failure: " + name
    assert not re.search(r"timed out|No space left|permission denied", text, re.I)
    row = {"name": name, "status": "KILLED", "failure_context": contexts[:36]}
    report["mutants"].append(row)
    print("MUTATION-CONTEXT " + json.dumps(row), flush=True)
assert len(report["mutants"]) == 8
for directory, labels in [
        (ROOT / "evidence-input/focused", ["ignore-ingestion", "review-privacy"]),
        (ROOT / "evidence-input/cancellation", ["cancel-watch", "task-abort"])]:
    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["status"] == "PASS" and manifest["production_base"] == CANDIDATE
    assert len(manifest["mutants"]) == 2
    for label in labels:
        negative = directory / ("negative-" + label + ".log")
        text = negative.read_text()
        assert "running 1 test" in text and "0 passed; 1 failed" in text
        assert "panicked at" in text or "Error:" in text
        assert not re.search(r"No space left|permission denied", text, re.I)
        report["mutants"].append({
            "name": label, "status": "KILLED",
            "log_sha256": hashlib.sha256(negative.read_bytes()).hexdigest()})
assert len(report["mutants"]) == 12
report["status"] = "PASS"
Path("adaptive-evidence-inspection.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2), flush=True)
