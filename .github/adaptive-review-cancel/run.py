#!/usr/bin/env python3
"""Exercise real stdio review cancellation with an in-process mock provider."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess

ROOT = Path.cwd()
OUT = ROOT / "adaptive-review-cancel-results"
OUT.mkdir(exist_ok=True)
SOURCE = ROOT / "src/reviewer.rs"
ORIGINAL = SOURCE.read_text()
BASE = "bd59059f1864aea81b11b5de0eb97e5d2ec53667"
TARGET = "reviewer::tests::test_det6_cancel_active_review_reaps_child_and_provider"
CONTROL = "cooldown::tests::identity_normalization_has_no_unknown_bucket"
ENV = os.environ.copy()
ENV.update({"CARGO_NET_RETRY": "0", "CARGO_HTTP_TIMEOUT": "20"})
SPEC = importlib.util.spec_from_file_location(
    "scanner", ROOT / ".github/adaptive-observability/instrument.py")
SCANNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCANNER)
REPORT = {"status": "RUNNING",
          "checkpoint": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
          "production_base": BASE,
          "source_sha256": hashlib.sha256(ORIGINAL.encode()).hexdigest(),
          "checks": [], "mutants": [],
          "limitations": [
              "Persisted adaptive owner; actual stdio RPC loop, cancellation watcher and model-permit wrapper.",
              "Provider is an in-process pending future; child is a local static Python script. No real model/API call.",
              "This isolates review-tool resource cleanup; full worktree preparation and remote SMTP acknowledgement are not exercised."]}

def save():
    (OUT / "manifest.json").write_text(json.dumps(REPORT, indent=2) + "\n")

def run(args, label, timeout=600, expected=0):
    print("START " + label, flush=True)
    with (OUT / (label + ".log")).open("w") as output:
        process = subprocess.Popen(args, cwd=ROOT, env=ENV, stdout=output,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
    text = (OUT / (label + ".log")).read_text()
    if code != expected:
        rendered = []
        for line in text.splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("reason") == "compiler-message":
                rendered.append(row.get("message", {}).get("rendered") or "")
        print(("\n".join(rendered) if rendered else text)[-18000:], flush=True)
        raise RuntimeError(label + ": unexpected exit " + str(code))
    print("PASS " + label, flush=True)
    return text

def build(label):
    text = run(["cargo", "test", "--locked", "--offline", "--all-features",
                "--lib", "--no-run", "--message-format=json"], label, 900)
    binaries = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (row.get("reason") == "compiler-artifact"
                and row.get("target", {}).get("kind") == ["lib"]
                and row.get("profile", {}).get("test") and row.get("executable")):
            binaries.append(row["executable"])
    if len(set(binaries)) != 1:
        raise RuntimeError("missing exact library test binary")
    return binaries[0]

def test(binary, label, negative=None, target=TARGET):
    text = run([binary, target, "--exact", "--nocapture", "--test-threads=1"],
               label, 35, expected=101 if negative else 0)
    expected = "0 passed; 1 failed" if negative else "1 passed; 0 failed"
    if "running 1 test" not in text or expected not in text:
        raise RuntimeError("test selector did not execute exactly one case")
    if negative and negative not in text:
        print(text[-10000:], flush=True)
        raise RuntimeError(label + ": wrong semantic failure")
    if not negative and target == TARGET and "mock_future_dropped=1 permit_restored=1" not in text:
        raise RuntimeError("in-flight mock/permit positive control missing")
    REPORT["checks"].append({"name": label, "target": target,
                             "status": "KILLED" if negative else "PASS"})
    save()
    for line in text.splitlines():
        if "DET6_CASES" in line:
            print(line[line.index("DET6_CASES"):], flush=True)

try:
    save()
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", BASE, "HEAD", "--", "src", "docs",
         "designs", "MAINTAINERS_GUIDE.md", "Cargo.toml", "Cargo.lock"], text=True)
    if changed.strip():
        raise RuntimeError("frozen production source changed")
    code = SCANNER.mask(ORIGINAL)
    matches = list(re.finditer(r"\bmod\s+tests\s*\{", code))
    if len(matches) != 1:
        raise RuntimeError("test-module anchor is ambiguous")
    closing = matches[0].end()
    depth = 1
    while depth and closing < len(code):
        if code[closing] == "{": depth += 1
        elif code[closing] == "}": depth -= 1
        closing += 1
    if depth:
        raise RuntimeError("test module is unclosed")
    fixture = (ROOT / ".github/adaptive-review-cancel/fixture.rs").read_text()
    REPORT["fixture_sha256"] = hashlib.sha256(fixture.encode()).hexdigest()
    SOURCE.write_text(ORIGINAL[:closing-1] + "\n" + fixture + "\n" + ORIGINAL[closing-1:])
    run(["cargo", "fetch", "--locked"], "fetch-dependencies", 120)
    run(["cargo", "fmt", "--all"], "format-fixture", 60)
    baseline = SOURCE.read_text()
    (OUT / "review-cancel-test-addition.patch").write_text(
        subprocess.check_output(["git", "diff", "--", "src/reviewer.rs"], text=True))
    binary = build("build-positive")
    test(binary, "active-review-cancellation")
    run(["cargo", "clippy", "--locked", "--offline", "--all-targets",
         "--all-features", "--", "-D", "warnings"], "clippy-fixture", 600)
    for label, reason in [
            ("cancel-watch", "active review cancellation did not finish"),
            ("task-abort", "mock provider task remained active after cancellation")]:
        source = baseline
        if label == "cancel-watch":
            start = source.index("_ = cancel_interval.tick() =>")
            at = source.index("&& status == ReviewStatus::Cancelled.as_str()", start)
            source = source[:at] + source[at:].replace(
                "&& status == ReviewStatus::Cancelled.as_str()", "&& false", 1)
        else:
            anchor = "for task in spawned_tasks {\n        task.abort();\n    }"
            if source.count(anchor) != 1:
                raise RuntimeError("task-abort mutation anchor is ambiguous")
            source = source.replace(anchor, "for task in spawned_tasks {\n        drop(task);\n    }")
        SOURCE.write_text(source)
        binary = build("build-mutant-" + label)
        test(binary, "negative-" + label, negative=reason)
        test(binary, "unrelated-" + label, target=CONTROL)
        REPORT["mutants"].append({"name": label, "status": "KILLED",
                                  "binary_sha256": hashlib.sha256(Path(binary).read_bytes()).hexdigest()})
        save()
    SOURCE.write_text(baseline)
    binary = build("build-restored")
    test(binary, "restored-cancellation")
    SOURCE.write_text(ORIGINAL)
    REPORT["source_restored"] = SOURCE.read_text() == ORIGINAL
    if not REPORT["source_restored"]:
        raise RuntimeError("source restore mismatch")
    REPORT["status"] = "PASS"
    save()
    print(json.dumps(REPORT, indent=2), flush=True)
except Exception as error:
    REPORT["status"] = "FAIL"
    REPORT["error"] = str(error)
    save()
    raise
finally:
    SOURCE.write_text(ORIGINAL)
