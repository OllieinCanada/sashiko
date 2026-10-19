#!/usr/bin/env python3
"""Native, exact-test regression runner. Defaults to offline Cargo."""
import argparse
import datetime
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time

parser = argparse.ArgumentParser()
parser.add_argument("--self-check", action="store_true")
parser.add_argument("--allow-dependency-downloads", action="store_true")
parser.add_argument("--command-timeout", type=int, default=1200)
args = parser.parse_args()
if not 30 <= args.command_timeout <= 1800:
    parser.error("--command-timeout must be between 30 and 1800 seconds")

SOURCE = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
ROOT = Path(os.environ["RUNNER_TEMP"]) / "held-series-validation"
ROOT.mkdir(exist_ok=True)
PRIMARY = "db::tests::test_superseded_series_held_review_is_not_released"
CONTROL = "db::tests::test_held_supersession_preserves_unrelated_reviews"

def executed_one(output, code, name, failure=False):
    wanted = "FAILED" if failure else "ok"
    summary = re.search(r"test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored;", output)
    if not summary or not re.search(r"running 1 test\b", output):
        return False
    if not re.search(r"test "+re.escape(name)+r" \.\.\. "+wanted+r"\b", output):
        return False
    result, passed, failed, ignored = summary.groups()
    if failure:
        return (code != 0 and result == "FAILED" and passed == "0" and failed == "1"
                and ignored == "0" and "assertion" in output
                and 'Some("Reviewed")' in output and 'Some("Cancelled")' in output)
    return code == 0 and result == "ok" and passed == "1" and failed == "0" and ignored == "0"

if args.self_check:
    success = f"running 1 test\ntest {PRIMARY} ... ok\ntest result: ok. 1 passed; 0 failed; 0 ignored; 7 filtered out;\n"
    failure = f'running 1 test\ntest {PRIMARY} ... FAILED\nassertion failed\nleft: Some("Reviewed")\nright: Some("Cancelled")\ntest result: FAILED. 0 passed; 1 failed; 0 ignored; 7 filtered out;\n'
    assert executed_one(success, 0, PRIMARY)
    assert executed_one(failure, 101, PRIMARY, failure=True)
    assert not executed_one("error: could not compile sashiko", 101, PRIMARY, failure=True)
    assert not executed_one("running 0 tests\ntest result: ok. 0 passed; 0 failed; 0 ignored;", 0, PRIMARY)
    assert not executed_one(success, 0, CONTROL)
    assert not executed_one(failure.replace('Some("Reviewed")', 'Some("Failed")'), 101, PRIMARY, failure=True)
    print(json.dumps({"runner_self_checks": 6, "result": "PASS", "native_tests": "NOT RUN"}))
    raise SystemExit(0)

OUT = ROOT / "evidence/native-runs" / datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
OUT.mkdir(parents=True, exist_ok=False)
manifest = {
    "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "mode": "focused native prerequisite validation; not full adaptive-feature validation",
    "source_commit": "f5b01837023512fb6b43a76f88a0aaf77c5ca43d",
    "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "cargo_offline": not args.allow_dependency_downloads,
    "commands": [], "status": "RUNNING", "native_tests": "NOT RUN",
    "required_full_gate": "NOT RUN", "model_self_review": "NOT RUN",
}
run_started = time.monotonic()

def save():
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")

def blocked(reason):
    manifest["status"] = "BLOCKED"
    manifest["reason"] = reason
    save()
    print(json.dumps({"status": "BLOCKED", "reason": reason,
                      "manifest": str(OUT / "manifest.json")}), flush=True)
    raise SystemExit(3)

cargo, rustc = shutil.which("cargo"), shutil.which("rustc")
if not cargo or not rustc:
    blocked("cargo and/or rustc unavailable on PATH; no download or substitute test runner attempted")

env = os.environ.copy()
for key in list(env):
    if key.startswith("GIT_") or key.startswith("SASHIKO"):
        env.pop(key)
for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
            "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
            "GH_TOKEN", "GITHUB_TOKEN", "SASHIKO_PATCHWORK_TOKEN"):
    env.pop(key, None)
env["RUSTUP_AUTO_INSTALL"] = "0"
env["CARGO_HOME"] = os.environ.get("CARGO_HOME", str(Path.home() / ".cargo"))
env["CARGO_TARGET_DIR"] = str(ROOT / "target")
env["CARGO_BUILD_JOBS"] = "2"

def run(label, command, cwd, timeout=None):
    remaining = 1800 - (time.monotonic() - run_started)
    if remaining <= 0:
        blocked("30-minute total native validation budget exhausted")
    logfile = OUT / (label+".log")
    started = time.monotonic()
    print(f"Running {label}; log: {logfile}", flush=True)
    with logfile.open("w") as stream:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=stream,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        timed_out = False
        try:
            process.wait(timeout=min(timeout or args.command_timeout, remaining))
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
    if logfile.stat().st_size > 20 * 1024 * 1024:
        blocked("command log exceeded 20 MiB; retain diagnostics and inspect resource use")
    output = logfile.read_text(errors="replace")
    record = {"label": label, "command": command, "cwd": str(cwd),
              "exit_code": process.returncode, "timed_out": timed_out,
              "elapsed_seconds": time.monotonic()-started, "log": logfile.name}
    # Freeze the actual test executable hash immediately after this invocation.
    binary = re.search(r"Running unittests src/lib.rs \(([^)]+)\)", output)
    if binary and Path(binary.group(1)).is_file():
        record["test_binary_sha256"] = hashlib.sha256(Path(binary.group(1)).read_bytes()).hexdigest()
    manifest["commands"].append(record)
    save()
    if timed_out:
        blocked(f"{label} timed out; native checks incomplete")
    return process.returncode, output

