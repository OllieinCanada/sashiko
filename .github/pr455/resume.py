"""Finish checks on the identical candidate; reuse exact mutation evidence."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path.cwd()
SOURCE = ROOT / "candidate"
INPUT = ROOT / "prior-validation"
OUT = ROOT / "pr455-results"
OUT.mkdir()
BASE = "9d2bf58b17817b2cb4719fd4e1a14ca755b0dd6b"
BRANCH = "test/sashiko-guidance-lifecycle-20261021"
os.environ["CARGO_TARGET_DIR"] = str(ROOT / "target")
REPORT = {"status": "RUNNING", "base": BASE, "checks": [], "provider_calls": 0,
          "pr_opened": False, "reused_validation_run": 39657476345}
def save():
    (OUT / "manifest.json").write_text(json.dumps(REPORT, indent=2) + "\n")
def command(name, args, cwd=SOURCE, timeout=1800):
    start = time.monotonic()
    log = OUT / (name + ".log")
    with log.open("w") as stream:
        result = subprocess.run(args, cwd=cwd, stdout=stream,
                                stderr=subprocess.STDOUT, timeout=timeout)
    REPORT["checks"].append({"name": name, "command": args, "exit": result.returncode,
                             "seconds": round(time.monotonic()-start, 3)})
    save()
    print(json.dumps(REPORT["checks"][-1]), flush=True)
    if result.returncode != 0:
        print(log.read_text()[-16000:], flush=True)
        raise RuntimeError(name + " failed")
    return log.read_text()
def git(*args):
    return subprocess.check_output(["git", *args], cwd=SOURCE, text=True).strip()
def errors(path):
    found = {}
    for line in path.read_text().splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("reason") != "compiler-message":
            continue
        message = row["message"]
        if message["level"] != "error":
            continue
        item = {"code": (message.get("code") or {}).get("code"),
                "message": message["message"],
                "spans": [(span["file_name"], span["line_start"], span["column_start"])
                          for span in message["spans"] if span["is_primary"]]}
        found[json.dumps(item, sort_keys=True)] = item
    return [found[key] for key in sorted(found)]
try:
    previous = json.loads((INPUT / "manifest.json").read_text())
    assert previous["base"] == BASE and previous["provider_calls"] == 0
    required = {item["name"]: item for item in previous["checks"]}
    for name in ["format-check", "targeted-positive", "restored-targeted"]:
        assert required[name]["exit"] == 0
    assert required["required-checks"]["exit"] == 2
    assert required["baseline-clippy"]["exit"] == required["candidate-clippy"]["exit"] == 101
    assert len(previous["mutants"]) == 4
    assert all(item["runtime_regression_detected"] for item in previous["mutants"])
    baseline = errors(INPUT / "baseline-clippy.log")
    candidate = errors(INPUT / "candidate-clippy.log")
    assert baseline == candidate and len(baseline) == 4
    assert all(item["code"] == "clippy::result_large_err"
               and all(span[0] == "src/server.rs" for span in item["spans"])
               for item in baseline)
    REPORT["upstream_clippy"] = {
        "same_exact_unique_diagnostics": True, "unique_errors": baseline,
        "make_check_pr_exit": 2,
        "note": "Strict all-feature lint remains failed on untouched main and candidate; no lint waiver or production change."}
    REPORT["reused_checks"] = previous["checks"]
    REPORT["mutants"] = previous["mutants"]
    command("clone", ["git", "clone", "--no-checkout",
            "https://github.com/sashiko-dev/sashiko.git", str(SOURCE)], cwd=ROOT, timeout=60)
    git("checkout", "--detach", BASE)
    assert not git("status", "--porcelain")
    assert subprocess.run(["pgrep", "-x", "sashiko"], stdout=subprocess.DEVNULL).returncode != 0
    git("config", "user.name", "Ollie Slapinski")
    git("config", "user.email", "oliverslapinski@hotmail.com")
    git("switch", "-c", BRANCH)
    path = SOURCE / "src/workflows/sashiko_patch_review.rs"
    production = path.read_text().split("#[cfg(test)]", 1)[0]
    patch = (INPUT / "candidate.patch").read_bytes()
    REPORT["candidate_patch_sha256"] = hashlib.sha256(patch).hexdigest()
    command("apply-checked-patch", ["git", "apply", str(INPUT / "candidate.patch")])
    assert git("diff").strip() == patch.decode().strip()
    assert path.read_text().split("#[cfg(test)]", 1)[0] == production
    assert git("diff", "--name-only") == "src/workflows/sashiko_patch_review.rs"
    REPORT["source_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    REPORT["production_prefix_unchanged"] = True
    REPORT["rustc"] = subprocess.check_output(["rustc", "--version"], text=True).strip()
    REPORT["cargo"] = subprocess.check_output(["cargo", "--version"], text=True).strip()
    command("dependencies", ["cargo", "fetch", "--locked"], timeout=240)
    os.environ["CARGO_NET_OFFLINE"] = "true"
    command("format-check", ["cargo", "fmt", "--all", "--", "--check"])
    command("minimal-clippy", ["cargo", "clippy", "--offline", "--all-targets",
            "--no-default-features", "--", "-D", "warnings"])
    command("cache-clippy", ["cargo", "clippy", "--offline", "--all-targets",
            "--no-default-features", "--features", "cache", "--", "-D", "warnings"])
    suite = command("full-suite", ["cargo", "test", "--offline", "--all-features"])
    REPORT["suite_summaries"] = [line for line in suite.splitlines() if line.startswith("test result:")]
    command("diff-check", ["git", "diff", "--check"])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == REPORT["source_sha256"]
    (OUT / "candidate.patch").write_bytes(patch)
    message = (
        "test: cover Sashiko guidance propagation and finding lifecycle\n\n"
        "Record actual first-party workflow provider requests to protect\n"
        "bundled guide selection, exact contents and ordering. Carry a\n"
        "nonempty finding through verification into the report request and\n"
        "final output, and reject unintended guide injection.\n\n"
        "Use deterministic in-process providers with no external API calls.\n"
        "Compiled mutations confirm guidance and finding regressions are\n"
        "caught. Retain the test value of closed PR 455 without its extra\n"
        "profile or project-context mechanism.\n")
    message_path = OUT / "commit-message.txt"
    message_path.write_text(message)
    git("add", "src/workflows/sashiko_patch_review.rs")
    command("commit", ["git", "commit", "-s", "-F", str(message_path)])
    REPORT["head"] = git("rev-parse", "HEAD")
    REPORT["tree"] = git("rev-parse", "HEAD^{tree}")
    REPORT["changed_files"] = git("diff", "--name-only", BASE, "HEAD").splitlines()
    REPORT["diff_stat"] = git("diff", "--stat", BASE, "HEAD")
    command("final-signoffs", ["make", "sob", "RANGE=" + BASE + "..HEAD"])
    command("export-bundle", ["git", "bundle", "create", str(OUT / "candidate.bundle"),
                             "HEAD", "^" + BASE])
    assert not git("status", "--porcelain")
    REPORT["status"] = "VALIDATED_WITH_UPSTREAM_CLIPPY_FAILURE"
except Exception as error:
    REPORT["status"] = "FAILED"
    REPORT["error"] = str(error)
finally:
    save()
    print(json.dumps(REPORT, indent=2), flush=True)
if REPORT["status"] != "VALIDATED_WITH_UPSTREAM_CLIPPY_FAILURE":
    raise SystemExit(1)
