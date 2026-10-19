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
HEAD = "fa8a32646362a11ce00b7a90a14df3af828465d3"
TREE = "178107288293535d3adeaf180ba0328b9da6714a"
PATHS = ["src", "docs", "designs", "MAINTAINERS_GUIDE.md", "Cargo.toml", "Cargo.lock"]
report = {"candidate": CANDIDATE, "source_only_head": HEAD, "source_only_tree": TREE,
          "status": "RUNNING", "mutants": [], "source_checks": []}

def git(*args, cwd=ROOT):
    return subprocess.check_output(["git", *args], cwd=cwd, text=True,
                                   stderr=subprocess.STDOUT).strip()

source = json.loads((SOURCE / "manifest.json").read_text())
mutation = json.loads((MUTATION / "manifest.json").read_text())
assert source["candidate_checkpoint"] == CANDIDATE
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
report["status"] = "PASS"
Path("adaptive-evidence-inspection.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2), flush=True)
