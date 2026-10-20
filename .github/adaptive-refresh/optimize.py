#!/usr/bin/env python3
"""Validate the query consolidation on the checked rebased contribution."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path.cwd()
OUT = ROOT / "optimization-results"
OUT.mkdir(exist_ok=True)
SOURCE = ROOT / "optimized-source"
SPEC = json.loads((ROOT / ".github/adaptive-refresh/optimization.json").read_text())
BASE = "026195ab58e2099e81017adbc6b97f33c509c8ba"
ENV = os.environ.copy()
ENV.update(CARGO_TARGET_DIR=str(ROOT / "target"), CARGO_NET_RETRY="0",
           CARGO_HTTP_TIMEOUT="20", PYTHONDONTWRITEBYTECODE="1",
           GIT_TERMINAL_PROMPT="0")
REPORT = {"status": "RUNNING", "upstream": BASE, "previous_head": SPEC["base"],
          "checks": [], "mutants": [], "provider_calls": 0,
          "upstream_pr_opened": False,
          "previous_performance": {"run": 39359678639, "status": "FAIL_BUDGET",
                                   "disabled_ratios": [1.2450766801569302, 1.35295309389588]}}
def save():
    (OUT / "manifest.json").write_text(json.dumps(REPORT, indent=2) + "\n")
def output(args, cwd=SOURCE):
    return subprocess.check_output(args, cwd=cwd, env=ENV, text=True).strip()
def run(args, label, cwd=SOURCE, timeout=1800, expected=0):
    print("START " + label, flush=True)
    if subprocess.run(["pgrep", "-x", "sashiko"], stdout=subprocess.DEVNULL).returncode == 0:
        raise RuntimeError("unexpected running sashiko")
    started = time.monotonic()
    with (OUT / (label + ".log")).open("w") as stream:
        proc = subprocess.Popen(args, cwd=cwd, env=ENV, stdout=stream,
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
def focused(label):
    text = run(["cargo", "test", "--locked", "--offline", "--all-features",
                "--lib", "db::conflict::tests::", "--", "--test-threads=1"],
               label)
    if "running 5 tests" not in text or "5 passed; 0 failed" not in text:
        raise RuntimeError("missing five native guard fixtures")
def main():
    if output(["git", "status", "--porcelain", "--untracked-files=no"], ROOT):
        raise RuntimeError("dirty tracked audit checkout")
    run(["git", "clone", "--no-hardlinks", "--no-checkout", str(ROOT), str(SOURCE)],
        "clone", ROOT, 60)
    run(["git", "fetch", "--no-tags", "https://github.com/sashiko-dev/sashiko.git", BASE],
        "fetch-upstream", timeout=60)
    run(["git", "fetch", str(ROOT / "input-refresh/rebased-source.bundle"), "HEAD"],
        "fetch-checked-bundle", timeout=60)
    run(["git", "checkout", "--detach", SPEC["base"]], "checkout", timeout=30)
    if output(["git", "rev-parse", "HEAD^{tree}"]) != SPEC["tree"]:
        raise RuntimeError("base tree mismatch")
    if output(["git", "status", "--porcelain"]):
        raise RuntimeError("dirty source checkout")
    for row in SPEC["replacements"]:
        path = SOURCE / row["path"]
        text = path.read_text()
        if text.count(row["from"]) != 1:
            raise RuntimeError("ambiguous optimization anchor")
        path.write_text(text.replace(row["from"], row["to"]))
    conflict = SOURCE / "src/db/conflict.rs"
    text = conflict.read_text()
    end = text.rfind("}")
    conflict.write_text(text[:end] + SPEC["regression"] + "\n" + text[end:])
    design = SOURCE / "designs/ADAPTIVE_PUBLICATION_COOLDOWN.md"
    design.write_text(SPEC["design"])
    run(["cargo", "fetch", "--locked"], "fetch-dependencies", timeout=120)
    run(["cargo", "clean", "-p", "sashiko"], "clear-package-generated-paths", timeout=60)
    run(["cargo", "fmt", "--all"], "format", timeout=60)
    focused("positive")
    module = SOURCE / "src/db/cooldown.rs"
    original = module.read_text()
    for name, oracle in [
        ("bind_cooldown_source_tx", "source binding bypassed the active group"),
        ("bind_cooldown_patch_tx", "patch binding bypassed the active group"),
        ("complete_patchset_tx", "completion bypassed the active group")]:
        start = original.index("fn " + name + "(")
        end = original.index("\n    }", start)
        chunk = original[start:end]
        anchor = "AND g.state = 'active'"
        if chunk.count(anchor) != 1:
            raise RuntimeError("ambiguous consolidated guard mutation")
        module.write_text(original[:start] +
                          chunk.replace(anchor, anchor + " AND 0") + original[end:])
        text = run(["cargo", "test", "--locked", "--offline", "--all-features",
                    "--lib",
                    "db::conflict::tests::test_conflict_binding_snapshots_reject_decided_and_legacy_owners",
                    "--", "--exact", "--nocapture", "--test-threads=1"],
                   "mutant-" + name, expected=101)
        if ("running 1 test" not in text or "0 passed; 1 failed" not in text
                or oracle not in text):
            raise RuntimeError("mutation failed for unrelated reason")
        REPORT["mutants"].append({"name": name, "status": "KILLED",
                                   "oracle": oracle})
        module.write_text(original)
        save()
    focused("restored")
    text = run(["make", "check-pr", "RANGE=" + BASE + "..HEAD"],
               "required-check-pr")
    REPORT["suite_summaries"] = [line for line in text.splitlines()
                                if line.startswith("test result:")]
    run(["git", "diff", "--check"], "diff-check", timeout=30)
    for key, value in [("user.name", "Ollie Slapinski"),
                       ("user.email", "oliverslapinski@hotmail.com")]:
        run(["git", "config", key, value], "configure-" + key, timeout=30)
    run(["git", "add", "--", "src/db/cooldown.rs", "src/db/conflict.rs"],
        "stage-optimization", timeout=30)
    run(["git", "commit", "-s", "-m",
         "db: consolidate quarantine checks into binding snapshots\n\n"
         "Check active groups and durable blocks in the existing binding\n"
         "and completion reads. Avoid a separate query for every part while\n"
         "retaining quarantine precedence over decided and legacy owners.\n\n"
         "Cover every consolidated entry point with direct regressions."],
        "commit-optimization", timeout=30)
    REPORT["checked_code_head"] = output(["git", "rev-parse", "HEAD"])
    run(["make", "check-pr", "RANGE=HEAD..HEAD"], "required-doc-check", timeout=120)
    run(["git", "add", "--", "designs/ADAPTIVE_PUBLICATION_COOLDOWN.md"],
        "stage-design", timeout=30)
    run(["git", "commit", "-s", "-m",
         "docs: describe staged conflict quarantine and recovery limits\n\n"
         "Document atomic activation, bounded writer batches and lease-based\n"
         "cleanup. Preserve the limits on scans, storage and previously claimed\n"
         "deliveries, and describe stopped rollback requirements."],
        "commit-design", timeout=30)
    run(["make", "sob", "RANGE=" + BASE + "..HEAD"], "final-signoffs", timeout=30)
    if output(["git", "diff", "--name-only", REPORT["checked_code_head"], "HEAD"]) != "designs/ADAPTIVE_PUBLICATION_COOLDOWN.md":
        raise RuntimeError("unexpected changes after checked code commit")
    if output(["git", "status", "--porcelain"]):
        raise RuntimeError("source left dirty")
    REPORT["head"] = output(["git", "rev-parse", "HEAD"])
    REPORT["tree"] = output(["git", "rev-parse", "HEAD^{tree}"])
    REPORT["commits"] = output(["git", "log", "--format=%H %s", BASE + "..HEAD"]).splitlines()
    run(["git", "bundle", "create", str(OUT / "rebased-source.bundle"), BASE + "..HEAD"],
        "export-source", timeout=60)
    (OUT / "rebased-source.patch").write_bytes(subprocess.check_output(
        ["git", "format-patch", "--stdout", BASE + "..HEAD"], cwd=SOURCE))
    REPORT["status"] = "CHECKED_OPTIMIZATION_EXTENDED_PENDING"
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
