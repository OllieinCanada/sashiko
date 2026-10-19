#!/usr/bin/env python3
"""Native old-version access after an explicit stop/cancel rehearsal."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
ROOT = Path.cwd()
OUT = ROOT / "adaptive-downgrade-results"
OUT.mkdir(exist_ok=True)
BASE = "7f92f869a960a20f7d395550b4879d897ebdf4ea"
SOURCE = ROOT / "src/db/cooldown.rs"
ORIGINAL = SOURCE.read_text()
ENV = os.environ.copy()
ENV["CARGO_TARGET_DIR"] = str(ROOT / "target")
REPORT = {"status": "RUNNING", "base": BASE, "checks": [],
          "checkpoint": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
          "limitations": ["Runs native test binaries containing the actual old/new database code, not a production daemon deployment.",
                          "Unsafe claims are demonstrated only on a copied fixture; no delivery workers or external services run.",
                          "Restoration assumes all ingestion, review and delivery processes are stopped and no new work was accepted during old-version access.",
                          "A full SQLite backup preserves pending state for a stopped-system restore; this is not a live daemon rollback."]}

def save():
    (OUT / "manifest.json").write_text(json.dumps(REPORT, indent=2) + "\n")

def run(args, label, cwd=ROOT, env=ENV, timeout=180):
    print("START " + label, flush=True)
    with (OUT / (label + ".log")).open("w") as stream:
        result = subprocess.run(args, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
    text = (OUT / (label + ".log")).read_text()
    if result.returncode:
        print(text[-18000:], flush=True)
        raise RuntimeError(label + ": exit " + str(result.returncode))
    print("PASS " + label, flush=True)
    return text

def build(directory, label):
    run(["cargo", "fmt", "--all"], "format-" + label, cwd=directory, timeout=60)
    text = run(["cargo", "test", "--locked", "--all-features", "--lib", "--no-run",
                "--message-format=json"], "build-" + label, cwd=directory, timeout=600)
    binaries = []
    for line in text.splitlines():
        try: item = json.loads(line)
        except json.JSONDecodeError: continue
        if item.get("reason") == "compiler-artifact" and item.get("target", {}).get("kind") == ["lib"] and item.get("profile", {}).get("test") and item.get("executable"):
            binaries.append(item["executable"])
    if len(set(binaries)) != 1: raise RuntimeError("ambiguous test executable")
    binary = OUT / (label + "-tests")
    shutil.copy2(binaries[0], binary)
    REPORT[label + "_binary_sha256"] = hashlib.sha256(binary.read_bytes()).hexdigest()
    save()
    return binary

def test(binary, name, phase, database):
    env = ENV.copy()
    env.update(COOLDOWN_DOWNGRADE_PHASE=phase, COOLDOWN_DOWNGRADE_DB=str(database))
    text = run([str(binary), name, "--ignored" if phase in ["prepare", "quiesce", "verify", "resume"] else "--include-ignored",
                "--nocapture", "--test-threads=1"], phase, env=env)
    if "1 passed; 0 failed" not in text: raise RuntimeError("expected one executed native test")
    REPORT["checks"].append({"phase": phase, "status": "PASS"})
    save()

try:
    save()
    fixture = (ROOT / ".github/adaptive-downgrade/candidate_fixture.rs").read_text()
    closing = ORIGINAL.rfind("}")
    SOURCE.write_text(ORIGINAL[:closing] + fixture + "\n" + ORIGINAL[closing:])
    candidate = build(ROOT, "candidate")
    run(["git", "fetch", "--no-tags", "origin", BASE], "fetch-old-version", timeout=60)
    archive = subprocess.check_output(["git", "archive", BASE], cwd=ROOT)
    with tempfile.TemporaryDirectory(prefix="adaptive-old-version-") as temporary:
        directory = Path(temporary)
        with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
            stream.extractall(directory, filter="data")
        source = directory / "src/db.rs"
        source.write_text(source.read_text() + (ROOT / ".github/adaptive-downgrade/old_fixture.rs").read_text())
        old = build(directory, "old")
    with tempfile.TemporaryDirectory(prefix="adaptive-downgrade-state-") as temporary:
        directory = Path(temporary)
        database = directory / "state.db"
        copy = directory / "unsafe-copy.db"
        snapshot = directory / "stopped-candidate-backup.db"
        test(candidate, "test_cooldown_downgrade_candidate_phases", "prepare", database)
        with sqlite3.connect(database) as original:
            with sqlite3.connect(copy) as destination:
                original.backup(destination)
        # All candidate processes have stopped. Preserve the complete pending
        # state separately from the scratch DB handed to old-version code.
        with sqlite3.connect(database) as original:
            with sqlite3.connect(snapshot) as backup:
                original.backup(backup)
        def pending_state(path):
            with sqlite3.connect("file:" + str(path) + "?mode=ro", uri=True) as conn:
                conn.execute("PRAGMA query_only=ON")
                return {
                    table: conn.execute('SELECT * FROM "' + table + '" ORDER BY rowid').fetchall()
                    for table in ["patchsets", "patches", "messages", "reviews", "findings",
                                  "email_outbox", "patchwork_outbox", "review_cooldown_intents",
                                  "review_cooldown_events", "review_cooldown_messages",
                                  "review_cooldown_exclusions", "review_cooldown_blocks",
                                  "review_cooldown_clock", "meta"]
                }
        preserved = pending_state(snapshot)
        REPORT["preserved_pending_state_sha256"] = hashlib.sha256(repr(preserved).encode()).hexdigest()
        test(old, "test_old_version_downgrade_access", "unsafe-copy", copy)
        test(candidate, "test_cooldown_downgrade_candidate_phases", "quiesce", database)
        test(old, "test_old_version_downgrade_access", "safe-old-access", database)
        test(candidate, "test_cooldown_downgrade_candidate_phases", "verify", database)
        # The old-version fixture accepted no new ingestion or delivery work.
        # Stop it before restoring the untouched candidate backup.
        with sqlite3.connect(snapshot) as backup:
            with sqlite3.connect(database) as restored:
                backup.backup(restored)
        if pending_state(database) != preserved:
            raise RuntimeError("backup restore lost or changed pending work")
        test(candidate, "test_cooldown_downgrade_candidate_phases", "resume", database)
        REPORT["pending_work_restore"] = "PASS: complete recorded pending state restored before candidate resume"
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
