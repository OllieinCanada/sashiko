"""Publish the signed-off source commit, without force or PR creation."""
import base64
import json
import os
from pathlib import Path
import subprocess

root = Path.cwd()
source = Path("/tmp/pr455-model-source")
manifest = json.loads((root / "native-artifact/manifest.json").read_text())
branch = "test/sashiko-guidance-lifecycle-20261021"
url = "https://github.com/OllieinCanada/sashiko.git"
remote = subprocess.check_output(
    ["git", "ls-remote", url, "refs/heads/" + branch], text=True).strip()
if remote and remote.split()[0] != manifest["head"]:
    raise RuntimeError("source branch already exists at a different commit")
if not remote:
    token = os.environ.pop("GH_TOKEN")
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_TRACE") and key not in ("GIT_CURL_VERBOSE",)}
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "http.https://github.com/.extraheader"
    env["GIT_CONFIG_VALUE_0"] = "AUTHORIZATION: basic " + base64.b64encode(
        ("x-access-token:" + token).encode()).decode()
    subprocess.run(["git", "push", url, "HEAD:refs/heads/" + branch],
                   cwd=source, env=env, check=True, timeout=60)
report = {"status": "PASS", "branch": branch, "head": manifest["head"],
          "tree": manifest["tree"], "base": manifest["base"],
          "provider_calls": 0, "pr_opened": False, "force_push": False}
(root / "source-publication.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
