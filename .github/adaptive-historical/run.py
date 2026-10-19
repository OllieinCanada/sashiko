#!/usr/bin/env python3
"""Replay one real public archived patch, never a production DB or transport."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import urllib.error
import urllib.request

ROOT = Path.cwd()
OUT = ROOT / "adaptive-historical-results"
OUT.mkdir(exist_ok=True)
MESSAGE = "20261009-work-fixes-rcu-v1-1-7446d2d335e6@kernel.org"
URL = "https://lore.kernel.org/all/" + MESSAGE + "/raw"
SOURCE_COMMIT = "c17b44266a1f9fcb49b894d4611d1254bf1aa313"
MAIN = ROOT / "src/main.rs"
ORIGINAL = MAIN.read_text()
REPORT = {
    "status": "RUNNING", "archive_url": URL,
    "provenance": "https://github.com/torvalds/linux/commit/" + SOURCE_COMMIT,
    "checkpoint": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "checks": [], "limitations": [
        "One public historical singleton; not an exhaustive archive or production activity dataset.",
        "Protected database is an isolated seeded source snapshot, not a supplied production database.",
        "No review model, publication worker, actual email or external integration runs."
    ],
}


def save():
    (OUT / "manifest.json").write_text(json.dumps(REPORT, indent=2) + "\n")


def run(args, label, env=None, timeout=120):
    print("START " + label, flush=True)
    with (OUT / (label + ".log")).open("w") as stream:
        result = subprocess.run(args, cwd=ROOT, env=env, stdout=stream,
                                stderr=subprocess.STDOUT, timeout=timeout)
    text = (OUT / (label + ".log")).read_text()
    if result.returncode:
        print(text[-12000:], flush=True)
        raise RuntimeError(label + ": exit " + str(result.returncode))
    return text


def download():
    try:
        with urllib.request.urlopen(URL, timeout=15) as response:
            data = response.read(512 * 1024 + 1)
        if len(data) > 512 * 1024 or b"message-id:" not in data.lower() or b"diff --git " not in data:
            raise RuntimeError("archive did not return a bounded raw patch")
        REPORT["transport"] = "HTTPS archive"
        return data
    except Exception:
        # One bounded read-only alternate transport; never solve an anti-bot
        # challenge or repeatedly retry a blocked archive.
        import nntplib
        with nntplib.NNTP("nntp.lore.kernel.org", 119, timeout=15) as nntp:
            _, info = nntp.article("<" + MESSAGE + ">")
        data = b"\r\n".join(info.lines) + b"\r\n"
        if len(data) > 512 * 1024 or b"diff --git " not in data:
            raise RuntimeError("NNTP did not return a bounded raw patch")
        REPORT["transport"] = "NNTP read-only ARTICLE"
        return data


def native(binary, phase, database, raw, policy):
    env = os.environ.copy()
    env.update(HISTORICAL_SHADOW_PHASE=phase, HISTORICAL_SHADOW_DB=str(database),
               HISTORICAL_RAW_EMAIL=str(raw), HISTORICAL_SHADOW_POLICY=str(policy),
               HISTORICAL_MESSAGE_ID=MESSAGE)
    text = run([str(binary), "test_historical_archive_shadow_replay", "--ignored",
                "--nocapture", "--test-threads=1"], phase, env, 90)
    if "1 passed; 0 failed" not in text or "running 1 test" not in text:
        raise RuntimeError("historical fixture did not execute exactly one test")
    REPORT["checks"].append({"name": phase, "status": "PASS"})
    save()


try:
    save()
    data = None
    supplied = os.environ.get("HISTORICAL_RAW_INPUT")
    if supplied:
        data = Path(supplied).read_bytes()
        if len(data) > 512 * 1024:
            raise RuntimeError("supplied archive sample exceeds the fixture cap")
        REPORT["transport"] = "explicitly supplied public archive fixture"
    elif os.environ.get("HISTORICAL_ARCHIVE_FETCH", "1") == "0":
        REPORT["archive_status"] = "BLOCKED: known unavailable transports are not retried"
    else:
        try:
            data = download()
        except Exception:
            REPORT["archive_status"] = "BLOCKED: HTTPS returned 403 and NNTP was unavailable"
    raw = OUT / "public-historical.eml"
    if data is not None:
        raw.write_bytes(data)
        REPORT["archive_sha256"] = hashlib.sha256(data).hexdigest()
    fixture = (ROOT / ".github/adaptive-historical/fixture.rs").read_text()
    MAIN.write_text(ORIGINAL + fixture)
    run(["cargo", "fmt", "--all"], "format-fixture", timeout=60)
    tracked_before = subprocess.check_output(
        ["git", "diff", "--binary", "HEAD", "--"], cwd=ROOT)
    build = run(["cargo", "test", "--locked", "--all-features", "--bin", "sashiko",
                 "--no-run", "--message-format=json"], "build-fixture", timeout=600)
    binaries = []
    for line in build.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (item.get("reason") == "compiler-artifact" and item.get("executable")
                and item.get("profile", {}).get("test")
                and item.get("target", {}).get("name") == "sashiko"
                and item.get("target", {}).get("kind") == ["bin"]):
            binaries.append(item["executable"])
    if len(set(binaries)) != 1:
        raise RuntimeError("missing or ambiguous historical test binary")
    binary = Path(binaries[0])
    REPORT["binary_sha256"] = hashlib.sha256(binary.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="adaptive-historical-shadow-") as temporary:
        directory = Path(temporary)
        source = directory / "protected-source.db"
        shadow = directory / "shadow.db"
        policy = directory / "policy.toml"
        policy.write_text(
            '["linux-ext4@vger.kernel.org"]\nnntp_group="org.kernel.vger.linux-ext4"\n'
            'embargo_hours=0\n["linux-ext4@vger.kernel.org".adaptive_cooldown]\n'
            'enabled=true\nwindow_seconds=86400\nburst=1\nstep_seconds=3600\nmax_extra_seconds=3600\n')
        native(binary, "prepare", source, raw, policy)
        with sqlite3.connect("file:" + str(source) + "?mode=ro", uri=True) as original:
            original.execute("PRAGMA query_only=ON")
            try:
                original.execute("CREATE TABLE forbidden_write(id INTEGER)")
            except sqlite3.OperationalError as error:
                if "readonly" not in str(error).lower():
                    raise
            else:
                raise RuntimeError("read-only negative control unexpectedly wrote")
            with sqlite3.connect(shadow) as destination:
                original.backup(destination)
        source.chmod(0o400)
        source_before = hashlib.sha256(source.read_bytes()).hexdigest()
        REPORT["checks"].append({"name": "read-only write negative control", "status": "PASS"})
        if data is None:
            REPORT["status"] = "BLOCKED_ARCHIVE_UNAVAILABLE"
            REPORT["replay_performed"] = False
            save()
            raise RuntimeError("historical harness compiled; raw archive input remains unavailable")
        frozen = None
        for number in range(3):
            native(binary, "replay-" + str(number), shadow, raw, policy)
            with sqlite3.connect("file:" + str(shadow) + "?mode=ro", uri=True) as conn:
                decision = conn.execute(
                    "SELECT patchset_id,list,author,admitted_at,prior_count,extra_seconds,decided_deadline FROM review_cooldown_intents").fetchall()
            if frozen is None:
                frozen = decision
            elif decision != frozen:
                raise RuntimeError("restarted historical replay changed frozen admission")
        if hashlib.sha256(source.read_bytes()).hexdigest() != source_before:
            raise RuntimeError("historical replay altered the protected source DB")
        if subprocess.check_output(["git", "diff", "--binary", "HEAD", "--"], cwd=ROOT) != tracked_before:
            raise RuntimeError("historical replay altered the tracked repository")
        REPORT["protected_source_sha256_before_and_after"] = source_before
        REPORT["checks"].extend([
            {"name": "read-only write negative control", "status": "PASS"},
            {"name": "source DB unchanged", "status": "PASS"},
            {"name": "tracked repository unchanged", "status": "PASS"},
            {"name": "frozen admission unchanged across three restarted replays", "status": "PASS"},
        ])
    REPORT["status"] = "PASS"
    REPORT["replay_performed"] = True
    save()
    print(json.dumps(REPORT, indent=2), flush=True)
except Exception as error:
    if REPORT["status"] != "BLOCKED_ARCHIVE_UNAVAILABLE":
        REPORT["status"] = "FAIL"
    REPORT["error"] = str(error)
    save()
    print(json.dumps(REPORT, indent=2), flush=True)
    raise
finally:
    MAIN.write_text(ORIGINAL)
