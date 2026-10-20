#!/usr/bin/env python3
"""Execute bounded maximum-series, missing-history and process-restart fixtures."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess

ROOT = Path.cwd()
SOURCE = ROOT / "maximum-source"
OUT = ROOT / "maximum-results"
OUT.mkdir(exist_ok=True)
INPUT = ROOT / "input-refresh"
META = json.loads((INPUT / "manifest.json").read_text())
ENV = os.environ.copy()
ENV.update(CARGO_TARGET_DIR=str(ROOT / "target"), CARGO_NET_RETRY="0",
           CARGO_HTTP_TIMEOUT="20", PYTHONDONTWRITEBYTECODE="1")
REPORT = {"status": "RUNNING", "head": META["head"], "tree": META["tree"],
          "upstream": META["upstream"], "checks": [], "provider_calls": 0}
def save():
    (OUT / "manifest.json").write_text(json.dumps(REPORT, indent=2) + "\n")
def run(args, label, cwd=SOURCE, expected=0, env=ENV, timeout=900):
    print("START " + label, flush=True)
    if subprocess.run(["pgrep", "-x", "sashiko"], stdout=subprocess.DEVNULL).returncode == 0:
        raise RuntimeError("unexpected running sashiko")
    with (OUT / (label + ".log")).open("w") as log:
        child = subprocess.Popen(args, cwd=cwd, env=env, stdout=log,
                                 stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = child.wait(timeout=timeout)
        finally:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()
    text = (OUT / (label + ".log")).read_text()
    if code != expected:
        print(text[-16000:], flush=True)
        raise RuntimeError(label + ": unexpected exit " + str(code))
    REPORT["checks"].append({"name": label, "exit": code})
    save()
    print("PASS " + label, flush=True)
    return text
def git(*args):
    return subprocess.check_output(["git", *args], cwd=SOURCE, env=ENV, text=True).strip()
try:
    save()
    run(["git", "clone", "--no-hardlinks", "--no-checkout", str(ROOT), str(SOURCE)],
        "clone", ROOT, timeout=60)
    run(["git", "fetch", "--no-tags", "https://github.com/sashiko-dev/sashiko.git", META["upstream"]],
        "fetch-upstream", timeout=60)
    run(["git", "fetch", str(INPUT / "rebased-source.bundle"), "HEAD"],
        "fetch-bundle", timeout=60)
    run(["git", "checkout", "--detach", META["head"]], "checkout", timeout=30)
    if git("rev-parse", "HEAD^{tree}") != META["tree"] or git("status", "--porcelain"):
        raise RuntimeError("not the clean checked source")
    path = SOURCE / "src/db/cooldown.rs"
    original = path.read_text()
    fixture = (ROOT / ".github/adaptive-validation/native_fixture.rs").read_text()
    closing = original.rfind("}")
    path.write_text(original[:closing] + fixture + "\n" + original[closing:])
    REPORT["fixture_sha256"] = hashlib.sha256(fixture.encode()).hexdigest()
    try:
        run(["cargo", "fetch", "--locked"], "fetch-dependencies", timeout=120)
        run(["cargo", "clean", "-p", "sashiko"], "clear-generated-paths", timeout=60)
        run(["cargo", "fmt", "--all"], "format", timeout=60)
        text = run(["cargo", "test", "--locked", "--offline", "--all-features",
                    "--lib", "--no-run", "--message-format=json"], "build")
        binaries = []
        for line in text.splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (item.get("reason") == "compiler-artifact"
                    and item.get("target", {}).get("kind") == ["lib"]
                    and item.get("profile", {}).get("test") and item.get("executable")):
                binaries.append(item["executable"])
        if len(set(binaries)) != 1:
            raise RuntimeError("ambiguous library artifact")
        binary = binaries[0]
        REPORT["binary_sha256"] = hashlib.sha256(Path(binary).read_bytes()).hexdigest()
        def test(name, label, env=ENV, expected=0):
            text = run([binary, "db::cooldown::tests::hosted_validation::" + name,
                        "--exact", "--ignored", "--nocapture", "--test-threads=1"],
                       label, env=env, expected=expected, timeout=90)
            if "running 1 test" not in text or (expected == 0 and "1 passed; 0 failed" not in text):
                raise RuntimeError("missing exact native fixture execution")
        test("test_cooldown_hosted_maximum_series", "maximum-1024-parts")
        test("test_cooldown_hosted_history_read_fault", "history-read-failure")
        env = ENV.copy()
        env.update(COOLDOWN_RESTART_PATH=str(OUT / "restart.db"), COOLDOWN_RESTART_PHASE="write")
        test("test_cooldown_hosted_process_restart", "exit-after-commit", env, 23)
        env["COOLDOWN_RESTART_PHASE"] = "read"
        test("test_cooldown_hosted_process_restart", "reopened-replay-and-release", env)
    finally:
        path.write_text(original)
    if git("diff", "--name-only", "HEAD", "--", "src", "Cargo.toml", "Cargo.lock"):
        raise RuntimeError("source not restored")
    REPORT["status"] = "PASS"
    REPORT["production_source_restored"] = True
    save()
    print(json.dumps(REPORT, indent=2), flush=True)
except BaseException as error:
    REPORT["status"] = "FAIL"
    REPORT["error"] = str(error)
    save()
    raise
