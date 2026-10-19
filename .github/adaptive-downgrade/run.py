#!/usr/bin/env python3
"""Native old-version access after an explicit stop/cancel rehearsal."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import time
import urllib.request
import urllib.error
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
ENV.update(CARGO_NET_RETRY="0", CARGO_HTTP_TIMEOUT="20")
REPORT = {"status": "RUNNING", "base": BASE, "checks": [],
          "checkpoint": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
          "limitations": ["Runs actual old/new daemon binaries on loopback plus native database fixtures; not a deployment.",
                          "Review concurrency zero is a test-only pause; all transports are dry-run and runtime network proxies refuse egress.",
                          "Unsafe claims are demonstrated only on a copied native fixture; daemon delivery workers run in dry-run with guarded pending work and no external service access.",
                          "Restoration assumes all ingestion, review and delivery processes are stopped and no new work was accepted during old-version access.",
                          "Stopped-system backup/restore includes old/new daemon cold starts; no live rolling upgrade or real remote acknowledgement is exercised."]}

def save():
    (OUT / "manifest.json").write_text(json.dumps(REPORT, indent=2) + "\n")

def run(args, label, cwd=ROOT, env=ENV, timeout=180):
    print("START " + label, flush=True)
    with (OUT / (label + ".log")).open("w") as stream:
        process = subprocess.Popen(args, cwd=cwd, env=env, stdout=stream,
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
    if code:
        print(text[-18000:], flush=True)
        raise RuntimeError(label + ": exit " + str(code))
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


def build_daemon(directory, label):
    run(["cargo", "build", "--locked", "--all-features", "--bin", "sashiko"],
        "build-" + label + "-daemon", cwd=directory, timeout=600)
    binary = OUT / (label + "-daemon")
    shutil.copy2(Path(ENV["CARGO_TARGET_DIR"]) / "debug/sashiko", binary)
    REPORT[label + "_daemon_sha256"] = hashlib.sha256(binary.read_bytes()).hexdigest()
    save()
    return binary

def boot_daemon(binary, database, directory, label):
    repository = directory / (label + "-repo")
    repository.mkdir()
    run(["git", "init", "-q", str(repository)], label + "-init", timeout=15)
    policy = directory / (label + "-legacy-lists.toml")
    policy.write_text("[defaults]\nmute_all=true\n")
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    config = directory / (label + ".toml")
    config.write_text(
        'log_level="info"\n[database]\nurl=' + json.dumps(str(database)) +
        '\n[git]\nrepository_path=' + json.dumps(str(repository)) +
        '\n[review]\nconcurrency=0\nmax_retries=0\nworktree_dir=' +
        json.dumps(str(directory / (label + "-worktrees"))) +
        '\nemail_policy_path=' + json.dumps(str(policy)) +
        '\n[ai]\nprovider="stdio-gemini"\nmodel="unused"\nresponse_cache=false\n' +
        '[nntp]\nserver=""\n[forge]\nenabled=false\ndisable_nntp=true\n' +
        '[linux_bug]\nenabled=false\n[server]\nhost="127.0.0.1"\n' +
        'port=' + str(port) + '\nread_only=true\npublic_base_url=' +
        json.dumps("https://review.example.test") +
        '\n[smtp]\ntransport="sendmail"\nsendmail_path="/never-run-sendmail"\n' +
        'sender_address="bot@example.test"\ndry_run=true\n')
    runtime = ENV.copy()
    for key in list(runtime):
        if any(word in key for word in ("TOKEN", "SECRET", "API_KEY")):
            runtime.pop(key)
    runtime.update(SASHIKO_CONFIG=str(config),
                   HTTP_PROXY="http://127.0.0.1:9", HTTPS_PROXY="http://127.0.0.1:9",
                   NO_PROXY="localhost,127.0.0.1", GIT_ALLOW_PROTOCOL="file")
    with (OUT / (label + "-daemon.log")).open("w") as log:
        process = subprocess.Popen([str(binary), "--project", "sashiko", "--no-ai"],
            cwd=ROOT, env=runtime, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            deadline = time.monotonic() + 15
            while True:
                if process.poll() is not None:
                    print((OUT / (label + "-daemon.log")).read_text()[-4000:], flush=True)
                    raise RuntimeError(label + ": daemon exited before health readiness")
                try:
                    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                        "http://127.0.0.1:" + str(port) + "/health", timeout=1) as response:
                        if response.status == 200:
                            break
                except (OSError, urllib.error.URLError):
                    pass
                if time.monotonic() > deadline:
                    raise RuntimeError(label + ": loopback health deadline")
                time.sleep(0.05)
            time.sleep(0.2)
            if process.poll() is not None:
                raise RuntimeError(label + ": daemon exited after health readiness")
        finally:
            try:
                os.killpg(process.pid, signal.SIGINT)
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            except ProcessLookupError:
                pass
    REPORT["checks"].append({"phase": label, "status": "PASS",
        "actual_daemon": True, "http_health": 200, "review_concurrency": 0, "dry_run": True})
    save()
    print("PASS " + label + " actual-daemon healthy/stopped", flush=True)

try:
    save()
    if subprocess.check_output(["git", "diff", "--name-only",
        "bd59059f1864aea81b11b5de0eb97e5d2ec53667", "HEAD", "--",
        "src", "docs", "designs", "MAINTAINERS_GUIDE.md", "Cargo.toml", "Cargo.lock"], text=True).strip():
        raise RuntimeError("frozen production source changed")
    fixture = (ROOT / ".github/adaptive-downgrade/candidate_fixture.rs").read_text()
    closing = ORIGINAL.rfind("}")
    SOURCE.write_text(ORIGINAL[:closing] + fixture + "\n" + ORIGINAL[closing:])
    candidate = build(ROOT, "candidate")
    candidate_daemon = build_daemon(ROOT, "candidate")
    run(["git", "cat-file", "-e", BASE + "^{commit}"], "verify-old-version", timeout=15)
    archive = subprocess.check_output(["git", "archive", BASE], cwd=ROOT)
    with tempfile.TemporaryDirectory(prefix="adaptive-old-version-") as temporary:
        directory = Path(temporary)
        with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
            stream.extractall(directory, filter="data")
        source = directory / "src/db.rs"
        source.write_text(source.read_text() + (ROOT / ".github/adaptive-downgrade/old_fixture.rs").read_text())
        old = build(directory, "old")
        old_daemon = build_daemon(directory, "old")
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
        boot_daemon(candidate_daemon, database, directory, "candidate-before-stop")
        # Back up after the real daemon has fully stopped, including startup metadata.
        with sqlite3.connect(database) as original:
            with sqlite3.connect(snapshot) as backup:
                original.backup(backup)
        preserved = pending_state(snapshot)
        REPORT["preserved_pending_state_sha256"] = hashlib.sha256(repr(preserved).encode()).hexdigest()
        test(old, "test_old_version_downgrade_access", "unsafe-copy", copy)
        test(candidate, "test_cooldown_downgrade_candidate_phases", "quiesce", database)
        boot_daemon(old_daemon, database, directory, "old-after-quiesce")
        test(old, "test_old_version_downgrade_access", "safe-old-access", database)
        test(candidate, "test_cooldown_downgrade_candidate_phases", "verify", database)
        # The old-version fixture accepted no new ingestion or delivery work.
        # Stop it before restoring the untouched candidate backup.
        with sqlite3.connect(snapshot) as backup:
            with sqlite3.connect(database) as restored:
                backup.backup(restored)
        if pending_state(database) != preserved:
            raise RuntimeError("backup restore lost or changed pending work")
        boot_daemon(candidate_daemon, database, directory, "candidate-after-restore")
        if pending_state(database) != preserved:
            raise RuntimeError("candidate daemon restart changed preserved pending state")
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
