#!/usr/bin/env python3
"""Refresh scoped native evidence from the exact checked rebase bundle."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path.cwd()
MODE = sys.argv[1]
OUT = ROOT / "extended-results"
OUT.mkdir(exist_ok=True)
SOURCE = ROOT / "extended-source"
INPUT = ROOT / "input-refresh"
PREPARED = json.loads((INPUT / "manifest.json").read_text())
HEAD = PREPARED["head"]
UPSTREAM = PREPARED["upstream"]
ENV = os.environ.copy()
ENV.update(CARGO_TARGET_DIR=str(ROOT / "target"), CARGO_NET_RETRY="0",
           CARGO_HTTP_TIMEOUT="20", PYTHONDONTWRITEBYTECODE="1",
           GIT_TERMINAL_PROMPT="0")
REPORT = {"status": "RUNNING", "phase": MODE, "head": HEAD,
          "tree": PREPARED["tree"], "upstream": UPSTREAM,
          "checks": [], "provider_calls": 0, "upstream_pr_opened": False}
def save():
    (OUT / "manifest.json").write_text(json.dumps(REPORT, indent=2) + "\n")
def output(args, cwd=SOURCE):
    return subprocess.check_output(args, cwd=cwd, env=ENV, text=True).strip()
def run(args, label, cwd=SOURCE, timeout=1800, expected=0):
    print("START " + label, flush=True)
    if subprocess.run(["pgrep", "-x", "sashiko"], stdout=subprocess.DEVNULL).returncode == 0:
        raise RuntimeError("unexpected running sashiko")
    started = time.monotonic()
    with (OUT / (label + ".log")).open("w") as log:
        proc = subprocess.Popen(args, cwd=cwd, env=ENV, stdout=log,
                                stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = proc.wait(timeout=timeout)
        finally:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
    text = (OUT / (label + ".log")).read_text()
    REPORT["checks"].append({"name": label, "exit": code,
                             "seconds": time.monotonic() - started})
    save()
    if code != expected:
        print(text[-18000:], flush=True)
        raise RuntimeError(label + ": unexpected exit " + str(code))
    print("PASS " + label, flush=True)
    return text
def main():
    run(["/tmp/adaptive-extended-lint/bin/yamllint", "."],
        "audit-yaml", cwd=ROOT, timeout=60)
    if output(["git", "status", "--porcelain", "--untracked-files=no"], ROOT):
        raise RuntimeError("tracked audit checkout dirty")
    run(["git", "clone", "--no-hardlinks", "--no-checkout", str(ROOT), str(SOURCE)],
        "clone", ROOT, 60)
    run(["git", "fetch", "--no-tags", "https://github.com/sashiko-dev/sashiko.git", UPSTREAM],
        "fetch-upstream", timeout=60)
    run(["git", "fetch", str(INPUT / "rebased-source.bundle"), "HEAD"], "fetch-bundle", timeout=60)
    run(["git", "checkout", "--detach", HEAD], "checkout", timeout=30)
    if output(["git", "rev-parse", "HEAD^{tree}"]) != REPORT["tree"]:
        raise RuntimeError("prepared tree mismatch")
    if output(["git", "status", "--porcelain"]):
        raise RuntimeError("contribution checkout not clean")
    if MODE == "performance" and PREPARED.get("performance"):
        previous = PREPARED["performance"]
        REPORT["detail"] = previous
        REPORT["original_performance_run"] = 39359678639
        if previous.get("status") == "FAIL_BUDGET":
            raise RuntimeError("exact-source performance failed its original budget; no retry")
        if previous.get("status") == "PASS":
            if (previous.get("candidate_commit") != HEAD
                    or previous.get("baseline_commit") != UPSTREAM):
                raise RuntimeError("performance provenance mismatch")
            REPORT["status"] = "PASS"
            REPORT["reused_exact_source_performance"] = True
            REPORT["production_source_restored"] = True
            save()
            print(json.dumps(REPORT, indent=2), flush=True)
            return
    for directory in (ROOT / ".github").glob("adaptive-*"):
        if directory.is_dir():
            shutil.copytree(directory, SOURCE / ".github" / directory.name, dirs_exist_ok=True)
    run(["git", "remote", "set-url", "origin",
         "https://github.com/sashiko-dev/sashiko.git"], "set-origin", timeout=30)
    run(["cargo", "fetch", "--locked"], "fetch-dependencies", timeout=120)
    if MODE == "upstream":
        run(["git", "checkout", "--detach", UPSTREAM], "checkout-baseline", timeout=30)
        REPORT["baseline_checked_commit"] = output(["git", "rev-parse", "HEAD"])
        try:
            run(["cargo", "fmt", "--all", "--", "--check"], "baseline-fmt", timeout=60)
            try:
                run(["cargo", "clippy", "--locked", "--offline", "--all-targets",
                     "--all-features", "--", "-D", "warnings"], "baseline-clippy")
                REPORT["baseline_clippy"] = "PASS"
            except RuntimeError:
                log = (OUT / "baseline-clippy.log").read_text()
                errors = [line for line in log.splitlines() if line.startswith("error:")]
                if (len([line for line in errors if
                         line == "error: the `Err`-variant returned from this function is very large"]) != 4
                        or any(not ("the `Err`-variant" in line
                                   or line.startswith("error: could not compile")) for line in errors)):
                    raise
                REPORT["baseline_clippy"] = "KNOWN_UPSTREAM_LARGE_ERROR_FAILURE"
                REPORT["baseline_clippy_errors"] = errors
            text = run(["cargo", "test", "--locked", "--offline", "--all-features"],
                       "baseline-tests")
            REPORT["baseline_suite_summaries"] = [line for line in text.splitlines()
                                                   if line.startswith("test result:")]
        finally:
            run(["git", "checkout", "--detach", HEAD], "restore-candidate", timeout=30)
    elif MODE == "crash":
        module = SOURCE / "src/db/conflict.rs"
        original = module.read_text()
        fixture = (ROOT / ".github/adaptive-refresh/process_fixture.rs").read_text()
        closing = original.rfind("}")
        module.write_text(original[:closing] + fixture + "\n" + original[closing:])
        try:
            run(["cargo", "fmt", "--all"], "format-crash-fixture", timeout=60)
            text = run(["cargo", "test", "--locked", "--offline", "--all-features",
                        "--lib", "--no-run", "--message-format=json"], "build-crash-fixture")
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
                raise RuntimeError("ambiguous crash fixture executable")
            binary = binaries[0]
            REPORT["binary_sha256"] = hashlib.sha256(Path(binary).read_bytes()).hexdigest()
            REPORT["fixture_sha256"] = hashlib.sha256(fixture.encode()).hexdigest()
            REPORT["crash_phases"] = []
            for phase in ["preparing", "active", "handoff"]:
                db = OUT / (phase + ".db")
                ready = OUT / (phase + ".ready")
                env = ENV.copy()
                env.update(CONFLICT_PROCESS_DB=str(db), CONFLICT_PROCESS_PHASE=phase,
                           CONFLICT_PROCESS_ACTION="prepare", CONFLICT_PROCESS_READY=str(ready))
                args = [binary, "db::conflict::tests::test_hosted_conflict_process_phases",
                        "--exact", "--ignored", "--nocapture", "--test-threads=1"]
                with (OUT / (phase + "-child.log")).open("w") as log:
                    child = subprocess.Popen(args, cwd=SOURCE, env=env, stdout=log,
                                             stderr=subprocess.STDOUT, start_new_session=True)
                    try:
                        deadline = time.monotonic() + 40
                        while not ready.exists():
                            if child.poll() is not None or time.monotonic() >= deadline:
                                raise RuntimeError("crash phase not ready: " + phase)
                            time.sleep(0.05)
                        os.killpg(child.pid, signal.SIGKILL)
                        if child.wait(timeout=5) != -signal.SIGKILL:
                            raise RuntimeError("native child not killed")
                    finally:
                        if child.poll() is None:
                            os.killpg(child.pid, signal.SIGKILL)
                            child.wait(timeout=5)
                env["CONFLICT_PROCESS_ACTION"] = "recover"
                with (OUT / (phase + "-recovery.log")).open("w") as log:
                    result = subprocess.run(args, cwd=SOURCE, env=env, stdout=log,
                                            stderr=subprocess.STDOUT, timeout=60)
                text = (OUT / (phase + "-recovery.log")).read_text()
                if result.returncode or "running 1 test" not in text or "1 passed; 0 failed" not in text:
                    print(text[-12000:], flush=True)
                    raise RuntimeError("native process recovery failed: " + phase)
                REPORT["crash_phases"].append({"phase": phase, "status": "PASS",
                                               "killed_after_commit": True})
                save()
            run(["cargo", "clippy", "--locked", "--offline", "--all-targets",
                 "--all-features", "--", "-D", "warnings"], "clippy-crash-fixture")
        finally:
            module.write_text(original)
    elif MODE == "conflict":
        migration = SOURCE / "src/migrations/016_cooldown_conflicts.sql"
        original = migration.read_text()
        args = ["cargo", "test", "--locked", "--offline", "--all-features", "--lib",
                "db::conflict::tests::", "--", "--test-threads=1", "--nocapture"]
        def focused(label, expected=0):
            text = run(args, label, expected=expected)
            if "running 4 tests" not in text:
                raise RuntimeError("missing four native conflict fixtures")
            if expected == 0 and "4 passed; 0 failed" not in text:
                raise RuntimeError("incomplete native conflict fixtures")
            return text
        try:
            focused("positive")
            REPORT["mutants"] = []
            for name, replacement, oracle in [
                ("preparing", "WHERE g.state IN ('preparing','active')", "preparing conflict became visible"),
                ("active", "WHERE g.state = 'active' AND 0", "group owner escaped quarantine")]:
                if original.count("WHERE g.state = 'active'") != 1:
                    raise RuntimeError("ambiguous guard anchor")
                migration.write_text(original.replace("WHERE g.state = 'active'", replacement))
                text = focused("mutant-" + name, 101)
                if oracle not in text:
                    raise RuntimeError("unrelated mutant failure")
                REPORT["mutants"].append({"name": name, "status": "KILLED", "oracle": oracle})
                migration.write_text(original)
            focused("restored")
        finally:
            migration.write_text(original)
    else:
        folders = {"performance": ("adaptive-baseline-validation", "adaptive-baseline-results"),
                   "rollback": ("adaptive-downgrade", "adaptive-downgrade-results"),
                   "clock": ("adaptive-clock", "adaptive-clock-results"),
                   "historical": ("adaptive-historical", "adaptive-historical-results"),
                   "cancel": ("adaptive-review-cancel", "adaptive-review-cancel-results"),
                   "concurrency": ("adaptive-concurrency", "adaptive-concurrency-results"),
                   "faults": ("adaptive-fault-recovery", "adaptive-fault-results")}
        folder, results = folders[MODE]
        path = SOURCE / ".github" / folder / "run.py"
        text = path.read_text()
        old = "bd59059f1864aea81b11b5de0eb97e5d2ec53667"
        if MODE in ["rollback", "clock", "historical", "cancel"]:
            if text.count(old) != 1:
                raise RuntimeError("ambiguous original source guard")
            text = text.replace(old, HEAD)
        if MODE == "performance":
            old_base = "7f92f869a960a20f7d395550b4879d897ebdf4ea"
            if text.count(old_base) != 1:
                raise RuntimeError("ambiguous performance baseline")
            text = text.replace(old_base, UPSTREAM)
            text = text.replace('"repeat_of": "39297399851",',
                                '"scope": "fresh upstream and exact rebased source",')
        if MODE == "rollback":
            text = text.replace('"review_cooldown_clock", "meta"]',
                                '"review_cooldown_clock", "review_cooldown_conflicts", '
                                '"review_cooldown_conflict_members", "meta"]')
            for variant in ["candidate", "old"]:
                target = SOURCE / ".github/adaptive-downgrade" / (variant + "_fixture.rs")
                target.write_bytes((ROOT / ".github/adaptive-refresh" /
                                    ("rollback_" + variant + ".rs")).read_bytes())
            # Demonstrate that the old daemon cannot interpret an active guard.
            text = text.replace(
                'test(old, "test_old_version_downgrade_access", "unsafe-copy", copy)',
                'with sqlite3.connect(copy) as unsafe:\n'
                '            unsafe.execute("UPDATE review_cooldown_conflicts SET state=\'active\'")\n'
                '        test(old, "test_old_version_downgrade_access", "unsafe-copy", copy)')
        path.write_text(text)
        REPORT["runner_sha256"] = hashlib.sha256(text.encode()).hexdigest()
        save()
        try:
            run(["python3", str(path)], MODE)
        finally:
            manifest = SOURCE / results / "manifest.json"
            if manifest.exists():
                REPORT["detail"] = json.loads(manifest.read_text())
                shutil.copy2(manifest, OUT / "detail.json")
            for log in (SOURCE / results).glob("*.log"):
                shutil.copy2(log, OUT / ("detail-" + log.name))
        if REPORT.get("detail", {}).get("status") != "PASS":
            raise RuntimeError("native harness did not report PASS")
    if output(["git", "diff", "--name-only", HEAD, "--", "src", "Cargo.toml", "Cargo.lock"]):
        raise RuntimeError("production source left changed")
    REPORT["production_source_restored"] = True
    REPORT["status"] = "PASS"
    save()
    print(json.dumps(REPORT, indent=2), flush=True)
try:
    save()
    main()
except BaseException as error:
    REPORT["status"] = "FAIL"
    REPORT["error"] = str(error)
    save()
    raise
