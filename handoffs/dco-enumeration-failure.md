# DCO checker failure: maintainer handoff

Target repository: [sashiko-dev/sashiko](https://github.com/sashiko-dev/sashiko).

This document packages a reproduced bug and a signed-off patch for maintainer review. The connected integration could not create an upstream issue; this public handoff keeps the reproduction, patch, and validation together. No pull request has been opened.

The DCO checker reports success when Git cannot enumerate the requested commits. This is reproducible on current main, `d7c69ae77326a3ef39362897cdf0751a06068cf1`.

A signed-off patch and offline regression tests are included below for a maintainer to take over.

### Reproduction

From a repository checkout:

```bash
bash scripts/check-sob.sh 'refs/heads/definitely-missing-dco-ref..HEAD'
echo "$?"
```

Git prints an invalid-revision diagnostic, but the checker then prints:

```text
All commits in refs/heads/definitely-missing-dco-ref..HEAD have valid matching sign-offs!
0
```

Running the checker outside a Git repository has the same false-success behavior. Consequently, the DCO step of `make check-pr` can pass without inspecting any commits.

Expected: a nonzero exit status, the original Git diagnostic, and no sign-off success message.

### Cause and correction

In [scripts/check-sob.sh](https://github.com/sashiko-dev/sashiko/blob/d7c69ae77326a3ef39362897cdf0751a06068cf1/scripts/check-sob.sh#L16), `git rev-list` runs in a `for` loop's command substitution. Its failure does not cause the enclosing loop to fail despite `set -e`.

The patch resolves the commit list in a standalone assignment before entering the loop. A failed enumeration then stops the script. Valid empty ranges and existing sign-off matching are preserved.

The original introducing change is [c4f84b0670b8](https://github.com/sashiko-dev/sashiko/commit/c4f84b0670b8ec7a1dbc76b758e5c60b2ba7e946).

### Validation

- Before the fix: 7 offline tests ran; 2 failed because invalid-range and non-repository invocations returned zero and printed success.
- After the fix: all 7 tests pass, covering signed, unsigned, mixed, empty, invalid, non-repository, and default ranges.
- `bash -n scripts/check-sob.sh`: passed.
- `make check-pr RANGE=origin/main..HEAD`: passed before and after committing, including matching DCO.
- `git diff --check origin/main..HEAD`: passed.
- Invalid range after the fix: checker exits 128; `make check-pr` exits 2; neither reports DCO success.
- Fixtures isolate inherited Git variables, configuration, hooks, and signing settings from the real checkout.

No Rust, Cargo, or YAML files changed. The documented diff-aware checks skipped Cargo formatting, Clippy, Rust tests, and yamllint. These checks are not claimed as executed.

### Maintainer handoff

Base: `d7c69ae77326a3ef39362897cdf0751a06068cf1`  
Local commit: `0ab3957292bff3603359eafdb9c67c7b0f8d0c23` (not pushed)  
Suggested PR title: **ci: propagate DCO commit enumeration failures**

Please apply the patch, recheck current main, and complete the repository-required local Sashiko self-review before pushing/opening a PR. **Model self-review is NOT RUN**: the execution environment lacked a runnable Sashiko/provider setup. Any model review should have an explicitly authorized provider/model and budget; an incomplete review should not be treated as clean.

Save the patch below as `dco-enumeration-fix.patch` and apply it with `git am dco-enumeration-fix.patch` on a clean dedicated branch based on the recorded base. Applying it may produce a different commit SHA.

<details>
<summary>Signed-off patch, including regression tests and check-pr integration</summary>

```diff
From 0ab3957292bff3603359eafdb9c67c7b0f8d0c23 Mon Sep 17 00:00:00 2001
From: Ollie Slapinski <oliverslapinski@hotmail.com>
Date: Sun, 25 Oct 2026 04:24:35 +0000
Subject: [PATCH] ci: propagate DCO commit enumeration failures

An invalid revision range or failed Git invocation currently produces an
empty loop and a successful DCO report. Bash does not propagate the
command substitution's status through the for loop, even with set -e.

Resolve the commit list in a standalone assignment before checking
trailers so enumeration errors stop the checker. Preserve valid empty
ranges and existing sign-off matching.

Add offline fixture tests and run them from check-pr when the checker or
its tests change.

Fixes: c4f84b0670b8 ("feature: introduce Justfile")
Signed-off-by: Ollie Slapinski <oliverslapinski@hotmail.com>
---
 Makefile                  |  4 ++
 scripts/check-sob.sh      |  5 ++-
 scripts/test_check_sob.py | 95 +++++++++++++++++++++++++++++++++++++++
 3 files changed, 103 insertions(+), 1 deletion(-)
 create mode 100644 scripts/test_check_sob.py

diff --git a/Makefile b/Makefile
index 938c67d..20b783b 100644
--- a/Makefile
+++ b/Makefile
@@ -75,6 +75,10 @@ check-pr: sob
 		echo "No changed files detected."; \
 		exit 0; \
 	fi; \
+	if echo "$$CHANGED" | grep -qE '^scripts/(check-sob\.sh|test_check_sob\.py)$$'; then \
+		echo "Running DCO checker regression tests..."; \
+		python3 scripts/test_check_sob.py; \
+	fi; \
 	if echo "$$CHANGED" | grep -qE '\.(yml|yaml)$$|^\.yamllint$$'; then \
 		echo "Running yamllint..."; \
 		yamllint .; \
diff --git a/scripts/check-sob.sh b/scripts/check-sob.sh
index e6f172b..1b95eac 100755
--- a/scripts/check-sob.sh
+++ b/scripts/check-sob.sh
@@ -13,7 +13,10 @@ fi
 
 echo "Checking Developer Certificate of Origin (S-O-B) in range: $RANGE"
 
-for commit in $(git rev-list "$RANGE" --no-merges); do
+# Resolve the range separately so set -e propagates Git enumeration failures.
+COMMITS=$(git rev-list "$RANGE" --no-merges)
+
+for commit in $COMMITS; do
     AUTHOR_NAME=$(git log -1 --format="%an" "$commit")
     AUTHOR_EMAIL=$(git log -1 --format="%ae" "$commit")
     
diff --git a/scripts/test_check_sob.py b/scripts/test_check_sob.py
new file mode 100644
index 0000000..27eb522
--- /dev/null
+++ b/scripts/test_check_sob.py
@@ -0,0 +1,95 @@
+#!/usr/bin/env python3
+"""Offline regression tests for the DCO checker, using an isolated Git repository."""
+
+import os
+from pathlib import Path
+import subprocess
+import tempfile
+import unittest
+
+
+CHECKER = Path(__file__).resolve().with_name("check-sob.sh")
+
+
+class CheckSobTests(unittest.TestCase):
+    @classmethod
+    def setUpClass(cls):
+        cls.scratch = tempfile.TemporaryDirectory(prefix="sashiko-dco-")
+        cls.addClassCleanup(cls.scratch.cleanup)
+        cls.repository = Path(cls.scratch.name) / "repository"
+        cls.outside = Path(cls.scratch.name) / "outside"
+        cls.outside.mkdir()
+        cls.env = {
+            key: value for key, value in os.environ.items()
+            if not key.startswith("GIT_")
+        }
+        cls.env.update(
+            GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, LC_ALL="C"
+        )
+        subprocess.run(
+            ["git", "init", "--quiet", str(cls.repository)],
+            env=cls.env, check=True, capture_output=True,
+        )
+        cls.git("config", "user.name", "DCO Fixture")
+        cls.git("config", "user.email", "dco-fixture@example.com")
+        cls.git("config", "commit.gpgsign", "false")
+        cls.git("config", "core.hooksPath", os.devnull)
+        cls.git("commit", "--quiet", "--allow-empty", "-s", "-m", "Root")
+        cls.root = cls.git("rev-parse", "HEAD")
+        cls.git("commit", "--quiet", "--allow-empty", "-s", "-m", "Signed")
+        cls.signed = cls.git("rev-parse", "HEAD")
+        cls.git("commit", "--quiet", "--allow-empty", "-m", "Unsigned")
+        cls.unsigned = cls.git("rev-parse", "HEAD")
+
+    @classmethod
+    def git(cls, *args):
+        return subprocess.check_output(
+            ["git", "-C", str(cls.repository), *args], env=cls.env, text=True
+        ).strip()
+
+    def check(self, *args, outside=False):
+        return subprocess.run(
+            ["bash", str(CHECKER), *args], env=self.env, text=True,
+            cwd=self.outside if outside else self.repository,
+            capture_output=True, check=False,
+        )
+
+    def assert_rejected(self, result):
+        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
+        self.assertNotIn("have valid matching sign-offs!", result.stdout)
+
+    def test_signed_commit_passes(self):
+        result = self.check(f"{self.root}..{self.signed}")
+        self.assertEqual(result.returncode, 0, result.stderr)
+        self.assertIn("have valid matching sign-offs!", result.stdout)
+
+    def test_unsigned_commit_fails(self):
+        result = self.check(f"{self.signed}..{self.unsigned}")
+        self.assert_rejected(result)
+        self.assertIn("DCO mismatch", result.stdout)
+
+    def test_mixed_range_fails(self):
+        self.assert_rejected(self.check(f"{self.root}..{self.unsigned}"))
+
+    def test_empty_valid_range_passes(self):
+        result = self.check(f"{self.signed}..{self.signed}")
+        self.assertEqual(result.returncode, 0, result.stderr)
+
+    def test_invalid_range_fails(self):
+        result = self.check("refs/heads/missing-dco-fixture..HEAD")
+        self.assert_rejected(result)
+        self.assertIn("fatal:", result.stderr)
+
+    def test_outside_repository_fails(self):
+        result = self.check("HEAD", outside=True)
+        self.assert_rejected(result)
+        self.assertIn("not a git repository", result.stderr)
+
+    def test_default_range_checks_head(self):
+        result = self.check()
+        self.assert_rejected(result)
+        self.assertIn("DCO mismatch", result.stdout)
+
+
+if __name__ == "__main__":
+    unittest.main()
-- 
2.52.0
```

</details>
