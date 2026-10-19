#!/usr/bin/env python3
"""OS-boundary faults and deterministic killed-process commit boundaries."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
ROOT = Path.cwd()
OUT = ROOT / "adaptive-fault-results"
OUT.mkdir(exist_ok=True)
DB = ROOT / "src/db.rs"
COOLDOWN = ROOT / "src/db/cooldown.rs"
ORIGINAL_DB = DB.read_text()
ORIGINAL_COOLDOWN = COOLDOWN.read_text()
REPORT = {"status": "RUNNING", "checks": [],
          "checkpoint": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
          "limitations": ["LD_PRELOAD injects ENOSPC/EIO and a partial WAL write; this is not actual device exhaustion or physical power loss.",
                          "SIGKILL tests process crash before and after successful COMMIT.",
                          "No remote SMTP acceptance crash or historical archive replay is exercised."]}

def save():
    (OUT / "manifest.json").write_text(json.dumps(REPORT, indent=2) + "\n")

def run(args, label, env=None, timeout=120, expected=0):
    print("START " + label, flush=True)
    with (OUT / (label + ".log")).open("w") as stream:
        result = subprocess.run(args, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
    text = (OUT / (label + ".log")).read_text()
    if result.returncode != expected:
        print(text[-18000:], flush=True)
        raise RuntimeError(label + ": exit " + str(result.returncode))
    print("PASS " + label, flush=True)
    return text

def gate():
    return r'''
#[cfg(all(test, feature = "server"))]
fn hosted_commit_gate(phase: &str) {
    if std::env::var("COOLDOWN_FAULT_MODE").as_deref() != Ok(phase) { return; }
    let Ok(arm) = std::env::var("COOLDOWN_FAULT_ARM") else { return; };
    if !std::path::Path::new(&arm).exists() { return; }
    let hit = std::env::var("COOLDOWN_FAULT_HIT").expect("fixture marker missing");
    std::fs::write(hit, "commit-gate").expect("cannot signal crash gate");
    loop { std::thread::sleep(std::time::Duration::from_millis(10)); }
}
'''

try:
    save()
    original = ORIGINAL_DB
    start = original.index("    pub async fn commit(self)")
    end = original.index("\n    }\n", start)
    chunk = original[start:end]
    if chunk.count('        if let Some(tx) = self.tx.as_ref() {') != 1 or chunk.count('        Ok(())') != 1:
        raise RuntimeError("unexpected commit implementation")
    chunk = chunk.replace('        if let Some(tx) = self.tx.as_ref() {',
                          '        hosted_commit_gate("precommit");\n        if let Some(tx) = self.tx.as_ref() {')
    chunk = chunk.replace('        Ok(())', '        hosted_commit_gate("postcommit");\n        Ok(())')
    DB.write_text(original[:start] + chunk + original[end:] + gate())
    fixture = (ROOT / ".github/adaptive-fault-recovery/native_fixture.rs").read_text()
    close = ORIGINAL_COOLDOWN.rfind("}")
    COOLDOWN.write_text(ORIGINAL_COOLDOWN[:close] + fixture + "\n" + ORIGINAL_COOLDOWN[close:])
    library = OUT / "faults.so"
    run(["cc", "-shared", "-fPIC", "-Wall", "-Wextra", "-Werror",
         ".github/adaptive-fault-recovery/faults.c", "-o", str(library)], "build-os-fault-injector", timeout=60)
    run(["cargo", "fmt", "--all"], "format-fault-fixture", timeout=60)
    text = run(["cargo", "test", "--locked", "--all-features", "--lib", "--no-run",
                "--message-format=json"], "build-fault-fixture", timeout=600)
    binaries = []
    for line in text.splitlines():
        try: item = json.loads(line)
        except json.JSONDecodeError: continue
        if item.get("reason") == "compiler-artifact" and item.get("target", {}).get("kind") == ["lib"] and item.get("profile", {}).get("test") and item.get("executable"):
            binaries.append(item["executable"])
    if len(set(binaries)) != 1: raise RuntimeError("ambiguous native test")
    binary = Path(binaries[0])
    REPORT["binary_sha256"] = hashlib.sha256(binary.read_bytes()).hexdigest()
    command = [str(binary), "test_cooldown_filesystem_fault_recovery", "--ignored", "--nocapture", "--test-threads=1"]
    for mode in ["enospc", "eio", "torn-write", "precommit", "postcommit"]:
        with tempfile.TemporaryDirectory(prefix="adaptive-fault-") as temporary:
            directory = Path(temporary)
            state = directory / "state"
            state.mkdir()
            arm = directory / "arm"
            hit = directory / "hit"
            env = os.environ.copy()
            env.update(COOLDOWN_FAULT_ROOT=str(state), COOLDOWN_FAULT_ARM=str(arm),
                       COOLDOWN_FAULT_HIT=str(hit), COOLDOWN_FAULT_MODE=mode,
                       COOLDOWN_FAULT_PHASE="seed")
            text = run(command, mode + "-seed", env=env)
            if "1 passed; 0 failed" not in text: raise RuntimeError("seed test missing")
            env["COOLDOWN_FAULT_PHASE"] = "write"
            env["LD_PRELOAD"] = str(library)
            if mode in ["precommit", "postcommit"]:
                with (OUT / (mode + "-write.log")).open("w") as stream:
                    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
                    try:
                        deadline = time.monotonic() + 30
                        while not hit.exists() and process.poll() is None and time.monotonic() < deadline:
                            time.sleep(0.02)
                        if not hit.exists(): raise RuntimeError("commit gate was not reached")
                        process.kill()
                        if process.wait(timeout=5) != -signal.SIGKILL: raise RuntimeError("writer was not killed")
                    finally:
                        if process.poll() is None:
                            process.kill()
                            process.wait(timeout=5)
            else:
                text = run(command, mode + "-write", env=env,
                           expected=-signal.SIGKILL if mode == "torn-write" else 0)
                if mode != "torn-write" and "1 passed; 0 failed" not in text: raise RuntimeError("fault test missing")
            if not hit.exists(): raise RuntimeError("OS fault did not execute")
            arm.unlink(missing_ok=True)
            env.pop("LD_PRELOAD", None)
            env["COOLDOWN_FAULT_PHASE"] = "recover"
            text = run(command, mode + "-recover", env=env)
            if "1 passed; 0 failed" not in text: raise RuntimeError("recovery test missing")
            REPORT["checks"].append({"mode": mode, "status": "PASS"})
            save()
    REPORT["status"] = "PASS"
    save()
    print(json.dumps(REPORT, indent=2), flush=True)
except Exception as error:
    REPORT["status"] = "FAIL"
    REPORT["error"] = str(error)
    save()
    raise
finally:
    DB.write_text(ORIGINAL_DB)
    COOLDOWN.write_text(ORIGINAL_COOLDOWN)
