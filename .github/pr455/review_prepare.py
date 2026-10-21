"""Verify the tested source before review or publication."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path.cwd()
SOURCE = Path("/tmp/pr455-model-source")
BASE = "9d2bf58b17817b2cb4719fd4e1a14ca755b0dd6b"
def git(*args):
    return subprocess.check_output(["git", *args], cwd=SOURCE, text=True).strip()
manifest = json.loads((ROOT / "native-artifact/manifest.json").read_text())
assert manifest["status"] == "VALIDATED_WITH_UPSTREAM_CLIPPY_FAILURE"
assert manifest["base"] == BASE
assert manifest["provider_calls"] == 0
assert manifest["production_prefix_unchanged"]
assert len(manifest["mutants"]) == 4 and all(m["runtime_regression_detected"] for m in manifest["mutants"])
for name in ["format-check", "minimal-clippy", "cache-clippy", "full-suite"]:
    assert any(c["name"] == name and c["exit"] == 0 for c in manifest["checks"]), name
assert manifest["upstream_clippy"]["same_exact_unique_diagnostics"]
assert len(manifest["upstream_clippy"]["unique_errors"]) == 4
assert manifest["changed_files"] == ["src/workflows/sashiko_patch_review.rs"]
assert subprocess.run(["pgrep", "-x", "sashiko"], stdout=subprocess.DEVNULL).returncode != 0
subprocess.run(["git", "clone", "--no-checkout",
                "https://github.com/sashiko-dev/sashiko.git", str(SOURCE)], check=True, timeout=60)
git("fetch", str(ROOT / "native-artifact/candidate.bundle"), "HEAD")
git("checkout", "--detach", manifest["head"])
assert git("rev-parse", "HEAD^{tree}") == manifest["tree"]
assert git("rev-list", "--count", BASE + "..HEAD") == "1"
assert git("diff", "--name-only", BASE, "HEAD") == "src/workflows/sashiko_patch_review.rs"
source = (SOURCE / "src/workflows/sashiko_patch_review.rs").read_bytes()
assert hashlib.sha256(source).hexdigest() == manifest["source_sha256"]
original = git("show", BASE + ":src/workflows/sashiko_patch_review.rs")
assert original.split("#[cfg(test)]", 1)[0] == source.decode().split("#[cfg(test)]", 1)[0]
assert not git("status", "--porcelain")
subprocess.run(["make", "sob", "RANGE=" + BASE + "..HEAD"], cwd=SOURCE, check=True)
print(json.dumps({"status": "PASS", "base": BASE, "head": manifest["head"],
                  "tree": manifest["tree"], "production_changes": 0}))
