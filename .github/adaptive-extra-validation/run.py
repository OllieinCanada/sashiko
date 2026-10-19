#!/usr/bin/env python3
"""Run bounded SQLite failure/recovery and pruning controls on the candidate."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path.cwd()
OUT = ROOT / "adaptive-extra-results"
OUT.mkdir(exist_ok=True)
SOURCE = ROOT / "src/db/cooldown.rs"
ORIGINAL = SOURCE.read_text()
FIXTURE = (ROOT / ".github/adaptive-extra-validation/native_fixture.rs").read_text()
REPORT = {
    "status": "RUNNING",
    "candidate_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "fixture_sha256": hashlib.sha256(FIXTURE.encode()).hexdigest(),
    "checks": [],
    "limitations": [
        "Read-only fault uses SQLite query_only on the writer connection.",
        "Busy fault uses another BEGIN IMMEDIATE writer and 1 ms busy_timeout.",
        "Stale outbox leases are simulated without external delivery; no filesystem I/O, power-loss or slow external collaborator fault is injected.",
    ],
}


def save():
    (OUT / "manifest.json").write_text(json.dumps(REPORT, indent=2) + "\n")


def run(args, label, timeout):
    print("START " + label, flush=True)
    with (OUT / (label + ".log")).open("w") as stream:
        process = subprocess.run(args, stdout=stream, stderr=subprocess.STDOUT,
                                 cwd=ROOT, timeout=timeout)
    text = (OUT / (label + ".log")).read_text()
    if process.returncode:
        print(text[-16000:], flush=True)
        raise RuntimeError(f"{label}: exit {process.returncode}")
    print("PASS " + label, flush=True)
    return text


try:
    save()
    closing = ORIGINAL.rfind("}")
    SOURCE.write_text(ORIGINAL[:closing] + FIXTURE + "\n" + ORIGINAL[closing:])
    run(["cargo", "fmt", "--all"], "format-fixture", 60)
    text = run(["cargo", "test", "--locked", "--all-features", "--lib", "--no-run",
                "--message-format=json"], "build-fixture", 600)
    binaries = []
    for line in text.splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (entry.get("reason") == "compiler-artifact"
                and entry.get("target", {}).get("kind") == ["lib"]
                and entry.get("profile", {}).get("test") and entry.get("executable")):
            binaries.append(entry["executable"])
    if len(set(binaries)) != 1:
        raise RuntimeError("ambiguous test artifact")
    binary = OUT / "extra-tests"
    shutil.copy2(binaries[0], binary)
    REPORT["binary_sha256"] = hashlib.sha256(binary.read_bytes()).hexdigest()
    for name in ["test_cooldown_hosted_read_only_writer_retry",
                 "test_cooldown_hosted_busy_writer_retry",
                 "test_cooldown_hosted_pruning_keeps_dedup_state",
                 "test_cooldown_hosted_stale_leases_recheck_quarantine",
                 "test_cooldown_hosted_disable_cancel_reopen",
                 "test_cooldown_hosted_policy_source_matrix"]:
        text = run([str(binary), name, "--ignored", "--nocapture", "--test-threads=1"],
                   name, 60)
        if "1 passed; 0 failed" not in text:
            raise RuntimeError("expected exactly one passing test")
        REPORT["checks"].append({"name": name, "status": "PASS"})
        save()
    REPORT["status"] = "PASS"
    save()
    print(json.dumps(REPORT, indent=2), flush=True)
except Exception as error:
    REPORT["status"] = "FAIL"
    REPORT["error"] = str(error)
    save()
    print(json.dumps(REPORT, indent=2), flush=True)
    raise
finally:
    SOURCE.write_text(ORIGINAL)