def git(*arguments, cwd=SOURCE):
    command = ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", *arguments]
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=30)
    if result.returncode:
        blocked("Git fixture preparation failed: "+result.stderr[-1000:])
    return result.stdout

try:
    for label, tool in [("rustc-version", rustc), ("cargo-version", cargo)]:
        code, output = run(label, [tool, "--version"], SOURCE, timeout=30)
        if code:
            blocked(label+" failed; installed pinned toolchain required")
        manifest[label] = output.strip()
    busy = subprocess.run(["pgrep", "-x", "sashiko"], capture_output=True)
    if busy.returncode == 0:
        blocked("another sashiko process is running; no process was killed")
    if busy.returncode != 1:
        blocked("could not establish absence of other sashiko processes")
    manifest["candidate_commit"] = git("rev-parse", "HEAD").strip()
    if git("status", "--porcelain").strip():
        blocked("checkout is dirty before validation")
    allowed = {"src/db.rs", "src/db/cooldown.rs", "src/cooldown.rs", "src/email_policy.rs", "src/lib.rs", "src/main.rs", "src/migrations/014_publication_cooldown.sql", "designs/ADAPTIVE_PUBLICATION_COOLDOWN.md", ".github/workflows/held-series-validation.yml", ".github/scripts/held_series_validation.py"}
    changed = set(git("diff", "--name-only", manifest["source_commit"], "HEAD").splitlines())
    if changed != allowed:
        blocked("unexpected candidate paths: " + repr(sorted(changed)))
    original = git("show", manifest["source_commit"]+":src/db.rs")
    candidate = (SOURCE / "src/db.rs").read_text()
    manifest["candidate_db_sha256"] = hashlib.sha256(candidate.encode()).hexdigest()
    marker = "    #[tokio::test]\n    async fn test_cancelled_patchset_not_reopened_by_claim_or_status_update()"
    begin = candidate.index("    async fn insert_reviewed_series_for_supersession(")
    end = candidate.index(marker, begin)
    if original.count(marker) != 1:
        blocked("test insertion boundary changed")
    test_only = original.replace(marker, candidate[begin:end]+marker)
    test_patch = OUT / "tests-only.patch"
    test_patch.write_text("".join(difflib.unified_diff(original.splitlines(True), test_only.splitlines(True),
                                                     fromfile="a/src/db.rs", tofile="b/src/db.rs")))
    full_patch = OUT / "candidate.patch"
    full_patch.write_text("".join(difflib.unified_diff(original.splitlines(True), candidate.splitlines(True),
                                                     fromfile="a/src/db.rs", tofile="b/src/db.rs")))
    with tempfile.TemporaryDirectory(prefix="native-fixture-", dir=ROOT) as temporary:
        base = Path(temporary)
        before, after = base / "before", base / "after"
        for checkout in (before, after):
            git("clone", "--quiet", "--no-hardlinks", str(SOURCE), str(checkout), cwd=ROOT)
        git("checkout", "--quiet", "--detach", manifest["source_commit"], cwd=before)
        git("apply", "--check", str(test_patch), cwd=before)
        git("apply", str(test_patch), cwd=before)
        # Candidate uses the complete actual head, including module and migration.
        git("checkout", "--quiet", "--detach", manifest["candidate_commit"], cwd=after)
        def test(checkout, label, name, failure=False):
            # Cargo's workspace fingerprint can consider another local clone's
            # root package fresh when both clones share one target directory.
            # Isolate baseline and candidate artifacts, not just their sources.
            env["CARGO_TARGET_DIR"] = str(ROOT / "target" / checkout.name)
            manifest.setdefault("build_targets", {})[checkout.name] = env["CARGO_TARGET_DIR"]
            command = [cargo, "test", "--locked"]
            if not args.allow_dependency_downloads:
                command.append("--offline")
            command += ["--lib", name, "--", "--exact", "--nocapture"]
            code, output = run(label, command, checkout)
            verified = executed_one(output, code, name, failure=failure)
            manifest.setdefault("native_test_results", []).append({
                "label": label, "name": name, "fixture": checkout.name,
                "expected_failure": failure, "required_result_verified": verified,
            })
            manifest["native_tests"] = "PARTIAL; see native_test_results and command logs"
            save()
            if not verified:
                blocked(label+": did not produce the required single-test native result; inspect log")
        test(before, "failing-before", PRIMARY, failure=True)
        test(before, "baseline-negative-control", CONTROL)
        test(after, "passing-after", PRIMARY)
        test(after, "candidate-negative-control", CONTROL)
        for name in (
            "test_held_candidate_released_before_cancellation_keeps_notifications",
            "test_held_supersession_outbox_failure_rolls_back",
            "test_held_reviews_do_not_displace_active_supersession_candidates",
            "test_superseded_series_versions_cancel_previous_versions",
            "test_superseded_pr_versions_cancel_all_previous_and_outbox",
            "test_cancelled_patchset_not_reopened_by_claim_or_status_update",
            "test_clean_patchset_is_releasable_before_embargo_expiry",
            "test_no_ai_review_is_not_clean",
            "test_release_patchset_embargo",
        ):
            test(after, name, "db::tests::"+name)
    manifest["status"] = "FOCUSED_NATIVE_PASS"
    manifest["native_tests"] = "Expected failing-before regression plus native passing-after/control checks"
    save()
    print(json.dumps({"status": manifest["status"], "full_repository_gate": "NOT RUN",
                      "manifest": str(OUT / "manifest.json")}), flush=True)
except SystemExit:
    raise
except Exception as error:
    manifest["status"] = "BLOCKED"
    manifest["reason"] = type(error).__name__+": "+str(error)
    save()
    raise

